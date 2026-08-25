"""MN Commerce Item 20 exhibit — pipe-delimited rows, as commonly produced
when MN's document-level PDFs are extracted with a text layer:

    Franchisee Name[; Guarantor; Guarantor]|Address|City|ST|Zip|Phone|Status
"""
from __future__ import annotations

import re

from pipeline.models import ItemRow
from pipeline.parsing.handler_registry import Handler, registry

ROW_RE = re.compile(
    r"^(?P<franchisee>[^|]+)\|"
    r"(?P<address>[^|]*)\|"
    r"(?P<city>[^|]*)\|"
    r"(?P<state>[A-Z]{2})\|"
    r"(?P<zip>\d{5}(?:-\d{4})?)\|"
    r"(?P<phone>[\d().\-\s]*)\|?"
    r"(?P<status>[^|]*)$"
)


def parse(item_20_text: str) -> list[ItemRow]:
    rows: list[ItemRow] = []
    for line in item_20_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        rows.append(
            ItemRow(
                franchisee_raw=m.group("franchisee").strip(),
                address=m.group("address").strip() or None,
                city=m.group("city").strip() or None,
                state=m.group("state"),
                zip=m.group("zip"),
                phone=m.group("phone").strip() or None,
                status=m.group("status").strip() or None,
            )
        )
    return rows


def matches(fingerprint: dict) -> bool:
    return fingerprint.get("delimiter") == "pipe" and fingerprint.get("data_line_count", 0) > 0


registry.register(
    Handler(
        id="mn_pipe_delim_v1",
        state="MN",
        description="MN Commerce pipe-delimited Item 20 exhibit.",
        fn=parse,
        matches=matches,
    )
)
