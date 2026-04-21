import asyncio
import logging

from src.bot.main import build_application
from src.database import Base, engine

logging.basicConfig(level=logging.INFO)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def main() -> None:
    asyncio.run(init_db())
    app = build_application()
    app.run_polling()


if __name__ == "__main__":
    main()
