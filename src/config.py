from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    database_url: str
    telegram_bot_token: str
    ludopedia_access_token: str

    # Amazon Creators API credentials (replaces old PA API)
    amazon_access_key: str = "unset"      # Credential ID from Creators API portal
    amazon_secret_key: str = "unset"      # Secret from Creators API portal
    amazon_partner_tag: str = ""
    amazon_credential_version: str = "3.1"  # 3.1=NA/LWA, 3.2=EU/LWA, 3.3=FE/LWA

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
