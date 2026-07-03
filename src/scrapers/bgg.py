import asyncio
import logging
from xml.etree import ElementTree as ET

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://boardgamegeek.com/xmlapi2"

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.bgg_api_token}"}


async def _get_with_retry(path: str, params: dict) -> ET.Element | None:
    """GET an XML API2 endpoint, retrying on BGG's 202 'please wait, building cache' response.
    Applies to both /search and /thing, not just /collection — confirmed both can return 202."""
    async with httpx.AsyncClient(timeout=15, headers=_headers()) as client:
        for attempt in range(_MAX_RETRIES):
            r = await client.get(f"{BASE_URL}/{path}", params=params)
            if r.status_code == 202:
                await asyncio.sleep(_RETRY_DELAY)
                continue
            r.raise_for_status()
            return ET.fromstring(r.text)
    logger.warning("BGG %s still not ready after %d retries", path, _MAX_RETRIES)
    return None


def _int(item: ET.Element, tag: str) -> int | None:
    el = item.find(tag)
    val = el.get("value") if el is not None else None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


async def search_game(title: str) -> int | None:
    """Search BGG by title, return the best-matching bgg_id or None.

    BGG's /search is not relevance-sorted — e.g. searching "Terra Mystica" returns
    "Gaia Project: Galaxie Terra Mystica" (a fan expansion) before the base game
    itself. Prefer an exact case-insensitive name match among results; fall back
    to the first result (still no fuzzy/year disambiguation beyond that) if none
    matches exactly.
    """
    if not settings.bgg_api_token:
        return None
    root = await _get_with_retry("search", {"query": title, "type": "boardgame"})
    if root is None:
        return None
    items = root.findall("item")
    if not items:
        return None

    title_lower = title.strip().lower()
    for item in items:
        for name_el in item.findall("name"):
            if (name_el.get("value") or "").strip().lower() == title_lower:
                return int(item.get("id"))

    return int(items[0].get("id"))


async def get_game_details(bgg_id: int) -> dict | None:
    """Fetch /thing?id=X&stats=1, return rating/weight/player-count metadata or None."""
    if not settings.bgg_api_token:
        return None
    root = await _get_with_retry("thing", {"id": bgg_id, "stats": 1})
    if root is None:
        return None
    item = root.find("item")
    if item is None:
        return None

    name_el = item.find("name")
    title = name_el.get("value") if name_el is not None else None

    rating = None
    weight = None
    ratings_el = item.find("statistics/ratings")
    if ratings_el is not None:
        bayes_el = ratings_el.find("bayesaverage")
        avg_el = ratings_el.find("average")
        # BGG returns literal "0" (not absent) for unranked games — fall back to
        # the raw average in that case rather than silently storing a 0.00 rating.
        bayes = float(bayes_el.get("value")) if bayes_el is not None else 0.0
        if bayes > 0:
            rating = bayes
        elif avg_el is not None:
            rating = float(avg_el.get("value"))

        weight_el = ratings_el.find("averageweight")
        weight = float(weight_el.get("value")) if weight_el is not None else None

    return {
        "bgg_id": bgg_id,
        "title": title,
        "rating": rating,
        "weight": weight,
        "min_players": _int(item, "minplayers"),
        "max_players": _int(item, "maxplayers"),
        "playing_time": _int(item, "playingtime"),
    }
