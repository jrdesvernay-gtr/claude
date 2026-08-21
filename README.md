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
  portals/                   WI + MN search/download clients (v1 scope)
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

Automation covers **WI and MN only** — both confirmed clean (no CAPTCHA) as
of 2026-08-21. VA and CA returned 503/maintenance on last check; they use
the same retry-with-backoff helper (`pipeline/portals/base.py`) but are not
yet promoted into `V1_STATE_SEARCH_ORDER` (`pipeline/config.py`) — do that
once several consecutive clean retries confirm they're scriptable. All
CAPTCHA-gated and FRED-dependent states, plus contact-only states (MI, WA,
HI), are permanently out of scope per the non-negotiable constraint against
bypassing CAPTCHA/bot-detection.

## Known gaps / next steps

- **Portal selectors are unverified.** This environment's network egress to
  state portals is blocked, so `pipeline/portals/wi.py` and `mn.py` are
  written against the portals' known public workflow but the exact
  form-field names and result-table selectors (marked `TODO`) need
  confirming against the live DOM before the first real run.
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
