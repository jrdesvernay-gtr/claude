"""Normalize a unit's `state` field to a canonical 2-letter USPS code before
it's written to Supabase.

Deliberately NOT agent-based, unlike address/city splitting -- state names
are a closed, fixed vocabulary (50 states + DC + territories), not an
open-ended per-franchisor format. A static lookup table handles it for
free with zero ambiguity; reaching for an LLM here would be pure waste.

Confirmed live: handlers already split `state` into its own ItemRow field
correctly (that's the agent-drafted handler's job, done once per table
format -- see pipeline/agents/handler_drafter.py), but the VALUE they
emit varies by franchisor's raw formatting: McDonald's rows carry a plain
2-letter code ("AK"), Wendy's rows carry the full state name
("NORTH CAROLINA"), Taco Bell's rows carry a combined "XX-Statename" token
("AR-Arkansas"). Filtering units by state (`WHERE state = 'NC'`) would
silently miss whichever franchisors don't happen to use that exact form.
"""
from __future__ import annotations

import re

USPS_STATE_ABBREVIATIONS = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
        "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
        "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
        "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
        "WI", "WY",
        "DC",  # District of Columbia
        "PR", "GU", "AS", "VI", "MP",  # territories
    }
)

STATE_NAME_TO_ABBR = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE",
    "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
    "PUERTO RICO": "PR", "GUAM": "GU", "AMERICAN SAMOA": "AS",
    "VIRGIN ISLANDS": "VI", "U.S. VIRGIN ISLANDS": "VI",
    "US VIRGIN ISLANDS": "VI", "NORTHERN MARIANA ISLANDS": "MP",
}

_COMBINED_CODE_PREFIX_RE = re.compile(r"^([A-Za-z]{2})[\s-]")


def normalize_state(raw: str | None) -> str | None:
    """Return a canonical 2-letter USPS code, or None if `raw` doesn't
    resolve to one -- fail-safe rather than guess, so a bad/unrecognized
    value shows up as NULL for review instead of silently breaking
    state-filtered queries with an unnormalized value.
    """
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None

    upper = text.upper()
    if upper in USPS_STATE_ABBREVIATIONS:
        return upper

    # Combined "XX-Statename" / "XX Statename" format (confirmed live:
    # Taco Bell's "AR-Arkansas") -- prefer the leading code if it's real.
    m = _COMBINED_CODE_PREFIX_RE.match(text)
    if m and m.group(1).upper() in USPS_STATE_ABBREVIATIONS:
        return m.group(1).upper()

    # Full state name, tolerating extra/irregular whitespace.
    collapsed = re.sub(r"\s+", " ", upper).strip()
    return STATE_NAME_TO_ABBR.get(collapsed)
