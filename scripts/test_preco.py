"""
Quick CLI test for get_price() — exercises Ludopedia API, marketplace scraper, and DB.
Usage: uv run python scripts/test_preco.py "Castle Combo"
"""
import asyncio
import sys

from src.bot.handlers import _format_price_message
from src.services import get_price


async def main(query: str) -> None:
    print(f"Looking up: {query!r}\n")
    result = await get_price(query)
    if not result:
        print("Game not found.")
        return
    print("--- Raw result ---")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("\n--- Bot message ---")
    print(_format_price_message(result))


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Castle Combo"
    asyncio.run(main(q))
