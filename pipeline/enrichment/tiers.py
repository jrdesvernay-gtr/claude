"""Step 4: three-tier contact enrichment, cheapest first. Each tier fills in
whatever it can on a FranchiseeCandidate; the orchestrator only escalates to
the next tier for fields still missing.
"""
from __future__ import annotations

from pipeline.models import FranchiseeCandidate


def tier1_from_parse(candidate: FranchiseeCandidate, units: list, brand_list: list[str]) -> FranchiseeCandidate:
    """Free — already produced by parsing + rollup. legal_name, guarantor_names,
    brand_list/brand_count/total_units are set upstream (rollup trigger);
    this just backfills hq_phone from an Item 20 row if nothing better exists.
    """
    if not candidate.hq_phone:
        for u in units:
            phone = getattr(u, "phone", None)
            if phone:
                candidate.hq_phone = phone
                break
    return candidate


def tier2_from_sos(candidate: FranchiseeCandidate, sos_lookup_fn) -> FranchiseeCandidate:
    """Free — state Secretary of State lookup. sos_lookup_fn(legal_name) ->
    {"hq_full_address": ..., "officer_names": [...]} | None. Officer names
    are a cross-check against guarantor_names, not stored separately.
    """
    result = sos_lookup_fn(candidate.legal_name)
    if not result:
        return candidate
    if not candidate.hq_full_address and result.get("hq_full_address"):
        candidate.hq_full_address = result["hq_full_address"]
    return candidate


def tier3_from_clay(candidate: FranchiseeCandidate, clay_enrich_fn) -> FranchiseeCandidate:
    """Paid — Clay (or similar) structured enrichment for domain,
    linkedin_url, contact_name/title/email/linkedin_url.
    """
    result = clay_enrich_fn(candidate.legal_name, candidate.hq_full_address)
    if not result:
        return candidate
    for field_name in (
        "domain", "linkedin_url", "contact_name", "contact_first_name",
        "contact_last_name", "contact_title", "contact_email", "contact_linkedin_url",
    ):
        if not getattr(candidate, field_name) and result.get(field_name):
            setattr(candidate, field_name, result[field_name])
    if "confidence" in result:
        candidate.contact_confidence = result["confidence"]
    return candidate


def needs_agent3(candidate: FranchiseeCandidate) -> bool:
    """Escalate to Agent 3 (web research) when tier 3 didn't resolve a
    contact at all, or resolved one at low confidence.
    """
    from pipeline.config import CONTACT_SYNC_THRESHOLD

    if not candidate.contact_email and not candidate.contact_linkedin_url:
        return True
    return (candidate.contact_confidence or 0.0) < CONTACT_SYNC_THRESHOLD
