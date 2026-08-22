"""Diagnostic: extract the Item 20 section from downloaded FDD PDFs and
show its real structure, so a handler can be written against reality
instead of guessed from a spec description.

Does NOT print the whole Item 20 section to the terminal (Wendy's alone
has thousands of outlet rows) -- prints a short preview plus a structural
fingerprint, and saves the full extracted text to a .txt file next to the
PDF for closer inspection.

Usage:
    python3 scripts/inspect_item20.py                     # all PDFs in data/downloads/
    python3 scripts/inspect_item20.py data/downloads/wi_Wendys.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.parsing.format_detection import (  # noqa: E402
    find_referenced_exhibit_letters,
    is_text_native,
    locate_franchisee_list_section,
    structural_fingerprint,
)

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "downloads"
PREVIEW_LINES = 40


def extract_full_text(pdf_path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def show_all_item20_occurrences(full_text: str) -> None:
    import re

    print("  --- All 'item 20' occurrences (context) ---")
    for m in re.finditer(r"item\s*20", full_text, re.IGNORECASE):
        start = max(0, m.start() - 30)
        end = min(len(full_text), m.end() + 150)
        snippet = full_text[start:end].replace("\n", "\\n")
        print(f"    @{m.start()}: ...{snippet}...")


def inspect(pdf_path: Path) -> None:
    print(f"\n{'=' * 70}\n{pdf_path.name}\n{'=' * 70}")

    full_text = extract_full_text(pdf_path)
    print(f"  Total extracted chars: {len(full_text)}")

    if not is_text_native(full_text):
        print("  NOT text-native -- looks scanned, needs the OCR gate (not run by this script).")
        return

    show_all_item20_occurrences(full_text)

    letters = find_referenced_exhibit_letters(full_text)
    print(f"  Referenced exhibit letter(s): {letters or '(none found)'}")

    result = locate_franchisee_list_section(full_text)
    if result is None:
        print("  Franchisee list section NOT FOUND (neither a referenced exhibit nor Item 20's own body).")
        out_path = pdf_path.with_suffix(".fulltext.txt")
        out_path.write_text(full_text)
        print(f"  Saved full extracted text to {out_path} for manual inspection.")
        return

    section_text, source_label = result
    lines = section_text.splitlines()
    print(f"  Located via: {source_label}")
    print(f"  Section: {len(lines)} lines, {len(section_text)} chars")

    fp = structural_fingerprint(section_text)
    print(f"  Structural fingerprint: {fp}")

    out_path = pdf_path.with_suffix(f".{source_label}.txt")
    out_path.write_text(section_text)
    print(f"  Saved full section text to {out_path}")

    item_20_text = section_text

    print(f"\n  --- First {PREVIEW_LINES} lines ---")
    for line in lines[:PREVIEW_LINES]:
        print(f"  {line!r}")

    if len(lines) > PREVIEW_LINES:
        print(f"\n  --- Last 10 lines (often the Table No. 1 summary) ---")
        for line in lines[-10:]:
            print(f"  {line!r}")


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or sorted(DOWNLOAD_DIR.glob("*.pdf"))
    if not paths:
        print(f"No PDFs found in {DOWNLOAD_DIR} and none passed as args.")
        sys.exit(1)
    for p in paths:
        inspect(p)
