"""WI DFI Franchise Search — https://apps.dfi.wi.gov/apps/FranchiseSearch/

Live-verified flow (2026-08-22, against "Wendy's" -> "Quality Is Our Recipe, LLC"):

Search:
  1. Load MainSearch.aspx
  2. Fill the "Name (Legal or Trade):" field, click "Search"
  3. Results table columns: File Number | Legal Name | Trade Name |
     Effective Date | Expiration Date | Status | Franchise Details.
     Only the current/"Registered" row has a "Details" link -- expired
     filings don't, which conveniently doubles as the current-registration
     filter.

Details/Download:
  1. Follow the row's "Details" link to details.aspx?id=...&hash=...
     (the hash is server-computed per filing -- must come from the actual
     link, never be constructed)
  2. Click "Download" -- this is an ASP.NET WebForms postback that hijacks
     the HTTP response with the PDF bytes instead of re-rendering the page
     (confirmed: no navigation/URL change on click, browser just downloads).

Uses Playwright (real browser) rather than raw HTTP requests + manually
harvested ASP.NET viewstate fields: selecting by visible label/role text
survives markup churn that a hardcoded field-name/CSS-selector scraper
would break on, and the browser handles WI's postback state automatically
instead of us re-implementing it.
"""
from __future__ import annotations

import time
from urllib.parse import urljoin

from pipeline.portals.base import SearchHit

BASE_URL = "https://apps.dfi.wi.gov/apps/FranchiseSearch/MainSearch.aspx"

_RETRY_BACKOFF = (2, 4, 8)


def _with_retries(fn):
    last_exc: Exception | None = None
    for attempt, delay in enumerate((0,) + _RETRY_BACKOFF):
        if delay:
            time.sleep(delay)
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - retry on any transient browser/network error
            last_exc = exc
    assert last_exc is not None
    raise last_exc


class WiPortalClient:
    def search(self, franchisor_name: str) -> list[SearchHit]:
        def run():
            from playwright.sync_api import sync_playwright

            hits: list[SearchHit] = []
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    page.set_default_timeout(30_000)
                    page.goto(BASE_URL)
                    # The "Name (Legal or Trade):" text isn't wrapped in a real
                    # <label> on this page (confirmed live -- get_by_label fails
                    # even though a human sees the label fine), so target the
                    # page's one text input by ARIA role instead, which doesn't
                    # require a label association to match.
                    page.get_by_role("textbox").first.fill(franchisor_name)
                    page.get_by_role("button", name="Search").click()
                    # ASP.NET postback -- wait for the results text to actually update
                    # rather than "networkidle", which can hang on pages with
                    # persistent background connections (analytics, etc.)
                    page.get_by_text("Results Count:").wait_for()

                    # Locate the header row by known content rather than assuming
                    # it's the page's first <tr> (the page may have other
                    # layout tables ahead of the results grid), and substring-
                    # match the date column since the live header cell includes
                    # a sort-order glyph (e.g. "Effective Date▼"), which
                    # breaks an exact-match lookup.
                    header_cells = page.locator("tr", has_text="File Number").first.locator("th, td").all_inner_texts()
                    effective_idx = next(
                        (i for i, h in enumerate(header_cells) if "effective date" in h.strip().lower()),
                        None,
                    )

                    rows = page.locator("table tr").all()
                    for row in rows:
                        details_link = row.locator("a", has_text="Details")
                        if details_link.count() == 0:
                            continue
                        href = details_link.first.get_attribute("href")
                        if not href:
                            continue

                        filing_year = None
                        if effective_idx is not None:
                            cells = row.locator("td").all_inner_texts()
                            if effective_idx < len(cells) and "/" in cells[effective_idx]:
                                filing_year = int(cells[effective_idx].strip().split("/")[-1])

                        hits.append(
                            SearchHit(
                                franchisor_name=franchisor_name,
                                filing_url=urljoin(page.url, href),
                                filing_year=filing_year,
                                document_type="final_fdd",  # WI is filing-level, no marked/clean split
                            )
                        )
                finally:
                    browser.close()
            return hits

        return _with_retries(run)

    def download(self, hit: SearchHit, dest_path: str) -> str:
        def run():
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    page.set_default_timeout(30_000)
                    page.goto(hit.filing_url)
                    page.get_by_role("button", name="Download").wait_for()
                    with page.expect_download() as download_info:
                        page.get_by_role("button", name="Download").click()
                    download = download_info.value
                    download.save_as(dest_path)
                finally:
                    browser.close()
            return dest_path

        return _with_retries(run)
