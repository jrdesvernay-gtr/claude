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

# Table 1 typically ends with a "Totals" row giving the systemwide outlet count.
TOTAL_ROW_RE = re.compile(
    r"total.{0,40}?(\d[\d,]{2,})\s*$", re.IGNORECASE | re.MULTILINE
)


def extract_table1_outlet_count(item_20_text: str) -> int | None:
    """Best-effort extraction of Table No. 1's disclosed systemwide outlet
    total from the raw exhibit text. Returns None if it can't be found —
    callers should treat that as "cannot verify" and flag for review rather
    than assume a match.
    """
    m = None
    for m in TOTAL_ROW_RE.finditer(item_20_text):
        pass  # keep the last "Total" match — Table 1 usually ends with the grand total
    if m is None:
        return None
    return int(m.group(1).replace(",", ""))


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
