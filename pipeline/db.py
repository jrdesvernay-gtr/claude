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
from pipeline.parsing.state_normalization import normalize_state


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
        "unmatched_line_count": filing.unmatched_line_count,
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
    if rows and len(rows) != len(franchisee_ids):
        raise ValueError("rows and franchisee_ids must be the same length (one franchisee_id per row)")

    # Idempotent per filing: clear any units from a previous load of this
    # same fdd_filing_id before inserting fresh ones. insert_fdd_filing()
    # upserts on (franchisor_id, state, source_url), so reprocessing an
    # already-loaded filing (e.g. re-running a load script against the same
    # PDF, or reprocessing after a handler fix) reuses the same
    # fdd_filing_id -- without this delete, units were append-only and
    # accumulated duplicates on every re-run (confirmed live: re-running
    # scripts/test_load_to_supabase.py against the same 3 PDFs doubled
    # every filing's unit count, 50 -> 100, under the same fdd_filing_id).
    client.table("units").delete().eq("fdd_filing_id", fdd_filing_id).execute()

    if not rows:
        return

    payload = [
        {
            "fdd_filing_id": fdd_filing_id,
            "franchisor_id": franchisor_id,
            "franchisee_id": franchisee_id,
            "franchisee_raw": row.franchisee_raw,
            "address": row.address,
            "city": row.city,
            # Normalized to a canonical 2-letter USPS code here, not left
            # as whatever the handler emitted -- confirmed live, different
            # franchisors' handlers emit different but individually-correct
            # forms (McDonald's: "AK", Wendy's: "NORTH CAROLINA", Taco
            # Bell: "AR-Arkansas"). Storing them as-is would make
            # `WHERE state = 'NC'` silently miss whichever franchisors
            # don't use that exact form. Unnormalizable values become NULL
            # (fail-safe) rather than storing raw text that would silently
            # break state-filtered queries.
            "state": normalize_state(row.state),
            "zip": row.zip,
            "phone": row.phone,
            "status": row.status,
        }
        for row, franchisee_id in zip(rows, franchisee_ids)
    ]
    for i in range(0, len(payload), batch_size):
        client.table("units").insert(payload[i : i + batch_size]).execute()


def fetch_units_by_state(client, state_code: str, limit: int = 1000) -> list[dict]:
    """Units for prospecting, filtered to one state. `state_code` must
    already be a canonical 2-letter USPS code (see normalize_state()) --
    insert_units() normalizes on write, so this is a plain equality filter,
    no fuzzy matching needed at query time.
    """
    result = (
        client.table("units")
        .select("*")
        .eq("state", state_code.strip().upper())
        .limit(limit)
        .execute()
    )
    return result.data


def sync_handler_registry(client, handler) -> None:
    """Persist a handler's current state. For an agent-drafted handler this
    includes its raw source and match fingerprint, not just bookkeeping
    fields -- without those there'd be nothing in Supabase to actually
    reconstruct a working handler from on the next process's startup (see
    load_persisted_handlers()), and every filing would keep re-drafting from
    scratch regardless of how many times sync ran.
    """
    payload = {
        "id": handler.id,
        "state": handler.state,
        "description": handler.description,
        "source": handler.source,
        "probation_runs_remaining": handler.probation_runs_remaining,
        "confidence_score": handler.confidence_score,
        "fingerprint": handler.fingerprint,
        "fn_source": handler.fn_source,
    }
    client.table("handler_registry").upsert(payload, on_conflict="id").execute()


def load_persisted_handlers(client) -> int:
    """Reconstitute every persisted agent-drafted handler into the
    in-process registry, preserving its earned probation state (does NOT
    reset probation the way a fresh draft does). Call this once at pipeline
    startup, before processing any filings, so a handler that already
    proved itself on a past run gets reused instead of every filing
    re-drafting from scratch. Returns the count loaded.

    Deterministic handlers (wi_standard_v1 etc.) aren't stored here -- they
    register themselves at import time via pipeline.parsing.handlers, same
    as always.
    """
    from pipeline.agents.handler_sandbox import compile_handler_code
    from pipeline.parsing.handler_registry import registry

    rows = (
        client.table("handler_registry")
        .select("*")
        .eq("source", "agent_drafted")
        .not_.is_("fn_source", "null")
        .execute()
        .data
    )
    loaded = 0
    for row in rows:
        try:
            fn = compile_handler_code(row["fn_source"], source_label=f" (reloaded handler {row['id']})")
        except ValueError:
            # A handler persisted under an older sandbox/prompt version
            # could fail today's stricter check -- skip it rather than
            # crash startup; it'll just get re-drafted next time it's needed.
            continue
        registry.register_persisted(
            handler_id=row["id"],
            state=row["state"],
            description=row["description"] or "",
            fn=fn,
            fingerprint=row["fingerprint"] or {},
            fn_source=row["fn_source"],
            probation_runs_remaining=row["probation_runs_remaining"],
            confidence_score=row["confidence_score"],
        )
        loaded += 1
    return loaded
