"""Agent-driven: identify which part of an FDD holds the actual per-unit
franchisee/licensee list.

FDD structure varies enormously across ~40,000 US franchisors -- different
exhibit letters, different Item 20 vocabulary (Franchisee/Licensee,
Outlets/Units), the list sometimes inside Item 20's own body and sometimes
deferred to a separately-lettered exhibit whose letter and title wording
aren't standardized. Chasing every format variant with regex doesn't scale
to that volume. This is the PRIMARY method for locating the section, not a
last-resort fallback: deterministic code still does the cheap, mechanical
text extraction (table of contents, exhibit titles, Item 20's own body --
see pipeline.parsing.format_detection), but an LLM makes the judgment call
of which one is actually the current-franchisee roster.
"""
from __future__ import annotations

import json

from pipeline.agents.client import complete

SYSTEM_PROMPT = """You are given the front matter of a Franchise Disclosure
Document (FDD): its list of exhibits (with titles), and the text of Item 20
itself ("Outlets and Franchisee Information" or "Units and Licensee
Information"). Item 20 is a standard FTC-required section that exists in
every FDD, but the actual per-unit list of CURRENT, ACTIVE franchisees/
licensees (with names, addresses, phone numbers) is sometimes inside Item
20's own body and sometimes deferred to a separately-lettered Exhibit (the
letter varies by franchisor and by year -- A, B, ... Z, AA, BB, etc., and
titles aren't standardized wording).

Your job: identify exactly where the CURRENT, ACTIVE per-unit franchisee/
licensee list lives -- NOT a list of terminated/transferred/closed
franchisees, NOT the franchise agreement's own attached exhibits (leases,
bills of sale, etc.), NOT aggregate summary tables (Table No. 1 etc.).

Respond with ONLY a JSON object:
{"location_type": "exhibit" | "item_20_body" | "not_found",
 "exhibit_letter": str | null,
 "confidence": 0.0-1.0,
 "reasoning": str}
"""


def locate_franchisee_list_via_agent(
    exhibit_titles: dict[str, str],
    item_20_body_text: str,
) -> dict:
    user_prompt = json.dumps(
        {
            "exhibit_titles": exhibit_titles,
            "item_20_body_text": item_20_body_text[:6000],
        }
    )
    raw = complete(SYSTEM_PROMPT, user_prompt, max_tokens=512)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # fail safe: report not_found rather than guessing
        return {
            "location_type": "not_found",
            "exhibit_letter": None,
            "confidence": 0.0,
            "reasoning": "agent response unparseable",
        }
    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    return result


VERIFY_SYSTEM_PROMPT = """You will be shown the first ~20 lines of a section
a prior step picked out of a Franchise Disclosure Document (FDD) as the
per-unit list of CURRENT, ACTIVE franchisees/licensees.

Look at the actual lines and confirm: is this really a list of individual
current franchisees/licensees (names, addresses, phone numbers, one row per
outlet)? Say no if it's actually a list of terminated/transferred/closed
franchisees, an aggregate summary table (counts/statistics, not names), a
franchise agreement's own attached exhibits (leases, bills of sale, etc.),
or anything else that isn't a current-franchisee roster.

Respond with ONLY a JSON object:
{"is_franchisee_list": true | false, "confidence": 0.0-1.0, "reasoning": str}
"""


def verify_franchisee_list_via_agent(preview_text: str) -> dict:
    raw = complete(VERIFY_SYSTEM_PROMPT, preview_text, max_tokens=256)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # fail safe: don't trust an unparseable verification
        return {
            "is_franchisee_list": False,
            "confidence": 0.0,
            "reasoning": "agent response unparseable",
        }
    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    return result
