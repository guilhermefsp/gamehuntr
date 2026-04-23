from collections.abc import Callable

from telegram.ext import Application

from src.bot import handlers
from src.config import settings


def build_application(post_init: Callable | None = None) -> Application:
    builder = Application.builder().token(settings.telegram_bot_token)
    if post_init:
        builder = builder.post_init(post_init)
    app = builder.build()
    handlers.register(app)
    return app
