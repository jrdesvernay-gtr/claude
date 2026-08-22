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


# "Item 20" (title case) shows up multiple times before the real section --
# in a front-matter "What You Need to Know" summary page, and again in the
# table of contents -- both confirmed live (Wendy's/McDonald's/Taco Bell all
# matched the front-matter mention when this took the first case-insensitive
# "item 20" match, capturing 8-2749 lines of unrelated prose instead of the
# real outlet table).
#
# The fix: Item 20's title -- "Outlets and Franchisee Information" -- is
# fixed by the FTC Franchise Rule across every FDD, not just these 3, and is
# rendered in ALL CAPS at the real section heading (confirmed in Wendy's
# table of contents: "ITEM 20 OUTLETS AND FRANCHISEE INFORMATION"). Matching
# the full title case-sensitively is far more specific than a bare "item 20"
# -- it also appears in the table of contents ahead of the real heading, so
# take the LAST match, not the first.
ITEM_20_HEADER_RE = re.compile(r"ITEM\s*20\s+OUTLETS\s+AND\s+FRANCHISEE\s+INFORMATION")
ITEM_21_HEADER_RE = re.compile(r"\bITEM\s*21\b")
TABLE1_HEADER_RE = re.compile(
    r"table\s*(no\.?)?\s*1.{0,80}?systemwide\s+outlet\s+summary", re.IGNORECASE | re.DOTALL
)


def locate_item_20_section(full_text: str) -> str | None:
    """Return the Item 20 section of the document, or None if not found."""
    matches = list(ITEM_20_HEADER_RE.finditer(full_text))
    if not matches:
        return None
    start = matches[-1].start()
    # Item 20 runs until the next "Item 21" heading (searched after our
    # chosen start, so the table-of-contents "Item 21" entry -- which comes
    # before the real Item 20 heading -- can't be matched by mistake), or EOF.
    next_item = ITEM_21_HEADER_RE.search(full_text, start + len(matches[-1].group()))
    end = next_item.start() if next_item else len(full_text)
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
