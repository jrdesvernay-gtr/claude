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
    text = "".join(block.text for block in resp.content if block.type == "text")
    if not text:
        # Confirmed live: a silently empty string here (e.g. the response
        # had no text block at all) surfaced downstream as a generic
        # "did not define a parse() function" with no way to tell an empty
        # API response apart from a genuine bad draft. Surface the actual
        # cause instead of guessing.
        block_types = [block.type for block in resp.content]
        raise RuntimeError(
            f"Claude API returned no text content "
            f"(stop_reason={resp.stop_reason!r}, block_types={block_types})"
        )
    return text
