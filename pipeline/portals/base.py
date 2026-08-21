"""Shared HTTP helpers: retry/backoff (for VA/CA "unknown" portals per the
scope doc, and generally good hygiene against any state portal), and the
common search/download interface each state module implements.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import requests

DEFAULT_BACKOFF = (2, 4, 8, 16)  # seconds


@dataclass
class SearchHit:
    franchisor_name: str
    filing_url: str
    filing_year: int | None = None
    document_type: str = "unknown"  # MN is document-level; caller must filter to final/clean


def request_with_backoff(
    method: str, url: str, backoff: tuple[float, ...] = DEFAULT_BACKOFF, **kwargs
) -> requests.Response:
    """Retry on network errors / 5xx. Used for VA/CA, which returned 503 on
    last check (2026-08-21) — do not trust a single clean read on those
    states before promoting them into automated scope; several consecutive
    clean retries across separate runs is the bar.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate((0,) + backoff):
        if delay:
            time.sleep(delay)
        try:
            resp = requests.request(method, url, timeout=30, **kwargs)
            if resp.status_code < 500:
                return resp
            last_exc = RuntimeError(f"{url} -> HTTP {resp.status_code}")
        except requests.RequestException as exc:
            last_exc = exc
    assert last_exc is not None
    raise last_exc


class PortalClient(Protocol):
    def search(self, franchisor_name: str) -> list[SearchHit]: ...
    def download(self, hit: SearchHit, dest_path: str) -> str: ...
