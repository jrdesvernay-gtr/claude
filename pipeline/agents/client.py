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


def complete(system: str, user: str, max_tokens: int = 2048, effort: str = "medium") -> str:
    # claude-sonnet-5 runs adaptive thinking by default even without an
    # explicit `thinking` param, and budget_tokens (the old way to cap
    # thinking spend) is rejected outright on this model -- confirmed live:
    # draft_handler() repeatedly hit stop_reason='max_tokens' with a
    # 'thinking' block consuming the entire budget before any code was
    # emitted, and raising max_tokens alone (512 -> 1024 -> 2048 -> 8192)
    # never reliably fixed it. output_config.effort is the actual lever for
    # thinking depth on this model; "medium" trades some reasoning depth for
    # headroom to reliably finish. Callers with a genuinely simple/short
    # task can still pass effort="low".
    client = get_client()
    resp = client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort},
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
