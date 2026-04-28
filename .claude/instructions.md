# boardgame-tracker — Claude Instructions

**Project path:** `D:\The Brain\raw\projects\boardgame-tracker`

## Shell conventions

- **Bash:** Never `cd` + command — triggers a permission prompt. Use `uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" ...` instead.
- **PowerShell:** Use for process management and any command with leading-slash args (e.g. Telegram `/preco`) — Git Bash mangles them into filesystem paths.

## Common commands

| Task | Command |
|------|---------|
| Start PostgreSQL | `docker compose -f "raw/projects/boardgame-tracker/docker-compose.yml" up -d` |
| Run bot (local/polling) | `uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" python main.py` |
| Kill bot | PowerShell: `Get-Process python* \| Stop-Process -Force` |
| Run migration (local) | `DATABASE_URL="postgresql+asyncpg://gamehunter:gamehunter@localhost:5432/gamehunter" uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" alembic upgrade head` |
| Run migration (Neon) | `DATABASE_URL="<neon-url>" uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" alembic upgrade head` |
| Test stack | `uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" python scripts/test_preco.py "Castle Combo"` |
| Test via Telegram | PowerShell: `uv run --directory "D:\The Brain\raw\projects\boardgame-tracker" python scripts/test_telegram.py "/preco Castle Combo"` |
| Register webhook (prod) | `uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" python scripts/setup_webhook.py https://your-app.vercel.app` |

## Deployment (Vercel + Neon)

1. Push repo to GitHub
2. Create [Neon](https://neon.tech) account → new project → copy `DATABASE_URL`
3. Run migrations against Neon (see command above)
4. Connect GitHub repo to [Vercel](https://vercel.com) → set all env vars from `.env` (use Neon `DATABASE_URL`)
5. Deploy → copy the Vercel URL
6. Register webhook (see command above)
7. Test: send `/preco Castle Combo` in Telegram
