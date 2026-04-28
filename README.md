# GameHuntr

Telegram bot for Brazilian board game price tracking. Send `/preço <jogo>` and get:

- **C2C price** — average of "Novo" listings on Ludopedia Marketplace
- **Amazon price** — current price + in-stock status
- **Lowest ever** — historical minimum price recorded

## Commands

| Command | Description |
|---------|-------------|
| `/preço <jogo>` | Search game and return current prices |
| `/preco <jogo>` | ASCII alias (works when `ç` is hard to type) |

> BotFather only supports ASCII command names for autocomplete. `/preço` works when typed manually; `/preco` shows in autocomplete.

## Architecture

```
User → Telegram → POST /webhook → Vercel (FastAPI, serverless)
                                        ↓
                               Neon PostgreSQL (free tier)
                                        ↓
                    Ludopedia API + Marketplace scraper (httpx)
                    Amazon PA API  ← or wishlist scraper (daily cron)
```

**Local dev** uses Docker Compose (Postgres) + polling mode.
**Production** runs on Vercel webhook, always on, zero cost.

## Local Setup

**Requirements:** Python 3.11+, [uv](https://github.com/astral-sh/uv), Docker

```bash
# 1. Copy and fill in env vars
cp .env.example .env

# 2. Start local PostgreSQL
docker compose up -d

# 3. Run migrations
uv run alembic upgrade head

# 4. Start bot (polling mode)
uv run python main.py
```

## Deploy (Vercel + Neon)

```bash
# 1. Create a Neon project at neon.tech, copy the connection string

# 2. Run migrations against Neon
DATABASE_URL="<neon-url>" uv run alembic upgrade head

# 3. Install Vercel CLI and deploy
npm install -g vercel
vercel --prod

# 4. Set all env vars in Vercel dashboard (or via CLI)

# 5. Register the Telegram webhook
uv run python scripts/setup_webhook.py https://your-app.vercel.app
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `TELEGRAM_BOT_TOKEN` | ✅ | From @BotFather |
| `LUDOPEDIA_ACCESS_TOKEN` | ✅ | Ludopedia API token |
| `AMAZON_ACCESS_KEY` | — | Amazon PA API key (optional until obtained) |
| `AMAZON_SECRET_KEY` | — | Amazon PA API secret |
| `AMAZON_PARTNER_TAG` | — | Amazon Associates tag |
| `WISHLIST_ENABLED` | — | `true` to activate wishlist scraper |
| `WISHLIST_URL` | — | Amazon public wishlist URL to scrape |
| `CRON_SECRET` | — | Auto-provided by Vercel for cron authentication |

## Wishlist Scraper

A bridge for Amazon prices until PA API credentials are available.

- Scrapes a public Amazon wishlist daily at noon UTC
- Matches each item to a Ludopedia game by title
- Prices appear on the next `/preço` call

**Enable:** set `WISHLIST_ENABLED=true` and `WISHLIST_URL=<your-wishlist-url>` in Vercel env vars.
**Disable:** set `WISHLIST_ENABLED=false` when PA API keys are configured.

## Common Commands

```bash
# Local bot (polling)
uv run python main.py

# Run migrations
uv run alembic upgrade head

# Test price lookup directly
uv run python scripts/test_preco.py "Castle Combo"

# Register Telegram webhook
uv run python scripts/setup_webhook.py https://your-app.vercel.app

# Deploy to Vercel production
vercel --prod
```
