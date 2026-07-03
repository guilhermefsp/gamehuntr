# Daily price export/history job — invert top-N sourcing to Ludopedia's own ranking

## Context (what's already built and live-tested)

The daily price-export job (`src/jobs/price_export.py`, `scripts/export_prices.py`, `.github/workflows/export-prices.yml`) is built and working: it refreshes prices for every previously-searched game, records real price history for Ludopedia C2C prices for the first time (via two new synthetic "stores" reusing the existing `Listing`/`PriceHistory` schema — no migration needed), and reuses `services.py`'s `enrich_bgg`/`fetch_c2c_data`/`resolve_amazon_price` helpers (already extracted/renamed for cross-module reuse). This part is unchanged by this plan update.

**What's changing:** the "top N" discovery mechanism. The original approach sourced the top 1000 from BGG's official ranks CSV (`src/scrapers/bgg_ranks.py`, login-gated, already live-verified and working), then tried to resolve each BGG-titled game to a Ludopedia listing via `ludopedia.search_games(bgg_title)`. A full-scale live run confirmed this only matched **136 of 1000** BGG games (13.6%). The user correctly diagnosed the likely cause: **name mismatch, not absence** — BGG's CSV gives international/English titles, while Ludopedia's catalog and search index use Brazilian-market titles, which are often translated (confirmed in our own data: "Twilight Imperium: Fourth Edition" → "Twilight Imperium (4ª Edição)", "Through the Ages..." → "...Uma Nova História da Civilização", "Gaia Project" → "Projeto Gaia"). Searching Ludopedia with an English title silently fails for many titles that do exist there.

**Fix — invert the flow.** Ludopedia has its own ranking at `https://ludopedia.com.br/ranking` (confirmed live: server-rendered, reachable via the existing tier-1 fetch — no bot-protection issue, and Ludopedia has no scraping ToS restriction unlike BGG). Sourcing top-N directly from there guarantees every entry is a real, resolvable Ludopedia listing (its own title, used to search its own catalog — should be a ~100% match rate, to be confirmed empirically). BGG then becomes purely a best-effort metadata enrichment step (already exactly what `services.enrich_bgg` does) — if a BGG match fails for a translated title, we just don't get a rating/weight for that game, we don't lose the game from tracking. This is a strict improvement: worst case degrades from "game untracked" to "game tracked without a BGG rating."

Confirmed live (this session) about the ranking page:
- `https://ludopedia.com.br/ranking?pagina=N` — 50 games per page, `pagina=1` is implicit/default. At least 101 pages exist (~5000+ ranked games total) — top 1000 needs pages 1–20.
- Each row (`div.media.pad-btm.bord-btm`) contains: rank (`"1º"`, `"2º"`, ... — strip the `º`), title (`h4.media-heading > a`), year, `Nota Rank` (Ludopedia's own bayesian-style rank score), `Média` (average user rating), `Notas` (rating count), and a link to the game page (slug-based URL, not the numeric `id_jogo` we need — still requires a `search_games` call to resolve the numeric id, same as before, just with a much more reliable title now).
- No BGG cross-reference field exists anywhere in Ludopedia's API (`get_game()` response fully inspected — no `bgg_id`-equivalent). Cross-referencing still has to go through a title search in whichever direction; only the direction changed.

## New file

### `src/scrapers/ludopedia_ranking.py` (new)
HTML scraping (not the official API — belongs alongside `ludopedia_marketplace.py`'s pattern, not `ludopedia.py`'s pure-API pattern):
```python
async def get_ranking(pages: int = 20) -> list[dict]:
    # -> [{"rank": int, "title": str, "year": int | None,
    #      "nota_rank": float | None, "media": float | None, "notas": int | None}, ...]
```
- Fetches `https://ludopedia.com.br/ranking?pagina=N` for `N` in `1..pages` via the existing `fetch.fetch()` tier-1 helper (matches `ludopedia_marketplace.py`'s approach — Ludopedia doesn't block tier-1 today, no stealth retry needed here either).
- Parses each `div.media.pad-btm.bord-btm` row via Scrapling `.css()` — reuse the adaptive-selector convention from `ludopedia_marketplace.py`/`amazon_wishlist.py` (adaptive only on the outer per-page row selector, plain `.css()` for nested fields, per the identifier-collision lesson learned earlier this session).
- Rank parsed from text like `"1º"` (strip trailing `º`, `int(...)`).
- Not persisted as new `Game` columns — used purely as a discovery/seed mechanism for which games to track, same as the original BGG-top-N's role. (If useful later, Ludopedia's own rank score could become a stored field, but that's out of scope for what was asked here.)

## Modified files

### `src/jobs/price_export.py`
- Replace `_ensure_top_bgg_games(limit)` with `_ensure_top_ludopedia_games(limit)`:
  - `ranking = await ludopedia_ranking.get_ranking(pages=ceil(limit / 50))`, truncate to `limit`.
  - For each entry: `results = await ludopedia.search_games(entry["title"], rows=1)` (existing client, now searching Ludopedia's own catalog with Ludopedia's own title — expected to reliably match); skip+log if no result (should be rare now, unlike before).
  - Create/find the `Game` row by `ludopedia_id` (the resolved numeric id) — same upsert shape as before, minus the `bgg_id`/`bgg_rating` pre-fill (Ludopedia's ranking doesn't give a BGG id).
  - Call `services.enrich_bgg(game)` on each (already exists, best-effort, cached via `bgg_synced_at`, searches BGG by title and silently no-ops on failure) — this is where BGG metadata now gets attached, accepting some misses gracefully rather than gating tracking on it.
  - Keep the existing per-entry `try/except` isolation (the fix already made after the first full-scale run crashed on one bad Ludopedia search) — same risk exists in the new direction (a bad title/API error on one entry must not kill the batch).
- Rename `run_export(bgg_top_n=..., ...)` → `run_export(ludopedia_top_n=..., ...)`, update the internal call site and the returned summary dict key (`bgg_top` → `ludopedia_top`).
- `bgg_ranks.py` (the CSV-login module) is **not deleted** — it's fully built, live-verified, and harmless sitting unused; just no longer called from `price_export.py`'s main flow. Kept in case it's useful later (e.g. cross-checking or a supplementary global list).

### `scripts/export_prices.py`
Rename `--bgg-top` → `--ludopedia-top` (default `1000`), update the `run_export(...)` call accordingly.

### `.github/workflows/export-prices.yml`
Rename the `workflow_dispatch` input `bgg_top` → `ludopedia_top`, update the `--bgg-top` flag in the run step to `--ludopedia-top`. `BGG_USERNAME`/`BGG_PASSWORD` secrets stay wired (still needed if `bgg_ranks.py` is ever reactivated, and harmless to leave configured) but are no longer load-bearing for this workflow to succeed — `enrich_bgg` already degrades gracefully without `BGG_API_TOKEN`/credentials.

## Verification

1. Small scale first: `scripts/export_prices.py --ludopedia-top 50 --concurrency 2`. The key thing to confirm versus last time: **near-100% resolution rate** (all or nearly all 50 ranking entries should successfully resolve to a Ludopedia game, unlike the 13.6% match rate from the BGG-sourced approach) — this is the actual fix being verified, not just "it runs."
2. Spot-check a few newly-created `Game` rows: confirm `bgg_id`/`bgg_rating`/`bgg_weight` got populated for at least some of them via `enrich_bgg` (some misses are expected and fine, but not all-misses).
3. Re-run at full `--ludopedia-top 1000` scale, confirm no crash (per-entry error isolation holds), and record the real total game count + timing for comparison against the previous BGG-sourced run's 140 games / 7m8s.
4. Confirm `scripts/test_preco.py` still passes (no changes to the interactive path in this update).
