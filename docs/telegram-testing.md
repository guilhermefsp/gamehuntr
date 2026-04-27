# Telegram Session Access for Claude

To let Claude send messages to the bot and see responses directly (without you having to relay them), you need a **Telethon user session**. This lets Claude log in as your Telegram account, send `/preco Castle Combo` to the bot, and read the reply.

## One-time setup (you do this once)

### 1. Get API credentials

Go to https://my.telegram.org → Log in → "API development tools" → Create an app (any name/platform).

You'll get:
- `api_id` (an integer, e.g. `12345678`)
- `api_hash` (a hex string, e.g. `abc123def456...`)

Add them to `.env`:
```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abc123def456...
```

### 2. Install Telethon

```bash
uv add telethon
```

### 3. Generate a session string (run once, interactive)

```bash
uv run python scripts/gen_telegram_session.py
```

This will ask for your phone number and the code Telegram sends you. It prints a **session string** — a long base64 blob that encodes your login. Copy it and add to `.env`:
```
TELEGRAM_SESSION=1BVtsOKABu3Q...
```

The session string is permanent until you revoke it from Telegram's active sessions. No phone number needed after this.

### 4. Find your bot's username

Look it up in BotFather or just note it — e.g. `@gamehunter_bot`. Add to `.env`:
```
TELEGRAM_BOT_USERNAME=@your_bot_username
```

---

## What Claude can do once this is set up

- Send any command to the bot (`/preco Wingspan`, `/preco Castle Combo`)
- Read the bot's reply text
- Report back whether the response looks correct

Claude uses `scripts/test_telegram.py` for this — it sends a message and waits up to 10 seconds for the bot's reply.

---

## Security notes

- The session string gives full access to your Telegram account. Treat it like a password.
- It lives only in `.env` (git-ignored). Never commit it.
- You can revoke it anytime: Telegram → Settings → Privacy → Active Sessions → terminate the session named after the script.
