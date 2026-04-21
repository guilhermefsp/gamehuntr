from telegram.ext import Application

from src.bot import handlers
from src.config import settings


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    handlers.register(app)
    return app
