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
    is_text_native,
    locate_item_20_section,
    structural_fingerprint,
)
from pipeline.parsing.handler_registry import registry
from pipeline.parsing.ocr_gate import ocr_pdf_to_text
from pipeline.parsing.table1_crosscheck import apply_crosscheck
from pipeline.models import FddFiling
from pipeline.portals.mn import MnPortalClient
from pipeline.portals.wi import WiPortalClient

log = logging.getLogger(__name__)

PORTAL_CLIENTS = {"WI": WiPortalClient, "MN": MnPortalClient}


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


def parse_item_20(state: str, full_text: str) -> tuple[FddFiling, list]:
    """Step 3.3-3.6: locate Item 20, classify format, parse, cross-check
    against Table 1. Returns the filing metadata (with review_flag set) and
    the parsed rows. Caller should NOT load rows into `units` if
    filing.review_flag is True.
    """
    item_20_text = locate_item_20_section(full_text)
    if item_20_text is None:
        raise ValueError("Item 20 section not found in document")

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
    )
    filing = apply_crosscheck(filing, rows, item_20_text)

    if not filing.review_flag:
        registry.record_clean_run(handler.id)  # advances agent-drafted handlers off probation

    return filing, rows
