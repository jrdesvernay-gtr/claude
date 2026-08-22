"""Test the full parse_item_20() path -- section locator (agent) + handler
registry / Agent 1 handler drafter + Table 1 cross-check hard gate --
against the real downloaded WI PDFs. Requires ANTHROPIC_API_KEY (loaded
from .env if python-dotenv is installed).

Usage:
    python3 scripts/test_parse_item_20.py                     # all PDFs in data/downloads/
    python3 scripts/test_parse_item_20.py data/downloads/wi_Taco_Bell.pdf
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

from pipeline.orchestrator import parse_item_20  # noqa: E402

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "downloads"
PREVIEW_ROWS = 10


def extract_full_text(pdf_path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def test_one(pdf_path: Path) -> None:
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


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or sorted(DOWNLOAD_DIR.glob("*.pdf"))
    if not paths:
        print(f"No PDFs found in {DOWNLOAD_DIR} and none passed as args.")
        sys.exit(1)
    for p in paths:
        test_one(p)
