"""Diagnostic: run a persisted handler's exact fn_source against the real
located section text for a PDF, with instrumentation on WHY each line fails
(no state/zip match, no franchisee text left, or an exception) -- for
debugging a handler that silently returns 0 (or very few) rows against real
data despite looking correct against hand-typed samples.

Requires ANTHROPIC_API_KEY (for the section locator) and
SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY (to fetch the persisted handler).

Usage:
    python3 scripts/debug_handler_against_real_text.py <handler_id> data/downloads/wi_Taco_Bell.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from pipeline import db  # noqa: E402
from pipeline.orchestrator import locate_franchisee_list_section  # noqa: E402

MAX_DIAGNOSTIC_LINES = 15


def extract_full_text(pdf_path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def main(handler_id: str, pdf_path: Path) -> None:
    client = db.get_client()
    rows = client.table("handler_registry").select("*").eq("id", handler_id).execute().data
    if not rows:
        print(f"No handler found with id {handler_id!r}")
        return
    fn_source = rows[0]["fn_source"]
    print(f"--- fn_source for {handler_id} ---\n{fn_source}\n")

    full_text = extract_full_text(pdf_path)
    section, source, confidence = locate_franchisee_list_section(full_text)
    lines = [ln for ln in section.splitlines() if ln.strip()]
    print(f"Section: {source} (confidence={confidence}), {len(lines)} non-blank lines\n")

    # Exec the real persisted source directly (no sandbox restriction here --
    # this is a local debugging tool, not the production path) so we can
    # instrument line-by-line without editing handler_sandbox.py.
    ns: dict = {}
    exec(fn_source, ns)
    real_parse = ns["parse"]

    rows_out = real_parse(section)
    print(f"parse() returned {len(rows_out)} rows total\n")

    print(f"--- First {MAX_DIAGNOSTIC_LINES} non-blank lines of the section, verbatim ---")
    for ln in lines[:MAX_DIAGNOSTIC_LINES]:
        print(f"  {ln!r}")

    print(f"\n--- Running parse() on each of those lines individually ---")
    for ln in lines[:MAX_DIAGNOSTIC_LINES]:
        try:
            out = real_parse(ln)
        except Exception as exc:  # noqa: BLE001
            print(f"  EXCEPTION on {ln!r}: {exc}")
            continue
        print(f"  {len(out)} row(s) from {ln!r} -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/debug_handler_against_real_text.py <handler_id> <pdf_path>")
        sys.exit(1)
    main(sys.argv[1], Path(sys.argv[2]))
