import csv
import html
import io
import logging
import re
import time
import zipfile
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

LOGIN_URL = "https://boardgamegeek.com/login/api/v1"
RANKS_PAGE_URL = "https://boardgamegeek.com/data_dumps/bg_ranks"

CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "bgg_ranks.csv"
CACHE_MAX_AGE_SECONDS = 24 * 3600


async def _download_ranks_csv() -> str:
    """Log into BGG (session-based, not the XML API2 Bearer token) and download the
    official ranks data dump. The ranks page renders a signed, short-lived S3 URL for
    the day's export zip — scraped from the page HTML, not a fixed/documented endpoint."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        login_resp = await client.post(
            LOGIN_URL,
            json={"credentials": {"username": settings.bgg_username, "password": settings.bgg_password}},
        )
        login_resp.raise_for_status()

        page_resp = await client.get(RANKS_PAGE_URL)
        page_resp.raise_for_status()

        match = re.search(r"href=['\"]([^'\"]*boardgames_ranks[^'\"]*)['\"]", page_resp.text)
        if not match:
            raise RuntimeError("Could not find ranks download link on BGG data dumps page")
        zip_url = html.unescape(match.group(1))

        zip_resp = await client.get(zip_url)
        zip_resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        return z.read(csv_name).decode("utf-8")


async def get_top_ranked(limit: int = 1000) -> list[dict]:
    """Return [{"bgg_id", "name", "rank", "rating"}, ...] for the top `limit` ranked
    (non-expansion) games, using a 24h-cached local copy of BGG's official ranks CSV.
    Returns [] (logs a warning) if BGG_USERNAME/BGG_PASSWORD are unset — same
    best-effort convention as bgg.py's enrichment functions.
    """
    if not settings.bgg_username or not settings.bgg_password:
        logger.warning("BGG_USERNAME/BGG_PASSWORD not set, skipping top-ranked BGG fetch")
        return []

    if CACHE_PATH.exists() and (time.time() - CACHE_PATH.stat().st_mtime) < CACHE_MAX_AGE_SECONDS:
        text = CACHE_PATH.read_text()
    else:
        text = await _download_ranks_csv()
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(text)

    reader = csv.DictReader(io.StringIO(text))
    ranked = []
    for row in reader:
        try:
            rank = int(row["rank"])
        except (KeyError, ValueError):
            continue
        # rank 0 means unranked (BGG's usual "0 instead of absent" convention);
        # is_expansion filters out expansions competing for "top game" slots.
        if rank <= 0 or row.get("is_expansion") == "1":
            continue
        ranked.append({
            "bgg_id": int(row["id"]),
            "name": row["name"],
            "rank": rank,
            "rating": float(row["bayesaverage"]) if row.get("bayesaverage") else None,
        })

    ranked.sort(key=lambda r: r["rank"])
    return ranked[:limit]
