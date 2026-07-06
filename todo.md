# Roadmap moved

The phased roadmap now lives in **`docs/plans/ludopedia-listing-crawler.md`** (unified design, 2026-07-06), which merged this file's phases with the marketplace crawler plan:

- Phase 0 — Termos de Uso, UA/contact decision
- Phase 1 — Bot launch readiness (was Phase 1 here: search_count, /start + /help, send_photo + BGG, disambiguation, link support, PA API)
- Phase 2 — Unified marketplace foundation (marketplace_listings table, upsert refactor, produto parser)
- Phase 3 — Nightly sitemap sync + one-time sweep; price_export reads C2C from DB
- Phase 4 — Engagement (was Phase 2 here: watchlist, alerts — now driven by the nightly sync)
- Phase 5 — Ops & surfacing (was Phase 3 here: admin dashboard; plus "últimas vendas")
- Deferred — forward monitor, gap probe, MercadoLivre scraper

See also `PRODUCT_BRIEF.md` for feature details (caption formats, disambiguation flow, dashboard contents).
