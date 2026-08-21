"""Agent 2: tiebreaks ambiguous fuzzy-match results from entity resolution
(Step 3.7). Only called when rapidfuzz's score falls between
FUZZY_MATCH_AUTO_REJECT and FUZZY_MATCH_AUTO_ACCEPT. Result is persisted as
merge_confidence, never silently trusted.
"""
from __future__ import annotations

import json

from pipeline.agents.client import complete

SYSTEM_PROMPT = """You decide whether two franchisee name strings refer to
the same legal entity, for a franchise-operator database. Consider common
variations: abbreviations (Inc/Incorporated), punctuation, DBA vs legal name,
typos, and entity suffix differences (LLC vs LLC.). Do NOT merge two
genuinely different entities just because they share a common word (e.g.
"Family" or "Group").

Respond with ONLY a JSON object: {"same_entity": true|false, "confidence": 0.0-1.0, "reason": "..."}
"""


def tiebreak(candidate_name: str, matched_name: str, fuzzy_score: float) -> dict:
    user_prompt = (
        f'Candidate name: "{candidate_name}"\n'
        f'Closest existing franchisee: "{matched_name}"\n'
        f"Fuzzy match score: {fuzzy_score:.1f}/100"
    )
    raw = complete(SYSTEM_PROMPT, user_prompt, max_tokens=256)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # fail safe: treat as no-merge, low confidence, rather than guessing
        return {"same_entity": False, "confidence": 0.0, "reason": "agent response unparseable"}
    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    return result
