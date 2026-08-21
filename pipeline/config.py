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

# v1 automation scope, in search order (Step 2: WI first, then MN, stop at first hit).
V1_STATE_SEARCH_ORDER = ["WI", "MN"]

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
