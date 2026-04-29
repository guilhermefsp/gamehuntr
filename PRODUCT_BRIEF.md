# GameHuntr — Product Brief

Telegram bot for Brazilian board game price tracking. Returns Amazon price, Ludopedia C2C marketplace average, and the lowest price ever recorded — all from a single `/preço` command. **Goal: public bot.**

---

## Current State

- `/preço <jogo>` — resolves game via Ludopedia API, scrapes C2C listings, queries Amazon, returns prices + lowest ever
- Deployed on Vercel (serverless webhook) + Neon PostgreSQL, free tier, always on
- Price history stored per game for lowest-ever tracking
- Ludopedia Marketplace scraper working (httpx + BeautifulSoup)
- Amazon PA API integrated but credentials not yet available — wishlist scraper is the bridge
- "Resultado errado?" inline button allows correcting wrong Amazon ASIN

---

## Phase 1 — Launch Readiness

### 1. Database: `search_count` + `User` table

**`search_count` on `Game`:**
- Add `search_count: int` column (default 0)
- Increment in `_resolve_game` on every hit
- Used post-launch to prioritize which games to add to the Amazon wishlist

**New `User` model:**
```
telegram_user_id  BIGINT  PK
username          VARCHAR nullable
first_name        VARCHAR nullable
created_at        DATETIME
```
- Upsert on every bot interaction
- FK target for watchlist table (Phase 2)

### 2. `/start` + `/help` commands

No onboarding exists today. Add:
- `/start` — welcome message, one-line description, list all commands
- `/help` — same as `/start`, always available

### 3. `/preço` → `send_photo` with BGG enrichment

**Visual upgrade:** change text reply to `send_photo` (game thumbnail as image, prices as caption). Fall back to text if `thumbnail` is `None`.

**BGG enrichment:**
- Two new nullable columns on `Game`: `bgg_rating FLOAT`, `bgg_weight FLOAT`
- Populated via BGG XML API (free, no auth) when `bgg_id` is set
- Shown in caption: `⭐ 8.1 · 🧠 2.9/5`

**Caption format:**
```
🎲 Wingspan

C2C Novo: R$ 180,00 média (4 anúncios) — ver anúncios
Amazon: R$ 220,00 ✅ — comprar
📉 Menor histórico: R$ 195,00
⭐ 8.1 · 🧠 2.9/5
```

### 4. Disambiguation — "Jogo errado?"

**Current problem:** `_resolve_game` fetches `rows=1` — always silently picks the first Ludopedia result.

**New flow:**
- Fetch `rows=5` from Ludopedia on every query
- Result #1 is shown immediately as the `send_photo` reply, with two inline buttons:
  - "Jogo errado?" → triggers disambiguation
  - "Resultado errado?" → existing Amazon ASIN correction flow
- On "Jogo errado?": send a new photo message using result #2's thumbnail, with inline keyboard buttons for results #2–5 (`"Wingspan: Oceania (2020)"`, etc.)
- Selecting a result triggers a fresh price lookup for that game → new photo message

### 5. Link support for `/preço`

Accept URLs directly instead of a game name:

| Input | Behavior |
|-------|----------|
| `/preço https://ludopedia.com.br/jogo/wingspan` | Extract slug → call Ludopedia API directly |
| `/preço https://ludopedia.com.br/anuncio/12345` | Extract game from listing page |
| `/preço https://boardgamegeek.com/boardgame/266192/wingspan` | Extract BGG ID → search Ludopedia by name via BGG XML API |

### 6. Enable wishlist scraper

- Set `WISHLIST_ENABLED=True` in Vercel env vars
- Amazon prices flow for all wishlist games; other games show "Preço indisponível" — acceptable at launch
- Grow the wishlist manually using `search_count DESC` data after launch

---

## Phase 2 — Engagement

### 7. `/quero` + watchlist + alerts

**Data model:**
```
watchlist
  id                  INT  PK
  user_id             BIGINT  FK → users.telegram_user_id
  game_id             INT  FK → games.ludopedia_id
  alert_threshold_brl NUMERIC(10,2)  nullable
  created_at          DATETIME
```

**Commands:**
- `/quero <jogo>` — adds game to watchlist; bot follows up with inline buttons: "Quer receber alerta de preço? R$100 / R$150 / R$200 / R$250 / Outro valor / Pular"
- `/lista` — shows all watched games with current prices and thresholds
- `/alertar <jogo> <preço>` — set or update threshold on an existing watchlist item
- `/alertas` — list active alerts with thresholds
- `/cancelar-alerta <jogo>` — remove threshold (keeps game on watchlist)

### 8. Daily C2C cron for watched games + alert check

New Vercel Cron Job (`0 10 * * *`) → `GET /cron/scrape-watched`:
1. Fetch all games that have at least one watchlist entry
2. Re-scrape Ludopedia C2C for each game → update `ludopedia_listings`
3. For each watchlist entry with a threshold: compare current C2C avg (and Amazon price if available) against threshold
4. Send Telegram message to user when threshold is crossed

Alert message format:
```
📉 Alerta de preço: Wingspan
C2C Novo: R$ 175,00 (abaixo do seu limite de R$ 200,00)
→ ver anúncios
```

---

## Phase 3 — Ops Dashboard

FastAPI + Jinja2, protected by HTTP Basic Auth, deployed as a Vercel route (`/admin`).

**Pages:**
- **Games** — table of all games: title, thumbnail, search_count, ASIN, bgg_id, last scraped. Click to open game detail.
- **Game detail** — price history chart (Chart.js), current C2C listings, ASIN correction form
- **Cron log** — last run time + result for each cron job (wishlist scraper, watched-games scraper)
- **Users / Watchlist** — user count, watchlist entries, games most watched

---

## Post-launch

- **MercadoLivre scraper** — highest-value multi-store addition; requires Playwright (heavier). Build after validating demand via `search_count`.
- **Amazon PA API** — when credentials arrive, set `WISHLIST_ENABLED=False` to retire the wishlist scraper. `amazon.py` is already implemented.

### Under evaluation (pursue later)

- **Keepa API** — provides Amazon price history going back years for any ASIN, including amazon.com.br (domain 11). Python library available (`keepa` on PyPI). Blocked by cost: €49/month floor with no free tier. Revisit if PA API credentials take too long or if users demand deeper price history than our own `price_history` table can provide. Would replace both the wishlist scraper and lowest-ever logic.

- **Amazon.com (US) → Brazil pricing** — some US products ship to Brazil with estimated import taxes shown dynamically. Scraping requires simulating a Brazilian delivery address in the session; tax calculation is dynamic and fragile. Total landed cost is rarely competitive vs. amazon.com.br for board games. Revisit only after MercadoLivre is live and there is explicit user demand for cross-border pricing.

---

## Architecture

```
User → Telegram → POST /webhook → Vercel (FastAPI)
                                       ↓
                              Neon PostgreSQL
                                       ↓
                    Ludopedia API + Marketplace scraper
                    BGG XML API (enrichment)
                    Amazon wishlist scraper (daily cron)
                    Watched-games C2C scraper (daily cron)
```

**Local dev:** `docker compose up -d` (Postgres) + `uv run python main.py` (polling)
**Production:** Vercel webhook, always on, zero cost
