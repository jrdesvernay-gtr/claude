"""Test the full parse_item_20() path -- section locator (agent) + handler
registry / Agent 1 handler drafter + Table 1 cross-check hard gate --
against the real downloaded WI PDFs. Requires ANTHROPIC_API_KEY (loaded
from .env if python-dotenv is installed).

If SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are also set, this bootstraps
the handler registry from Supabase before running and syncs any newly-
drafted (or probation-advanced) handlers back after each filing -- so a
second run of this script should show "Handler used" reusing a handler
from the FIRST run instead of drafting a fresh one (a different
wi_agent_drafted_* id each time is the old, pre-persistence behavior).
Without Supabase credentials, persistence is skipped and every run drafts
fresh, same as before.

Usage:
    python3 scripts/test_parse_item_20.py                     # all PDFs in data/downloads/
    python3 scripts/test_parse_item_20.py data/downloads/wi_Taco_Bell.pdf
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from pipeline.orchestrator import bootstrap_handler_registry, parse_item_20  # noqa: E402

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "downloads"
PREVIEW_ROWS = 10


def _maybe_supabase_client():
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")):
        print("(SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set -- handler persistence skipped, every run drafts fresh)")
        return None
    from pipeline import db

    client = db.get_client()
    loaded = bootstrap_handler_registry(client)
    print(f"(Loaded {loaded} persisted agent-drafted handler(s) from Supabase)")
    return client


def extract_full_text(pdf_path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def test_one(pdf_path: Path, client) -> None:
    print(f"\n{'=' * 70}\n{pdf_path.name}\n{'=' * 70}")

    full_text = extract_full_text(pdf_path)

    try:
        filing, rows = parse_item_20("WI", full_text)
    except Exception as exc:  # noqa: BLE001 - report every failure mode
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        return

    print(f"  Section source: {filing.section_source} (locator confidence={filing.section_locator_confidence})")
    print(f"  Handler used: {filing.handler_id_used} (confidence={filing.handler_confidence})")
    print(f"  Parsed rows: {filing.parsed_row_count}")
    print(f"  Table 1 disclosed outlet count: {filing.table1_outlet_count}")
    print(f"  Table 1 match: {filing.table1_match}")
    print(f"  REVIEW FLAG: {filing.review_flag}")

    print(f"\n  --- First {PREVIEW_ROWS} parsed rows ---")
    for row in rows[:PREVIEW_ROWS]:
        print(f"  {row}")

    if client is not None:
        from pipeline import db
        from pipeline.parsing.handler_registry import registry

        handler = registry.get(filing.handler_id_used)
        if handler is not None:
            db.sync_handler_registry(client, handler)
            print(f"  (Synced handler {handler.id} to Supabase: "
                  f"probation_runs_remaining={handler.probation_runs_remaining}, "
                  f"confidence={handler.confidence_score})")


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or sorted(DOWNLOAD_DIR.glob("*.pdf"))
    if not paths:
        print(f"No PDFs found in {DOWNLOAD_DIR} and none passed as args.")
        sys.exit(1)
    supabase_client = _maybe_supabase_client()
    for p in paths:
        test_one(p, supabase_client)
