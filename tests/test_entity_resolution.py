from pipeline.resolution.entity_resolution import resolve, ResolutionOutcome


EXISTING = {
    "id-1": "Sunrise Restaurant Group LLC",
    "id-2": "KBP Foods Inc",
}


def test_no_existing_franchisees_is_new_entity():
    result = resolve("Anything LLC", {})
    assert result.outcome == ResolutionOutcome.NEW_ENTITY


def test_near_exact_match_auto_merges():
    result = resolve("Sunrise Restaurant Group, LLC", EXISTING)
    assert result.outcome == ResolutionOutcome.AUTO_MERGE
    assert result.matched_franchisee_id == "id-1"


def test_unrelated_name_is_new_entity():
    result = resolve("Totally Different Ventures Corp", EXISTING)
    assert result.outcome == ResolutionOutcome.NEW_ENTITY


def test_partial_overlap_is_ambiguous():
    result = resolve("Sunrise Group Holdings LLC", EXISTING)
    assert result.outcome in (ResolutionOutcome.AMBIGUOUS, ResolutionOutcome.AUTO_MERGE)
