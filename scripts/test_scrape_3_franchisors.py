"""Manual smoke test for the Playwright-based WI/MN scrapers (Step 2/3.1-3.2
only -- search + download, no parsing). Run this locally, where you have
real internet access (this repo's CI/dev-container environment does not).

Usage:
    python3 -m playwright install chromium   # one-time browser install
    python3 scripts/test_scrape_3_franchisors.py
    python3 scripts/test_scrape_3_franchisors.py "Subway" "Domino's Pizza"

For each franchisor: search WI first, then MN (per v1 scope order), download
the first hit's filing, and report success/failure with enough detail to
debug a selector break. Downloaded PDFs land in data/downloads/ so you can
eyeball them afterward.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.orchestrator import find_filing_for_franchisor  # noqa: E402

DEFAULT_FRANCHISORS = ["Wendy's", "McDonald's", "Taco Bell"]
DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "downloads"


def run(franchisor_names: list[str]) -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for name in franchisor_names:
        print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")
        t0 = time.monotonic()
        try:
            state, client, hit = find_filing_for_franchisor(name)
        except Exception as exc:  # noqa: BLE001 - report every failure mode
            print(f"  SEARCH FAILED: {type(exc).__name__}: {exc}")
            results.append((name, "search_failed", str(exc)))
            continue

        if hit is None:
            print("  No hit in WI or MN.")
            results.append((name, "no_hit", None))
            continue

        print(f"  Found in {state}: {hit.filing_url} (year={hit.filing_year}, doc_type={hit.document_type})")

        safe_name = name.replace(" ", "_").replace("'", "")
        dest = DOWNLOAD_DIR / f"{state.lower()}_{safe_name}.pdf"
        try:
            client.download(hit, str(dest))
        except Exception as exc:  # noqa: BLE001
            print(f"  DOWNLOAD FAILED: {type(exc).__name__}: {exc}")
            results.append((name, "download_failed", str(exc)))
            continue

        size_kb = dest.stat().st_size / 1024
        elapsed = time.monotonic() - t0
        print(f"  Downloaded {dest} ({size_kb:.0f} KB) in {elapsed:.1f}s")
        results.append((name, "ok", str(dest)))

    print(f"\n{'=' * 60}\nSummary\n{'=' * 60}")
    for name, status, detail in results:
        print(f"  {name}: {status}" + (f" -- {detail}" if detail and status != 'ok' else ""))

    n_ok = sum(1 for _, status, _ in results if status == "ok")
    print(f"\n{n_ok}/{len(results)} succeeded.")


if __name__ == "__main__":
    names = sys.argv[1:] or DEFAULT_FRANCHISORS
    run(names)
