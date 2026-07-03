import logging
from datetime import datetime

from sqlalchemy import delete, select

from src.config import settings
from src.database import AsyncSessionLocal
from src.models import Game, Listing, LudopediaListing, PriceHistory, Store
from src.scrapers import amazon, bgg, ludopedia
from src.scrapers import ludopedia_marketplace

logger = logging.getLogger(__name__)

AMAZON_STORE_NAME = "Amazon BR"
LUDOPEDIA_NOVO_STORE_NAME = "Ludopedia C2C Novo"
LUDOPEDIA_USADO_STORE_NAME = "Ludopedia C2C Usado"


async def get_price(query: str) -> dict | None:
    """Main entry point: resolve game, fetch C2C + Amazon prices, persist, return display dict."""
    game = await _resolve_game(query)
    if not game:
        return None

    # Backfill ludopedia_link if missing or stored as a broken relative path
    if not game.ludopedia_link or not game.ludopedia_link.startswith("https://"):
        game = await backfill_link(game)

    game = await enrich_bgg(game)

    c2c = await fetch_c2c_data(game)
    item = await resolve_amazon_price(game, query)
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


async def resolve_amazon_price(game: Game, query: str | None = None) -> dict | None:
    """3-tier Amazon price resolution: Creators API -> stored DB price -> wishlist
    scrape fallback. Shared by the interactive get_price() flow and the bulk
    price-export job."""
    query = query or game.title

    # 1. PA API (primary)
    item = None
    if amazon.is_available():
        if not game.asin:
            results = amazon.search_items(query, count=1)
            if results:
                await _save_asin(game.ludopedia_id, results[0]["asin"])
                game.asin = results[0]["asin"]
        amazon_result = amazon.search_items(game.title, count=1)
        item = amazon_result[0] if amazon_result else None
        if item:
            await _record_price(game, item)

    # 2. Stored DB price fallback (from last PA API or wishlist cron run)
    if not item:
        item = await _get_stored_amazon_price(game)

    # 3. Live wishlist scrape fallback (when enabled; matches by ASIN or title)
    if not item and settings.wishlist_enabled and settings.wishlist_url:
        item = await _fetch_wishlist_price(game)

    return item


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


async def fetch_c2c_data(game: Game) -> dict:
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
    novo_min = min(novo_prices) if novo_prices else None
    used_min = min(used_prices) if used_prices else None

    await _record_c2c_price(game, LUDOPEDIA_NOVO_STORE_NAME, novo_min, c2c_url)
    await _record_c2c_price(game, LUDOPEDIA_USADO_STORE_NAME, used_min, c2c_url)

    return {
        "c2c_novo_min": novo_min,
        "c2c_novo_count": len(novo_prices),
        "c2c_used_min": used_min,
        "c2c_used_count": len(used_prices),
        "c2c_url": c2c_url,
    }


async def _record_c2c_price(game: Game, store_name: str, price_brl: float | None, url: str | None) -> None:
    """Records a Ludopedia C2C min-price snapshot as PriceHistory, reusing the same
    Store/Listing/PriceHistory tables Amazon prices already use — this is what actually
    gives C2C prices a history, since LudopediaListing rows are fully replaced on
    every scrape and have no trend data of their own."""
    if price_brl is None:
        return
    await _record_price(
        game,
        {"price_brl": price_brl, "in_stock": True, "url": url or ""},
        store_name=store_name,
        store_base_url="https://ludopedia.com.br",
    )


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


async def backfill_link(game: Game) -> Game:
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


async def enrich_bgg(game: Game) -> Game:
    """Best-effort BGG metadata enrichment. Never raises; caches via bgg_synced_at
    so we don't re-query BGG (slow, rate-limited) on every single lookup."""
    if game.bgg_synced_at is not None or not settings.bgg_api_token:
        return game
    try:
        bgg_id = game.bgg_id or await bgg.search_game(game.title)
        details = await bgg.get_game_details(bgg_id) if bgg_id else None
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Game).where(Game.ludopedia_id == game.ludopedia_id))
            g = result.scalar_one_or_none()
            if g:
                g.bgg_id = bgg_id
                g.bgg_rating = details["rating"] if details else None
                g.bgg_weight = details["weight"] if details else None
                g.bgg_synced_at = datetime.utcnow()
                await session.commit()
                await session.refresh(g)
                return g
    except Exception as e:
        logger.warning("BGG enrichment failed for %s: %s", game.title, e)
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


async def _record_price(
    game: Game,
    item: dict,
    store_name: str = AMAZON_STORE_NAME,
    store_base_url: str = "https://www.amazon.com.br",
) -> None:
    async with AsyncSessionLocal() as session:
        store = await _get_or_create_store(session, store_name, store_base_url)
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


async def _get_stored_amazon_price(game: Game) -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Listing)
            .join(Store, Listing.store_id == Store.id)
            .where(Listing.game_id == game.ludopedia_id, Store.name == AMAZON_STORE_NAME)
        )
        listing = result.scalar_one_or_none()
        if listing:
            return {"price_brl": listing.price_brl, "in_stock": listing.in_stock, "url": listing.url}
    return None


async def _fetch_wishlist_price(game: Game) -> dict | None:
    from src.scrapers import amazon_wishlist
    try:
        items = await amazon_wishlist.scrape_wishlist(settings.wishlist_url)
        # Match by ASIN if known, otherwise fall back to case-insensitive title match
        match = None
        if game.asin:
            match = next((i for i in items if i["asin"] == game.asin), None)
        if not match:
            game_title_lower = game.title.lower()
            match = next((i for i in items if i.get("title") and game_title_lower in i["title"].lower()), None)
        if match:
            if not game.asin and match.get("asin"):
                await _save_asin(game.ludopedia_id, match["asin"])
                game.asin = match["asin"]
            result = {"price_brl": match["price_brl"], "in_stock": True, "url": match["url"]}
            await _record_price(game, result)
            return result
    except Exception as e:
        logger.warning("Wishlist fallback failed for %s: %s", game.title, e)
    return None


async def _get_or_create_store(session, name: str, base_url: str) -> Store:
    result = await session.execute(select(Store).where(Store.name == name))
    store = result.scalar_one_or_none()
    if not store:
        store = Store(name=name, base_url=base_url)
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
