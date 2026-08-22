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


# Item 20's own body is usually narrative + aggregate tables (Table No. 1
# Systemwide Outlet Summary etc.), NOT the row-level franchisee list --
# confirmed live: Wendy's/McDonald's/Taco Bell all defer the actual list to
# a separately-lettered Exhibit, referenced by the FDD's standardized
# front-matter cross-reference sentence (FTC-mandated summary page), e.g.
# "Item 20 or Exhibits P and R list current and former franchisees." /
# "Exhibit F lists current and former licensees." The letter(s) differ
# every franchisor -- that sentence is how we find the right one.
EXHIBIT_REFERENCE_SENTENCE_RE = re.compile(
    # Real FDDs render this as a two-column table (question | answer), and
    # pdfplumber's line-based extraction interleaves the columns -- confirmed
    # live: "...Exhibits P and R list current and former\nfranchisee?
    # franchisees." has a stray question-column fragment ("franchisee? ")
    # wedged between "former" and "franchisees". Allow a short gap there
    # rather than requiring the phrase to be contiguous.
    r"[^.]*Exhibits?\s+[A-Z][^.]*current and former[^.]{0,60}?(?:franchisees|licensees)[^.]*\.",
    re.IGNORECASE,
)


def find_referenced_exhibit_letters(full_text: str) -> list[str]:
    """Extract the exhibit letter(s) named by the front-matter cross-
    reference sentence, e.g. "...Exhibits P and R..." -> ['P', 'R'].
    Returns [] if that sentence isn't found (some FDDs may put the list
    directly under Item 20 instead of deferring to an exhibit).
    """
    m = EXHIBIT_REFERENCE_SENTENCE_RE.search(full_text)
    if not m:
        return []
    return re.findall(r"\b[A-Z]\b", m.group())


def locate_exhibit_section(full_text: str, letter: str) -> str | None:
    """Locate EXHIBIT {letter}'s section by its ALL-CAPS heading. Like Item
    headings, an exhibit letter can appear earlier in a table of contents /
    list of exhibits before the real heading, so take the LAST match. Runs
    until the next "EXHIBIT {other letter}" or "ITEM {n}" heading, or EOF.
    """
    heading_re = re.compile(rf"\bEXHIBIT\s+{re.escape(letter)}\b")
    matches = list(heading_re.finditer(full_text))
    if not matches:
        return None
    start = matches[-1].start()
    boundary_re = re.compile(r"\bEXHIBIT\s+[A-Z]\b|\bITEM\s*\d+\b")
    next_match = boundary_re.search(full_text, start + len(matches[-1].group()))
    end = next_match.start() if next_match else len(full_text)
    return full_text[start:end]


def locate_franchisee_list_section(full_text: str) -> tuple[str, str] | None:
    """The real Step 3.3 entry point: find wherever the actual per-unit
    franchisee list lives, which is usually a lettered Exhibit rather than
    Item 20's own body. Returns (section_text, source_label) --
    source_label is e.g. "exhibit_O" or "item_20_body", useful for
    fdd_filings provenance/debugging. None if nothing could be located
    deterministically (candidate for Agent 1 escalation).
    """
    for letter in find_referenced_exhibit_letters(full_text):
        section = locate_exhibit_section(full_text, letter)
        if section:
            return section, f"exhibit_{letter}"

    item_20 = locate_item_20_section(full_text)
    if item_20:
        return item_20, "item_20_body"

    return None


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
