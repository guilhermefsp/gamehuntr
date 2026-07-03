import re

from src.scrapers import fetch as fetch_module

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

_ROWS_PER_PAGE = 50


def _parse_float(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def _parse_int(text: str) -> int | None:
    try:
        return int(re.sub(r"[^\d]", "", text))
    except ValueError:
        return None


def _parse_row(row) -> dict | None:
    # The ranking page conveniently exposes Ludopedia's own numeric game id directly
    # via data-id_jogo — no need to resolve it separately via search_games().
    id_els = row.css("[data-id_jogo]")
    if not id_els:
        return None
    ludopedia_id = _parse_int(id_els[0].attrib.get("data-id_jogo", ""))
    if ludopedia_id is None:
        return None

    rank_els = row.css("span.rank")
    rank = _parse_int(rank_els[0].get_all_text(separator="", strip=True)) if rank_els else None

    title_els = row.css("h4.media-heading a")
    title = title_els[0].attrib.get("title") if title_els else None
    if not title and title_els:
        title = title_els[0].get_all_text(separator="", strip=True)

    year = None
    year_els = row.css("h4.media-heading small i")
    if year_els:
        match = re.search(r"\d{4}", year_els[0].get_all_text(separator="", strip=True))
        if match:
            year = int(match.group())

    stat_els = row.css("div.rank-info b")
    nota_rank = _parse_float(stat_els[0].get_all_text(separator="", strip=True)) if len(stat_els) > 0 else None
    media = _parse_float(stat_els[1].get_all_text(separator="", strip=True)) if len(stat_els) > 1 else None
    notas = _parse_int(stat_els[2].get_all_text(separator="", strip=True)) if len(stat_els) > 2 else None

    if not title:
        return None

    return {
        "ludopedia_id": ludopedia_id,
        "rank": rank,
        "title": title,
        "year": year,
        "nota_rank": nota_rank,
        "media": media,
        "notas": notas,
    }


async def get_ranking(pages: int = 20) -> list[dict]:
    """Fetch Ludopedia's own game ranking, `pages` pages of 50 games each.
    Returns [{"ludopedia_id", "rank", "title", "year", "nota_rank", "media", "notas"}, ...]
    sorted by rank ascending. Every entry is guaranteed to be a real, resolvable
    Ludopedia listing since it's read directly from Ludopedia's own catalog.
    """
    entries = []
    for page_num in range(1, pages + 1):
        url = "https://ludopedia.com.br/ranking" if page_num == 1 else f"https://ludopedia.com.br/ranking?pagina={page_num}"
        result = await fetch_module.fetch(url, headers=_HEADERS)
        if not result:
            break

        rows = result.page.css(
            "div.media.pad-btm.bord-btm", identifier="ludopedia_ranking_row", adaptive=True, auto_save=True
        )
        if not rows:
            break

        page_entries = [e for e in (_parse_row(r) for r in rows) if e]
        if not page_entries:
            break
        entries.extend(page_entries)

    entries.sort(key=lambda e: e["rank"] or 10**9)
    return entries
