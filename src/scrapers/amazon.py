import logging

from amazon_creatorsapi import AmazonCreatorsApi, Country
from amazon_creatorsapi.errors import ItemsNotFoundError

from src.config import settings

logger = logging.getLogger(__name__)


def is_available() -> bool:
    return settings.amazon_access_key not in ("", "unset") and \
           settings.amazon_secret_key not in ("", "unset")


def _client() -> AmazonCreatorsApi:
    return AmazonCreatorsApi(
        credential_id=settings.amazon_access_key,
        credential_secret=settings.amazon_secret_key,
        version=settings.amazon_credential_version,
        tag=settings.amazon_partner_tag,
        country=Country.BR,
    )


def search_items(query: str, count: int = 5) -> list[dict]:
    try:
        result = _client().search_items(keywords=query, item_count=count)
    except ItemsNotFoundError:
        return []
    except Exception as e:
        logger.warning("Creators API search_items failed for %r: %s: %s", query, type(e).__name__, e)
        return []

    if not result or not result.items:
        return []

    return [_parse_item(item) for item in result.items]


def _parse_item(item) -> dict:
    price = None
    in_stock = False
    url = getattr(item, "detail_page_url", None) or \
          f"https://www.amazon.com.br/dp/{item.asin}?tag={settings.amazon_partner_tag}"

    try:
        listing = item.offers_v2.listings[0]
        price = listing.price.money.amount
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
