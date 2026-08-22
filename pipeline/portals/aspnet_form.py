"""Generic helper for classic ASP.NET WebForms postback pages (WI's Franchise
Search runs on this stack: search results and the FDD download are both
plain synchronous postbacks that hijack the response instead of rendering
the page).

Harvests every hidden <input> on a page -- the usual
__VIEWSTATE/__VIEWSTATEGENERATOR/__EVENTVALIDATION trio plus anything else
the page adds -- and posts them back with one extra field overridden: the
button that was "clicked". This avoids hardcoding field names that can
change page to page and that we can't fully enumerate from a handful of
manual page inspections.
"""
from __future__ import annotations

from bs4 import BeautifulSoup


def harvest_hidden_fields(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    for inp in soup.find_all("input", attrs={"type": "hidden"}):
        name = inp.get("name")
        if name:
            fields[name] = inp.get("value", "")
    return fields


def first_text_input_name(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    inp = soup.find("input", attrs={"type": "text"})
    return inp.get("name") if inp else None


def submit_button_field(html: str, value_contains: str) -> tuple[str, str] | None:
    """Find an <input type="submit"> whose visible value contains
    `value_contains` (case-insensitive), e.g. "Search" or "Download".
    Returns (field_name, field_value) to add to the POST body -- this is
    what a real browser sends for the button that was clicked.
    """
    soup = BeautifulSoup(html, "html.parser")
    for inp in soup.find_all("input", attrs={"type": "submit"}):
        value = inp.get("value", "")
        if value_contains.lower() in value.lower():
            name = inp.get("name")
            if name:
                return name, value
    return None
