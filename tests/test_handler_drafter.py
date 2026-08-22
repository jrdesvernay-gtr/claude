"""Tests Agent 1 (handler drafter) sandboxing, mocking the LLM call so the
suite runs with no network/API key. Covers two real bugs hit against live
data: a leading-prose response defeating prefix-only fence stripping, and
the sandbox missing __import__ so a drafted "import re" statement failed
even though "re" itself is allowed.
"""
from unittest.mock import patch

import pytest

from pipeline.agents.handler_drafter import draft_handler
from pipeline.parsing.handler_registry import registry

COMPLETE = "pipeline.agents.handler_drafter.complete"

PLAIN_CODE = """
def parse(item_20_text: str) -> list[dict]:
    rows = []
    for line in item_20_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\\t")
        if len(parts) < 2:
            continue
        rows.append({"franchisee_raw": parts[0]})
    return rows
"""

FENCED_WITH_LEADING_PROSE = (
    "Looking at the sample, here's a parser for this format:\n\n"
    "```python\n" + PLAIN_CODE.strip() + "\n```"
)

CODE_WITH_IMPORT_RE = """
import re

def parse(item_20_text: str) -> list[dict]:
    rows = []
    for m in re.finditer(r"(\\S+)\\t(\\S+)", item_20_text):
        rows.append({"franchisee_raw": m.group(1)})
    return rows
"""


def test_plain_code_response_works():
    with patch(COMPLETE, return_value=PLAIN_CODE):
        handler_id, fn = draft_handler("WI", "a\\tb\nc\\td\n", {"delimiter": "tab"})
    rows = fn("a\tb\nc\td\n")
    assert [row.franchisee_raw for row in rows] == ["a", "c"]
    assert registry.get(handler_id) is not None


def test_fenced_response_with_leading_prose_is_still_extracted():
    # Confirmed live: a response that doesn't start exactly with "```"
    # (because of a leading sentence) previously skipped fence-stripping
    # entirely and failed with "did not define a parse() function".
    with patch(COMPLETE, return_value=FENCED_WITH_LEADING_PROSE):
        handler_id, fn = draft_handler("WI", "a\\tb\n", {"delimiter": "tab"})
    assert registry.get(handler_id) is not None


def test_response_without_parse_function_raises_with_raw_response_visible():
    with patch(COMPLETE, return_value="I couldn't figure out the format."):
        with pytest.raises(ValueError, match="Raw response"):
            draft_handler("WI", "garbage\n", {"delimiter": "fixed_width"})


def test_drafted_code_using_import_re_statement_executes():
    # Confirmed live: omitting __import__ from the sandbox's restricted
    # __builtins__ raised "ImportError: __import__ not found" the moment a
    # drafted handler's own text contained an "import re" statement, even
    # though "re" itself is allowed and pre-injected as a global.
    with patch(COMPLETE, return_value=CODE_WITH_IMPORT_RE):
        handler_id, fn = draft_handler("WI", "x\ty\n", {"delimiter": "tab"})
    rows = fn("Alpha\tBeta\n")
    assert rows and rows[0].franchisee_raw == "Alpha"
    assert registry.get(handler_id) is not None


def test_disallowed_import_in_drafted_code_is_rejected():
    with patch(COMPLETE, return_value="import os\n\ndef parse(item_20_text):\n    return []\n"):
        with pytest.raises(ValueError, match="sandbox check"):
            draft_handler("WI", "x\n", {"delimiter": "fixed_width"})


CODE_USING_ISINSTANCE = """
def parse(item_20_text: str) -> list[dict]:
    rows = []
    for line in item_20_text.splitlines():
        parts = line.split("\\t") if isinstance(line, str) else []
        if len(parts) >= 1 and parts[0].strip():
            rows.append({"franchisee_raw": parts[0].strip()})
    return rows
"""


def test_drafted_code_using_isinstance_executes():
    # Confirmed live: the original builtins whitelist (len/range/str/int
    # only) was too narrow for realistic parsing code -- a drafted handler
    # using isinstance() for a defensive type check hit NameError since it
    # wasn't in scope.
    with patch(COMPLETE, return_value=CODE_USING_ISINSTANCE):
        handler_id, fn = draft_handler("WI", "Alpha\tx\n", {"delimiter": "tab"})
    rows = fn("Alpha\tx\n")
    assert rows and rows[0].franchisee_raw == "Alpha"
