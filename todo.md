See PRODUCT_BRIEF.md for full phased plan. Summary:

## Phase 1 — Launch Readiness
- [ ] search_count column on Game + User table (migrations)
- [ ] /start + /help commands
- [ ] /preço → send_photo with BGG rating/weight enrichment (bgg_rating, bgg_weight columns)
- [ ] Disambiguation: fetch rows=5, "Jogo errado?" → results #2-5 as new photo + inline buttons
- [ ] Link support: /preço <ludopedia_url> and /preço <bgg_url>
- [ ] Enable wishlist scraper (WISHLIST_ENABLED=True)

## Phase 2 — Engagement
- [ ] User table FK + watchlist table (migration)
- [ ] /quero + /lista + /alertar + /alertas + /cancelar-alerta
- [ ] Daily C2C cron for watched games + alert check + Telegram notifications

## Phase 3 — Ops
- [ ] Admin dashboard: /admin route, FastAPI + Jinja2, Basic Auth
  - Games table (search_count, ASIN correction)
  - Price history chart per game
  - Cron log
  - Users/watchlist overview

## Post-launch
- [ ] MercadoLivre scraper (Playwright)
- [ ] Amazon PA API (retire wishlist scraper)
