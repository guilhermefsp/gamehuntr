"""
One-time script to register the Telegram webhook URL.
Usage: uv run python scripts/setup_webhook.py https://your-app.vercel.app
"""
import sys

import httpx

from src.config import settings

if len(sys.argv) != 2:
    print("Usage: uv run python scripts/setup_webhook.py https://your-app.vercel.app")
    sys.exit(1)

url = sys.argv[1].rstrip("/")
r = httpx.post(
    f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
    json={"url": f"{url}/webhook"},
)
print(r.json())
