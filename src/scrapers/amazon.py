from amazon_paapi import AmazonApi

from src.config import settings


def _client() -> AmazonApi:
    return AmazonApi(
        key=settings.amazon_access_key,
        secret=settings.amazon_secret_key,
        tag=settings.amazon_partner_tag,
        country="BR",
    )


def search_items(query: str, count: int = 5) -> list[dict]:
    try:
        results = _client().search_items(keywords=query, item_count=count)
    except Exception:
        return []

    if not results or not results.items:
        return []

    return [_parse_item(item) for item in results.items]


def _parse_item(item) -> dict:
    price = None
    in_stock = False
    url = getattr(item, "detail_page_url", None) or f"https://www.amazon.com.br/dp/{item.asin}?tag={settings.amazon_partner_tag}"

    try:
        listing = item.offers.listings[0]
        price = listing.price.amount
        in_stock = "estoque" in (listing.availability.message or "").lower()
    except (AttributeError, IndexError, TypeError):
        pass

    title = None
    try:
        title = item.item_info.title.display_value
    except AttributeError:
        pass

    return {
        "asin": item.asin,
        "title": title,
        "price_brl": price,
        "in_stock": in_stock,
        "url": url,
    }
