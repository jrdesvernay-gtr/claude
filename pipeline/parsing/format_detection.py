"""Step 3.2/3.3: detect text-native vs. scanned documents, then classify the
Item 20 exhibit's table format against the handler registry via structural
probes (column layout, delimiter pattern).
"""
from __future__ import annotations

import re


def is_text_native(extracted_text: str, min_chars: int = 200) -> bool:
    """True if a text-layer extraction (e.g. pdfplumber/pdftotext) produced
    enough real content that OCR isn't needed. Below the threshold, the
    document is presumed scanned and must go through the OCR gate first.
    """
    return len(extracted_text.strip()) >= min_chars


ITEM_20_HEADER_RE = re.compile(r"item\s*20", re.IGNORECASE)
TABLE1_HEADER_RE = re.compile(
    r"table\s*(no\.?)?\s*1.{0,80}?systemwide\s+outlet\s+summary", re.IGNORECASE | re.DOTALL
)


def locate_item_20_section(full_text: str) -> str | None:
    """Return the Item 20 section of the document, or None if not found."""
    matches = list(ITEM_20_HEADER_RE.finditer(full_text))
    if not matches:
        return None
    start = matches[0].start()
    # Item 20 runs until the next "Item 21" heading, or EOF.
    next_item = re.search(r"item\s*21", full_text[start:], re.IGNORECASE)
    end = start + next_item.start() if next_item else len(full_text)
    return full_text[start:end]


def structural_fingerprint(item_20_text: str) -> dict:
    """Cheap structural probes used to route to a handler: delimiter guess,
    column count on the densest line, whether rows look pipe/tab/comma
    delimited vs. fixed-width.
    """
    lines = [ln for ln in item_20_text.splitlines() if ln.strip()]
    data_lines = [ln for ln in lines if re.search(r"\d{3,}", ln)]  # lines with addresses/zips/phones

    def count_delim(delim: str) -> int:
        if not data_lines:
            return 0
        return max(ln.count(delim) for ln in data_lines)

    pipe_count = count_delim("|")
    tab_count = count_delim("\t")
    comma_count = count_delim(",")

    if pipe_count >= 3:
        delimiter = "pipe"
    elif tab_count >= 3:
        delimiter = "tab"
    elif comma_count >= 3:
        delimiter = "comma"
    else:
        delimiter = "fixed_width"

    return {
        "delimiter": delimiter,
        "data_line_count": len(data_lines),
        "has_semicolon_franchisee_field": any(";" in ln for ln in data_lines),
    }
