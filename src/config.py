from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig")

    database_url: str
    telegram_bot_token: str
    ludopedia_access_token: str

    # Amazon PA API — optional until credentials are obtained
    amazon_access_key: str = "unset"
    amazon_secret_key: str = "unset"
    amazon_partner_tag: str = ""
    amazon_country: str = "BR"

    # Wishlist scraper — set WISHLIST_ENABLED=true to activate
    # Disable (set to false) once Amazon PA API credentials are available
    wishlist_enabled: bool = False
    wishlist_url: str = ""

    # Vercel cron authentication (auto-provided by Vercel)
    cron_secret: str | None = None

    # Optional — only needed for Claude's Telegram testing scripts
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session: str | None = None
    telegram_bot_username: str | None = None

    @model_validator(mode="before")
    @classmethod
    def strip_bom(cls, values: dict) -> dict:
        """Strip UTF-8 BOM (﻿) injected by some Windows tools when setting env vars."""
        return {k: v.lstrip("﻿") if isinstance(v, str) else v for k, v in values.items()}


settings = Settings()
