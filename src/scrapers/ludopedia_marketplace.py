import re

import httpx
from bs4 import BeautifulSoup

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

    async with httpx.AsyncClient(timeout=20, headers=_HEADERS, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        return []

    listings = []
    title_lower = game_title.strip().lower()

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        product_name = cells[0].get_text(strip=True)
        city = cells[1].get_text(strip=True)
        condition = cells[2].get_text(strip=True)

        notes_span = cells[3].find("span", class_="anuncio-sub-titulo")
        notes = notes_span.get_text(strip=True) if notes_span else ""

        price_el = cells[4].find("span", class_="proximo_lance")
        price_brl = _parse_price(price_el.get_text(strip=True)) if price_el else None

        link_tag = cells[5].find("a")
        listing_url = link_tag["href"] if link_tag and link_tag.get("href") else ""

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
