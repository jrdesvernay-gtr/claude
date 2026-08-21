"""MN Commerce Franchise Registration Search —
https://www.cards.commerce.state.mn.us/franchise-registrations

Document-level (not filing-level): must filter document_type to Final/Clean
FDD, not Marked FDD. Confirmed clean/no-CAPTCHA as of 2026-08-21 (see
data/reference/fdd-registration-portals.csv).

NOTE: same caveat as portals/wi.py — this environment's network egress to
state portals is blocked, so selectors below are unverified against the live
DOM. Confirm before first real run.
"""
from __future__ import annotations

from pipeline.portals.base import SearchHit, request_with_backoff

BASE_URL = "https://www.cards.commerce.state.mn.us/franchise-registrations"

# MN's document type labels we accept vs. reject for parsing.
ACCEPTED_DOCUMENT_LABELS = {"final fdd", "clean fdd"}
REJECTED_DOCUMENT_LABELS = {"marked fdd"}


def _classify_document_type(label: str) -> str:
    normalized = label.strip().lower()
    if normalized in ACCEPTED_DOCUMENT_LABELS:
        return "final_fdd" if "final" in normalized else "clean_fdd"
    if normalized in REJECTED_DOCUMENT_LABELS:
        return "marked_fdd"
    return "unknown"


class MnPortalClient:
    def __init__(self) -> None:
        self.session = None

    def _ensure_session(self):
        import requests

        if self.session is None:
            self.session = requests.Session()
        return self.session

    def search(self, franchisor_name: str) -> list[SearchHit]:
        self._ensure_session()
        # TODO(confirm on first live run): exact query param / form field name.
        resp = request_with_backoff("GET", BASE_URL, params={"name": franchisor_name})
        return self._parse_results(resp.text, franchisor_name)

    def _parse_results(self, html: str, franchisor_name: str) -> list[SearchHit]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        hits: list[SearchHit] = []
        # TODO(confirm on first live run): actual result-row / document-type-label selector.
        for row in soup.select("table.registrations tr"):
            link = row.find("a", href=True)
            doc_type_cell = row.find(class_="document-type")
            if not link or not doc_type_cell:
                continue
            doc_type = _classify_document_type(doc_type_cell.get_text())
            if doc_type not in ("final_fdd", "clean_fdd"):
                continue  # filter out Marked FDD per scope
            hits.append(
                SearchHit(
                    franchisor_name=franchisor_name,
                    filing_url=link["href"] if link["href"].startswith("http") else BASE_URL + link["href"],
                    document_type=doc_type,
                )
            )
        return hits

    def download(self, hit: SearchHit, dest_path: str) -> str:
        self._ensure_session()
        resp = request_with_backoff("GET", hit.filing_url)
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        return dest_path
