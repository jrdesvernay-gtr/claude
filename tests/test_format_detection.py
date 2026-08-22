from pipeline.parsing.format_detection import (
    find_referenced_exhibit_letters,
    find_roster_exhibit_letter,
    gather_locator_context,
    list_exhibit_titles,
    locate_franchisee_list_section_heuristic,
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
EXHIBIT O MISCELLANEOUS DISCLOSURE ................................................................................. 200
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
    result = locate_franchisee_list_section_heuristic(SAMPLE_FDD_WITH_EXHIBIT)
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
    result = locate_franchisee_list_section_heuristic(SAMPLE_FDD)
    assert result is not None
    section, source = result
    assert source == "item_20_body"
    assert "Sunrise Restaurant Group LLC" in section


def test_find_referenced_exhibit_letters():
    assert find_referenced_exhibit_letters(SAMPLE_FDD_WITH_EXHIBIT) == ["P", "R"]
    assert find_referenced_exhibit_letters("nothing relevant here") == []


# Mirrors the real Wendy's case: the front-matter sentence names Exhibits P
# and R, but neither is the actual roster (P = transfers, R = closures) --
# the real roster is Exhibit O, "OPERATING OUTLETS BY STATE", never
# mentioned by that sentence at all. Title-matching must win.
SAMPLE_FDD_WENDYS_LIKE = """
What's it like to be a Wendy's Item 20 or Exhibits P and R list current and former
franchisee? franchisees. You can contact them to ask about their experiences.

TABLE OF CONTENTS
ITEM 20 OUTLETS AND FRANCHISEE INFORMATION ................................................................... 57
ITEM 21 FINANCIAL STATEMENTS ........................................................................................... 60
EXHIBIT O - OPERATING OUTLETS BY STATE .............................................................................. 200
EXHIBIT P - RECENT TRANSFERS .......................................................................................... 210
EXHIBIT R - RESTAURANT CLOSURES ..................................................................................... 220

ITEM 20
OUTLETS AND FRANCHISEE INFORMATION
Table No. 1
Systemwide Outlet Summary
2024  500  20  520

ITEM 21
FINANCIAL STATEMENTS
Some unrelated Item 21 body content here.

EXHIBIT O
OPERATING OUTLETS BY STATE
Sunrise Restaurant Group LLC\t123 Main St\tMadison\tWI\t53703\t608-555-0100\tOperating
KBP Foods Inc\t456 Elm St\tGreen Bay\tWI\t54301\t920-555-0199\tOperating

EXHIBIT P
RECENT TRANSFERS
Some Transfer LLC\t789 Oak St\tKenosha\tWI\t53140\t262-555-0177\tTransferred

EXHIBIT R
RESTAURANT CLOSURES
Some Closed LLC\t111 Pine St\tRacine\tWI\t53401\t414-555-0199\tClosed
"""


def test_prefers_title_matched_roster_exhibit_over_front_matter_reference():
    result = locate_franchisee_list_section_heuristic(SAMPLE_FDD_WENDYS_LIKE)
    assert result is not None
    section, source = result
    assert source == "exhibit_O"
    assert "Sunrise Restaurant Group LLC" in section
    assert "KBP Foods Inc" in section
    assert "Some Transfer LLC" not in section
    assert "Some Closed LLC" not in section


def test_falls_back_to_referenced_exhibit_when_no_title_matches():
    text = SAMPLE_FDD_WENDYS_LIKE.replace("OPERATING OUTLETS BY STATE", "MISC DISCLOSURE")
    result = locate_franchisee_list_section_heuristic(text)
    assert result is not None
    section, source = result
    assert source == "exhibit_P"


def test_find_roster_exhibit_letter():
    assert find_roster_exhibit_letter(SAMPLE_FDD_WENDYS_LIKE) == "O"
    assert find_roster_exhibit_letter("nothing relevant") is None


def test_list_exhibit_titles():
    titles = list_exhibit_titles(SAMPLE_FDD_WENDYS_LIKE)
    assert titles["O"].startswith("OPERATING OUTLETS BY STATE")
    assert titles["P"].startswith("RECENT TRANSFERS")
    assert titles["R"].startswith("RESTAURANT CLOSURES")


def test_list_exhibit_titles_keeps_first_occurrence_over_nested_document_exhibits():
    # A franchise agreement attached as its own exhibit can have internal
    # "EXHIBIT A/B/C..." headings for lease/deed paperwork reusing letters
    # already used by the FDD's own top-level exhibits (confirmed live:
    # Taco Bell's attached franchise agreement has its own nested Exhibits
    # A-I). The FDD's own top-level list (appearing first) must win, not
    # whichever nested mention comes later.
    text = SAMPLE_FDD_WENDYS_LIKE + """
EXHIBIT Z
FORM OF FRANCHISE AGREEMENT
EXHIBIT O
BILL OF SALE
EXHIBIT P
GENERAL RELEASE
"""
    titles = list_exhibit_titles(text)
    assert titles["O"].startswith("OPERATING OUTLETS BY STATE")
    assert titles["P"].startswith("RECENT TRANSFERS")


# FDDs with more than 26 exhibits continue A..Z then AA, BB, ... -- a
# single-letter-only pattern would mis-parse "Exhibit AA" as just "A".
SAMPLE_FDD_DOUBLE_LETTER_EXHIBIT = """
What's it like to be a Burger King Item 20 or Exhibits AA and BB list current and former
franchisee? franchisees. You can contact them to ask about their experiences.

TABLE OF CONTENTS
ITEM 20 OUTLETS AND FRANCHISEE INFORMATION ................................................................... 57
ITEM 21 FINANCIAL STATEMENTS ........................................................................................... 60
EXHIBIT AA - OPERATING OUTLETS BY STATE ......................................................................... 200
EXHIBIT BB - RECENT TRANSFERS ......................................................................................... 210

ITEM 20
OUTLETS AND FRANCHISEE INFORMATION
Table No. 1
Systemwide Outlet Summary
2024  500  20  520

ITEM 21
FINANCIAL STATEMENTS
Some unrelated Item 21 body content here.

EXHIBIT AA
OPERATING OUTLETS BY STATE
Sunrise Restaurant Group LLC\t123 Main St\tMadison\tWI\t53703\t608-555-0100\tOperating

EXHIBIT BB
RECENT TRANSFERS
Some Transfer LLC\t789 Oak St\tKenosha\tWI\t53140\t262-555-0177\tTransferred
"""


def test_handles_double_letter_exhibit_codes():
    assert find_referenced_exhibit_letters(SAMPLE_FDD_DOUBLE_LETTER_EXHIBIT) == ["AA", "BB"]
    assert find_roster_exhibit_letter(SAMPLE_FDD_DOUBLE_LETTER_EXHIBIT) == "AA"

    result = locate_franchisee_list_section_heuristic(SAMPLE_FDD_DOUBLE_LETTER_EXHIBIT)
    assert result is not None
    section, source = result
    assert source == "exhibit_AA"
    assert "Sunrise Restaurant Group LLC" in section
    assert "Some Transfer LLC" not in section


def test_gather_locator_context_finds_item_20_and_exhibit_mentions():
    context = gather_locator_context(SAMPLE_FDD_WENDYS_LIKE)
    assert "ITEM 20" in context.upper()
    assert "EXHIBIT O" in context.upper()
    assert "EXHIBIT P" in context.upper()
    assert "EXHIBIT R" in context.upper()
    # each snippet is tagged with its raw character position so the agent
    # can reason about which occurrence is real
    assert "[@" in context


def test_gather_locator_context_is_case_insensitive():
    # Mirrors the real Taco Bell case: "Item 20" title-case, not "ITEM 20".
    text = "Item 20\nUNITS AND LICENSEE INFORMATION\nSome body text."
    context = gather_locator_context(text)
    assert "[@0]" in context


def test_gather_locator_context_respects_max_chars():
    text = "\n".join(f"EXHIBIT {chr(65 + i % 26)} some filler text here" for i in range(500))
    context = gather_locator_context(text, max_chars=500)
    assert len(context) <= 500
