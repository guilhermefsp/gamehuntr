"""
Run once (interactive) to generate a Telethon session string.
Add the printed string to .env as TELEGRAM_SESSION=...

Usage: uv run python scripts/gen_telegram_session.py
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from src.config import settings

with TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash) as client:
    print("\n=== Telegram Session Generator ===")
    print("Follow the prompts to log in.\n")
    client.start()
    session_string = client.session.save()
    print("\n=== Session String (add to .env) ===")
    print(f"TELEGRAM_SESSION={session_string}")
    print("\nDone. You can revoke this session anytime from Telegram → Settings → Active Sessions.")
