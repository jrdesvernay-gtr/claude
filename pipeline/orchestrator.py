"""Ties Steps 2-4 together. Orchestration choice: plain script + LLM API
calls at exactly the 3 agent points (handler_drafter, entity_tiebreaker,
enrichment_researcher) — no LangGraph/agent-framework layer. Rationale:
deterministic-first / agent-as-fallback is a small number of clean call
sites; a graph framework would add indirection without buying anything here,
and a plain script keeps the "which step is deterministic vs. agent-backed"
boundary auditable by reading top to bottom.
"""
from __future__ import annotations

import logging

from pipeline.config import v1_scoped_portals
from pipeline.parsing import handlers  # noqa: F401 - registers built-in handlers
from pipeline.parsing.format_detection import (
    gather_locator_context,
    is_text_native,
    locate_exhibit_section,
    locate_item_20_section,
    structural_fingerprint,
)
from pipeline.parsing.franchisee_field import split_franchisee_field
from pipeline.parsing.handler_registry import registry
from pipeline.parsing.ocr_gate import ocr_pdf_to_text
from pipeline.parsing.table1_crosscheck import apply_crosscheck
from pipeline.models import FddFiling, FranchiseeCandidate, ItemRow
from pipeline.portals.mn import MnPortalClient
from pipeline.portals.wi import WiPortalClient
from pipeline.resolution.entity_resolution import resolve, ResolutionOutcome

log = logging.getLogger(__name__)

PORTAL_CLIENTS = {"WI": WiPortalClient, "MN": MnPortalClient}


def bootstrap_handler_registry(client) -> int:
    """Call once at pipeline startup, before processing any filings, to
    reload previously-persisted agent-drafted handlers from Supabase into
    the in-process registry. Without this, every filing re-drafts a handler
    from scratch each process run regardless of how many times a format was
    already seen and proven -- see pipeline.db.load_persisted_handlers() and
    pipeline.parsing.handler_registry.register_agent_drafted()'s fingerprint
    matching. Returns the count of handlers loaded.
    """
    from pipeline import db

    return db.load_persisted_handlers(client)


def find_filing_for_franchisor(franchisor_name: str):
    """Step 2/3.1: search WI first, then MN, per v1 scope. Stop at first hit."""
    for portal in v1_scoped_portals():
        client = PORTAL_CLIENTS[portal.state]()
        hits = client.search(franchisor_name)
        if hits:
            return portal.state, client, hits[0]
    return None, None, None


def extract_text(pdf_path: str, extracted_text_layer: str) -> str:
    """Step 3.2: OCR gate only if the text layer looks scanned."""
    if is_text_native(extracted_text_layer):
        return extracted_text_layer
    log.info("Document at %s looks scanned; routing through OCR gate.", pdf_path)
    return ocr_pdf_to_text(pdf_path)


def locate_franchisee_list_section(full_text: str) -> tuple[str, str, float | None]:
    """Step 3.3: find wherever the actual per-unit franchisee list lives.
    FDD structure varies too much across the ~40,000 US franchisors for
    regex to keep up (different exhibit letters, different vocabulary, the
    list sometimes inside Item 20's own body and sometimes deferred to an
    exhibit) -- this is agent-primary, not agent-as-fallback. Deterministic
    code only does the cheap, mechanical extraction fed to the agent
    (exhibit titles, Item 20's own body); the agent makes the judgment call
    of which one is the actual current-franchisee roster.

    Two agent calls, not one: the first reads raw "Item 20"/"Exhibit X"
    mentions gathered from the whole document (see
    format_detection.gather_locator_context -- deliberately no attempt made
    there to decide which mention is real) and picks a candidate location,
    which can still be wrong (an exhibit titled like a roster that's
    actually something else). The second reads the first 20 lines of
    whatever the first call picked and confirms it's really a current-
    franchisee list before we commit to it -- confirmed live this catches
    real mistakes the first call alone can't (e.g. an exhibit title that
    reads like a roster but isn't one).

    Once the agent names a location, extracting its actual text is a
    mechanical slicing job (find this heading, run until the next one) --
    that part stays deterministic.

    Returns (section_text, section_source, confidence). Raises if nothing
    usable was found or verification fails.
    """
    from pipeline.agents.section_locator import (
        locate_franchisee_list_via_agent,
        verify_franchisee_list_via_agent,
    )

    locator_context = gather_locator_context(full_text)
    decision = locate_franchisee_list_via_agent(locator_context)

    section, source = None, None
    if decision.get("location_type") == "exhibit" and decision.get("exhibit_letter"):
        letter = decision["exhibit_letter"]
        section = locate_exhibit_section(full_text, letter)
        source = f"exhibit_{letter}"
    elif decision.get("location_type") == "item_20_body":
        section = locate_item_20_section(full_text)
        source = "item_20_body"

    if not section:
        raise ValueError(
            f"Section locator agent could not find the franchisee list "
            f"(decision={decision})"
        )

    preview = "\n".join(section.splitlines()[:20])
    verification = verify_franchisee_list_via_agent(preview)
    if not verification.get("is_franchisee_list"):
        raise ValueError(
            f"Section locator agent picked {source} but verification rejected it "
            f"(decision={decision}, verification={verification})"
        )

    return section, source, verification.get("confidence")


def parse_item_20(state: str, full_text: str) -> tuple[FddFiling, list]:
    """Step 3.3-3.6: locate the franchisee list section, classify format,
    parse, cross-check against Table 1. Returns the filing metadata (with
    review_flag set) and the parsed rows. Caller should NOT load rows into
    `units` if filing.review_flag is True.
    """
    item_20_text, section_source, section_locator_confidence = locate_franchisee_list_section(full_text)

    # Table No. 1 (Systemwide Outlet Summary), which apply_crosscheck() reads
    # its verification count from, lives in Item 20's own narrative body --
    # NOT in the roster section itself when the roster is deferred to a
    # separately-lettered exhibit (confirmed live: McDonald's roster is
    # Exhibit R, which has no Table 1 in it at all, so cross-checking
    # against item_20_text alone always came back "can't verify" for any
    # exhibit-sourced filing, regardless of whether the parse was actually
    # correct). Look it up separately so the hard gate has real numbers to
    # compare against.
    item_20_body_text = locate_item_20_section(full_text) or item_20_text

    fingerprint = structural_fingerprint(item_20_text)
    handler = registry.find_match(state, fingerprint)

    if handler is None:
        # Step 3.4: Agent 1 drafts a new handler, goes live immediately on probation.
        from pipeline.agents.handler_drafter import draft_handler

        handler_id, fn = draft_handler(state, item_20_text, fingerprint)
        handler = registry.get(handler_id)
    else:
        fn = handler.fn

    rows = fn(item_20_text)

    filing = FddFiling(
        franchisor_name="",  # filled by caller with the known franchisor context
        state=state,
        source_url="",
        handler_id_used=handler.id,
        handler_confidence=handler.confidence_score,
        section_source=section_source,
        section_locator_confidence=section_locator_confidence,
    )
    filing = apply_crosscheck(filing, rows, item_20_body_text)

    if not filing.review_flag:
        registry.record_clean_run(handler.id)  # advances agent-drafted handlers off probation

    return filing, rows


def resolve_row_franchisee(client, row: ItemRow, cached_franchisees: dict[str, str]) -> str:
    """Step 3.7 for one Item 20 row: split the franchisee field, fuzzy-match
    against existing franchisees, escalate to Agent 2 if ambiguous, upsert,
    and return the resulting franchisee_id. `cached_franchisees` (id -> name)
    is mutated in place so later rows in the same filing see earlier upserts.
    """
    from pipeline import db

    legal_name, guarantors = split_franchisee_field(row.franchisee_raw)
    candidate = FranchiseeCandidate(legal_name=legal_name, guarantor_names=guarantors)

    result = resolve(legal_name, cached_franchisees)

    if result.outcome == ResolutionOutcome.NEW_ENTITY:
        franchisee_id = db.upsert_franchisee(client, candidate)
    elif result.outcome == ResolutionOutcome.AUTO_MERGE:
        franchisee_id = db.upsert_franchisee(client, candidate, franchisee_id=result.matched_franchisee_id)
    else:  # AMBIGUOUS -> Agent 2 tiebreaks; merge_confidence persisted either way
        from pipeline.agents.entity_tiebreaker import tiebreak

        matched_name = cached_franchisees[result.matched_franchisee_id]
        verdict = tiebreak(legal_name, matched_name, result.score)
        candidate.merge_confidence = verdict["confidence"]
        if verdict["same_entity"]:
            franchisee_id = db.upsert_franchisee(client, candidate, franchisee_id=result.matched_franchisee_id)
        else:
            franchisee_id = db.upsert_franchisee(client, candidate)

    cached_franchisees[franchisee_id] = legal_name
    return franchisee_id


def load_filing_to_db(client, franchisor_name: str, franchisor_website: str | None, filing: FddFiling, rows: list[ItemRow]) -> str:
    """Step 3.6/3.7: write a parsed filing to Supabase. Refuses to load units
    if the Table 1 hard gate flagged the filing for review — the fdd_filings
    row is still written (with review_flag=True) so it shows up for review,
    but no units/franchisees are touched.
    """
    from pipeline import db

    franchisor_id = db.upsert_franchisor(client, franchisor_name, franchisor_website)
    filing.franchisor_name = franchisor_name
    fdd_filing_id = db.insert_fdd_filing(client, filing, franchisor_id)

    if filing.handler_id_used:
        handler = registry.get(filing.handler_id_used)
        if handler is not None:
            db.sync_handler_registry(client, handler)

    if filing.review_flag:
        log.warning(
            "Filing %s flagged for review (parsed=%s, table1=%s) — units not loaded.",
            fdd_filing_id, filing.parsed_row_count, filing.table1_outlet_count,
        )
        return fdd_filing_id

    cached_franchisees = db.fetch_all_franchisees(client)
    franchisee_ids = [resolve_row_franchisee(client, row, cached_franchisees) for row in rows]
    db.insert_units(client, rows, fdd_filing_id, franchisor_id, franchisee_ids)

    return fdd_filing_id
