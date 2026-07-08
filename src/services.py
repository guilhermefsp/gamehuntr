import logging
import re
from datetime import datetime

from sqlalchemy import delete, select, update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.database import AsyncSessionLocal
from src.models import Game, Listing, LudopediaListing, PriceHistory, Store, User
from src.scrapers import amazon, bgg, ludopedia
from src.scrapers import ludopedia_marketplace

logger = logging.getLogger(__name__)

AMAZON_STORE_NAME = "Amazon BR"
LUDOPEDIA_NOVO_STORE_NAME = "Ludopedia C2C Novo"
LUDOPEDIA_USADO_STORE_NAME = "Ludopedia C2C Usado"


LUDOPEDIA_JOGO_URL_RE = re.compile(r"https?://(?:www\.)?ludopedia\.com\.br/jogo/([\w-]+)", re.IGNORECASE)
BGG_URL_RE = re.compile(r"https?://(?:www\.)?boardgamegeek\.com/boardgame(?:expansion)?/(\d+)", re.IGNORECASE)


def _is_url(query: str) -> bool:
    return query.lower().startswith(("http://", "https://"))


async def get_price(query: str) -> dict | None:
    """Main entry point: resolve game (by name, Ludopedia /jogo/ URL, or BGG URL),
    fetch C2C + Amazon prices, persist, return display dict."""
    query = query.strip()
    game = await _resolve_input(query)
    if not game:
        return None
    # A raw URL is useless as an Amazon keyword search — use the resolved title
    amazon_query = game.title if _is_url(query) else query
    return await _build_price_result(game, amazon_query)


async def get_price_by_id(ludopedia_id: int) -> dict | None:
    """Price lookup for a known Ludopedia id — used when the user picks a game
    from the disambiguation buttons."""
    game = await _get_or_fetch_game_by_id(ludopedia_id)
    if not game:
        return None
    await _increment_search_count(game.ludopedia_id)
    return await _build_price_result(game, game.title)


async def _build_price_result(game: Game, amazon_query: str) -> dict:
    # Backfill ludopedia_link if missing or stored as a broken relative path
    if not game.ludopedia_link or not game.ludopedia_link.startswith("https://"):
        game = await backfill_link(game)

    game = await enrich_bgg(game)

    c2c = await fetch_c2c_data(game)
    item = await resolve_amazon_price(game, amazon_query)
    lowest = await _get_lowest_ever(game.ludopedia_id)

    return {
        "title": game.title,
        "ludopedia_id": game.ludopedia_id,
        "thumbnail": game.thumbnail,
        "bgg_rating": float(game.bgg_rating) if game.bgg_rating is not None else None,
        "bgg_weight": float(game.bgg_weight) if game.bgg_weight is not None else None,
        "price_brl": item["price_brl"] if item else None,
        "in_stock": item["in_stock"] if item else False,
        "url": item["url"] if item else None,
        "lowest_ever": lowest,
        **c2c,
    }


async def _resolve_input(query: str) -> Game | None:
    m = LUDOPEDIA_JOGO_URL_RE.search(query)
    if m:
        return await _resolve_ludopedia_slug(m.group(1))
    m = BGG_URL_RE.search(query)
    if m:
        return await _resolve_bgg_id(int(m.group(1)))
    return await _resolve_game(query)


async def search_alternatives(query: str, exclude_id: int | None = None, limit: int = 4) -> list[dict]:
    """Top Ludopedia search results for the disambiguation flow ("Jogo errado?")."""
    results = await ludopedia.search_games(query, rows=5)
    return [
        {
            "ludopedia_id": r["id_jogo"],
            "title": r["nm_jogo"],
            "year": r.get("ano_publicacao"),
            "thumbnail": r.get("thumb"),
        }
        for r in results if r["id_jogo"] != exclude_id
    ][:limit]


async def record_user(tg_user) -> None:
    """Upsert the Telegram user on every interaction (FK target for the Phase 4
    watchlist). Never raises — user bookkeeping must not break a price lookup."""
    if tg_user is None:
        return
    try:
        async with AsyncSessionLocal() as session:
            stmt = pg_insert(User).values(
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            ).on_conflict_do_update(
                index_elements=["telegram_user_id"],
                set_={"username": tg_user.username, "first_name": tg_user.first_name},
            )
            await session.execute(stmt)
            await session.commit()
    except Exception as e:
        logger.warning("record_user failed for %s: %s", getattr(tg_user, "id", None), e)


_TITLE_STOPWORDS = {"a", "an", "the", "de", "da", "do", "e", "and", "of", "is",
                    "edition", "edicao", "edição", "2nd", "second"}


def _title_tokens(title: str) -> set[str]:
    return {t for t in re.sub(r"[^a-z0-9]+", " ", title.lower()).split() if t not in _TITLE_STOPWORDS}


def _is_plausible_amazon_match(game_title: str, item_title: str | None, threshold: float = 0.6) -> bool:
    """Guards against Amazon's keyword search returning an unrelated/near-miss product
    (e.g. searching "Caylus 1303" returning plain "Caylus") as the top hit. Without this,
    resolve_amazon_price would tag the wrong game with someone else's ASIN, which then
    fails loudly at save time (unique constraint) — or worse, silently shows the wrong
    game's price when the constraint doesn't happen to collide."""
    if not item_title:
        return True
    game_tokens = _title_tokens(game_title)
    if not game_tokens:
        return True
    item_tokens = _title_tokens(item_title)
    return len(game_tokens & item_tokens) / len(game_tokens) >= threshold


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
            if results and _is_plausible_amazon_match(game.title, results[0].get("title")):
                if await _save_asin(game.ludopedia_id, results[0]["asin"]):
                    game.asin = results[0]["asin"]
        amazon_result = amazon.search_items(game.title, count=1)
        item = amazon_result[0] if amazon_result else None
        if item:
            await _record_price(game, item)

    # 2. Stored DB price fallback (from last PA API or wishlist cron run)
    if not item:
        item = await _get_stored_amazon_price(game)

    # 3. Live wishlist scrape fallback (only when the Creators API isn't configured;
    # matches by ASIN or title)
    if not item and not amazon.is_available() and settings.wishlist_url:
        item = await _fetch_wishlist_price(game)

    return item


async def get_amazon_alternatives(query: str) -> list[dict]:
    return amazon.search_items(query, count=5)


async def update_asin(ludopedia_id: int, asin: str) -> None:
    await _save_asin(ludopedia_id, asin)


async def sync_wishlist_prices() -> dict:
    """Scrape the Amazon wishlist, match games to Ludopedia, store prices. No-op once the
    Amazon Creators API is configured (wishlist is only the bridge until then)."""
    if amazon.is_available() or not settings.wishlist_url:
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
                    if await _save_asin(game.ludopedia_id, item["asin"]):
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
        await _increment_search_count(game.ludopedia_id)
        return game

    results = await ludopedia.search_games(query, rows=5)
    if not results:
        return None
    return await _get_or_create_game_from_search(results[0])


async def _resolve_ludopedia_slug(slug: str) -> Game | None:
    """Resolve a https://ludopedia.com.br/jogo/{slug} URL to a Game."""
    url = f"https://ludopedia.com.br/jogo/{slug}"
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.ludopedia_link == url))
        game = result.scalar_one_or_none()
    if game:
        await _increment_search_count(game.ludopedia_id)
        return game

    # The API has no by-slug endpoint: search on the de-hyphenated slug and
    # prefer the result whose link actually ends with the slug
    results = await ludopedia.search_games(slug.replace("-", " "), rows=5)
    if not results:
        return None
    suffix = f"/jogo/{slug}".lower()
    match = next(
        (r for r in results if _normalize_link(r.get("link", "")).lower().endswith(suffix)),
        results[0],
    )
    return await _get_or_create_game_from_search(match)


async def _resolve_bgg_id(bgg_id: int) -> Game | None:
    """Resolve a boardgamegeek.com/boardgame/{id} URL to a Game via the BGG title."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.bgg_id == bgg_id))
        game = result.scalar_one_or_none()
    if game:
        await _increment_search_count(game.ludopedia_id)
        return game

    details = await bgg.get_game_details(bgg_id)
    if not details or not details.get("title"):
        return None
    game = await _resolve_game(details["title"])
    if game and game.bgg_id is None:
        await _save_bgg_id(game.ludopedia_id, bgg_id)
        game.bgg_id = bgg_id
    return game


async def _get_or_create_game_from_search(raw: dict) -> Game:
    """Turn a Ludopedia API search row into a persisted Game, reusing an existing
    row when the id is already known (a game can be reached via many search terms)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.ludopedia_id == raw["id_jogo"]))
        game = result.scalar_one_or_none()
    if game:
        await _increment_search_count(game.ludopedia_id)
        return game

    link = _normalize_link(raw.get("link", ""))

    # Fallback: search endpoint may not include link — fetch detail
    if not link:
        try:
            detail = await ludopedia.get_game(raw["id_jogo"])
            link = _normalize_link(detail.get("link", ""))
        except Exception:
            link = ""

    game = Game(
        ludopedia_id=raw["id_jogo"],
        title=raw["nm_jogo"],
        thumbnail=raw.get("thumb"),
        qt_quer=raw.get("qt_quer"),
        ludopedia_link=link or None,
        search_count=1,
    )
    async with AsyncSessionLocal() as session:
        session.add(game)
        await session.commit()
        await session.refresh(game)
    return game


async def _get_or_fetch_game_by_id(ludopedia_id: int) -> Game | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.ludopedia_id == ludopedia_id))
        game = result.scalar_one_or_none()
    if game:
        return game

    try:
        detail = await ludopedia.get_game(ludopedia_id)
    except Exception as e:
        logger.warning("Could not fetch Ludopedia game %s: %s", ludopedia_id, e)
        return None

    game = Game(
        ludopedia_id=detail["id_jogo"],
        title=detail["nm_jogo"],
        thumbnail=detail.get("thumb"),
        qt_quer=detail.get("qt_quer"),
        ludopedia_link=_normalize_link(detail.get("link", "")) or None,
    )
    async with AsyncSessionLocal() as session:
        session.add(game)
        await session.commit()
        await session.refresh(game)
    return game


async def _increment_search_count(ludopedia_id: int) -> None:
    """Tracks lookup popularity — used post-launch to decide which games to add
    to the Amazon wishlist."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa_update(Game)
            .where(Game.ludopedia_id == ludopedia_id)
            .values(search_count=Game.search_count + 1)
        )
        await session.commit()


async def _save_bgg_id(ludopedia_id: int, bgg_id: int) -> bool:
    """Returns False (instead of raising) when another game already owns this bgg_id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.ludopedia_id == ludopedia_id))
        game = result.scalar_one_or_none()
        if not game:
            return False
        game.bgg_id = bgg_id
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning("bgg_id %s already belongs to another game; not assigning to ludopedia_id=%s", bgg_id, ludopedia_id)
            return False
        return True


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


async def _save_asin(ludopedia_id: int, asin: str) -> bool:
    """Returns False (instead of raising) when another game already owns this ASIN,
    so callers can skip the assignment without losing everything else they fetched."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.ludopedia_id == ludopedia_id))
        game = result.scalar_one_or_none()
        if not game:
            return False
        game.asin = asin
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning("ASIN %s already belongs to another game; not assigning to ludopedia_id=%s", asin, ludopedia_id)
            return False
        return True


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
                if await _save_asin(game.ludopedia_id, match["asin"]):
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
