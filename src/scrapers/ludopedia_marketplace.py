import re

from src.scrapers import fetch as fetch_module

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def _parse_price(text: str) -> float | None:
    cleaned = re.sub(r"[^\d,]", "", text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def scrape_listings(game_link: str, game_title: str) -> list[dict]:
    """
    Scrapes the ?v=anuncios page for a game and returns all listings.
    game_link: e.g. "https://ludopedia.com.br/jogo/terra-mystica"
    """
    url = f"{game_link.rstrip('/')}?v=anuncios"

    # Ludopedia doesn't block tier-1 requests today, so no stealth retry-on-empty
    # here (unlike amazon_wishlist.py) — a stealth retry would just add latency
    # with no benefit for a site that isn't blocking us.
    result = await fetch_module.fetch(url, headers=_HEADERS)
    if not result:
        raise RuntimeError(f"Failed to fetch marketplace page for {game_title}")

    page = result.page
    # Adaptive relocation is only applied to this outer row selector: it appears once
    # per page, so its (url, identifier) fingerprint is unambiguous. The nested per-row
    # lookups below deliberately use plain (non-adaptive) css() — every row would share
    # the same identifier string, so a saved fingerprint from one row could get
    # "relocated" onto an unrelated sibling row and silently return wrong data instead
    # of a clean empty match. See amazon_wishlist.py for a concrete case of this.
    rows = page.css("tbody tr", identifier="ludopedia_listing_row", adaptive=True, auto_save=True)
    if not rows:
        return []

    listings = []
    title_lower = game_title.strip().lower()

    for row in rows:
        cells = row.css("td")
        if len(cells) < 6:
            continue

        product_name = cells[0].get_all_text(separator="", strip=True)
        city = cells[1].get_all_text(separator="", strip=True)
        condition = cells[2].get_all_text(separator="", strip=True)

        notes_els = cells[3].css("span.anuncio-sub-titulo")
        notes = notes_els[0].get_all_text(separator="", strip=True) if notes_els else ""

        price_els = cells[4].css("span.proximo_lance")
        price_brl = _parse_price(price_els[0].get_all_text(separator="", strip=True)) if price_els else None

        link_els = cells[5].css("a")
        listing_url = link_els[0].attrib.get("href", "") if link_els else ""

        listings.append({
            "product_name": product_name,
            "city": city,
            "condition": condition,
            "notes": notes,
            "price_brl": price_brl,
            "listing_url": listing_url,
            "is_game_match": product_name.strip().lower() == title_lower,
        })

    return listings
