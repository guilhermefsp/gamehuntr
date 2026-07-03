"""
Daily price export: refreshes prices for all previously-searched games plus BGG's
top-N ranked games (requires BGG_USERNAME/BGG_PASSWORD in .env for the latter —
skips the BGG-top-N side gracefully if unset).

Usage: uv run python scripts/export_prices.py [--bgg-top 1000] [--concurrency 4]
"""
import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from src.jobs.price_export import run_export


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bgg-top", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    result = asyncio.run(run_export(bgg_top_n=args.bgg_top, concurrency=args.concurrency))
    print(result)


if __name__ == "__main__":
    main()
