import asyncio
import os
import ssl as ssl_lib
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine

from src.models import Base

load_dotenv()

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> tuple[str, dict]:
    url = os.environ["DATABASE_URL"]
    connect_args = {}
    if "sslmode=require" in url:
        url = url.replace("?sslmode=require", "").replace("&sslmode=require", "")
        connect_args["ssl"] = ssl_lib.create_default_context()
    return url, connect_args


def run_migrations_offline() -> None:
    url, _ = get_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url, connect_args = get_url()
    engine = create_async_engine(url, connect_args=connect_args)
    async with engine.connect() as conn:
        await conn.run_sync(lambda sync_conn: context.configure(
            connection=sync_conn, target_metadata=target_metadata
        ))
        async with conn.begin():
            await conn.run_sync(lambda _: context.run_migrations())
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
