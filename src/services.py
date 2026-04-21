from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models import Game, Listing, PriceHistory, Store
from src.scrapers import amazon, ludopedia

AMAZON_STORE_NAME = "Amazon BR"


async def get_price(query: str) -> dict | None:
    """Main entry point: resolve game, fetch Amazon price, persist, return display dict."""
    game = await _resolve_game(query)
    if not game:
        return None

    if not game.asin:
        results = amazon.search_items(query, count=1)
        if not results:
            return {"title": game.title, "ludopedia_id": game.ludopedia_id, "price_brl": None, "in_stock": False, "url": None, "lowest_ever": None}
        top = results[0]
        await _save_asin(game.ludopedia_id, top["asin"])
        game.asin = top["asin"]

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
    }


async def get_amazon_alternatives(query: str) -> list[dict]:
    return amazon.search_items(query, count=5)


async def update_asin(ludopedia_id: int, asin: str) -> None:
    await _save_asin(ludopedia_id, asin)


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
    game = Game(
        ludopedia_id=raw["id_jogo"],
        title=raw["nm_jogo"],
        thumbnail=raw.get("thumb"),
        qt_quer=raw.get("qt_quer"),
    )
    async with AsyncSessionLocal() as session:
        session.add(game)
        await session.commit()
        await session.refresh(game)
    return game


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
                Listing.store_id == store.id
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
