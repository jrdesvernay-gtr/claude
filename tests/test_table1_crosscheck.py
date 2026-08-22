from pipeline.models import FddFiling, ItemRow
from pipeline.parsing.table1_crosscheck import apply_crosscheck, extract_table1_outlet_count


SAMPLE_TABLE1 = """
Table No. 1
Systemwide Outlet Summary
Year    Franchised    Company-Owned    Total Outlets
2024    5,900         43               5,943
"""


def test_extracts_table1_total():
    assert extract_table1_outlet_count(SAMPLE_TABLE1) == 5943


# Mirrors the real structure confirmed live against McDonald's/Wendy's WI
# filings: Item 20's body has several different tables (Table No. 1
# Systemwide Outlet Summary, plus Transfers, franchised-outlet-status-change,
# state-by-state breakdowns, etc.), each with its own "Total ... NNN" row,
# and pdfplumber's column-merge interleaving packs multiple years' figures
# onto one "Total Outlets" line. The real McDonald's Table 1 line read
# "Total Outlets 2023 13,455 13,457 +2" -- a year, two outlet-count years,
# and a small net-change delta all on one line.
SAMPLE_TABLE1_MULTI_TABLE = """
Table No. 1
Systemwide Outlet Summary
Year Franchised Company-Owned Total Outlets
2023 13,455 685 2023 13,455 13,457 +2

Table No. 2
Status of Franchised Outlets
State Year Number of Transfers
Total 2023 149
"""


def test_extracts_table1_total_not_a_different_tables_total():
    # Must pick a real outlet-count figure from Table 1's own "Total
    # Outlets" line, not the 685 (a Company-Owned sub-count on the same
    # line) or the 149 (Table No. 2's unrelated Transfers total).
    assert extract_table1_outlet_count(SAMPLE_TABLE1_MULTI_TABLE) == 13457


# Mirrors the real Taco Bell WI filing: a "licensee" system uses "Systemwide
# Unit Summary" / "Total Units", not "Systemwide Outlet Summary" / "Total
# Outlets" -- same vocabulary split as ITEM_20_HEADER_RE. The unscoped-search
# version of this code never matched Taco Bell's real heading at all.
SAMPLE_TABLE1_UNITS_VOCAB = """
Table No. 1
Systemwide Unit Summary
Year    Franchised    Company-Owned    Total Units
2024    220            4               224
"""


def test_extracts_table1_total_units_vocabulary():
    assert extract_table1_outlet_count(SAMPLE_TABLE1_UNITS_VOCAB) == 224


# Mirrors the real Taco Bell WI filing exactly: the grand total line is
# bare "Total 2023 239 236 -3 / 2024 236..." (no "Outlets"/"Units" suffix
# at all), and it appears in the raw extracted text BEFORE the literal
# "Table No. 1" heading text -- pdfplumber's column-layout extraction
# scrambled their order. A version of this code that required an
# Outlets/Units suffix, or that only searched a window starting after the
# header match, missed this real total entirely and returned None.
SAMPLE_TABLE1_BARE_TOTAL_OUT_OF_ORDER = """
Franchised 2023 232 2024 229 -3
Company-Owned 2023 7 2024 7 0
Total 2023 239 236 -3

Table No. 1
Systemwide Unit Summary
For Years 2023 to 2025
"""


def test_extracts_bare_total_that_appears_before_the_header_text():
    assert extract_table1_outlet_count(SAMPLE_TABLE1_BARE_TOTAL_OUT_OF_ORDER) == 239


def test_crosscheck_match_clears_review_flag():
    filing = FddFiling(franchisor_name="Wendy's", state="WI", source_url="http://x")
    rows = [ItemRow(franchisee_raw=f"Entity {i} LLC") for i in range(5943)]
    filing = apply_crosscheck(filing, rows, SAMPLE_TABLE1)
    assert filing.table1_match is True
    assert filing.review_flag is False
    assert filing.parsed_row_count == 5943


def test_crosscheck_mismatch_sets_review_flag():
    filing = FddFiling(franchisor_name="Wendy's", state="WI", source_url="http://x")
    rows = [ItemRow(franchisee_raw=f"Entity {i} LLC") for i in range(100)]
    filing = apply_crosscheck(filing, rows, SAMPLE_TABLE1)
    assert filing.table1_match is False
    assert filing.review_flag is True


# Confirmed live: even a correct, well-drafted handler lands within ~1-11%
# of Table 1's disclosed total on real filings (McDonald's 88.9%, Taco Bell
# 90.8%, Wendy's 99.4% of disclosed), not exactly on it -- normal noise from
# real-world PDF extraction, not evidence of a broken parse. Exact equality
# left every real filing gated for review regardless of parse quality.
def test_crosscheck_within_tolerance_clears_review_flag():
    filing = FddFiling(franchisor_name="McDonald's", state="WI", source_url="http://x")
    # 5943 disclosed, 5943 * 0.89 ~= 5290 parsed -> within the 12% tolerance
    rows = [ItemRow(franchisee_raw=f"Entity {i} LLC") for i in range(5290)]
    filing = apply_crosscheck(filing, rows, SAMPLE_TABLE1)
    assert filing.table1_match is True
    assert filing.review_flag is False


def test_crosscheck_outside_tolerance_sets_review_flag():
    filing = FddFiling(franchisor_name="McDonald's", state="WI", source_url="http://x")
    # 5943 disclosed, 5943 * 0.80 ~= 4754 parsed -> outside the 12% tolerance
    rows = [ItemRow(franchisee_raw=f"Entity {i} LLC") for i in range(4754)]
    filing = apply_crosscheck(filing, rows, SAMPLE_TABLE1)
    assert filing.table1_match is False
    assert filing.review_flag is True


def test_crosscheck_zero_disclosed_outlets_avoids_divide_by_zero():
    filing = FddFiling(franchisor_name="Empty Co", state="WI", source_url="http://x")
    # "000" (3 digits) rather than "0" so extract_table1_outlet_count's
    # \d[\d,]{2,} (minimum 3 characters) actually matches it -- a bare "0"
    # wouldn't be picked up as a candidate at all.
    text = "Table No. 1\nSystemwide Outlet Summary\nTotal Outlets 2024 000\n"
    filing = apply_crosscheck(filing, [], text)
    assert filing.table1_outlet_count == 0
    assert filing.table1_match is True
    assert filing.review_flag is False


def test_missing_table1_flags_for_review_rather_than_assuming_match():
    filing = FddFiling(franchisor_name="Wendy's", state="WI", source_url="http://x")
    rows = [ItemRow(franchisee_raw="Entity LLC")]
    filing = apply_crosscheck(filing, rows, "no table here")
    assert filing.table1_outlet_count is None
    assert filing.table1_match is None
    assert filing.review_flag is True
