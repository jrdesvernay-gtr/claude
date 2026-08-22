"""Supabase write layer for Step 3.6/3.7: load parsed filings into
franchisors/fdd_filings/units, and resolve+upsert franchisees.

Kept as plain functions taking an explicit `client` (rather than a module-
level singleton) so tests can pass a fake client with the same
`.table(...).select/insert/update/upsert(...).execute()` surface used here,
without needing network access or real credentials.
"""
from __future__ import annotations

import os

from pipeline.models import FddFiling, FranchiseeCandidate, ItemRow


def get_client():
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def upsert_franchisor(client, name: str, website: str | None = None) -> str:
    existing = client.table("franchisors").select("id").eq("name", name).limit(1).execute()
    if existing.data:
        return existing.data[0]["id"]
    inserted = client.table("franchisors").insert({"name": name, "website": website}).execute()
    return inserted.data[0]["id"]


def insert_fdd_filing(client, filing: FddFiling, franchisor_id: str) -> str:
    """Upserts on the (franchisor_id, state, source_url) uniqueness constraint
    so re-running a search-and-download for the same filing is idempotent.
    """
    payload = {
        "franchisor_id": franchisor_id,
        "state": filing.state,
        "filing_year": filing.filing_year,
        "source_url": filing.source_url,
        "document_type": filing.document_type,
        "handler_id_used": filing.handler_id_used,
        "handler_confidence": filing.handler_confidence,
        "section_source": filing.section_source,
        "section_locator_confidence": filing.section_locator_confidence,
        "table1_outlet_count": filing.table1_outlet_count,
        "parsed_row_count": filing.parsed_row_count,
        "table1_match": filing.table1_match,
        "review_flag": filing.review_flag,
        "raw_document_path": filing.raw_document_path,
    }
    result = client.table("fdd_filings").upsert(payload, on_conflict="franchisor_id,state,source_url").execute()
    return result.data[0]["id"]


def fetch_all_franchisees(client) -> dict[str, str]:
    """id -> legal_name, for pipeline.resolution.entity_resolution.resolve()."""
    result = client.table("franchisees").select("id, legal_name").execute()
    return {row["id"]: row["legal_name"] for row in result.data}


def _franchisee_payload(candidate: FranchiseeCandidate) -> dict:
    fields = {
        "legal_name": candidate.legal_name,
        "entity_type": candidate.entity_type,
        "guarantor_names": candidate.guarantor_names,
        "hq_full_address": candidate.hq_full_address,
        "hq_phone": candidate.hq_phone,
        "hq_email": candidate.hq_email,
        "domain": candidate.domain,
        "linkedin_url": candidate.linkedin_url,
        "contact_name": candidate.contact_name,
        "contact_first_name": candidate.contact_first_name,
        "contact_last_name": candidate.contact_last_name,
        "contact_title": candidate.contact_title,
        "contact_email": candidate.contact_email,
        "contact_linkedin_url": candidate.contact_linkedin_url,
        "contact_confidence": candidate.contact_confidence,
        "merge_confidence": candidate.merge_confidence,
    }
    # drop empty-list/None so an update() doesn't clobber existing values
    # (e.g. an AUTO_MERGE candidate usually only carries legal_name + guarantors)
    return {k: v for k, v in fields.items() if v not in (None, [])}


def upsert_franchisee(client, candidate: FranchiseeCandidate, franchisee_id: str | None = None) -> str:
    """franchisee_id set -> merge onto that existing row (AUTO_MERGE, or an
    AMBIGUOUS case Agent 2 resolved as same_entity). franchisee_id None ->
    insert a new row (NEW_ENTITY, or AMBIGUOUS resolved as not same_entity).
    """
    payload = _franchisee_payload(candidate)
    if franchisee_id:
        if payload:
            client.table("franchisees").update(payload).eq("id", franchisee_id).execute()
        return franchisee_id

    result = client.table("franchisees").insert(payload).execute()
    return result.data[0]["id"]


def insert_units(
    client,
    rows: list[ItemRow],
    fdd_filing_id: str,
    franchisor_id: str,
    franchisee_ids: list[str | None],
    batch_size: int = 500,
) -> None:
    if not rows:
        return
    if len(rows) != len(franchisee_ids):
        raise ValueError("rows and franchisee_ids must be the same length (one franchisee_id per row)")

    payload = [
        {
            "fdd_filing_id": fdd_filing_id,
            "franchisor_id": franchisor_id,
            "franchisee_id": franchisee_id,
            "franchisee_raw": row.franchisee_raw,
            "address": row.address,
            "city": row.city,
            "state": row.state,
            "zip": row.zip,
            "phone": row.phone,
            "status": row.status,
        }
        for row, franchisee_id in zip(rows, franchisee_ids)
    ]
    for i in range(0, len(payload), batch_size):
        client.table("units").insert(payload[i : i + batch_size]).execute()


def sync_handler_registry(client, handler) -> None:
    payload = {
        "id": handler.id,
        "state": handler.state,
        "description": handler.description,
        "source": handler.source,
        "probation_runs_remaining": handler.probation_runs_remaining,
        "confidence_score": handler.confidence_score,
    }
    client.table("handler_registry").upsert(payload, on_conflict="id").execute()
