from paapi5_python_sdk.api.default_api import DefaultApi
from paapi5_python_sdk.models.partner_type import PartnerType
from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
from paapi5_python_sdk.models.search_items_resource import SearchItemsResource

from src.config import settings

_RESOURCES = [
    SearchItemsResource.ITEMINFO_TITLE,
    SearchItemsResource.OFFERS_LISTINGS_PRICE,
    SearchItemsResource.OFFERS_LISTINGS_AVAILABILITY_MESSAGE,
    SearchItemsResource.IMAGES_PRIMARY_MEDIUM,
]


def _client() -> DefaultApi:
    return DefaultApi(
        access_key=settings.amazon_access_key,
        secret_key=settings.amazon_secret_key,
        host="webservices.amazon.com.br",
        region="us-east-1",
    )


def search_items(query: str, count: int = 5) -> list[dict]:
    request = SearchItemsRequest(
        partner_tag=settings.amazon_partner_tag,
        partner_type=PartnerType.ASSOCIATES,
        keywords=query,
        search_index="Toys",
        item_count=count,
        resources=_RESOURCES,
    )
    response = _client().search_items(request)
    if not response.search_result or not response.search_result.items:
        return []
    return [_parse_item(item) for item in response.search_result.items]


def _parse_item(item) -> dict:
    price = None
    in_stock = False
    url = f"https://www.amazon.com.br/dp/{item.asin}?tag={settings.amazon_partner_tag}"

    if item.offers and item.offers.listings:
        listing = item.offers.listings[0]
        if listing.price:
            price = listing.price.amount
        if listing.availability:
            in_stock = "Em estoque" in (listing.availability.message or "")

    return {
        "asin": item.asin,
        "title": item.item_info.title.display_value if item.item_info and item.item_info.title else None,
        "price_brl": price,
        "in_stock": in_stock,
        "url": url,
    }
