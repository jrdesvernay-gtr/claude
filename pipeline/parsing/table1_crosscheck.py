"""Step 3.5 hard gate: cross-check parsed row count against the filing's own
Item 20 Table No. 1 Systemwide Outlet Summary. A free, built-in verification
that needs no external data source. Mismatch blocks the write and flags the
filing for review.

Table No. 1 lives in Item 20's own narrative body, not necessarily wherever
the per-unit roster itself ended up -- confirmed live: when the roster is
deferred to a separately-lettered exhibit (e.g. McDonald's Exhibit R), that
exhibit has no Table 1 in it at all. Callers must pass Item 20's own body
text here (pipeline.parsing.format_detection.locate_item_20_section), NOT
whatever section the roster was parsed from -- passing the roster section
instead makes extract_table1_outlet_count() silently return None for every
exhibit-sourced filing, regardless of whether the parse was correct.
"""
from __future__ import annotations

import re

from pipeline.models import FddFiling, ItemRow
from pipeline.parsing.format_detection import TABLE1_HEADER_RE

# Confirmed live: Item 20's body has SEVERAL different tables (Table No. 1
# Systemwide Outlet Summary, plus Transfers, franchised-outlet-status-change,
# state-by-state breakdowns, etc.), each with its own "Total ... NNN" row.
# Searching for "total...NNN" anywhere in the whole body and taking the last
# match picked up numbers from the WRONG table entirely -- e.g. McDonald's
# real Table No. 1 shows "Total Outlets 2023 13,455 ... 2025 ...", but the
# old unscoped search returned 685 (actually a Company-Owned count from a
# nearby but different line); Wendy's real Table 1 shows "Total Outlets 2023
# 5,994 6,030 ...", but the old search returned 4033 from an unrelated
# by-state sub-table. Scope the search to right after the real Table No. 1 /
# Systemwide Outlet Summary heading, look specifically for "Total Outlets"
# (not just "total"), and take the largest number found there (pdfplumber's
# column-merge interleaving mixes several years' start/end/change figures
# into one line -- the true outlet count is the largest of them, not
# necessarily the first or last).
TOTAL_OUTLETS_RE = re.compile(r"total\s+outlets(.{0,300})", re.IGNORECASE | re.DOTALL)
NEXT_TABLE_HEADER_RE = re.compile(r"table\s*(no\.?)?\s*\d+", re.IGNORECASE)


def extract_table1_outlet_count(item_20_text: str) -> int | None:
    """Best-effort extraction of Table No. 1's disclosed systemwide outlet
    total from Item 20's own body text. Returns None if it can't be found —
    callers should treat that as "cannot verify" and flag for review rather
    than assume a match.
    """
    header = TABLE1_HEADER_RE.search(item_20_text)
    if header is None:
        return None

    window_start = header.end()
    next_table = NEXT_TABLE_HEADER_RE.search(item_20_text, window_start)
    window_end = next_table.start() if next_table else min(len(item_20_text), window_start + 3000)
    window = item_20_text[window_start:window_end]

    m = TOTAL_OUTLETS_RE.search(window)
    if m is None:
        return None

    numbers = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]{2,}", m.group(1))]
    # A 4-digit year (e.g. "2024") sitting in the same row reads like a
    # plausible outlet count -- exclude it rather than risk picking it as
    # the max.
    candidates = [n for n in numbers if not (2000 <= n <= 2099)]
    if not candidates:
        return None
    return max(candidates)


def apply_crosscheck(filing: FddFiling, parsed_rows: list[ItemRow], item_20_text: str) -> FddFiling:
    filing.parsed_row_count = len(parsed_rows)
    filing.table1_outlet_count = extract_table1_outlet_count(item_20_text)

    if filing.table1_outlet_count is None:
        # Can't verify -> fail safe: flag for review rather than silently load.
        filing.table1_match = None
        filing.review_flag = True
    else:
        filing.table1_match = filing.table1_outlet_count == filing.parsed_row_count
        filing.review_flag = not filing.table1_match

    return filing
