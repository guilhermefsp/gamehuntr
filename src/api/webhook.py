from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update

from src.bot.main import build_application

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


@app.get("/")
async def health():
    return {"status": "ok"}
