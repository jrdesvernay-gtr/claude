from pipeline.models import FddFiling, ItemRow
from pipeline.parsing.table1_crosscheck import apply_crosscheck, extract_table1_outlet_count


SAMPLE_TABLE1 = """
Table No. 1
Systemwide Outlet Summary
Year    Franchised    Company-Owned    Total
2024    5,900         43               5,943
Total                                  5,943
"""


def test_extracts_table1_total():
    assert extract_table1_outlet_count(SAMPLE_TABLE1) == 5943


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


def test_missing_table1_flags_for_review_rather_than_assuming_match():
    filing = FddFiling(franchisor_name="Wendy's", state="WI", source_url="http://x")
    rows = [ItemRow(franchisee_raw="Entity LLC")]
    filing = apply_crosscheck(filing, rows, "no table here")
    assert filing.table1_outlet_count is None
    assert filing.table1_match is None
    assert filing.review_flag is True
