"""Static configuration: state scope, confidence thresholds, file paths.

Thresholds live here (not in the DB) so they can be tuned without a migration.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
PORTALS_CSV = REFERENCE_DIR / "fdd-registration-portals.csv"
SEED_LIST_CSV = REFERENCE_DIR / "franchisor-seed-list.csv"

# v1 automation scope, in search order (Step 2: stop at first hit).
# MN was pulled 2026-08-22: live-tested 403 Forbidden to headless Playwright
# while loading fine in a normal browser at the same time -- automation-
# fingerprint blocking. Per the non-negotiable constraint against bypassing
# bot-detection, no stealth/spoofing workaround was attempted; see
# data/reference/fdd-registration-portals.csv for detail. v1_scoped_portals()
# below also filters on the CSV's v1_scope column, so this list is
# belt-and-suspenders with that file -- keep them in sync.
V1_STATE_SEARCH_ORDER = ["WI"]

# Entity resolution (Step 3.7): fuzzy match on legal_name.
FUZZY_MATCH_AUTO_ACCEPT = 92   # rapidfuzz score >= this: auto-merge, no agent call
FUZZY_MATCH_AUTO_REJECT = 60   # rapidfuzz score <  this: treat as new entity, no agent call
# Between reject and accept: ambiguous -> Agent 2 (entity tiebreaker) decides,
# and merge_confidence is persisted rather than silently trusted.

# New format handlers (Step 3.4, Agent 1): probationary period.
HANDLER_PROBATION_RUNS = 3
HANDLER_PROBATION_CONFIDENCE = 0.60
HANDLER_PROVEN_CONFIDENCE = 0.95

# Contact enrichment (Step 4): hard gate before syncing to Instantly/Pipedrive.
CONTACT_SYNC_THRESHOLD = 0.70

# Table 1 cross-check (Step 3.5) hard gate: how far parsed_row_count may
# differ from Table 1's disclosed outlet count and still count as a match.
# Confirmed live against real McDonald's/Wendy's/Taco Bell WI filings once
# the section-locator, Table 1 extraction, and handler-sandbox bugs were
# fixed: even a correct, well-drafted handler lands within ~1-11% of the
# disclosed total, not exactly on it -- normal noise from real-world PDF
# extraction (a stray header/footer line miscounted as a row, a name-
# splitting edge case, etc.), not evidence of a broken parse. Exact equality
# was too strict a bar for realistic data and left every filing gated for
# review regardless of parse quality. 12% comfortably covers that normal
# noise while still catching genuinely broken parses, which have shown up
# as errors of 10-1700%+ (a multi-page exhibit truncated to one page, an
# unbounded capture running past the exhibit's real end), not single-digit
# percentages.
TABLE1_MATCH_TOLERANCE = 0.12

# Unmatched-line safety net (Step 3.4): how large a share of row-shaped
# lines in a section a drafted handler is allowed to silently skip before
# it also trips review_flag, independent of the Table 1 tolerance above.
# "Row-shaped" (structural_fingerprint's data_line_count) is a loose count
# -- it also catches footer/page-number/subtotal lines that aren't real
# rows -- so some nonzero unmatched share is expected even from a correct
# parse. Not yet confirmed against real noisy filings the way
# TABLE1_MATCH_TOLERANCE was; starts at the same order of magnitude and
# should be tuned once real mismatches (or false positives) are observed.
UNMATCHED_LINE_TOLERANCE = 0.15


@dataclass(frozen=True)
class PortalConfig:
    state: str
    portal_name: str
    portal_url: str
    access_type: str
    bot_protected: str
    document_level: str
    v1_scope: bool
    notes: str


def load_portals() -> list[PortalConfig]:
    with PORTALS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            PortalConfig(
                state=row["state"],
                portal_name=row["portal_name"],
                portal_url=row["portal_url"],
                access_type=row["access_type"],
                bot_protected=row["bot_protected"],
                document_level=row["document_level"],
                v1_scope=row["v1_scope"].strip().lower() == "true",
                notes=row["notes"],
            )
            for row in reader
        ]


def v1_scoped_portals() -> list[PortalConfig]:
    """Portals confirmed clean and in v1 automation scope, in search order."""
    by_state = {p.state: p for p in load_portals() if p.v1_scope}
    return [by_state[s] for s in V1_STATE_SEARCH_ORDER if s in by_state]
