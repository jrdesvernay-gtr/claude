"""Split the raw Item 20 franchisee field into entity name + guarantor names.

The field is semicolon-delimited: the legal entity name first, then personal
guarantors (likely owners). An earlier draft parser dropped everything after
the first ';' — that silently discarded the guarantor names, which the
franchisees.guarantor_names column depends on. Keep every segment.
"""
from __future__ import annotations


def split_franchisee_field(raw: str) -> tuple[str, list[str]]:
    """('Sunrise Restaurant Group LLC; John Smith; Jane Smith')
    -> ('Sunrise Restaurant Group LLC', ['John Smith', 'Jane Smith'])
    """
    segments = [s.strip() for s in raw.split(";") if s.strip()]
    if not segments:
        return "", []
    legal_name, *guarantors = segments
    return legal_name, guarantors
