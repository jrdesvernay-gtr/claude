from pipeline.parsing.handlers.wi_standard import parse, matches
from pipeline.parsing.format_detection import structural_fingerprint

SAMPLE = (
    "Sunrise Restaurant Group LLC; John Smith\t123 Main St\tMadison\tWI\t53703\t608-555-0100\tOperating\n"
    "KBP Foods Inc\t456 Elm St\tGreen Bay\tWI\t54301\t920-555-0199\tOperating\n"
)


def test_fingerprint_detects_tab_delimiter():
    fp = structural_fingerprint(SAMPLE)
    assert fp["delimiter"] == "tab"
    assert matches(fp)


def test_parses_rows_and_preserves_semicolon_field():
    rows = parse(SAMPLE)
    assert len(rows) == 2
    assert rows[0].franchisee_raw == "Sunrise Restaurant Group LLC; John Smith"
    assert rows[0].city == "Madison"
    assert rows[0].state == "WI"
    assert rows[0].zip == "53703"
    assert rows[1].franchisee_raw == "KBP Foods Inc"
