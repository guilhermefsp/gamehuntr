import logging
import re

import httpx
from bs4 import BeautifulSoup

from src.config import settings

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}


def _parse_price(text: str) -> float | None:
    cleaned = re.sub(r"[^\d,]", "", text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def scrape_wishlist(url: str) -> list[dict]:
    """
    Scrape a public Amazon wishlist and return items as dicts.
    Returns [] if Amazon blocks the request or page structure changes.

    Each item: {"asin": str, "title": str|None, "price_brl": float|None, "url": str}

    To swap in a Playwright implementation (more reliable but heavier),
    replace the httpx fetch below while keeping the same return shape.
    """
    try:
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
    except Exception as e:
        logger.warning("Wishlist fetch failed: %s", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = []

    for li in soup.find_all("li", attrs={"data-id": True}):
        asin = li.get("data-asin")
        if not asin:
            continue

        title_el = li.find(id=re.compile(r"^itemName_"))
        title = title_el.get_text(strip=True) if title_el else None

        price = None
        price_el = li.find("span", class_="a-offscreen")
        if price_el:
            price = _parse_price(price_el.get_text(strip=True))

        link_el = li.find("a", id=re.compile(r"^itemName_"))
        if link_el and link_el.get("href", "").startswith("/"):
            product_url = f"https://www.amazon.com.br{link_el['href']}"
        else:
            product_url = f"https://www.amazon.com.br/dp/{asin}"
        if settings.amazon_partner_tag:
            product_url += f"?tag={settings.amazon_partner_tag}"

        items.append({"asin": asin, "title": title, "price_brl": price, "url": product_url})

    if not items:
        logger.warning(
            "Wishlist scrape returned 0 items — Amazon may be blocking the request "
            "or the page structure changed. Consider switching to a Playwright-based scraper."
        )

    return items
