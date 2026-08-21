"""Agent 3: web research to fill contact gaps when structured enrichment
(Clay tier) doesn't resolve or is ambiguous (Step 4). Output is gated by
contact_confidence before any outbound sync — low confidence never syncs.
"""
from __future__ import annotations

import json

from pipeline.agents.client import complete

SYSTEM_PROMPT = """You research a franchise operator (a legal entity that
runs multiple restaurant units under one or more brands) to find the best
outbound contact: name, title, email, LinkedIn URL. Prefer an owner/
operating-partner/VP-of-Operations level contact over a generalist. If you
cannot find a confident answer, say so — do not guess an email address.

Respond with ONLY a JSON object:
{"contact_name": str|null, "contact_title": str|null, "contact_email": str|null,
 "contact_linkedin_url": str|null, "confidence": 0.0-1.0, "reasoning": str}
"""


def research_contact(
    legal_name: str,
    brand_list: list[str],
    hq_full_address: str | None,
    guarantor_names: list[str],
    web_search_fn,
) -> dict:
    """web_search_fn: callable(query: str) -> list[dict] the caller supplies
    (e.g. the harness's WebSearch tool) — kept as a dependency injection so
    this module has no direct network access of its own.
    """
    queries = [f'"{legal_name}" franchisee owner'] + [f'"{g}" "{legal_name}"' for g in guarantor_names[:2]]
    search_results = []
    for q in queries:
        search_results.extend(web_search_fn(q))

    user_prompt = json.dumps(
        {
            "legal_name": legal_name,
            "brands": brand_list,
            "hq_full_address": hq_full_address,
            "guarantor_names": guarantor_names,
            "search_results": search_results[:20],
        }
    )
    raw = complete(SYSTEM_PROMPT, user_prompt, max_tokens=512)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "contact_name": None, "contact_title": None, "contact_email": None,
            "contact_linkedin_url": None, "confidence": 0.0,
            "reasoning": "agent response unparseable",
        }
    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    return result
