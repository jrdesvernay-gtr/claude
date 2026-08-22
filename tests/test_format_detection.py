from pipeline.parsing.format_detection import locate_item_20_section

# Mirrors the real structure confirmed live against Wendy's/McDonald's/
# Taco Bell WI filings: a front-matter mention, then a table-of-contents
# entry, then the real ALL-CAPS section heading followed by actual content.
SAMPLE_FDD = """
What's it like to be a Wendy's Item 20 or Exhibits P and R list current and former
franchisee? franchisees. You can contact them to ask about their experiences.

TABLE OF CONTENTS
ITEM 19 FINANCIAL PERFORMANCE REPRESENTATIONS ........................................................... 52
ITEM 20 OUTLETS AND FRANCHISEE INFORMATION ................................................................... 57
ITEM 21 FINANCIAL STATEMENTS ........................................................................................... 60

ITEM 19
FINANCIAL PERFORMANCE REPRESENTATIONS
Some unrelated Item 19 body content here.

ITEM 20
OUTLETS AND FRANCHISEE INFORMATION
Table No. 1
Systemwide Outlet Summary
Sunrise Restaurant Group LLC\t123 Main St\tMadison\tWI\t53703\t608-555-0100\tOperating

ITEM 21
FINANCIAL STATEMENTS
Some unrelated Item 21 body content here.
"""


def test_locates_real_body_section_not_front_matter_or_toc():
    section = locate_item_20_section(SAMPLE_FDD)
    assert section is not None
    assert "Sunrise Restaurant Group LLC" in section
    assert "or Exhibits P and R" not in section  # front-matter mention excluded
    assert "TABLE OF CONTENTS" not in section  # TOC entry excluded
    assert "FINANCIAL STATEMENTS" not in section  # cut off before real Item 21


def test_returns_none_when_no_item_20_title_present():
    assert locate_item_20_section("no such section here") is None
