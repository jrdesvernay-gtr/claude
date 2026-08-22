"""In-memory row shapes mirroring sql/schema.sql. Plain dataclasses — the
orchestrator maps these to Supabase inserts; no ORM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ItemRow:
    """One parsed row out of an Item 20 exhibit. Handlers (text-in, rows-out,
    pure functions) return a list of these — no file I/O, no network.
    """
    franchisee_raw: str          # verbatim field, incl. semicolon-delimited guarantor names
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    status: str | None = None


@dataclass
class FddFiling:
    franchisor_name: str
    state: str
    source_url: str
    document_type: str = "unknown"
    filing_year: int | None = None
    handler_id_used: str | None = None
    handler_confidence: float | None = None
    section_source: str | None = None          # e.g. "exhibit_O" or "item_20_body"
    section_locator_confidence: float | None = None  # Agent locator's confidence, 0-1
    table1_outlet_count: int | None = None
    parsed_row_count: int | None = None
    table1_match: bool | None = None
    review_flag: bool = False
    raw_document_path: str | None = None
    downloaded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FranchiseeCandidate:
    legal_name: str
    entity_type: str | None = None
    guarantor_names: list[str] = field(default_factory=list)
    hq_full_address: str | None = None
    hq_phone: str | None = None
    hq_email: str | None = None
    domain: str | None = None
    linkedin_url: str | None = None
    contact_name: str | None = None
    contact_first_name: str | None = None
    contact_last_name: str | None = None
    contact_title: str | None = None
    contact_email: str | None = None
    contact_linkedin_url: str | None = None
    contact_confidence: float | None = None
    merge_confidence: float | None = None
