"""
Quick CLI test for the BGG XML API2 client — isolated, no DB round-trip.
Usage: uv run python scripts/test_bgg.py "Terra Mystica"
"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.WARNING)

from src.scrapers import bgg


async def main(title: str) -> None:
    print(f"Searching BGG for: {title!r}\n")
    bgg_id = await bgg.search_game(title)
    if not bgg_id:
        print("No match found (or BGG_API_TOKEN is unset).")
        return
    print(f"bgg_id: {bgg_id}")

    details = await bgg.get_game_details(bgg_id)
    if not details:
        print("Could not fetch details.")
        return
    for k, v in details.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Terra Mystica"
    asyncio.run(main(q))
