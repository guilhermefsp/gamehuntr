import asyncio
import logging

from sqlalchemy import select

from src import services
from src.database import AsyncSessionLocal
from src.models import Game
from src.scrapers import ludopedia_ranking

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 4
ROWS_PER_PAGE = 50


async def _get_searched_games() -> list[Game]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game))
        return list(result.scalars().all())


async def _ensure_top_ludopedia_games(limit: int) -> list[Game]:
    """Fetch Ludopedia's own top-N ranked games (source of truth for "which games to
    track" — every entry is guaranteed to be a real Ludopedia listing since it's read
    directly from Ludopedia's own catalog, unlike the earlier BGG-CSV-sourced approach
    which only matched 13.6% of games due to translated-title mismatches), creating new
    Game rows for any not already tracked. BGG metadata (rating/weight) is attached
    best-effort via services.enrich_bgg — a failed BGG match just means no rating,
    not an untracked game."""
    pages = (limit + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE
    ranking = (await ludopedia_ranking.get_ranking(pages=pages))[:limit]
    games = []
    failed = 0

    for entry in ranking:
        try:
            async with AsyncSessionLocal() as session:
                game = await session.get(Game, entry["ludopedia_id"])
                if not game:
                    game = Game(ludopedia_id=entry["ludopedia_id"], title=entry["title"])
                    session.add(game)
                    await session.commit()
                    await session.refresh(game)
            games.append(game)
        except Exception as e:
            # One bad entry must not take down the whole batch of ~1000 lookups
            # (this already happened once with a title containing an apostrophe).
            logger.warning("Could not track Ludopedia game %r (id %s): %s", entry["title"], entry["ludopedia_id"], e)
            failed += 1

    if failed:
        logger.info("Failed to track %d top-ranked Ludopedia games", failed)
    return games


async def _refresh_one(game: Game, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        try:
            if not game.ludopedia_link or not game.ludopedia_link.startswith("https://"):
                game = await services.backfill_link(game)
            game = await services.enrich_bgg(game)
            await services.fetch_c2c_data(game)
            await services.resolve_amazon_price(game)
        except Exception as e:
            logger.warning("Price refresh failed for %s: %s", game.title, e)


async def run_export(ludopedia_top_n: int = 1000, concurrency: int = DEFAULT_CONCURRENCY) -> dict:
    """Refresh prices for every previously-searched game plus Ludopedia's own top-N
    ranked games. Games that drop out of top-N on a later run are never removed —
    once tracked, always tracked, so price history stays continuous. Top-N is only
    used as today's seed for discovering new games to start tracking."""
    searched = await _get_searched_games()
    ludopedia_top = await _ensure_top_ludopedia_games(ludopedia_top_n)

    seen_ids = set()
    games = []
    for g in searched + ludopedia_top:
        if g.ludopedia_id not in seen_ids:
            seen_ids.add(g.ludopedia_id)
            games.append(g)

    semaphore = asyncio.Semaphore(concurrency)
    await asyncio.gather(*(_refresh_one(g, semaphore) for g in games))

    logger.info(
        "Price export complete: %d games refreshed (%d searched, %d ludopedia-top)",
        len(games), len(searched), len(ludopedia_top),
    )
    return {"games_refreshed": len(games), "searched": len(searched), "ludopedia_top": len(ludopedia_top)}
