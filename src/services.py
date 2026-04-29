import logging

from sqlalchemy import delete, select

from src.config import settings
from src.database import AsyncSessionLocal
from src.models import Game, Listing, LudopediaListing, PriceHistory, Store
from src.scrapers import amazon, ludopedia
from src.scrapers import ludopedia_marketplace

logger = logging.getLogger(__name__)

AMAZON_STORE_NAME = "Amazon BR"


async def get_price(query: str) -> dict | None:
    """Main entry point: resolve game, fetch C2C + Amazon prices, persist, return display dict."""
    game = await _resolve_game(query)
    if not game:
        return None

    # Backfill ludopedia_link if missing or stored as a broken relative path
    if not game.ludopedia_link or not game.ludopedia_link.startswith("https://"):
        game = await _backfill_link(game)

    c2c = await _fetch_c2c_data(game)

    if not game.asin:
        results = amazon.search_items(query, count=1)
        if results:
            await _save_asin(game.ludopedia_id, results[0]["asin"])
            game.asin = results[0]["asin"]

    amazon_result = amazon.search_items(game.title, count=1)
    item = amazon_result[0] if amazon_result else None

    if item:
        await _record_price(game, item)

    lowest = await _get_lowest_ever(game.ludopedia_id)

    return {
        "title": game.title,
        "ludopedia_id": game.ludopedia_id,
        "price_brl": item["price_brl"] if item else None,
        "in_stock": item["in_stock"] if item else False,
        "url": item["url"] if item else None,
        "lowest_ever": lowest,
        **c2c,
    }


async def get_amazon_alternatives(query: str) -> list[dict]:
    return amazon.search_items(query, count=5)


async def update_asin(ludopedia_id: int, asin: str) -> None:
    await _save_asin(ludopedia_id, asin)


async def sync_wishlist_prices() -> dict:
    """Scrape the Amazon wishlist, match games to Ludopedia, store prices. No-op when disabled."""
    if not settings.wishlist_enabled or not settings.wishlist_url:
        return {"skipped": True}

    from src.scrapers import amazon_wishlist

    items = await amazon_wishlist.scrape_wishlist(settings.wishlist_url)
    synced = 0
    failed = 0

    for item in items:
        try:
            game = await _get_game_by_asin(item["asin"])
            if not game and item["title"]:
                game = await _resolve_game(item["title"])
                if game and not game.asin:
                    await _save_asin(game.ludopedia_id, item["asin"])
                    game.asin = item["asin"]

            if game and item["price_brl"] is not None:
                await _record_price(game, {
                    "price_brl": item["price_brl"],
                    "in_stock": True,
                    "url": item["url"],
                })
                synced += 1
        except Exception as e:
            logger.warning("Wishlist sync failed for ASIN %s: %s", item.get("asin"), e)
            failed += 1

    logger.info("Wishlist sync complete: %d synced, %d failed, %d total", synced, failed, len(items))
    return {"synced": synced, "failed": failed, "total": len(items)}


async def _fetch_c2c_data(game: Game) -> dict:
    if not game.ludopedia_link:
        return {"c2c_novo_min": None, "c2c_novo_count": 0, "c2c_used_min": None, "c2c_used_count": 0, "c2c_url": None}

    c2c_url = f"{game.ludopedia_link}?v=anuncios"

    try:
        listings = await ludopedia_marketplace.scrape_listings(game.ludopedia_link, game.title)
    except Exception as e:
        logger.warning("Marketplace scrape failed for %s: %s", game.title, e)
        return {"c2c_novo_min": None, "c2c_novo_count": 0, "c2c_used_min": None, "c2c_used_count": 0, "c2c_url": c2c_url}

    if listings:
        await _save_ludopedia_listings(game.ludopedia_id, listings)

    matched = [l for l in listings if l["is_game_match"] and l["price_brl"] is not None]
    novo_prices = [l["price_brl"] for l in matched if l["condition"] == "Novo"]
    used_prices = [l["price_brl"] for l in matched if l["condition"] == "Usado"]

    return {
        "c2c_novo_min": min(novo_prices) if novo_prices else None,
        "c2c_novo_count": len(novo_prices),
        "c2c_used_min": min(used_prices) if used_prices else None,
        "c2c_used_count": len(used_prices),
        "c2c_url": c2c_url,
    }


async def _save_ludopedia_listings(game_id: int, listings: list[dict]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(LudopediaListing).where(LudopediaListing.game_id == game_id)
        )
        for l in listings:
            session.add(LudopediaListing(
                game_id=game_id,
                listing_url=l["listing_url"],
                product_name=l["product_name"],
                city=l["city"],
                price_brl=l["price_brl"],
                condition=l["condition"],
                notes=l["notes"],
                is_game_match=l["is_game_match"],
            ))
        await session.commit()


async def _get_game_by_asin(asin: str) -> Game | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.asin == asin))
        return result.scalar_one_or_none()


async def _resolve_game(query: str) -> Game | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Game).where(Game.title.ilike(f"%{query}%")).limit(1)
        )
        game = result.scalar_one_or_none()
        if game:
            return game

    results = await ludopedia.search_games(query, rows=1)
    if not results:
        return None

    raw = results[0]
    link = _normalize_link(raw.get("link", ""))

    # Fallback: search endpoint may not include link — fetch detail
    if not link:
        try:
            detail = await ludopedia.get_game(raw["id_jogo"])
            link = _normalize_link(detail.get("link", ""))
        except Exception:
            link = None

    game = Game(
        ludopedia_id=raw["id_jogo"],
        title=raw["nm_jogo"],
        thumbnail=raw.get("thumb"),
        qt_quer=raw.get("qt_quer"),
        ludopedia_link=link or None,
    )
    async with AsyncSessionLocal() as session:
        session.add(game)
        await session.commit()
        await session.refresh(game)
    return game


async def _backfill_link(game: Game) -> Game:
    try:
        detail = await ludopedia.get_game(game.ludopedia_id)
        link = _normalize_link(detail.get("link", ""))
        if link:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Game).where(Game.ludopedia_id == game.ludopedia_id)
                )
                g = result.scalar_one_or_none()
                if g:
                    g.ludopedia_link = link
                    await session.commit()
                    await session.refresh(g)
                    return g
    except Exception as e:
        logger.warning("Could not backfill link for game %s: %s", game.ludopedia_id, e)
    return game


def _normalize_link(link: str) -> str:
    if not link:
        return ""
    if link.startswith("https://") or link.startswith("http://"):
        pass
    elif link.startswith("https:"):
        link = "https://" + link[6:]
    elif link.startswith("/"):
        link = "https://ludopedia.com.br" + link
    else:
        link = "https://ludopedia.com.br/" + link
    return link.rstrip("/")


async def _save_asin(ludopedia_id: int, asin: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.ludopedia_id == ludopedia_id))
        game = result.scalar_one_or_none()
        if game:
            game.asin = asin
            await session.commit()


async def _record_price(game: Game, item: dict) -> None:
    async with AsyncSessionLocal() as session:
        store = await _get_or_create_amazon_store(session)
        result = await session.execute(
            select(Listing).where(
                Listing.game_id == game.ludopedia_id,
                Listing.store_id == store.id,
            )
        )
        listing = result.scalar_one_or_none()

        if not listing:
            listing = Listing(
                game_id=game.ludopedia_id,
                store_id=store.id,
                url=item["url"],
                price_brl=item["price_brl"],
                in_stock=item["in_stock"],
            )
            session.add(listing)
            await session.flush()
        else:
            listing.url = item["url"]
            listing.price_brl = item["price_brl"]
            listing.in_stock = item["in_stock"]

        session.add(PriceHistory(
            listing_id=listing.id,
            price_brl=item["price_brl"],
            in_stock=item["in_stock"],
        ))
        await session.commit()


async def _get_or_create_amazon_store(session) -> Store:
    result = await session.execute(select(Store).where(Store.name == AMAZON_STORE_NAME))
    store = result.scalar_one_or_none()
    if not store:
        store = Store(name=AMAZON_STORE_NAME, base_url="https://www.amazon.com.br")
        session.add(store)
        await session.flush()
    return store


async def _get_lowest_ever(ludopedia_id: int) -> float | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PriceHistory.price_brl)
            .join(Listing, PriceHistory.listing_id == Listing.id)
            .where(Listing.game_id == ludopedia_id, PriceHistory.price_brl.isnot(None))
            .order_by(PriceHistory.price_brl.asc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return float(row) if row else None
