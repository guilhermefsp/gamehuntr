import asyncio
import logging

from sqlalchemy import select

from src import services
from src.database import AsyncSessionLocal
from src.models import Game
from src.scrapers import bgg_ranks, ludopedia

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 4


async def _get_searched_games() -> list[Game]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game))
        return list(result.scalars().all())


async def _get_game_by_bgg_id(bgg_id: int) -> Game | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game).where(Game.bgg_id == bgg_id))
        return result.scalar_one_or_none()


async def _ensure_top_bgg_games(limit: int) -> list[Game]:
    """Resolve BGG's top-N ranked games to Ludopedia entries, creating new Game rows
    for any not already tracked. Games with no Ludopedia listing are skipped (logged,
    not retried every run — they simply won't appear in the returned list)."""
    ranks = await bgg_ranks.get_top_ranked(limit)
    games = []
    skipped = 0

    for entry in ranks:
        try:
            game = await _get_game_by_bgg_id(entry["bgg_id"])
            if game:
                games.append(game)
                continue

            results = await ludopedia.search_games(entry["name"], rows=1)
            if not results:
                skipped += 1
                continue

            raw = results[0]
            async with AsyncSessionLocal() as session:
                existing = await session.execute(select(Game).where(Game.ludopedia_id == raw["id_jogo"]))
                game = existing.scalar_one_or_none()
                if game:
                    game.bgg_id = entry["bgg_id"]
                    game.bgg_rating = entry["rating"]
                else:
                    game = Game(
                        ludopedia_id=raw["id_jogo"],
                        title=raw["nm_jogo"],
                        thumbnail=raw.get("thumb"),
                        qt_quer=raw.get("qt_quer"),
                        bgg_id=entry["bgg_id"],
                        bgg_rating=entry["rating"],
                    )
                    session.add(game)
                await session.commit()
                await session.refresh(game)
            games.append(game)
        except Exception as e:
            # One bad Ludopedia search (e.g. a title with characters that trip up
            # their API) must not take down the whole batch of ~1000 lookups.
            logger.warning("Could not resolve BGG game %r (id %s) to Ludopedia: %s", entry["name"], entry["bgg_id"], e)
            skipped += 1

    if skipped:
        logger.info("Skipped %d top-ranked BGG games with no Ludopedia match", skipped)
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


async def run_export(bgg_top_n: int = 1000, concurrency: int = DEFAULT_CONCURRENCY) -> dict:
    """Refresh prices for every previously-searched game plus BGG's top-N ranked
    games. Games that drop out of top-N on a later run are never removed — once
    tracked, always tracked, so price history stays continuous. Top-N is only
    used as today's seed for discovering new games to start tracking."""
    searched = await _get_searched_games()
    bgg_top = await _ensure_top_bgg_games(bgg_top_n)

    seen_ids = set()
    games = []
    for g in searched + bgg_top:
        if g.ludopedia_id not in seen_ids:
            seen_ids.add(g.ludopedia_id)
            games.append(g)

    semaphore = asyncio.Semaphore(concurrency)
    await asyncio.gather(*(_refresh_one(g, semaphore) for g in games))

    logger.info(
        "Price export complete: %d games refreshed (%d searched, %d bgg-top)",
        len(games), len(searched), len(bgg_top),
    )
    return {"games_refreshed": len(games), "searched": len(searched), "bgg_top": len(bgg_top)}
