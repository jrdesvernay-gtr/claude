"""Step 3.2: detect text-native vs. scanned documents. Also the mechanical
text-extraction primitives (Item 20 body, exhibit titles, exhibit sections)
that pipeline.orchestrator.locate_franchisee_list_section() feeds to Agent
1 for Step 3.3's real judgment call -- see pipeline/agents/section_locator.py
for why that's agent-primary rather than more regex: FDD structure (which
exhibit letter holds the roster, if any; what it's titled) varies too much
across ~40,000 US franchisors to chase with keyword matching.
structural_fingerprint() still feeds Step 3.4's handler-registry routing
via structural probes (column layout, delimiter pattern).
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
#
# A "licensee" system (confirmed live: Taco Bell) uses different vocabulary
# throughout -- "ITEM 20 UNITS AND LICENSEE INFORMATION" -- so match both.
ITEM_20_HEADER_RE = re.compile(
    r"ITEM\s*20\s+(?:OUTLETS|UNITS)\s+AND\s+(?:FRANCHISEE|LICENSEE)\s+INFORMATION"
)
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
    # live in two DIFFERENT places depending on the franchisor: Wendy's/Taco
    # Bell wrap between "former" and "franchisees" ("...current and former\n
    # franchisee? franchisees."), McDonald's wraps between "and" and "former"
    # instead ("...lists current and\nformer franchisees."). Tolerate
    # whitespace/short gaps in both spots rather than assuming one fixed wrap
    # point.
    r"[^.]*Exhibits?\s+[A-Z][^.]*current\s+and\s+former\s*[^.]{0,60}?(?:franchisees|licensees)[^.]*\.",
    re.IGNORECASE,
)


def find_referenced_exhibit_letters(full_text: str) -> list[str]:
    """Extract the exhibit letter(s) named by the front-matter cross-
    reference sentence, e.g. "...Exhibits P and R..." -> ['P', 'R'].
    Returns [] if that sentence isn't found (some FDDs may put the list
    directly under Item 20 instead of deferring to an exhibit).

    Matches 1-2 letter codes (A, ..., Z, AA, BB, ...) -- FDDs with more
    than 26 exhibits continue with doubled letters, and a single-letter-only
    pattern would silently mis-parse "Exhibit AA" as just "A".
    """
    m = EXHIBIT_REFERENCE_SENTENCE_RE.search(full_text)
    if not m:
        return []
    return re.findall(r"\b[A-Z]{1,2}\b", m.group())


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
    # 1-2 letter exhibit codes (A..Z, then AA, BB, ...) for the same reason
    # as find_referenced_exhibit_letters above.
    boundary_re = re.compile(r"\bEXHIBIT\s+[A-Z]{1,2}\b|\bITEM\s*\d+\b")
    next_match = boundary_re.search(full_text, start + len(matches[-1].group()))
    end = next_match.start() if next_match else len(full_text)
    return full_text[start:end]


# The front-matter cross-reference sentence isn't reliable on its own --
# confirmed live: Wendy's names Exhibits P and R (transfers, closures) and
# never mentions Exhibit O at all, even though O ("OPERATING OUTLETS BY
# STATE") is the real current-outlet roster. An exhibit's own TITLE is a
# stronger, more direct signal of what it actually contains.
EXHIBIT_HEADING_RE = re.compile(r'^EXHIBIT\s+["“]?([A-Z]{1,2})["”]?\s*[-–—]?\s*(.*)$')
ROSTER_TITLE_KEYWORDS_RE = re.compile(
    r"OPERATING\s+OUTLETS|LIST\s+OF\s+(?:CURRENT\s+)?(?:FRANCHISEES|LICENSEES|OUTLETS)|"
    r"OUTLETS?\s+(?:BY|LIST)|CURRENT\s+(?:FRANCHISEES|LICENSEES|OUTLETS|UNITS)|"
    r"INFORMATION\s+REGARDING.*(?:FRANCHISEES|LICENSEES)",
    re.IGNORECASE,
)


def list_exhibit_titles(full_text: str) -> dict[str, str]:
    """Best-effort map of exhibit letter -> title, scraped only from the
    front matter (everything before Item 20's own real body heading).
    Restricting to the front matter matters: a franchisor's FDD can have an
    embedded document -- e.g. the franchise agreement itself, attached as
    an exhibit -- with its own internal "EXHIBIT A/B/C..." heading list
    deep in the document. Confirmed live: Taco Bell's attached franchise
    agreement (Exhibit B) has its own nested Exhibits A-I for lease/deed/
    etc. paperwork, which would otherwise be picked up as if they were the
    FDD's own top-level exhibit list.
    """
    item_20_matches = list(ITEM_20_HEADER_RE.finditer(full_text))
    boundary = item_20_matches[-1].start() if item_20_matches else len(full_text)
    window = full_text[:boundary]

    titles: dict[str, str] = {}
    lines = window.splitlines()
    for i, line in enumerate(lines):
        m = EXHIBIT_HEADING_RE.match(line.strip())
        if not m:
            continue
        letter, same_line_title = m.group(1), m.group(2).strip()
        if same_line_title:
            titles.setdefault(letter, same_line_title)
            continue
        for nxt in lines[i + 1 : i + 3]:
            nxt = nxt.strip()
            if nxt and not EXHIBIT_HEADING_RE.match(nxt):
                titles.setdefault(letter, nxt)
                break
    return titles


def find_roster_exhibit_letter(full_text: str) -> str | None:
    """Pick the exhibit whose own title says "this is the current outlet
    roster" -- see list_exhibit_titles for why this beats the front-matter
    cross-reference sentence.
    """
    for letter, title in list_exhibit_titles(full_text).items():
        if ROSTER_TITLE_KEYWORDS_RE.search(title):
            return letter
    return None


def locate_franchisee_list_section_heuristic(full_text: str) -> tuple[str, str] | None:
    """NOT the pipeline's real entry point -- that's
    pipeline.orchestrator.locate_franchisee_list_section(), which is
    agent-primary (see pipeline/agents/section_locator.py). FDD structure
    varies too much across ~40,000 US franchisors for keyword regex to
    keep up on its own; this heuristic version is kept only as a zero-cost
    offline utility (e.g. sanity-checking the agent's answer, or a fallback
    if the agent API is unavailable), not as the thing that decides.

    Returns (section_text, source_label) -- source_label is e.g.
    "exhibit_O" or "item_20_body". None if nothing matched.

    Priority: an exhibit whose own title identifies it as the roster, then
    an exhibit named by the front-matter cross-reference sentence (a
    narrower signal -- can point at a related-but-wrong disclosure like
    transfers or closures instead), then Item 20's own body as a last
    resort.
    """
    roster_letter = find_roster_exhibit_letter(full_text)
    if roster_letter:
        section = locate_exhibit_section(full_text, roster_letter)
        if section:
            return section, f"exhibit_{roster_letter}"

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
