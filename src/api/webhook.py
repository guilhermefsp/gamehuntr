from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update

from src import services
from src.bot.main import build_application
from src.config import settings

_bot_app = build_application()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _bot_app.initialize()
    yield
    await _bot_app.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, _bot_app.bot)
    await _bot_app.process_update(update)
    return {"ok": True}


@app.get("/cron/scrape-wishlist")
async def cron_scrape_wishlist(authorization: str | None = Header(None)):
    if settings.cron_secret and authorization != f"Bearer {settings.cron_secret}":
        raise HTTPException(status_code=401)
    result = await services.sync_wishlist_prices()
    return result


@app.get("/")
async def health():
    return {"status": "ok"}
