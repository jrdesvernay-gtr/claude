"""Shared sandboxing for Item 20 handler code -- whether it just came fresh
off Agent 1 (handler_drafter.py) or is being reloaded from a persisted
fn_source in Supabase (handler_registry.load_persisted_handlers). Both paths
must go through the exact same safety checks, so this is the one place that
defines them.

Output must be a pure function body: text-in, rows-out, no file I/O or
network access. exec() runs in a restricted namespace (no builtins beyond
what's needed).
"""
from __future__ import annotations

import builtins as _builtins
import re
import textwrap

from pipeline.models import ItemRow
from pipeline.parsing.handler_registry import HandlerFn

_FORBIDDEN = re.compile(r"\b(import\s+(?!re\b)|open\(|exec\(|eval\(|subprocess|os\.|sys\.)")

# Fence content anywhere in the response, not just when the whole response
# starts with a fence -- confirmed live: a leading sentence before the fence
# (despite the drafting prompt asking for none) made an earlier prefix-only
# check silently skip stripping, leaving the prose+fence blob to fail the
# "def parse(" check with no clue why.
_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(raw: str) -> str:
    text = textwrap.dedent(raw).strip()
    fence = _CODE_FENCE_RE.search(text)
    return fence.group(1).strip() if fence else text


# Confirmed live: an original whitelist of just len/range/str/int was too
# narrow for realistic parsing code -- a drafted handler that had enough
# token budget to actually reason through a messy format used isinstance()
# for a defensive type check and hit NameError, since it wasn't in scope.
# This is a generous but still safe set: ordinary data-munging builtins, no
# file/process/import/eval access (those stay excluded, blocked both by
# _FORBIDDEN's source-text check and by simply not appearing here).
_SAFE_BUILTINS = {
    name: getattr(_builtins, name)
    for name in (
        "len", "range", "str", "int", "float", "bool", "list", "dict", "tuple", "set",
        "enumerate", "zip", "map", "filter", "sorted", "reversed", "min", "max", "sum",
        "abs", "round", "isinstance", "hasattr", "getattr", "any", "all", "repr",
        "ValueError", "TypeError", "KeyError", "IndexError", "StopIteration", "Exception",
    )
}


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


def compile_handler_code(code: str, source_label: str = "") -> HandlerFn:
    """Sandbox-check and exec() a handler's `def parse(item_20_text): ...`
    source, returning the wrapped, ItemRow-producing HandlerFn. Raises
    ValueError on a sandbox violation, a missing parse() definition, or
    invalid syntax -- always with the actual code/response visible in the
    message, not just a bare exception.
    """
    if _FORBIDDEN.search(code):
        raise ValueError(
            f"Handler code failed sandbox check: disallowed import/call{source_label}"
        )
    if "def parse(" not in code:
        raise ValueError(f"Handler code did not define a parse() function{source_label}: {code[:500]!r}")

    sandbox_globals = {
        "__builtins__": {**_SAFE_BUILTINS, "__import__": _restricted_import},
        "re": re,
    }
    sandbox_locals: dict = {}
    try:
        exec(code, sandbox_globals, sandbox_locals)  # noqa: S102 - sandboxed namespace, reviewed above
    except SyntaxError as exc:
        # Confirmed live: a drafted handler can have a genuine syntax error
        # (unterminated string literal), most likely from embedding a
        # snippet of real sample data -- which can contain stray quotes/
        # apostrophes (e.g. real entity names like "Tasty Chick'n...") --
        # directly into a string literal in the generated code. Surface the
        # actual broken code instead of letting a bare SyntaxError propagate
        # with no way to see what it looked like.
        raise ValueError(f"Handler code has invalid Python syntax{source_label}: {exc}\nCode:\n{code[:2000]}") from exc
    raw_fn = sandbox_locals["parse"]

    def fn(item_20_text: str) -> list[ItemRow]:
        return [ItemRow(**row) for row in raw_fn(item_20_text)]

    return fn
