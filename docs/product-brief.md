# Board Game Price Tracker — Product Brief

**Working name:** CaçaJogos (provisional — may change)
**Status:** Pre-development — architecture decided, ready to build
**Created:** 2026-04-14
**Decisions locked:** 2026-04-21
**Market:** Brazil (international expansion later)

---

## Decisions (2026-04-21)

| Decision | Choice |
|----------|--------|
| MVP platform | Telegram-first (website deferred to v2) |
| First vertical | Amazon PA API end-to-end, then Phase 1 scrapers |
| Game catalog | Lazy — on-demand via Ludopedia API, `ludopedia_id` as primary key |
| ASIN matching | Auto-pick Amazon top result; "Resultado errado?" inline button shows top 3–5 for user correction |
| Ludopedia auth | Static app token in env var — no user OAuth for MVP |
| Bot output | Game name + price + stock status + affiliate link + lowest price ever |
| Architecture | Single process (bot + API + scheduler in one service) |
| Dev setup | Long-polling locally; Railway for production |
| Price alerts | Deferred to v2 |

---

## Core Concept

A service that aggregates board game prices from Brazilian retailers, tracks price history, and alerts users when prices drop. Think Buscapé/Zoom but specialized for tabletop games.

Target user: Brazilian board game buyer who wants to know the best time and place to buy a specific title.

---

## Competitive Landscape

| Competitor | Type | Overlap | Our Differentiation |
|-----------|------|---------|---------------------|
| ComparaJogos (comparajogos.com.br) | Specialized BR | Medium — both have "price comparison" | Price history over time, alerts, retail focus vs. C2C |
| Zoom / Buscapé | General BR aggregators | Low — cover Amazon but no depth | Board game catalog, BGG/Ludopedia integration, alerts, community |

**ComparaJogos** is a C2C marketplace (used games between users) built on Discourse, launched recently (ToS updated April 2026, marketplace in restricted beta). ~3,500 active users/week. They have price comparison in name but focus on user-to-user sales, not retail store tracking. They have no price history, no alerts, no Telegram bot, no retail scraping.

**Key insight:** ComparaJogos and CaçaJogos serve different purchase intents. "Buy new at the best retail price" (CaçaJogos) vs. "buy used from another collector" (ComparaJogos). Opportunity: include C2C prices from ComparaJogos as a source alongside retail — showing new vs. used price on the same page.

**The moat is price history.** Every month of data collected before launch is a permanent advantage. Start scrapers in silent mode before public launch.

---

## Platform Options

### Option A: Website Only
**Pros:** SEO discovery (organic traffic), shareable links, rich UI (charts, filtering), no app store friction, easiest to monetize with ads/affiliates
**Cons:** No native notifications, user must remember to check, higher dev complexity upfront

### Option B: Telegram Bot Only
**Pros:** Zero install friction, push notifications are native, easy to build v1 fast, Brazil has very high Telegram penetration, interactive commands feel natural
**Cons:** No SEO, discovery only through word-of-mouth/sharing, UI is constrained, harder to show price history charts, monetization is harder

### Option C: Website + Telegram Bot (Recommended) ✓ DECIDED — Telegram-first
**Pros:** Website is the discovery/browsing surface; Telegram handles alerts and power-user interaction; they share the same backend
**Cons:** More work, but the split is clean — same data, two frontends
**Decision:** Build Telegram bot first for MVP. Website comes in v2 once data pipeline is proven.

### Option D: PWA (Progressive Web App)
Basically a website that can be "installed" on mobile and send push notifications. Gets you 80% of an app experience without the Play Store. Worth considering as an upgrade path from Option C.

---

## Data Acquisition

### Amazon BR
Has the **Product Advertising API** (PA API 5.0) — requires an active Associates account and approval. Returns price, availability, images, buy link (already with your affiliate tag). Cleanest integration. **First vertical for MVP** — build end-to-end before any scrapers.

**ASIN matching strategy:** Search Amazon PA API by game title → auto-pick top result → store `asin ↔ ludopedia_id` mapping in DB. Bot message includes a "Resultado errado?" inline button that surfaces top 3–5 results for user correction. Wrong mappings are fixed by users, not pre-curated.

### Ludopedia
Has a new **official API (LudoAPI v0.0.5, Alpha)** — OAuth 2.0, base URL `https://ludopedia.com.br/api/v1/`. Register an app at `ludopedia.com.br/aplicativos`.

**Auth decision:** Registering an app auto-generates an `access_token` tied to the app owner's account. This static token is sufficient for all game catalog endpoints (`GET /jogos`, `GET /jogos/{id_jogo}`). No user OAuth flow needed for MVP — store the token in an env var. User OAuth (for importing user collections) is a v2 feature.

**What the API provides:**
- Game search and full game details: name, thumbnail URL, player counts, playtime, mechanics, categories, themes, designers, artists
- Popularity metrics unique to Brazil: `qt_tem` (own), `qt_quer` (want), `qt_jogou` (played), `qt_favorito`
- User collection and play logs via user OAuth — enables "import your Ludopedia collection" feature
- Thumbnail URL pattern: `https://storage.googleapis.com/ludopedia-capas/{id_jogo}_t.jpg`

**What the API does NOT provide (yet — marked `não implementado`):**
- Per-game reviews/ratings (`/notas`)
- Image gallery (`/imagens`)
- Videos (`/videos`)
- Marketplace listings (user-to-user sales) — **always requires scraping**

The marketplace (`ludopedia.com.br/anuncios`) still needs scraping for second-hand prices. The API fully replaces scraping for game catalog data.

### Stores — Phase 1 (First Scrapers)

These three are the initial scraping targets for the MVP:

| Store | URL | Notes |
|-------|-----|-------|
| Loja Lúdica | https://lojaludica.com.br/ | Priority 1 |
| Bravo Jogos | https://bravojogos.com.br/ | Priority 1 |
| Masmorra | https://www.masmorra.com.br/ | Priority 1 |

### Stores — Phase 2 (Backlog)

| Store | Notes |
|-------|-------|
| Buró Games | Major specialized retailer |
| Meeple BR | Big online store |
| Jogo de Tabuleiro | Another major retailer |
| Shopee / Mercado Livre | Marketplace — harder, inconsistent listings |
| Devir Brasil | Publisher with direct sales |

### Crowdfunding Platforms

Track retail price of a game **after** the campaign ends. Only store the final retail price from the campaign page — not pledge tiers or early bird prices.

| Platform | Notes |
|----------|-------|
| *(to be added)* | |

### Scraping Strategy
- **Python + Playwright** (headless browser) for JS-rendered pages; **httpx + BeautifulSoup** for static HTML — use the lighter tool first
- Schedule scrapers every 4–12h per store (more frequent = more blocking risk)
- Rotate User-Agents, add delays, respect `robots.txt`
- Store raw HTML snapshots so you can re-parse without re-fetching if structure changes
- **Anti-blocking options:** polite delays + retry logic first; residential proxies as fallback (adds cost)

---

## Data Model (Simplified)

```
Game
  ludopedia_id   ← PRIMARY KEY — Ludopedia id_jogo (Brazilian canonical)
  bgg_id         ← optional, add when available
  asin           ← Amazon ASIN, populated on first search + user-confirmed
  title, thumbnail, players, duration
  qt_quer        ← "want to buy" count from Ludopedia (Brazilian demand signal)

Store
  name, base_url, affiliate_tag

Listing (many per Game × Store)
  game_id, store_id
  url, price_brl, in_stock
  scraped_at

PriceHistory
  listing_id, price_brl, in_stock, recorded_at

Alert (user-configured)  ← v2, not MVP
  user_id, game_id, target_price_brl
```

**Catalog strategy (decided):** Lazy — no pre-seeded catalog. Games are added to DB on first search via Ludopedia API. `ludopedia_id` is the primary key. BGG ID stored when available but not required for MVP.

**Note on game identity:** Same game sold under different names/editions needs deduplication. Ludopedia `id_jogo` is the Brazilian canonical key for MVP. BGG ID added later for global metadata.

---

## Feature Tiers

### MVP (v1)
- Game search by name
- Current price from 3–5 stores side by side
- Direct buy links (with affiliate tag)
- "Lowest price ever" indicator
- Telegram bot: `/preco Wingspan` returns current prices + links

### v2
- Price history chart (30/90/180 days)
- Price drop alerts via Telegram
- Wishlist: save games, get notified
- Ludopedia integration: import wishlist/collection

### v3
- "Best time to buy" signal (pattern analysis on price history)
- Shipping cost estimation by CEP
- International stores with currency + shipping + import tax conversion
- Portfolio tracker (games you own, current resale value)
- Community-reported prices (Mercado Livre, etc.)

---

## UX Flow

```
User searches "Ark Nova"
  → Sees: [Amazon R$279 ✓] [Buró R$310 ✓] [Meeple R$295 ✗ out of stock]
  → Clicks "Alert me when below R$250"
  → Bot DMs them when price hits target
```

Key UX decisions:
- **Shipping changes the real price.** Even a "include shipping" toggle would be valuable and differentiating.
- **Out-of-stock tracking** is almost as valuable as price — knowing something was R$180 last month helps you judge the current R$220.
- **International imports:** 60%+ import tax in Brazil makes "landed cost" estimation very useful.

---

## Monetization Options

### 1. Affiliate Links (Best Fit — implement from day one)
Amazon Associates pays ~3–8% commission on sales driven through your links. Other stores (Buró, Meeple) likely have affiliate programs or would negotiate a deal. Every "buy" click earns something. Low friction for users, scales with traffic.

### 2. Display Ads
Google AdSense or similar. Board game audience is niche but engaged. Revenue is low until traffic is significant (~10k+ monthly visitors). Best as a secondary passive layer.

### 3. Featured Store Listings
Charge stores to appear first in results or get a "verified" badge. Requires traffic leverage to negotiate. v3+ play.

### 4. Freemium Tier

| Free | Premium (~R$15/mo) |
|------|-------------------|
| Current prices | Full price history charts |
| 3 price alerts | Unlimited alerts |
| Manual search | Weekly personalized digest |
| — | Portfolio tracking |
| — | Import Ludopedia collection |

Freemium works when the free tier is genuinely useful (drives retention) and the paid tier solves real pain (history + more alerts).

### 5. Data/API Access
Sell API access to stores, publishers, or other developers. Long-tail revenue, but the dataset has real value if the coverage is comprehensive.

**Recommended combo:** Affiliate links as primary revenue from day one → display ads as passive layer → freemium as v2 upgrade once there's a user base.

---

## Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Scrapers | Python + Playwright / httpx | Scraping-native ecosystem |
| Backend API | FastAPI | Fast to build, async-friendly |
| Database | PostgreSQL | Price history needs a real relational DB |
| Task queue | APScheduler or Celery + Redis | Scheduled scraping jobs |
| Telegram Bot | python-telegram-bot | Mature, well-documented |
| Frontend | SvelteKit or Next.js | v2 — deferred |
| Hosting | Railway | São Paulo region, managed PostgreSQL, simplest deploy |

---

## Risks & Open Questions

| Risk | Notes |
|------|-------|
| **BGG API licensing** | Registration now required (Bearer token). BGG can **deny applications that compete with their business** — a price tracker that drives purchases away from BGG's marketplace is an explicit risk case. Commercial license required for monetized apps; free until 1,000 ad-supported users or 100 paying users, then fees possible. Must show "Powered by BGG" logo. Mitigation: use BGG only for game metadata (name, image, mechanics), never for pricing decisions. |
| Amazon Associates ToS | **No explicit ban on price comparison sites** in the Associates agreement (reviewed 2026-04-14). Must show required disclosure on all pages with Amazon links: *"Como participante do Programa de Associados da Amazon, sou remunerado pelas compras qualificadas efetuadas."* Amazon can terminate for "brand damage" — subjective clause. PA API has separate terms (not yet reviewed). |
| Legal/ToS (scraping) | Scraping store pages without permission is a grey area. Amazon prices come via PA API (clean). For other stores, check robots.txt and ToS individually. |
| Scraper maintenance | Every store redesign breaks a scraper. Budget ongoing maintenance time. |
| Game deduplication | "Wingspan: Oceania" vs "Wingspan + Oceania bundle" — fuzzy matching + BGG ID + Ludopedia ID is the approach. |
| Ludopedia cooperation | They have a new API and may welcome a partnership. Worth a cold email early. |
| Import tax complexity | Customs calculation for international orders is complex — show a disclaimer for v1. |

---

## Repository Structure (Planned)

```
cacajogos/
├── docs/
│   └── product-brief.md     ← this file
├── src/
│   ├── scrapers/             ← one module per store
│   ├── api/                  ← FastAPI backend
│   ├── bot/                  ← Telegram bot
│   └── frontend/             ← web UI
├── scripts/
│   └── seed_bgg.py           ← populate game DB from BGG API
├── tests/
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## Next Steps (ordered build plan)

1. Register Ludopedia app at ludopedia.com.br/aplicativos → copy auto-generated `access_token`
2. Initialize git repo at `raw/projects/boardgame-tracker/` with planned folder structure
3. Set up project skeleton — `pyproject.toml`, env var config, Docker Compose for local PostgreSQL
4. Define DB schema — `games`, `stores`, `listings`, `price_history` tables, migrations with Alembic
5. Build Ludopedia search — `GET /jogos?search=` wrapper, cache result to `games` table
6. Build Amazon PA API search — keyword → top ASIN, store `asin` on the game record
7. Build `/preco` bot command — search → lookup → format message → "Resultado errado?" button flow
8. Wire the scheduler — APScheduler job that re-fetches Amazon prices on schedule, updates `price_history`
9. Deploy to Railway — PostgreSQL addon + single service, set env vars
10. (After MVP stable) Build Phase 1 scrapers: Loja Lúdica, Bravo Jogos, Masmorra
