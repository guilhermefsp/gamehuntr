# Daily price export/history job (searched games + BGG top-N)

## Context

`boardgame-tracker` currently only fetches prices reactively, one game at a time, when a user runs `/preço`. There's no scheduled job building up price history at scale. The user wants a **daily export** that keeps a real price history for (a) every game that's ever been searched, and (b) the top ~1000 games on BoardGameGeek by rank — explicitly *not* all tens of thousands of BGG games, just these two bounded sets.

Two things surfaced during research that shape this plan:

1. **BGG's `/browse/boardgame` pages cannot be scraped** — BGG's 2025-07 policy change (the same one that added mandatory Bearer-token auth to the XML API2) explicitly prohibits scraping their site; a BGG community thread confirms this directly. This is unlike the existing Amazon/Ludopedia scraping, which is a normal, unrestricted personal-use case. Instead, BGG officially publishes a daily-updated CSV **data dump** (`id, name, rank, bayesaverage, rater count` for every ranked game) specifically intended for this kind of data mining — but downloading it requires being **logged into a BGG account** (session-based, not the `BGG_API_TOKEN` already configured for the XML API2, which is a separate mechanism). The user chose this route and added `BGG_USERNAME`/`BGG_PASSWORD` to `.env`.
2. **Ludopedia C2C prices currently have zero history.** `LudopediaListing` rows are fully deleted and reinserted on every scrape (`_save_ludopedia_listings` in `services.py`) — there's no trend data at all today, only a live snapshot. Amazon prices, by contrast, already get full history via the existing `Listing`/`PriceHistory` tables (`_record_price`). The fix is cheap: treat Ludopedia as another tracked "Store" (like `"Amazon BR"` already is) with two synthetic per-game listings (C2C Novo min, C2C Usado min), and record `PriceHistory` for them the same way Amazon prices already are. **No schema changes needed** — this reuses the existing `Store`/`Listing`/`PriceHistory` tables and their existing lazy-create pattern (`_get_or_create_amazon_store`), generalized to take a store name.

## Deployment: GitHub Actions, not Vercel

At current/expected scale (up to ~1000 games, each requiring a Ludopedia marketplace scrape taking a few seconds), a full daily run will take tens of minutes — far beyond Vercel serverless function duration limits (even Pro tier caps at 300s). This reinforces the Vercel limitation already flagged in the prior scraping-refactor plan.

Options considered: (a) a **GitHub Actions scheduled workflow** — free, no new accounts, Playwright installs cleanly on GitHub's Ubuntu runners (unlike the Arch dev box used this session), secrets via GitHub Actions Secrets; (b) the user's own machine/home server cron — free but unreliable unless the machine is always on; (c) migrating the whole app off Vercel to a VPS — solves this and consolidates hosting, but is a separate, larger migration decision, not required just for this feature. **Chosen: (a) GitHub Actions.** The bot itself stays on Vercel, unchanged.

Concretely: `scripts/export_prices.py` (deployment-agnostic, no Vercel coupling — same pattern as the existing scraper modules) gets a matching `.github/workflows/export-prices.yml` with a `schedule:` cron trigger, a `uv sync` + `uv run scrapling install` + `playwright install --with-deps chromium` setup step, then `uv run python scripts/export_prices.py`. Secrets (`DATABASE_URL`, `BGG_USERNAME`, `BGG_PASSWORD`, etc.) go into the GitHub repo's Actions Secrets, mirroring how they're already in `.env` for local/Vercel use.

## Step 0 — verify the BGG login flow live (do this first, before building the rest)

BGG's exact login API (endpoint, payload shape, whether it needs CSRF/cookies from a prior GET, whether the login form itself sits behind bot protection) is **not confirmed** — direct fetches to boardgamegeek.com have been Cloudflare-blocked from research in this session, and I could not verify the mechanics without real credentials. Now that `BGG_USERNAME`/`BGG_PASSWORD` are in `.env`:

1. Try a plain `httpx` POST to `https://boardgamegeek.com/login/api/v1` with `{"credentials": {"username": ..., "password": ...}}` (BGG's known modern login API shape from community references) and inspect the response/cookies.
2. If that fails (403/Cloudflare/CSRF), fall back to Scrapling's `StealthyFetcher` (already a project dependency) to drive a real browser through the login form, then extract cookies from that browser context for reuse in subsequent plain `httpx` requests to `data_dumps/bg_ranks`.
3. Once a working method is found, implement it as `src/scrapers/bgg_ranks.py`'s `_login()`. Don't guess further than this — confirm against the live site.

## New files

### `.github/workflows/export-prices.yml` (new)
Scheduled workflow: `on: schedule` (daily cron), sets up `uv`, runs `uv sync`, `uv run scrapling install`, `playwright install --with-deps chromium`, then `uv run python scripts/export_prices.py`, using repo Actions Secrets for `DATABASE_URL`/`BGG_USERNAME`/`BGG_PASSWORD`/etc. Also supports `workflow_dispatch` for manual runs while testing.

### `src/scrapers/bgg_ranks.py` (new)
```python
async def get_top_ranked(limit: int = 1000) -> list[dict]:
    # -> [{"bgg_id": int, "name": str, "rank": int, "rating": float | None}, ...]
```
- Logs in (per Step 0), downloads the CSV from `boardgamegeek.com/data_dumps/bg_ranks`, caches it at `data/bgg_ranks.csv` (already gitignored via the existing `data/` rule) for 24h to avoid re-authenticating on every run.
- Parses with stdlib `csv.DictReader`, filters `rank > 0` (BGG uses `0`/absent for unranked, same footgun pattern as `bayesaverage` in `bgg.py`), sorts by rank, returns top `limit`.
- Returns `[]` (logs a warning, doesn't raise) if `BGG_USERNAME`/`BGG_PASSWORD` are unset — same best-effort convention as `_enrich_bgg`.

### `src/jobs/__init__.py`, `src/jobs/price_export.py` (new package)
Bulk orchestration, separate from `services.py` (which stays focused on "answer one interactive query"):
```python
async def run_export(bgg_top_n: int = 1000, concurrency: int = 4) -> dict:
    # 1. searched = every row in `games` (already-searched games — no new tracking needed,
    #    _resolve_game already upserts a Game row on every /preço lookup)
    # 2. bgg_top = bgg_ranks.get_top_ranked(bgg_top_n), resolved to Game rows via
    #    ludopedia.search_games(name) for any bgg_id not already tracked (new Game rows
    #    created with bgg_id/bgg_rating pre-filled from the CSV; games with no Ludopedia
    #    match are skipped and logged, not retried every run)
    # 3. dedupe by ludopedia_id, refresh each concurrently (asyncio.Semaphore(concurrency)):
    #    backfill_link -> enrich_bgg -> fetch_c2c_data (now also records C2C history,
    #    see services.py changes) -> resolve_amazon_price
    # 4. never remove games that drop out of top-N later — once tracked, always tracked,
    #    so history stays continuous. Top-N is just today's seed for discovering new games.
```
Concurrency is bounded (default 4) to stay polite to Ludopedia (a small site) — first run costs ~1000 new `ludopedia.search_games` calls (official API) for BGG-sourced games not yet known; subsequent daily runs only search for newly-entered top-N games, everything else just re-scrapes/re-fetches prices for already-known games.

### `scripts/export_prices.py` (new)
Thin CLI wrapper matching the existing `scripts/test_*.py` pattern: `uv run python scripts/export_prices.py [--bgg-top 1000] [--concurrency 4]`, prints the summary dict (`games_refreshed`, `searched`, `bgg_top`).

## Modified files

### `src/services.py`
- **Generalize `_record_price`** to take a `store_name`/`store_base_url` (defaulting to the current Amazon values, so all existing call sites are unchanged) instead of being hardcoded to `_get_or_create_amazon_store`. Rename that helper to `_get_or_create_store(session, name, base_url)`.
- **Add C2C history recording**: new `_record_c2c_price(game, condition, price_brl, url)` using two new store names (`"Ludopedia C2C Novo"`, `"Ludopedia C2C Usado"`, base url `https://ludopedia.com.br`), called from `_fetch_c2c_data` right after computing `c2c_novo_min`/`c2c_used_min`. This is what actually fixes "we have zero C2C history today" — it applies to every scrape, interactive or bulk.
- **Extract `_resolve_amazon_price(game, query=None)`** from the inline 3-tier logic (Creators API → stored price → wishlist fallback) currently inside `get_price()`, so `price_export.py` can reuse it without duplicating. `get_price()` calls it the same way it does today; pure extraction, no behavior change.
- **Drop the leading underscore** from `_enrich_bgg`, `_fetch_c2c_data`, `_backfill_link`, and the new `_resolve_amazon_price` — they're genuinely reused across modules now (`price_export.py` needs them), so keeping the "private" naming convention would be misleading. Straightforward rename, all call sites updated.

### `src/config.py`
Add:
```python
bgg_username: str = ""
bgg_password: str = ""
```
(No new setting needed for concurrency — passed as a CLI arg with a sane default instead, avoids config sprawl for a value only the export script uses.)

### `.env.example`
Add `BGG_USERNAME`/`BGG_PASSWORD` with a comment clarifying this is for the ranks CSV dump specifically, distinct from `BGG_API_TOKEN`. (The user added real values to `.env` directly, not pasted into chat — same caution as any password, stricter than the API token.)

## Verification

0. ~~Copy this plan into the project repo~~ — done, this file.
1. Complete Step 0 (live BGG login spike) now that credentials are in `.env` — confirm `bgg_ranks.get_top_ranked(10)` returns real ranked games.
2. Run `scripts/export_prices.py --bgg-top 20 --concurrency 2` (small N first) and confirm: new `Game` rows appear for previously-untracked top-ranked titles, `PriceHistory` rows appear for both `"Amazon BR"` and the two new Ludopedia C2C stores, and nothing crashes on games with no Ludopedia match.
3. Run `scripts/test_preco.py` again afterward to confirm the interactive path still works unchanged (pure-extraction refactor of `services.py` should be behavior-preserving).
4. Query `PriceHistory` joined to the new C2C stores for a couple of games to confirm multiple rows accumulate across repeated runs (i.e. history is actually being built, not just a snapshot overwrite).
5. Scale up `--bgg-top 1000` only after the above passes, and time it to give the user a real number for how long a full daily run takes (needed for them to pick a cron host/schedule later).
