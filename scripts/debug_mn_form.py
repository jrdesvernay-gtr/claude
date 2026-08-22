"""One-off debug: dump the actual <input>/<select> elements on MN's
Franchise Registrations search form, so selectors can be written against
real DOM structure instead of guessed from screenshots.

Usage: python3 scripts/debug_mn_form.py
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE_URL = "https://cards.web.commerce.state.mn.us/franchise-registrations"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_default_timeout(30_000)
    page.goto(BASE_URL)
    page.wait_for_timeout(3000)  # let any client-side JS render finish

    print(f"Page title: {page.title()}")
    print(f"URL after load: {page.url}")
    print()

    print("=== <input> elements ===")
    for i, el in enumerate(page.locator("input").all()):
        try:
            html = el.evaluate("el => el.outerHTML")
        except Exception as exc:  # noqa: BLE001
            html = f"<error: {exc}>"
        print(f"[{i}] {html}")

    print()
    print("=== <select> elements ===")
    for i, el in enumerate(page.locator("select").all()):
        try:
            html = el.evaluate("el => el.outerHTML")
        except Exception as exc:  # noqa: BLE001
            html = f"<error: {exc}>"
        print(f"[{i}] {html}")

    print()
    print("=== <label> elements ===")
    for i, el in enumerate(page.locator("label").all()):
        try:
            html = el.evaluate("el => el.outerHTML")
        except Exception as exc:  # noqa: BLE001
            html = f"<error: {exc}>"
        print(f"[{i}] {html}")

    browser.close()
