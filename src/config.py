from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    telegram_bot_token: str
    ludopedia_access_token: str
    amazon_access_key: str
    amazon_secret_key: str
    amazon_partner_tag: str
    amazon_country: str = "BR"

    # Optional — only needed for Claude's Telegram testing scripts
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session: str | None = None
    telegram_bot_username: str | None = None


settings = Settings()
