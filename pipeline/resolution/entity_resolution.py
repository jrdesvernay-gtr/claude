"""Step 3.7: entity resolution. Fuzzy-match each unit's franchisee name
against existing franchisees rows — match-before-insert is the default.

Applies both within one franchisor's list (same-brand rollup) and across
franchisors (multi-brand operator rollup), since it just matches against the
full franchisees table regardless of which brand created the candidate row.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz, process

from pipeline.config import FUZZY_MATCH_AUTO_ACCEPT, FUZZY_MATCH_AUTO_REJECT


class ResolutionOutcome(str, Enum):
    AUTO_MERGE = "auto_merge"      # score >= FUZZY_MATCH_AUTO_ACCEPT
    NEW_ENTITY = "new_entity"      # score <  FUZZY_MATCH_AUTO_REJECT (or no candidates)
    AMBIGUOUS = "ambiguous"        # in between -> Agent 2 tiebreaks


@dataclass
class ResolutionResult:
    outcome: ResolutionOutcome
    matched_franchisee_id: str | None = None
    score: float | None = None
    merge_confidence: float | None = None  # persisted flag; None when unambiguous


def _normalize(name: str) -> str:
    return " ".join(name.strip().upper().split())


def resolve(
    candidate_name: str,
    existing: dict[str, str],  # franchisee_id -> legal_name
) -> ResolutionResult:
    """existing is the current franchisees table (id -> legal_name). Caller
    is responsible for calling the entity tiebreaker agent on AMBIGUOUS
    results and persisting the resulting merge_confidence.
    """
    if not existing:
        return ResolutionResult(outcome=ResolutionOutcome.NEW_ENTITY)

    normalized_candidate = _normalize(candidate_name)
    choices = {fid: _normalize(name) for fid, name in existing.items()}

    best = process.extractOne(
        normalized_candidate, choices, scorer=fuzz.token_sort_ratio
    )
    if best is None:
        return ResolutionResult(outcome=ResolutionOutcome.NEW_ENTITY)

    _, score, matched_id = best

    if score >= FUZZY_MATCH_AUTO_ACCEPT:
        return ResolutionResult(
            outcome=ResolutionOutcome.AUTO_MERGE,
            matched_franchisee_id=matched_id,
            score=score,
        )
    if score < FUZZY_MATCH_AUTO_REJECT:
        return ResolutionResult(outcome=ResolutionOutcome.NEW_ENTITY, score=score)

    return ResolutionResult(
        outcome=ResolutionOutcome.AMBIGUOUS,
        matched_franchisee_id=matched_id,
        score=score,
    )
