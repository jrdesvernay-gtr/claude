"""WI DFI Item 20 exhibit — the format validated against the Wendy's WI
filing (5,943 outlet rows / 576 distinct franchisee entities). Rows are
tab-delimited when extracted with a text-layer PDF extractor:

    Franchisee Name[; Guarantor; Guarantor]\tAddress\tCity\tST\tZip\tPhone\tStatus
"""
from __future__ import annotations

import re

from pipeline.models import ItemRow
from pipeline.parsing.handler_registry import Handler, registry

ROW_RE = re.compile(
    r"^(?P<franchisee>[^\t]+)\t"
    r"(?P<address>[^\t]*)\t"
    r"(?P<city>[^\t]*)\t"
    r"(?P<state>[A-Z]{2})\t"
    r"(?P<zip>\d{5}(?:-\d{4})?)\t"
    r"(?P<phone>[\d().\-\s]*)\t?"
    r"(?P<status>[^\t]*)$"
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
    return fingerprint.get("delimiter") == "tab" and fingerprint.get("data_line_count", 0) > 0


registry.register(
    Handler(
        id="wi_standard_v1",
        state="WI",
        description="WI DFI tab-delimited Item 20 exhibit (validated against Wendy's WI filing).",
        fn=parse,
        matches=matches,
    )
)
