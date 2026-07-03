"""Shared adaptive-selector storage configuration for HTML scrapers.

Scrapling fingerprints matched elements (tag, text, attrs, DOM path) and can
relocate them via similarity scoring if a site's markup changes later. All
scrapers share one SQLite fingerprint file/domain namespace so relocation
data accumulates instead of fragmenting per-module.
"""

from pathlib import Path

from scrapling.fetchers import AsyncFetcher, StealthyFetcher

ADAPTIVE_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "scrapling_adaptive.sqlite3"
ADAPTIVE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

STORAGE_ARGS = {"storage_file": str(ADAPTIVE_DB_PATH)}


def configure_adaptive_storage() -> None:
    """Point every fetcher tier at the shared fingerprint DB. Call once at import time."""
    AsyncFetcher.configure(adaptive=True, storage_args=STORAGE_ARGS)
    StealthyFetcher.configure(adaptive=True, storage_args=STORAGE_ARGS)


configure_adaptive_storage()
