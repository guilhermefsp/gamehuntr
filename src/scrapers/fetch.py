"""Shared tiered fetch helper for HTML scrapers.

Tier 1 is a plain HTTP request impersonating a real browser's TLS/JA3
fingerprint (via curl_cffi) — cheap and fast, and often enough to get past
naive bot detection that blocks bare httpx requests. Tier 2 is a full
Playwright-driven stealth browser (fingerprint spoofing, Cloudflare
challenge solving) for sites that block tier 1 outright.

This module only handles the fetch layer. It does not decide "the page
loaded but had zero matching items" — that's DOM-shape-specific and belongs
to each scraper, which should parse tier 1's result first and call
fetch(url, force_stealth=True) for one retry if it got nothing.
"""

import logging
from dataclasses import dataclass

from scrapling.engines.toolbelt.custom import Response
from scrapling.fetchers import AsyncFetcher, StealthyFetcher

from src.scrapers import adaptive  # noqa: F401 - side effect: configures shared adaptive storage

logger = logging.getLogger(__name__)

BLOCK_STATUS_CODES = {403, 429, 503}


@dataclass
class FetchResult:
    page: Response
    tier: str  # "http" | "stealth"


async def fetch(
    url: str,
    *,
    force_stealth: bool = False,
    headers: dict | None = None,
    timeout: int = 20,
) -> FetchResult | None:
    """Tier-1 impersonated HTTP fetch, falling back to tier-2 stealth browser
    fetch when tier-1 is blocked, errors, or force_stealth is set.
    Returns None if both applicable tiers fail.
    """
    if not force_stealth:
        try:
            page = await AsyncFetcher.get(
                url,
                impersonate="chrome",
                stealthy_headers=True,
                headers=headers,
                timeout=timeout,
                retries=1,
            )
            if page.status not in BLOCK_STATUS_CODES:
                return FetchResult(page=page, tier="http")
            logger.warning("Tier-1 fetch blocked (status %s) for %s, falling back to stealth", page.status, url)
        except Exception as e:
            logger.warning("Tier-1 fetch failed for %s: %s, falling back to stealth", url, e)

    try:
        page = await StealthyFetcher.async_fetch(
            url,
            headless=True,
            network_idle=True,
            solve_cloudflare=True,
            timeout=timeout * 1000,
        )
        return FetchResult(page=page, tier="stealth")
    except Exception as e:
        logger.error("Tier-2 stealth fetch failed for %s: %s", url, e)
        return None
