"""Diagnostic: why parsed row counts and Table 1 disclosed counts don't
match. Prints the size and tail of the located exhibit section (to check
whether locate_exhibit_section() is running past the exhibit's real end),
and every "total"-like line found in Item 20's own body with context (to
check whether extract_table1_outlet_count() is grabbing the right number).

Usage:
    python3 scripts/diagnose_row_counts.py data/downloads/wi_McDonalds.pdf
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from pipeline.orchestrator import locate_franchisee_list_section  # noqa: E402
from pipeline.parsing.format_detection import locate_item_20_section  # noqa: E402


def extract_full_text(pdf_path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def diagnose(pdf_path: Path) -> None:
    print(f"\n{'=' * 70}\n{pdf_path.name}\n{'=' * 70}")
    full_text = extract_full_text(pdf_path)

    section, source, confidence = locate_franchisee_list_section(full_text)
    lines = section.splitlines()
    print(f"Located section: {source} (confidence={confidence})")
    print(f"Section size: {len(lines)} lines, {len(section)} chars")

    print(f"\n--- First 15 lines ---")
    for line in lines[:15]:
        print(f"  {line!r}")

    print(f"\n--- Last 30 lines ---")
    for line in lines[-30:]:
        print(f"  {line!r}")

    item_20_body = locate_item_20_section(full_text) or ""
    print(f"\nItem 20 body size: {len(item_20_body.splitlines())} lines, {len(item_20_body)} chars")
    print(f"\n--- Every 'total'-like line in Item 20's body, with context ---")
    for m in re.finditer(r"total.{0,60}?\d[\d,]{2,}", item_20_body, re.IGNORECASE):
        start = max(0, m.start() - 60)
        end = min(len(item_20_body), m.end() + 20)
        snippet = item_20_body[start:end].replace("\n", " / ")
        print(f"  @{m.start()}: ...{snippet}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/diagnose_row_counts.py <pdf_path> [<pdf_path> ...]")
        sys.exit(1)
    for p in sys.argv[1:]:
        diagnose(Path(p))
