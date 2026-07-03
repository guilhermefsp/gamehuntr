import logging
import re
import time

from src.config import settings
from src.scrapers import fetch as fetch_module

logger = logging.getLogger(__name__)

# Short-lived in-process cache: the bulk price-export job resolves many games against
# the same wishlist URL in one run, and without this each of those calls would trigger
# its own full page fetch (and possibly a stealth-browser retry) for identical content.
_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, list[dict]]] = {}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _parse_price(text: str) -> float | None:
    cleaned = re.sub(r"[^\d,]", "", text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_items(page) -> list[dict]:
    items = []
    # Adaptive relocation is only applied to this outer item selector: it appears once
    # per page, so its (url, identifier) fingerprint is unambiguous. The nested per-item
    # lookups below deliberately use plain (non-adaptive) css() — every item would share
    # the same identifier string, so a saved fingerprint from one item could get
    # "relocated" onto an unrelated sibling item and silently return wrong data (e.g. a
    # fabricated price) instead of a clean empty match when that item genuinely has none.
    rows = page.css("li[data-id]", identifier="amazon_wishlist_item", adaptive=True, auto_save=True)

    for li in rows:
        # Amazon no longer puts a data-asin attribute on the <li> (markup changed since
        # this scraper was first written) — the ASIN is only reliably available in the
        # item link's href (/dp/{ASIN}/...), so it's parsed from there instead.
        link_els = li.css("a[id^='itemName_']")
        href = link_els[0].attrib.get("href", "") if link_els else ""
        asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
        if not asin_match:
            continue
        asin = asin_match.group(1)

        title_els = li.css("[id^='itemName_']")
        title = title_els[0].get_all_text(separator="", strip=True) if title_els else None

        price = None
        price_els = li.css("span.a-offscreen")
        if price_els:
            price = _parse_price(price_els[0].get_all_text(separator="", strip=True))

        if href.startswith("/"):
            product_url = f"https://www.amazon.com.br{href}"
        else:
            product_url = f"https://www.amazon.com.br/dp/{asin}"
        if settings.amazon_partner_tag:
            separator = "&" if "?" in product_url else "?"
            product_url += f"{separator}tag={settings.amazon_partner_tag}"

        items.append({"asin": asin, "title": title, "price_brl": price, "url": product_url})

    return items


def _has_any_price(items: list[dict]) -> bool:
    return any(i["price_brl"] is not None for i in items)


async def scrape_wishlist(url: str) -> list[dict]:
    """
    Scrape a public Amazon wishlist and return items as dicts.
    Returns [] if Amazon blocks the request or page structure changes.

    Each item: {"asin": str, "title": str|None, "price_brl": float|None, "url": str}

    Tries a tier-1 impersonated HTTP fetch first (cheap); retries once via a tier-2
    stealth browser fetch if that yields zero items (Amazon blocked it or served an
    empty/challenge page) OR yields items with no price data at all — Amazon's
    wishlist page intermittently server-renders item cards without their price
    markup (observed directly: same URL, consecutive requests, 10/10 items but 0/10
    prices on one fetch and 10/10 on the next) even when not obviously blocked, and
    a real browser fetch reliably waits for that content to finish rendering.

    Results are cached in-process for a few minutes (see _CACHE_TTL_SECONDS) so that
    resolving many games against the same wishlist in one job run doesn't re-fetch it
    once per game.
    """
    cached = _cache.get(url)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    result = await fetch_module.fetch(url, headers=_HEADERS)
    items = _parse_items(result.page) if result else []

    if not items or not _has_any_price(items):
        logger.info("Tier-1 wishlist scrape got no usable price data, retrying with stealth browser")
        result = await fetch_module.fetch(url, headers=_HEADERS, force_stealth=True)
        stealth_items = _parse_items(result.page) if result else []
        if stealth_items:
            items = stealth_items

    if not items:
        logger.warning(
            "Wishlist scrape returned 0 items on both tiers — Amazon may be blocking the request "
            "or the page structure changed."
        )
    elif not _has_any_price(items):
        logger.warning("Wishlist scrape got items but no price data on either tier.")

    _cache[url] = (time.monotonic(), items)
    return items
