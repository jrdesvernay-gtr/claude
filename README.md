# Multi-Unit Franchisee Pipeline

Identifies multi-unit franchise operators by parsing FDD Item 20 exhibits
from state registration portals, resolving franchisee entities across
brands, and enriching them with contact data for outbound targeting.
Output lands in Supabase. Full scope: see the handoff spec passed in at
project start (state portal audit, entity/contact field spec, workflow,
agent guardrails).

## Layout

```
sql/schema.sql              Supabase DDL — franchisors, fdd_filings, units,
                             franchisees, handler_registry, rollup trigger,
                             franchisee_units_view
data/reference/              Static reference CSVs (portal audit, seed list)
pipeline/
  config.py                  v1 state scope + confidence thresholds
  models.py                  in-memory row shapes mirroring the schema
  portals/                   WI search/download client (v1 scope). mn.py is
                              written but NOT wired in -- see below
  parsing/                   format detection, handler registry + handlers,
                              OCR gate, Table 1 cross-check, franchisee-field
                              split (legal name vs. guarantor names)
  resolution/                fuzzy entity resolution (match-before-insert)
  enrichment/                3-tier contact enrichment
  agents/                    the 3 LLM fallback agents (handler drafter,
                              entity tiebreaker, enrichment researcher)
  orchestrator.py             ties Step 2-4 together
tests/                        pytest suite for the deterministic pieces
```

## Orchestration choice

Plain script + LLM API calls at the 3 agent points, not LangGraph or a full
agent framework. The three escalation points (no handler match, ambiguous
fuzzy match, enrichment gap) are a small, fixed set of call sites; a graph
framework would add indirection without buying anything, and a plain script
keeps the deterministic-first/agent-as-fallback boundary readable top to
bottom in `pipeline/orchestrator.py`.

## v1 scope

Automation covers **WI only**, live-verified end-to-end (search + download)
against real franchisors on 2026-08-22. **MN was pulled from v1 scope the
same day**: it returns 403 Forbidden to headless Playwright while loading
fine in a normal browser at the same time — automation-fingerprint
blocking, confirmed live, not a selector bug or a general outage. Per the
non-negotiable constraint against bypassing CAPTCHAs/bot-detection, no
workaround (stealth plugin, header spoofing, `navigator.webdriver`
override) was attempted or should be added — `pipeline/portals/mn.py` is
kept for reference but isn't wired into `V1_STATE_SEARCH_ORDER`. See
`data/reference/fdd-registration-portals.csv` for detail.

VA and CA returned 503/maintenance on last check; they use the same
retry-with-backoff helper (`pipeline/portals/base.py`) but are not yet
promoted into `V1_STATE_SEARCH_ORDER` — do that once several consecutive
clean retries confirm they're scriptable (and confirm they don't also
403 a headless browser the way MN does). All CAPTCHA-gated and
FRED-dependent states, plus contact-only states (MI, WA, HI), are
permanently out of scope per the same constraint.

## Portal scraping: Playwright, not raw HTTP

`pipeline/portals/wi.py` (live and working) and `mn.py` (written, but
blocked — see v1 scope above) drive a real headless browser (Playwright)
rather than hand-rolled `requests` calls:

- **WI** runs on classic ASP.NET WebForms — search and the FDD download are
  both synchronous postbacks (the download button hijacks the HTTP response
  with the PDF instead of re-rendering the page). Playwright handles the
  viewstate/postback machinery automatically instead of us harvesting hidden
  fields by hand. Live-verified 2026-08-22: search + download both succeed
  for Wendy's, McDonald's, and Taco Bell.
- Selectors ended up **positional/role-based** (`get_by_role("textbox")`,
  indexed where a page has several), not label-based as originally written
  — WI's and MN's form fields turned out not to be wrapped in real
  `<label>` elements despite looking labeled to a human, so
  `get_by_label(...)` reliably timed out live. Substring-matching header
  lookups (e.g. `"effective date" in header_text`) were also needed since
  live sortable-column headers include a sort-order glyph that breaks an
  exact-match lookup.
- MN's intended flow (written but unreachable): plain query-string search,
  document type `Clean FDD` first, `Final FDD` fallback — never `Marked
  FDD` (a redline/diff document, not the clean filed FDD Item 20 needs to
  be parsed from).

Requires a one-time browser install: `python3 -m playwright install
chromium`. Test against real franchisors with:
```
python3 scripts/test_scrape_3_franchisors.py            # Wendy's, McDonald's, Taco Bell
python3 scripts/test_scrape_3_franchisors.py "Subway" "Domino's Pizza"
```
This tests search + download only (Step 2/3.1-3.2) — not parsing, since the
Item 20 table-layout handlers (`wi_standard_v1`, `mn_pipe_delim_v1`) are
still unverified against a real downloaded PDF's structure. If Playwright's
label/role selectors turn out too brittle in practice, the fallback plan is
an AI browser agent (browser-use/Skyvern) for search+download, kept
consistent with the project's deterministic-first/agent-as-fallback
principle rather than making that the default path.

## Known gaps / next steps

- **Supabase project is provisioned and schema applied** — project
  `kgbpftfwbvaxzhjjrehx` ("Relay - Franchisee", us-east-1). All 5 tables,
  the rollup trigger, and `franchisee_units_view` are live. RLS is
  intentionally left disabled — this pipeline runs server-side with the
  service-role key, so only that key should ever be used against these
  tables (the anon/public key currently has full read/write access; revisit
  if any client-side/browser code is ever pointed at this project).
  `pipeline/db.py` now writes `franchisors`/`fdd_filings`/`franchisees`/
  `units`/`handler_registry` rows via the `supabase` client, and
  `pipeline/orchestrator.load_filing_to_db()` ties Step 3.6/3.7 together:
  it refuses to write `units` when the Table 1 hard gate flagged the filing
  for review, and otherwise resolves each row's franchisee (fuzzy match,
  escalating to Agent 2 on an ambiguous score) before loading. Tested
  against a fake in-memory Supabase client (`tests/fake_supabase.py`) — no
  network required to run the suite.
- **`handler_registry` and `confidence` thresholds are in-process only** —
  `handler_registry` table in `sql/schema.sql` exists for persistence, but
  `pipeline/parsing/handler_registry.py`'s `HandlerRegistry` doesn't yet
  load/save from it, so agent-drafted handlers and probation state don't
  survive a process restart.
- **Franchisor seed list beyond Wendy's is unverified** against WI/MN —
  Step 3's search-and-download confirms each brand's presence on first run.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY, SUPABASE_*, CLAY_API_KEY
pytest
```
