"""
Daily price export: refreshes prices for all previously-searched games plus
Ludopedia's own top-N ranked games (guaranteed real Ludopedia listings, unlike the
earlier BGG-CSV-sourced approach — see docs/plans/daily-price-export.md). BGG
metadata (rating/weight) is attached best-effort via enrich_bgg when BGG_API_TOKEN
is set; the export still tracks games and prices fine without it.

Usage: uv run python scripts/export_prices.py [--ludopedia-top 1000] [--concurrency 4]
"""
import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from src.jobs.price_export import run_export


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ludopedia-top", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    result = asyncio.run(run_export(ludopedia_top_n=args.ludopedia_top, concurrency=args.concurrency))
    print(result)


if __name__ == "__main__":
    main()
