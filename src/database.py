import ssl as ssl_lib

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


def _make_engine():
    url = settings.database_url
    connect_args = {}
    # asyncpg doesn't accept sslmode= in the URL (that's a psycopg2 param);
    # strip it and pass SSL via connect_args instead.
    if "sslmode=require" in url:
        url = url.replace("?sslmode=require", "").replace("&sslmode=require", "")
        connect_args["ssl"] = ssl_lib.create_default_context()
    return create_async_engine(
        url,
        echo=False,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=connect_args,
    )


engine = _make_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
