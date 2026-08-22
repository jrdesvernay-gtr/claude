"""Tests the two-step agent-primary section-locator wiring in
orchestrator.py, mocking the actual LLM calls so the suite runs with no
network/API key.
"""
from unittest.mock import patch

import pytest

from pipeline.orchestrator import locate_franchisee_list_section

SAMPLE_TEXT = """
EXHIBIT O
OPERATING OUTLETS BY STATE
Sunrise Restaurant Group LLC\t123 Main St\tMadison\tWI\t53703\t608-555-0100\tOperating

EXHIBIT P
RECENT TRANSFERS
Some Transfer LLC\t789 Oak St\tKenosha\tWI\t53140\t262-555-0177\tTransferred
"""

LOCATE_MOD = "pipeline.agents.section_locator.locate_franchisee_list_via_agent"
VERIFY_MOD = "pipeline.agents.section_locator.verify_franchisee_list_via_agent"


def test_uses_agent_decision_to_pick_exhibit_and_confirms_it():
    with patch(
        LOCATE_MOD,
        return_value={
            "location_type": "exhibit",
            "exhibit_letter": "O",
            "confidence": 0.9,
            "reasoning": "Exhibit O's title identifies it as the current outlet roster.",
        },
    ), patch(
        VERIFY_MOD,
        return_value={"is_franchisee_list": True, "confidence": 0.95, "reasoning": "looks like a roster"},
    ):
        section, source, confidence = locate_franchisee_list_section(SAMPLE_TEXT)

    assert source == "exhibit_O"
    assert confidence == 0.95
    assert "Sunrise Restaurant Group LLC" in section
    assert "Some Transfer LLC" not in section


def test_uses_agent_decision_to_pick_item_20_body():
    text = "ITEM 20\nOUTLETS AND FRANCHISEE INFORMATION\nSome narrative body text.\n\nITEM 21\nFINANCIAL STATEMENTS\n"
    with patch(
        LOCATE_MOD,
        return_value={"location_type": "item_20_body", "exhibit_letter": None, "confidence": 0.6, "reasoning": "no exhibit deferred"},
    ), patch(
        VERIFY_MOD,
        return_value={"is_franchisee_list": True, "confidence": 0.6, "reasoning": "narrative body has the list"},
    ):
        section, source, confidence = locate_franchisee_list_section(text)

    assert source == "item_20_body"
    assert "Some narrative body text" in section


def test_raises_when_agent_reports_not_found():
    with patch(
        LOCATE_MOD,
        return_value={"location_type": "not_found", "exhibit_letter": None, "confidence": 0.0, "reasoning": "nothing matched"},
    ):
        with pytest.raises(ValueError):
            locate_franchisee_list_section(SAMPLE_TEXT)


def test_raises_when_agent_names_an_exhibit_that_does_not_exist():
    with patch(
        LOCATE_MOD,
        return_value={"location_type": "exhibit", "exhibit_letter": "Z", "confidence": 0.8, "reasoning": "wrong guess"},
    ):
        with pytest.raises(ValueError):
            locate_franchisee_list_section(SAMPLE_TEXT)


def test_raises_when_verification_rejects_the_candidate():
    # Locator picks Exhibit P (title looked plausible), but verification
    # reads the actual first lines and recognizes it's a transfers list,
    # not a current-franchisee roster -- this is exactly the second-look
    # check the verify step exists for.
    with patch(
        LOCATE_MOD,
        return_value={"location_type": "exhibit", "exhibit_letter": "P", "confidence": 0.7, "reasoning": "title looked roster-like"},
    ), patch(
        VERIFY_MOD,
        return_value={"is_franchisee_list": False, "confidence": 0.9, "reasoning": "this is a list of recent transfers, not current franchisees"},
    ):
        with pytest.raises(ValueError):
            locate_franchisee_list_section(SAMPLE_TEXT)
