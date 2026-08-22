"""Agent 1: drafts a new Item 20 format handler when no registered handler
matches a filing's structural fingerprint (Step 3.4).

Output must be a pure function body: text-in, rows-out, no file I/O or
network access. We ask the model for the function body only, exec() it in a
restricted namespace (no builtins beyond what's needed), and register the
result on probation (see handler_registry.register_agent_drafted).
"""
from __future__ import annotations

import re
import textwrap
import uuid

from pipeline.agents.client import complete
from pipeline.models import ItemRow
from pipeline.parsing.handler_registry import HandlerFn, registry

SYSTEM_PROMPT = """You draft Python parsers for Item 20 franchisee-outlet
tables extracted from Franchise Disclosure Document exhibits.

Write ONE function:

    def parse(item_20_text: str) -> list[dict]:
        ...

Each returned dict has keys: franchisee_raw (str, required), address, city,
state, zip, phone, status (all optional, default None).

Rules:
- Pure function only: no imports beyond `re`, no file I/O, no network calls,
  no exec/eval, no access to os/sys/subprocess.
- franchisee_raw must be the VERBATIM field as it appears (semicolon-
  delimited legal name + guarantor names) — do not split or truncate it,
  downstream code does that.
- Return [] if you can't parse a line; never raise on a single bad line.

Return ONLY the function source code, no prose, no markdown fences.
"""

_FORBIDDEN = re.compile(r"\b(import\s+(?!re\b)|open\(|exec\(|eval\(|subprocess|os\.|sys\.)")

# Fence content anywhere in the response, not just when the whole response
# starts with a fence -- confirmed live: a leading sentence before the fence
# (despite the system prompt asking for none) made the old prefix-only check
# silently skip stripping, leaving the prose+fence blob to fail the
# "def parse(" check with no clue why.
_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def _extract_code(raw: str) -> str:
    text = textwrap.dedent(raw).strip()
    fence = _CODE_FENCE_RE.search(text)
    return fence.group(1).strip() if fence else text


def _restricted_import(name: str, *args, **kwargs):
    # Executing a drafted "import re" statement needs Python's __import__
    # builtin internally, even though "re" itself is allowed -- confirmed
    # live: omitting it from the sandbox's __builtins__ entirely raised
    # "ImportError: __import__ not found" the moment any drafted handler
    # actually contained an import statement (as opposed to relying on the
    # pre-injected `re` global alone).
    if name != "re":
        raise ImportError(f"import of {name!r} is not allowed in agent-drafted handlers")
    return re


def draft_handler(state: str, item_20_sample: str, fingerprint: dict) -> tuple[str, HandlerFn]:
    """Returns (handler_id, fn). Raises if the drafted code fails the
    sandboxing check or doesn't compile.
    """
    user_prompt = (
        f"State: {state}\n"
        f"Structural fingerprint: {fingerprint}\n\n"
        f"Sample Item 20 text (may be truncated):\n{item_20_sample[:6000]}"
    )
    # Confirmed live: Taco Bell's messier, irregular fixed-width format
    # (combined state field, optional phone, multi-word entity names) made
    # the model spend its entire budget on internal reasoning ("thinking"
    # block) and hit max_tokens before emitting any actual code -- the
    # default budget is fine for simple formats but not a safe floor once
    # the reasoning itself gets long.
    raw = complete(SYSTEM_PROMPT, user_prompt, max_tokens=8192)
    code = _extract_code(raw)

    if _FORBIDDEN.search(code):
        raise ValueError("Agent 1 draft failed sandbox check: disallowed import/call in generated handler")
    if "def parse(" not in code:
        raise ValueError(f"Agent 1 draft did not define a parse() function. Raw response: {raw[:500]!r}")

    sandbox_globals = {
        "__builtins__": {
            "len": len, "range": range, "str": str, "int": int,
            "__import__": _restricted_import,
        },
        "re": re,
    }
    sandbox_locals: dict = {}
    exec(code, sandbox_globals, sandbox_locals)  # noqa: S102 - sandboxed namespace, reviewed above
    raw_fn = sandbox_locals["parse"]

    def fn(item_20_text: str) -> list[ItemRow]:
        return [ItemRow(**row) for row in raw_fn(item_20_text)]

    handler_id = f"{state.lower()}_agent_drafted_{uuid.uuid4().hex[:8]}"
    registry.register_agent_drafted(
        handler_id=handler_id,
        state=state,
        description=f"Agent-drafted handler for {state}, fingerprint={fingerprint}",
        fn=fn,
    )
    return handler_id, fn
