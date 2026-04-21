import httpx

from src.config import settings

BASE_URL = "https://ludopedia.com.br/api/v1"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.ludopedia_access_token}"}


async def search_games(query: str, rows: int = 5) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/jogos",
            params={"search": query, "tp_jogo": "b", "rows": rows},
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json().get("jogos", [])


async def get_game(ludopedia_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/jogos/{ludopedia_id}", headers=_headers())
        r.raise_for_status()
        return r.json()
