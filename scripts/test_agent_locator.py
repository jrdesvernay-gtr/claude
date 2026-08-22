"""Test the real, agent-primary section locator
(pipeline.orchestrator.locate_franchisee_list_section) against the
downloaded WI PDFs. Requires ANTHROPIC_API_KEY (loaded from .env if
python-dotenv is installed).

Usage:
    python3 scripts/test_agent_locator.py                     # all PDFs in data/downloads/
    python3 scripts/test_agent_locator.py data/downloads/wi_Wendys.pdf
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

from pipeline.orchestrator import locate_franchisee_list_section  # noqa: E402

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "downloads"
PREVIEW_LINES = 30


def extract_full_text(pdf_path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def test_one(pdf_path: Path) -> None:
    print(f"\n{'=' * 70}\n{pdf_path.name}\n{'=' * 70}")

    full_text = extract_full_text(pdf_path)

    try:
        section, source, confidence = locate_franchisee_list_section(full_text)
    except Exception as exc:  # noqa: BLE001 - report every failure mode
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        return

    lines = section.splitlines()
    print(f"  Agent picked: {source} (confidence={confidence})")
    print(f"  Section: {len(lines)} lines, {len(section)} chars")
    print(f"\n  --- First {PREVIEW_LINES} lines ---")
    for line in lines[:PREVIEW_LINES]:
        print(f"  {line!r}")


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or sorted(DOWNLOAD_DIR.glob("*.pdf"))
    if not paths:
        print(f"No PDFs found in {DOWNLOAD_DIR} and none passed as args.")
        sys.exit(1)
    for p in paths:
        test_one(p)
