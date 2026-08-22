from pipeline.parsing.format_detection import (
    find_referenced_exhibit_letters,
    locate_franchisee_list_section,
    locate_item_20_section,
)

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


# Mirrors the case that came up on the real WI PDFs: Item 20's own body is
# narrative + aggregate stats, and the actual per-unit franchisee list lives
# in a separately-lettered Exhibit (letter differs per franchisor) that the
# front-matter cross-reference sentence names.
SAMPLE_FDD_WITH_EXHIBIT = """
What's it like to be a Wendy's Item 20 or Exhibits P and R list current and former
franchisee? franchisees. You can contact them to ask about their experiences.

TABLE OF CONTENTS
ITEM 20 OUTLETS AND FRANCHISEE INFORMATION ................................................................... 57
ITEM 21 FINANCIAL STATEMENTS ........................................................................................... 60
EXHIBIT O LIST OF FRANCHISEES ........................................................................................... 200
EXHIBIT P LIST OF FRANCHISEES ........................................................................................... 210

ITEM 20
OUTLETS AND FRANCHISEE INFORMATION
Table No. 1
Systemwide Outlet Summary
2024  500  20  520
See Exhibit P for a list of franchisees.

ITEM 21
FINANCIAL STATEMENTS
Some unrelated Item 21 body content here.

EXHIBIT P
LIST OF FRANCHISEES
Sunrise Restaurant Group LLC\t123 Main St\tMadison\tWI\t53703\t608-555-0100\tOperating
KBP Foods Inc\t456 Elm St\tGreen Bay\tWI\t54301\t920-555-0199\tOperating

EXHIBIT R
LIST OF FORMER FRANCHISEES
Some Former Franchisee LLC\t789 Oak St\tKenosha\tWI\t53140\t262-555-0177\tTerminated
"""


def test_prefers_referenced_exhibit_over_item_20_body():
    result = locate_franchisee_list_section(SAMPLE_FDD_WITH_EXHIBIT)
    assert result is not None
    section, source = result
    assert source == "exhibit_P"
    assert "Sunrise Restaurant Group LLC" in section
    assert "KBP Foods Inc" in section
    assert "Table No. 1" not in section  # not the Item 20 narrative body
    assert "Some Former Franchisee LLC" not in section  # cut off before Exhibit R


def test_falls_back_to_item_20_body_when_referenced_exhibit_not_found():
    # SAMPLE_FDD references "Exhibits P and R" but neither heading exists
    # in the document -- falls back to Item 20's own body.
    result = locate_franchisee_list_section(SAMPLE_FDD)
    assert result is not None
    section, source = result
    assert source == "item_20_body"
    assert "Sunrise Restaurant Group LLC" in section


def test_find_referenced_exhibit_letters():
    assert find_referenced_exhibit_letters(SAMPLE_FDD_WITH_EXHIBIT) == ["P", "R"]
    assert find_referenced_exhibit_letters("nothing relevant here") == []
