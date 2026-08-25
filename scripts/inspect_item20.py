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
    find_roster_exhibit_letter,
    is_text_native,
    list_exhibit_titles,
    locate_exhibit_section,
    locate_franchisee_list_section_heuristic,
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


def show_list_of_exhibits(full_text: str) -> None:
    import re

    print("  --- List of Exhibits ---")
    m = re.search(r"LIST\s+OF\s+EXHIBITS", full_text)
    if m:
        chunk = full_text[m.start(): m.start() + 4000]
        for line in chunk.splitlines():
            if line.strip():
                print(f"    {line!r}")
        return

    print("  ('LIST OF EXHIBITS' heading not found -- falling back to scanning all EXHIBIT lines)")
    seen = set()
    for line in full_text.splitlines():
        stripped = line.strip()
        em = re.match(r"^EXHIBIT\s+([A-Z])\b", stripped)
        if em and em.group(1) not in seen:
            seen.add(em.group(1))
            print(f"    {line!r}")


def inspect(pdf_path: Path) -> None:
    print(f"\n{'=' * 70}\n{pdf_path.name}\n{'=' * 70}")

    full_text = extract_full_text(pdf_path)
    print(f"  Total extracted chars: {len(full_text)}")

    if not is_text_native(full_text):
        print("  NOT text-native -- looks scanned, needs the OCR gate (not run by this script).")
        return

    show_all_item20_occurrences(full_text)
    show_list_of_exhibits(full_text)

    titles = list_exhibit_titles(full_text)
    print(f"  Exhibit titles found in front matter: {titles or '(none)'}")

    roster_letter = find_roster_exhibit_letter(full_text)
    print(f"  Title-matched roster exhibit: {roster_letter or '(none)'}")

    letters = find_referenced_exhibit_letters(full_text)
    print(f"  Front-matter-referenced exhibit letter(s): {letters or '(none found)'}")

    # Show every candidate exhibit (title match plus every referenced
    # letter), not just whichever locate_franchisee_list_section_heuristic() would
    # pick -- useful for comparing them side by side while validating.
    candidate_letters = ([roster_letter] if roster_letter else []) + [
        l for l in letters if l != roster_letter
    ]
    if not candidate_letters:
        result = locate_franchisee_list_section_heuristic(full_text)
        if result is None:
            print("  Franchisee list section NOT FOUND (no title match, no referenced exhibit, no Item 20 body).")
            out_path = pdf_path.with_suffix(".fulltext.txt")
            out_path.write_text(full_text)
            print(f"  Saved full extracted text to {out_path} for manual inspection.")
            return
        show_section(pdf_path, *result)
        return

    print(f"\n  >>> locate_franchisee_list_section_heuristic() would pick: exhibit_{candidate_letters[0]} <<<")
    for letter in candidate_letters:
        section = locate_exhibit_section(full_text, letter)
        if section is None:
            print(f"  Exhibit {letter}: heading not found in document.")
            continue
        show_section(pdf_path, section, f"exhibit_{letter}")


def show_section(pdf_path: Path, section_text: str, source_label: str) -> None:
    lines = section_text.splitlines()
    print(f"\n  === {source_label} ===")
    print(f"  Section: {len(lines)} lines, {len(section_text)} chars")

    fp = structural_fingerprint(section_text)
    print(f"  Structural fingerprint: {fp}")

    out_path = pdf_path.with_suffix(f".{source_label}.txt")
    out_path.write_text(section_text)
    print(f"  Saved full section text to {out_path}")

    print(f"  --- First {PREVIEW_LINES} lines ---")
    for line in lines[:PREVIEW_LINES]:
        print(f"  {line!r}")

    if len(lines) > PREVIEW_LINES:
        print(f"  --- Last 10 lines ---")
        for line in lines[-10:]:
            print(f"  {line!r}")


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or sorted(DOWNLOAD_DIR.glob("*.pdf"))
    if not paths:
        print(f"No PDFs found in {DOWNLOAD_DIR} and none passed as args.")
        sys.exit(1)
    for p in paths:
        inspect(p)
