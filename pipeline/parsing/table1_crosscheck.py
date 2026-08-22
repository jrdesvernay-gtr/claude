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

from pipeline.config import TABLE1_MATCH_TOLERANCE
from pipeline.models import FddFiling, ItemRow
from pipeline.parsing.format_detection import TABLE1_HEADER_RE

# Confirmed live: Item 20's body has SEVERAL different tables (Table No. 1
# Systemwide Outlet Summary, plus Transfers, franchised-outlet-status-change,
# state-by-state breakdowns, etc.), each with its own "Total ... NNN" row.
# Searching for "total...NNN" anywhere in the whole body and taking the LAST
# match picked up numbers from the WRONG table entirely -- e.g. McDonald's
# real Table No. 1 shows "Total Outlets 2023 13,455 ... 2025 ...", but an
# unscoped last-match search returned 685 (a Company-Owned count from a
# nearby but different line); Wendy's real Table 1 shows "Total Outlets 2023
# 5,994 6,030 ...", but returned 4033 from an unrelated by-state sub-table.
#
# An earlier fix scoped the search to a window starting right after the
# Table No. 1 / Systemwide Outlet Summary heading match, requiring an
# "Outlets"/"Units" suffix on "Total". Confirmed live that's also wrong for
# some real filings: Taco Bell's real Table 1 total line is bare "Total 2023
# 239 236 -3 / 2024 236..." (no "Outlets"/"Units" word at all), AND it
# appears in the raw extracted text BEFORE the literal "Table No. 1" heading
# text -- pdfplumber's column-layout extraction scrambled their order (the
# same interleaving problem seen elsewhere in this pipeline), so a window
# starting after the header missed it entirely.
#
# Table No. 1 is always the FIRST table FTC-mandated Item 20 lists (before
# Transfers, status-change, state breakdowns, etc.), so instead of trying to
# bound a window by position -- unreliable once interleaving can put the
# heading text out of order relative to its own data -- just take the FIRST
# "total"-line in the whole body, preferring one with an explicit
# Outlets/Units suffix (reduces the odds of matching some other, later
# table's total by coincidence) and falling back to a bare "Total" if no
# suffixed one is found.
TOTAL_SUFFIXED_RE = re.compile(r"total\s+(?:outlets|units)(.{0,300})", re.IGNORECASE | re.DOTALL)
TOTAL_BARE_RE = re.compile(r"total(.{0,300})", re.IGNORECASE | re.DOTALL)


def extract_table1_outlet_count(item_20_text: str) -> int | None:
    """Best-effort extraction of Table No. 1's disclosed systemwide outlet
    total from Item 20's own body text. Returns None if it can't be found —
    callers should treat that as "cannot verify" and flag for review rather
    than assume a match.
    """
    if TABLE1_HEADER_RE.search(item_20_text) is None:
        # Gate on a real Table No. 1 actually being present, but don't
        # bound the search to "after" it -- see module comment above.
        return None

    m = TOTAL_SUFFIXED_RE.search(item_20_text) or TOTAL_BARE_RE.search(item_20_text)
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
    elif filing.table1_outlet_count == 0:
        # Avoid a divide-by-zero below; a disclosed total of 0 outlets with
        # any parsed rows at all is a real mismatch, not tolerance noise.
        filing.table1_match = filing.parsed_row_count == 0
        filing.review_flag = not filing.table1_match
    else:
        # TABLE1_MATCH_TOLERANCE, not exact equality -- confirmed live that
        # even a correct, well-drafted handler lands within ~1-11% of the
        # disclosed total on real filings, not exactly on it. See the
        # constant's own comment in pipeline/config.py for the reasoning.
        relative_diff = abs(filing.table1_outlet_count - filing.parsed_row_count) / filing.table1_outlet_count
        filing.table1_match = relative_diff <= TABLE1_MATCH_TOLERANCE
        filing.review_flag = not filing.table1_match

    return filing
