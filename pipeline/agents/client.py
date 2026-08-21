"""Shared Claude API client for the three fallback agents. Deterministic
parsing/matching is the default path everywhere in this pipeline; these
agents are only invoked when a script genuinely can't handle the case
(Step 3.4 no handler match, Step 3.7 ambiguous fuzzy match, Step 4 enrichment
gap) — never as the primary parser for high-volume, well-structured data.
"""
from __future__ import annotations

import os

_MODEL = os.environ.get("PIPELINE_AGENT_MODEL", "claude-sonnet-5")


def get_client():
    import anthropic

    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def complete(system: str, user: str, max_tokens: int = 2048) -> str:
    client = get_client()
    resp = client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")
