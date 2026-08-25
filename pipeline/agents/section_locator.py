"""Agent-driven: identify which part of an FDD holds the actual per-unit
franchisee/licensee list.

FDD structure varies enormously across ~40,000 US franchisors -- different
exhibit letters, different Item 20 vocabulary (Franchisee/Licensee,
Outlets/Units), the list sometimes inside Item 20's own body and sometimes
deferred to a separately-lettered exhibit whose letter and title wording
aren't standardized. Chasing every format variant with regex doesn't scale
to that volume. This is the PRIMARY method for locating the section, not a
last-resort fallback.

Deterministic code (pipeline.parsing.format_detection.gather_locator_context)
does only the cheap, hard-to-get-wrong part: find every raw "Item 20" and
"Exhibit X" mention in the document, with a little surrounding context. It
deliberately does NOT try to decide which mention is the real heading, which
exhibit's title is trustworthy, or where a "list of exhibits" page starts --
an earlier version of this module tried to pre-parse that structure and
broke twice against real FDDs (a front-matter boundary wrong for Wendy's,
a case-sensitive regex that silently matched nothing for Taco Bell), each
time starving the agent of any signal instead of just imperfect signal.
Interpreting the raw evidence is the agent's job.
"""
from __future__ import annotations

import json
import re

from pipeline.agents.client import complete


def _extract_json_object(raw: str) -> dict | None:
    """Parse a JSON object out of an agent response, tolerating a wrapping
    markdown code fence (```json ... ```) or stray text around the object --
    confirmed live: Wendy's raw locator context is the largest of the three
    real FDDs tested (21 exhibit letters, many mentions each), and the
    model's response was cut off before valid JSON closed at the previous,
    tighter token budget. Widening the budget is the main fix; this parse
    is just defense in depth against formatting the strict json.loads(raw)
    doesn't tolerate.
    """
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None

SYSTEM_PROMPT = """You are given every raw "Item 20" and "Exhibit X" mention
found anywhere in a Franchise Disclosure Document (FDD), each as a short
snippet with its character position (e.g. "[@225710] ITEM 20 / OUTLETS AND
FRANCHISEE INFORMATION..."). These are unfiltered raw matches, not curated:
expect noise -- a mention in a front-matter summary, a table-of-contents
entry (often just a letter/number and a page number, no real title), a
"list of exhibits" page (often with real titles), the actual section
heading itself, and possibly an embedded document's own internal exhibit
numbering (e.g. a franchise agreement attached as an exhibit, with its own
nested Exhibits A, B, C... for leases/deeds/etc. -- not the FDD's own
top-level exhibits). Character position can help you judge which
occurrence of a given mention is the real one, but don't assume any fixed
rule (e.g. "last occurrence wins") -- structure varies by franchisor.

Item 20 ("Outlets and Franchisee Information" or "Units and Licensee
Information") is a standard FTC-required section in every FDD, but the
actual per-unit list of CURRENT, ACTIVE franchisees/licensees (names,
addresses, phone numbers) is sometimes inside Item 20's own body and
sometimes deferred to a separately-lettered Exhibit (letter varies by
franchisor and year -- A, B, ... Z, AA, BB, etc.; title wording isn't
standardized).

Your job: from the raw mentions alone, identify where the CURRENT, ACTIVE
per-unit franchisee/licensee list most likely lives -- NOT a list of
terminated/transferred/closed franchisees, NOT a franchise agreement's own
attached exhibits, NOT aggregate summary tables (Table No. 1 etc.).

Respond with ONLY a JSON object:
{"location_type": "exhibit" | "item_20_body" | "not_found",
 "exhibit_letter": str | null,
 "confidence": 0.0-1.0,
 "reasoning": str}
"""


def locate_franchisee_list_via_agent(locator_context: str) -> dict:
    # Confirmed live: repeatedly raising max_tokens alone (512 -> 1024 ->
    # 2048) didn't reliably fix truncation -- the real lever is thinking
    # depth (see client.complete()'s effort param). This is a location
    # decision from a handful of short text snippets, not a task that
    # needs deep reasoning, so effort="low" both avoids the truncation and
    # is cheaper. The raw response is included in the fail-safe reasoning
    # below so a repeat doesn't again require a blind guess at the cause.
    raw = complete(SYSTEM_PROMPT, locator_context, max_tokens=2048, effort="low")
    result = _extract_json_object(raw)
    if result is None:
        # fail safe: report not_found rather than guessing
        return {
            "location_type": "not_found",
            "exhibit_letter": None,
            "confidence": 0.0,
            "reasoning": f"agent response unparseable, raw response: {raw[:500]!r}",
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
    # A yes/no classification over 20 lines of text -- effort="low" per the
    # same reasoning as the locate call above.
    raw = complete(VERIFY_SYSTEM_PROMPT, preview_text, max_tokens=512, effort="low")
    result = _extract_json_object(raw)
    if result is None:
        # fail safe: don't trust an unparseable verification
        return {
            "is_franchisee_list": False,
            "confidence": 0.0,
            "reasoning": f"agent response unparseable, raw response: {raw[:500]!r}",
        }
    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    return result
