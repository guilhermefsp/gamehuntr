# Ludopedia Marketplace — Unified Plan

> Status: proposed (recon 2026-07-05; unified design 2026-07-06; ToS reviewed 2026-07-06)
>
> Supersedes the original two-process crawler plan (forward monitor + backward backfill) **and** absorbs the phasing from `todo.md` / `PRODUCT_BRIEF.md`. This is now the single roadmap.

## Design decision (2026-07-06)

The original plan proposed a standalone crawler (24/7 daemon, priority fetch queue, ID-space walking) feeding a new table, fully separate from the existing per-game `?v=anuncios` scraper. Deep comparison showed the two are **two entry points into the same data**:

- The `?v=anuncios` rows already contain `/produto/{id}` URLs — the existing scraper just throws that identity away (`ludopedia_listings` is delete-and-replace per game, no lifecycle, no history).
- The daily sitemap already lists all ~26k live listings newest-first — a daily diff replaces the forward monitor's frontier-probing machinery (pending states, consecutive-miss detection, re-probe windows) at the cost of hours of latency that no planned feature needs.
- The ~360k-ID backward gap probe is ~90% of the requests for the least valuable data: it only recovers *pre-existing* finished auctions. Going forward, every auction that closes after launch gets its real final price via the sitemap diff — history accumulates on its own.
- Today's `price_export.py` bulk job scrapes ~1000 `?v=anuncios` pages per run at concurrency 4 with **no rate limiting** — less polite than anything in the crawler plan. Once the unified table is populated nightly, that job reads C2C prices from the DB instead. Net Ludopedia load goes **down** versus current behavior.

**Unified design:** one table (`marketplace_listings`, keyed by `produto_id`), fed by two channels — the interactive `/preço` scrape (upsert instead of delete-and-replace) and one nightly sitemap-sync job. No daemon, no priority queue. Explicitly dropped: forward monitor, gap probe (deferrable, see end).

**Known trade-off:** a listing posted and sold within the same day, between two sitemaps, is never seen. Volume unknown — two consecutive sitemap diffs measure it (Phase 3). A lightweight frontier probe can be bolted on later if it matters.

---

## Recon findings (verified 2026-07-05)

| Finding | Evidence |
|---|---|
| robots.txt **allows** `/produto/` for `User-agent: *` with `Crawl-delay: 5` | https://ludopedia.com.br/robots.txt — only SEO bots are banned; `/admin`, `/login`, `/checkout`, `/cart`, `/feed` disallowed |
| Compliant budget = 1 req / 5 s = **720/h = 17,280/day** | crawl-delay 5 |
| Produto pages are server-rendered — all fields present without JS | Fetched produto/386761 with no JS: title, breadcrumb (`Home > BoardGames > Jogos Expert`), Leilão flag, lance, condition + notes, seller + city/UF, `Término … (10/07 22:00)`, publisher/edition |
| **Closed auctions persist and show the final winning bid** | produto/300000 → "Leilão Finalizado (27/11 20:00)", winning bid R$ 255,00, winner masked. Historical *actual sale prices* are recoverable — the most valuable data in the system |
| Some old IDs are gone | produto/100000 → "Produto não localizado". Old ID space is a mix of finished auctions, live listings, and dead IDs |
| **Daily sitemap of all live listings** | `sitemap-index.xml.gz` → `sitemaps/produtos-{1,2}.xml.gz`, regenerated ~04:00 BRT, ~25,900 URLs ordered newest→oldest (386756 … 119). This is the cheap discovery + reconciliation channel |
| `/loja` index is Angular/XHR-rendered | Not scrapeable with plain fetch; not needed — sitemap covers discovery |
| Public API (`/api/v1`) has no marketplace endpoints | Existing client (`src/scrapers/ludopedia.py`) only covers games/search |

Category filtering: breadcrumb on each page (`BoardGames > …` vs `Acessórios > …` etc.). The sitemap mixes categories (e.g. 386753 is a 3D insert), so classification happens at parse time.

Product rules: board games only (non-boardgames stored as `ignored`, never refetched); auctions store the **end date but never the live price** (it can only go up) — final winning bid only, captured after close; fixed-price sales store the asking price.

---

## Architecture

### Channel 1 — interactive `/preço` scrape (existing, refactored)

`ludopedia_marketplace.scrape_listings` keeps scraping `?v=anuncios` on demand for freshness, but:

- Extracts `produto_id` from each row's listing URL.
- `services._save_ludopedia_listings` becomes an **upsert** into `marketplace_listings` (match on `produto_id`; update price/condition/`last_checked_at`; insert with `first_seen_at` when new) instead of delete-and-replace.
- `game_id` is set from the page context when the row matches the game (current `is_game_match` logic); left NULL otherwise until a produto fetch resolves it via the `/jogo/` link.
- The min-price snapshots into `Store`/`Listing`/`PriceHistory` ("Ludopedia C2C Novo/Usado") stay unchanged — that's still the per-game trend mechanism.

### Channel 2 — nightly sitemap sync (new: `src/jobs/marketplace_sync.py`)

One sequential pass, `asyncio.sleep(5)` between fetches (plus 0–2 s jitter), tier-1 fetch only. Runnable as a plain cron / systemd timer on the desktop — **not Vercel** (a politeness loop that idles 5 s between requests for ~an hour is incompatible with serverless limits). Downtime is harmless; the next run reconciles.

1. **Diff** — download the two produtos sitemap files (~26k URLs), diff against DB.
2. **New IDs** → fetch produto page → parse → classify by breadcrumb → upsert. Non-boardgames: store `produto_id + status=ignored` (+ category) only, never refetched.
3. **Closer** — IDs `active` in DB but gone from today's sitemap: auctions get **one** refetch to record the final winning bid from "Leilão Finalizado" (this is the only way auction prices enter the DB); fixed-price listings get `closed_at` + last asking price (sold vs cancelled is indistinguishable — don't try). Also refetch auctions with `auction_end_at < now` still present in the sitemap.
4. **Price changes** — for fixed-price rows whose asking price changed since last seen, update in place (listing-level price history can be added later if needed; per-game trend is already covered by Channel 1's snapshots).
5. **Log** — append a `crawl_log` row: requests, new, closed, ignored, 404s, 403/429s, duration. Feeds the admin dashboard.

Steady-state estimate: a few hundred fetches/day ≈ 30–60 min nightly runtime, single-digit % of the compliant budget.

### One-time sitemap sweep (backfill, Phase 3)

Same job with a `--sweep` flag: fetch all live-listing IDs not yet in DB. ~26k guaranteed-hit pages ≈ 36 h of polite crawling. Resumable cursor in `crawl_state`; pause/stop anytime.

### `price_export.py` after the sweep

The bulk job's C2C portion (`fetch_c2c_data` per game) is replaced by a DB query over `marketplace_listings` (`game_id = X AND status = 'active'`, min by condition) — eliminating ~1000 unthrottled page fetches per run. Amazon/BGG portions unchanged. Interactive `/preço` keeps its live scrape.

---

## Data model

`marketplace_listings` **replaces** `ludopedia_listings` (whose data is throwaway — fully rebuilt on every scrape — so drop it, nothing to migrate):

```
produto_id        INT PK              -- the URL id
game_id           INT FK→games NULL   -- from /jogo/ link on produto page, or /preço page context
title             VARCHAR             -- product_name from either channel
category          VARCHAR NULL        -- breadcrumb level 1 (BoardGames, Acessórios, …); NULL until a produto fetch
subcategory       VARCHAR NULL
kind              ENUM(sale, auction) NULL -- NULL until known
status            ENUM(active, finished, removed, not_found, ignored)
price_brl         NUMERIC NULL        -- sale: asking price; auction: FINAL bid only (NULL while live)
condition         VARCHAR NULL        -- Novo / Usado
condition_notes   VARCHAR NULL
seller_city       VARCHAR NULL        -- city/UF only; do NOT store seller username (LGPD)
auction_end_at    TIMESTAMP NULL
first_seen_at     TIMESTAMP
closed_at         TIMESTAMP NULL
last_checked_at   TIMESTAMP
```

Support tables:

- `crawl_state` — named cursors (sweep cursor, last sitemap date/etag).
- `crawl_log` — one row per sync run with daily counters (requests, hits, new, closed, ignored, 404s, 403/429s).

Neon free tier (0.5 GB): even 400k rows without descriptions ≈ 150 MB. Never store full descriptions or photos.

---

## Politeness, risks, mitigations

1. **robots.txt** — compliant by design: 5 s delay + jitter, single connection, `/produto/` allowed. Re-read robots.txt weekly; kill switch if `/produto/` becomes disallowed.
2. **Rate/IP blocking** — tier-1 (curl_cffi) fetch only. On 403/429/503: exponential backoff (15 min → 1 h → 6 h), Telegram alert, full stop after repeated blocks. **Never escalate to the stealth browser for bulk crawling** — a block at bulk scale is a signal to stop and reassess, not to evade. (Stealth tier stays for the existing low-volume `/preço` flow only.)
3. **User-Agent** — decide: honest `GameHuntrBot/1.0 (+contact-email)` vs browser UA. Recommendation: honest UA — transparent, robots-compliant crawlers identify themselves, and it gives Ludopedia a way to reach you instead of just banning. The unified design strengthens the case: total volume is *lower* than the current unthrottled bulk job.
4. **Terms of Use** — read 2026-07-06 (`docs/termos-de-uso.md`). No explicit anti-scraping/anti-bot clause, but two clauses create real exposure:
   - **Cláusula 19.2** (the sharpest): the site's "bancos de dados" are its property and "reprodução total ou parcial" is prohibited "**salvo a autorização expressa do SITE**". `marketplace_listings` is by design a partial reproduction of their marketplace DB — the ~26k sweep especially, the deferred 360k gap probe even more so; surfacing "últimas vendas" is republication. The clause itself provides the cure (express authorization) → **emailing Ludopedia is a blocking prerequisite for Phase 3**, not optional. Channel 1's interactive scrape is much lower risk (small volume, user-triggered, no different from today).
   - **Cláusula 15.1**: broad ban on any "dispositivo, software ou outro recurso que venha a interferir nas atividades e operações do SITE … bem como nos ANÚNCIOS … ou seus bancos de dados". A robots-compliant 1 req/5 s crawler defensibly doesn't "interfere" — but today's unthrottled `price_export.py` is the thing most plausibly interfering right now; the refactor *reduces* ToS exposure (good argument to have ready).
   - **Enforcement reality**: not a lawsuit — preamble + cláusulas 3.8/18 allow account termination at exclusive discretion, without notice. Key exposure: **the Ludopedia API token** — `/preço` depends on their official API; a ban kills the whole product. Punishments are account-scoped (aviso → bloqueio 3 meses → exclusão, cl. 5.2). Consider a separate/secondary account's token for crawl-adjacent work so a ban doesn't take down `/preço` (less important if the heads-up email is sent first).
   - **Cláusula 17 + 16.2**: Ludopedia actively monitors and already runs bots analyzing DMs for commission evasion — an operator that polices automated behavior; expect scraping patterns to be noticed. Strengthens the honest-UA choice: a browser-UA crawler discovered later looks like concealment under 15.1.
   - **Commission sensitivity (cl. 10, 16.2, 18)**: their revenue is the 10–12% commission and the ToS is acutely sensitive to anything routing sales around it. The bot funnels buyers *into* listings — the single best talking point in the Phase 0 email.
   - **Terms change without notice** (preamble) — the weekly robots.txt re-check should periodically re-diff the ToS against the `docs/termos-de-uso.md` baseline.
5. **LGPD + ToS cl. 5.2 item 2** — the ToS also prohibits spreading "informação pessoal real a respeito de outros usuários", so this is a hard rule on two grounds: city/UF only, no usernames (never surface seller identity in the bot, even though it's on the public page); never republish listing photos/descriptions; show aggregates and always link to the original listing.
6. **Parser fragility** — pages have Angular template artifacts; build the produto parser against saved fixtures of all six shapes: active sale, active auction, finished auction, removed/sold, not-found, non-boardgame. Alert (don't silently skip) when a page matches no shape.

---

## Phases

Integrates `todo.md` / `PRODUCT_BRIEF.md`. Bot-UX work (Phase 1) is orthogonal to the marketplace foundation (Phases 2–3) and can run in parallel.

### Phase 0 — Groundwork
- [x] Read Ludopedia Termos de Uso (2026-07-06 — findings in "Politeness, risks, mitigations" item 4; baseline saved at `docs/termos-de-uso.md`)
- [ ] Decide UA + contact email
- [ ] **Email Ludopedia a heads-up — blocking prerequisite for Phase 3** (cl. 19.2 requires express authorization for DB reproduction; pitch: the bot funnels buyers into listings, and total scraping volume goes *down* vs today's bulk job)

### Phase 1 — Bot launch readiness (from todo.md, unchanged)
- [ ] `search_count` column on Game + `User` table (migrations)
- [ ] `/start` + `/help` commands
- [ ] `/preço` → `send_photo` with BGG rating/weight enrichment
- [ ] Disambiguation: fetch rows=5, "Jogo errado?" → results #2–5 as new photo + inline buttons
- [ ] Link support: `/preço <ludopedia_url>` and `/preço <bgg_url>` — also accept `/produto/{id}` URLs once Phase 2 lands
- [ ] PA API as primary price path; wishlist scraper as fallback

### Phase 2 — Unified marketplace foundation
- [ ] Migration: create `marketplace_listings` + `crawl_state` + `crawl_log`; drop `ludopedia_listings`
- [ ] Refactor `ludopedia_marketplace.py` to extract `produto_id`; `services` upserts instead of delete-and-replace
- [ ] `src/scrapers/ludopedia_produto.py` — produto page parser, built against the six saved fixtures

### Phase 3 — Nightly sync + sweep

> Gate: do not start until the Phase 0 heads-up email to Ludopedia is sent (see risk item 4, cl. 19.2).

- [ ] `src/jobs/marketplace_sync.py`: sitemap diff → fetch new → closer → crawl_log; systemd timer / cron on the desktop
- [ ] Run two consecutive daily diffs → measure new-listings/day volume and same-day-churn (the known blind spot)
- [ ] One-time sitemap sweep (~26k pages, ~36 h, resumable)
- [ ] Point `price_export.py`'s C2C portion at the DB (removes ~1000 unthrottled fetches/run)

### Phase 4 — Engagement (from todo.md Phase 2)
- [ ] Watchlist table + `/quero` + `/lista` + `/alertar` + `/alertas` + `/cancelar-alerta`
- [ ] Alert check runs off `marketplace_listings` after each nightly sync (no separate scraping loop) + Telegram notifications

### Phase 5 — Ops & surfacing (todo.md Phase 3 + original plan Phase 5)
- [ ] Admin dashboard (`/admin`, FastAPI + Jinja2, Basic Auth): games table (search_count, ASIN correction), price history chart per game, `crawl_log` view, users/watchlist overview
- [ ] `/preço` gains "últimas vendas" — real final auction prices from `marketplace_listings` where `status=finished`
- [ ] User-facing price history

### Deferred (not dropped)
- **Forward monitor** (near-live new-listing detection) — add a lightweight frontier probe only if Phase 3 measurements show meaningful same-day churn
- **Gap probe** (~360k old IDs backward) — the table and parser support it; run it later if pre-launch auction history proves valuable
- **MercadoLivre scraper** (post-launch, from todo.md)

## Open questions

- New listings/day volume + same-day churn → measured in Phase 3 via consecutive sitemap diffs.
- Do sold fixed-price listings persist like finished auctions, or 404? → track a few live ones through sale in Phase 3.
- Are "Produto não localizado" IDs permanently dead? → only matters if the gap probe is ever revived.
