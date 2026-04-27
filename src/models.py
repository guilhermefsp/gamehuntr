from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Game(Base):
    __tablename__ = "games"

    ludopedia_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bgg_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    asin: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True)
    ludopedia_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str] = mapped_column(String(256))
    thumbnail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    min_players: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_players: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qt_quer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    listings: Mapped[list["Listing"]] = relationship(back_populates="game")
    ludopedia_listings: Mapped[list["LudopediaListing"]] = relationship(back_populates="game")


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    base_url: Mapped[str] = mapped_column(String(256))
    affiliate_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)

    listings: Mapped[list["Listing"]] = relationship(back_populates="store")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.ludopedia_id"))
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    url: Mapped[str] = mapped_column(String(1024))
    price_brl: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    game: Mapped["Game"] = relationship(back_populates="listings")
    store: Mapped["Store"] = relationship(back_populates="listings")
    history: Mapped[list["PriceHistory"]] = relationship(back_populates="listing")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    price_brl: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    listing: Mapped["Listing"] = relationship(back_populates="history")


class LudopediaListing(Base):
    __tablename__ = "ludopedia_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.ludopedia_id"))
    listing_url: Mapped[str] = mapped_column(String(1024))
    product_name: Mapped[str] = mapped_column(String(256))
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_brl: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_game_match: Mapped[bool] = mapped_column(Boolean)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    game: Mapped["Game"] = relationship(back_populates="ludopedia_listings")
