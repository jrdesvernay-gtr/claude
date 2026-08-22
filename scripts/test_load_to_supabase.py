"""End-to-end test: locate + parse + cross-check + load a real filing all
the way into Supabase (franchisors, fdd_filings, units, franchisees), using
pipeline.orchestrator.load_filing_to_db(). Requires ANTHROPIC_API_KEY and
SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY.

Prints what actually landed in each table afterward (not just what the
in-memory filing object claims), so a review_flag=True filing's units
being skipped is visible, not just theoretical.

Usage:
    python3 scripts/test_load_to_supabase.py                     # all PDFs in data/downloads/
    python3 scripts/test_load_to_supabase.py data/downloads/wi_Taco_Bell.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from pipeline import db  # noqa: E402
from pipeline.orchestrator import bootstrap_handler_registry, load_filing_to_db, parse_item_20  # noqa: E402
from pipeline.parsing.handler_registry import registry  # noqa: E402

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "downloads"

# franchisor name derived from filename, e.g. "wi_Taco_Bell.pdf" -> "Taco Bell"
def franchisor_name_from_path(pdf_path: Path) -> str:
    stem = pdf_path.stem
    if "_" in stem:
        stem = stem.split("_", 1)[1]
    return stem.replace("_", " ")


def extract_full_text(pdf_path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def load_one(pdf_path: Path, client) -> None:
    print(f"\n{'=' * 70}\n{pdf_path.name}\n{'=' * 70}")

    franchisor_name = franchisor_name_from_path(pdf_path)
    full_text = extract_full_text(pdf_path)

    try:
        filing, rows = parse_item_20("WI", full_text)
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED to parse: {type(exc).__name__}: {exc}")
        return

    filing.source_url = f"local://{pdf_path.name}"

    handler = registry.get(filing.handler_id_used)
    if handler is not None:
        db.sync_handler_registry(client, handler)

    print(f"  Section source: {filing.section_source} | Handler: {filing.handler_id_used}")
    print(f"  Parsed rows: {filing.parsed_row_count} | Table 1 disclosed: {filing.table1_outlet_count}")
    print(f"  Table 1 match: {filing.table1_match} | REVIEW FLAG: {filing.review_flag}")

    fdd_filing_id = load_filing_to_db(client, franchisor_name, None, filing, rows)
    print(f"  Loaded. fdd_filing_id={fdd_filing_id}")

    units_written = client.table("units").select("id").eq("fdd_filing_id", fdd_filing_id).execute().data
    print(f"  Units actually written to Supabase: {len(units_written)}"
          + (" (skipped -- review_flag was True)" if filing.review_flag else ""))


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or sorted(DOWNLOAD_DIR.glob("*.pdf"))
    if not paths:
        print(f"No PDFs found in {DOWNLOAD_DIR} and none passed as args.")
        sys.exit(1)

    client = db.get_client()
    loaded = bootstrap_handler_registry(client)
    print(f"(Loaded {loaded} persisted agent-drafted handler(s) from Supabase)")

    for p in paths:
        load_one(p, client)
