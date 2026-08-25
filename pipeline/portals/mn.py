"""MN Commerce Franchise Registration Search --
https://cards.web.commerce.state.mn.us/franchise-registrations

*** OUT OF V1 AUTOMATED SCOPE (2026-08-22) ***
Live-tested: this portal returns 403 Forbidden to headless Playwright --
page never loads, zero form elements present -- while loading fine in a
normal browser at the same moment. That's automation-fingerprint blocking,
not a general outage or a selector bug (two earlier "fix" attempts targeting
this file were chasing a phantom -- the form was never there to select
against). Per the project's non-negotiable constraint against bypassing
CAPTCHAs/bot-detection, no stealth plugin, header spoofing, or
navigator.webdriver override was attempted or should be added here. See
data/reference/fdd-registration-portals.csv and pipeline/config.py's
V1_STATE_SEARCH_ORDER (WI-only) for the current scope. This module is kept
for documentation/future-reference (e.g. if MN ever offers a non-blocked
access path) but MnPortalClient should not be wired into the live pipeline
until that changes.

Live-verified flow (2026-08-22, against "Quality Is Our Recipe, LLC" / Wendy's,
before the 403 was discovered -- i.e. this describes the intended flow, not
a currently-working one).

Document type: search "Clean FDD" first, "Final FDD" second (only fall back
if Clean FDD returns nothing) -- NOT "Marked FDD", which is a redline/diff
document (confirmed by "Redlined FDD" notes on those rows), not the clean
filed document Item 20 needs to be parsed from. "Final FDD" returned zero
results for Wendy's specifically, but the label exists in the dropdown and
may be what other franchisors use, so it's a fallback rather than dropped
entirely.

Results table columns (from the live page): # | Document | Franchisor |
Franchise names | Document types | Year | File number | Notes | Received
date | Added on. The "Document" column links straight to a download URL
(/documents/{GUID}/download?...) -- confirmed by no page/URL change on
click, i.e. a direct file response, not an intermediate page.

Uses Playwright (real browser) rather than raw HTTP requests: driving the
actual form via visible labels survives markup/param-name changes better
than hardcoding query-string keys, and downloads are captured through the
browser's own download handling rather than assumed to be an unauthenticated
plain GET.
"""
from __future__ import annotations

import time

from pipeline.portals.base import SearchHit

BASE_URL = "https://cards.web.commerce.state.mn.us/franchise-registrations"

DOCUMENT_TYPE_PRIORITY = ["Clean FDD", "Final FDD"]

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


def _document_type_key(label: str) -> str:
    return label.strip().lower().replace(" ", "_")


class MnPortalClient:
    def search(self, franchisor_name: str) -> list[SearchHit]:
        def run():
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    for doc_type in DOCUMENT_TYPE_PRIORITY:
                        hits = self._search_one_document_type(page, franchisor_name, doc_type)
                        if hits:
                            return hits
                    return []
                finally:
                    browser.close()

        return _with_retries(run)

    def _search_one_document_type(self, page, franchisor_name: str, doc_type: str) -> list[SearchHit]:
        page.set_default_timeout(30_000)
        page.goto(BASE_URL)
        # Like WI's "Name (Legal or Trade):" field, MN's "Franchisor:" text
        # isn't wrapped in a real <label> either (confirmed live --
        # get_by_label times out), so target fields positionally instead.
        # Form field order: Document, Franchisor, Franchise name, Year,
        # File number, [Document type dropdown], Content search -- so
        # Franchisor is the 2nd text input, and there's only one <select>.
        page.get_by_role("textbox").nth(1).fill(franchisor_name)
        page.locator("select").first.select_option(label=doc_type)
        page.get_by_role("button", name="Search").click()
        # Wait for the results view's "Export (CSV)" button rather than
        # "networkidle", which can hang on pages with persistent background
        # connections (analytics, etc.).
        page.get_by_role("button", name="Export").wait_for()

        # Locate the header row by known content, and substring-match the
        # "Year" column, in case the live header includes a sort-order glyph
        # (confirmed to happen on WI's equivalent "Effective Date" column;
        # MN's "Year" header shows sort arrows in the UI too) that would
        # break an exact-match lookup.
        table = page.locator("table").first
        header_cells = table.locator("tr").first.locator("th, td").all_inner_texts()
        year_idx = next(
            (i for i, h in enumerate(header_cells) if h.strip().lower().startswith("year")),
            None,
        )

        hits: list[SearchHit] = []
        seen_file_numbers: set[str] = set()
        rows = table.locator("tr").all()
        for row in rows:
            doc_link = row.locator("a[href*='/documents/']")
            if doc_link.count() == 0:
                continue

            file_number = doc_link.first.inner_text().strip()
            if file_number in seen_file_numbers:
                continue  # de-dupe rows split across multiple franchise-name lines
            seen_file_numbers.add(file_number)

            href = doc_link.first.get_attribute("href")
            if not href:
                continue

            filing_year = None
            if year_idx is not None:
                cells = row.locator("td").all_inner_texts()
                if year_idx < len(cells) and cells[year_idx].strip().isdigit():
                    filing_year = int(cells[year_idx].strip())

            hits.append(
                SearchHit(
                    franchisor_name=franchisor_name,
                    filing_url=href if href.startswith("http") else f"https://cards.web.commerce.state.mn.us{href}",
                    filing_year=filing_year,
                    document_type=_document_type_key(doc_type),
                )
            )
        return hits

    def download(self, hit: SearchHit, dest_path: str) -> str:
        def run():
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    with page.expect_download() as download_info:
                        page.goto(hit.filing_url)
                    download = download_info.value
                    download.save_as(dest_path)
                finally:
                    browser.close()
            return dest_path

        return _with_retries(run)
