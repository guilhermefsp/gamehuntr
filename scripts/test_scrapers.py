"""
Verifies the Scrapling-based scraper rewrites:
  1. ludopedia_marketplace.scrape_listings() still returns the original dict shape.
  2. amazon_wishlist.scrape_wishlist() returns items (tier-1 or tier-2 fallback — check
     the INFO logs to see which tier succeeded).

Usage: uv run python scripts/test_scrapers.py
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from src.config import settings
from src.scrapers import amazon_wishlist, ludopedia_marketplace

EXPECTED_LISTING_KEYS = {
    "product_name", "city", "condition", "notes", "price_brl", "listing_url", "is_game_match",
}
EXPECTED_WISHLIST_KEYS = {"asin", "title", "price_brl", "url"}


async def test_ludopedia_marketplace() -> None:
    print("--- ludopedia_marketplace.scrape_listings ---")
    listings = await ludopedia_marketplace.scrape_listings(
        "https://ludopedia.com.br/jogo/terra-mystica", "Terra Mystica"
    )
    print(f"Got {len(listings)} listings")
    assert listings, "expected at least one listing"
    assert set(listings[0].keys()) == EXPECTED_LISTING_KEYS, f"shape drift: {listings[0].keys()}"
    print("Shape OK:", listings[0])


async def test_amazon_wishlist() -> None:
    print("\n--- amazon_wishlist.scrape_wishlist ---")
    if not settings.wishlist_url:
        print("WISHLIST_URL not set, skipping.")
        return
    items = await amazon_wishlist.scrape_wishlist(settings.wishlist_url)
    print(f"Got {len(items)} items")
    if items:
        assert set(items[0].keys()) == EXPECTED_WISHLIST_KEYS, f"shape drift: {items[0].keys()}"
        print("Shape OK:", items[0])
    else:
        print("0 items on both tiers — see WARNING log above for cause.")


async def main() -> None:
    await test_ludopedia_marketplace()
    await test_amazon_wishlist()


if __name__ == "__main__":
    asyncio.run(main())
