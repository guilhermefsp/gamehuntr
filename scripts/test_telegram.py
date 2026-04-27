"""
Sends a command to the bot via your Telegram account and prints the final reply.
Skips the bot's interim "Buscando..." placeholder and waits for the edited result.

Usage: uv run python scripts/test_telegram.py "/preco Castle Combo"
"""
import asyncio
import sys

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.config import settings


async def main(command: str) -> None:
    async with TelegramClient(
        StringSession(settings.telegram_session),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    ) as client:
        bot_username = settings.telegram_bot_username
        result: asyncio.Future = asyncio.get_event_loop().create_future()

        async def on_any(event):
            text = event.message.text or ""
            # Ignore the interim placeholder
            if "Buscando" in text:
                return
            if not result.done():
                result.set_result(text)

        client.add_event_handler(on_any, events.NewMessage(from_users=bot_username))
        client.add_event_handler(on_any, events.MessageEdited(from_users=bot_username))

        print(f"Sending to {bot_username}: {command!r}")
        await client.send_message(bot_username, command)

        try:
            reply = await asyncio.wait_for(result, timeout=20)
            print("\n--- Bot reply ---")
            print(reply)
        except asyncio.TimeoutError:
            print("No final reply within 20 seconds.")


if __name__ == "__main__":
    cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "/preco Castle Combo"
    asyncio.run(main(cmd))
