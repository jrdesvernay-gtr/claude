"""WI DFI Franchise Search — https://apps.dfi.wi.gov/apps/FranchiseSearch/

Filing-level PDF download, confirmed clean/no-CAPTCHA as of 2026-08-21 (see
data/reference/fdd-registration-portals.csv).

NOTE: this environment's network egress to state portals is blocked, so the
exact form field names / result-table selectors below are written from the
portal's known public search-by-name workflow but are NOT live-verified in
this change. Confirm against the live DOM (or capture a saved HTML sample)
before the first real run, and update the two marked spots.
"""
from __future__ import annotations

from pipeline.portals.base import SearchHit, request_with_backoff

BASE_URL = "https://apps.dfi.wi.gov/apps/FranchiseSearch/"


class WiPortalClient:
    def __init__(self) -> None:
        self.session = None  # lazily created on first use to avoid a network dependency at import time

    def _ensure_session(self):
        import requests

        if self.session is None:
            self.session = requests.Session()
        return self.session

    def search(self, franchisor_name: str) -> list[SearchHit]:
        self._ensure_session()
        # TODO(confirm on first live run): exact query param / form field name.
        resp = request_with_backoff(
            "GET", BASE_URL, params={"searchName": franchisor_name}
        )
        return self._parse_results(resp.text, franchisor_name)

    def _parse_results(self, html: str, franchisor_name: str) -> list[SearchHit]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        hits: list[SearchHit] = []
        # TODO(confirm on first live run): actual result-row selector.
        for row in soup.select("table.results tr"):
            link = row.find("a", href=True)
            if not link:
                continue
            hits.append(
                SearchHit(
                    franchisor_name=franchisor_name,
                    filing_url=link["href"] if link["href"].startswith("http") else BASE_URL + link["href"],
                    document_type="final_fdd",  # WI is filing-level; no marked/clean split to filter
                )
            )
        return hits

    def download(self, hit: SearchHit, dest_path: str) -> str:
        self._ensure_session()
        resp = request_with_backoff("GET", hit.filing_url)
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        return dest_path
