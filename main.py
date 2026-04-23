import logging

from telegram.ext import Application

from src.bot.main import build_application
from src.database import Base, engine

logging.basicConfig(level=logging.INFO)


async def post_init(application: Application) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def main() -> None:
    app = build_application(post_init=post_init)
    app.run_polling()


if __name__ == "__main__":
    main()
