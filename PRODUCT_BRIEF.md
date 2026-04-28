# GameHuntr — Product Brief

Telegram bot for Brazilian board game price tracking. Returns Amazon price, Ludopedia C2C marketplace average, and the lowest price ever recorded — all from a single `/preço` command.

---

## Current State

- `/preço <jogo>` — looks up a game, scrapes Ludopedia C2C listings, queries Amazon PA API, returns prices + lowest ever
- Deployed on Vercel (serverless webhook) + Neon PostgreSQL, free tier, always on
- Price history stored per game for lowest-ever tracking
- Ludopedia Marketplace scraper working (httpx + BeautifulSoup)
- Amazon PA API integrated but awaiting real credentials

---

## Next Steps

### 1. Rename command + README + config cleanup
- `/preço` as primary command (keep `/preco` as ASCII alias — BotFather only supports ASCII for autocomplete)
- `README.md` with setup, deploy, and env var docs
- `config.py`: fix `env_file_encoding="utf-8-sig"` (Windows BOM); make Amazon keys optional (no crash when unset)

### 2. Amazon wishlist scraper (daily cron)
Bridge to Amazon prices until PA API credentials are available.

**Wishlist:** `https://www.amazon.com.br/hz/wishlist/ls/SNXDXF4S9XUI`

- Scrape wishlist daily → extract (ASIN, title, price) for each item
- Match each item to a Ludopedia game by title search
- Store price in `listings` + `price_history` — available on next `/preço` call
- Vercel Cron Job at 9am UTC (`0 9 * * *`) → `GET /cron/scrape-wishlist`
- **Toggle:** `WISHLIST_ENABLED` env var — set to `False` when PA API is live

**Files:** `src/scrapers/amazon_wishlist.py`, cron endpoint in `src/api/webhook.py`, `vercel.json` crons, `.env.example`

### 3. Amazon PA API credentials
- Obtain keys from Amazon Associates program
- Add real `AMAZON_ACCESS_KEY` + `AMAZON_SECRET_KEY` to Vercel env vars
- `amazon.py` is already implemented — prices appear automatically
- Set `WISHLIST_ENABLED=False` to retire the scraper

### 4. Price drop alerts
- `/alertar <jogo> <preço>` — notify when price drops below threshold
- New `alerts` table: `game_id`, `chat_id`, `threshold_brl`
- Daily cron (extend Step 2's job) checks all active alerts
- Sends Telegram message when threshold is crossed
- `/alertas` to list; `/cancelar-alerta` to remove

### 5. `/quero` personal watchlist
- `/quero <jogo>` — adds game to a watchlist (new `watchlist` table)
- `/lista` — shows all watched games with current prices
- Feeds into Step 4 (alerts on watchlist items)

### 6. Multi-store support
- `Store` + `Listing` model is already generic
- Add scrapers for MercadoLivre, Girafa, NetShop
- `/preço` output gains one row per store

---

## Architecture

```
User → Telegram → POST /webhook → Vercel (FastAPI)
                                       ↓
                              Neon PostgreSQL
                                       ↓
                    Ludopedia API + Marketplace scraper
                    Amazon PA API (or wishlist scraper)
```

**Local dev:** `docker compose up -d` (Postgres) + `uv run python main.py` (polling)
**Production:** Vercel webhook, always on, zero cost
