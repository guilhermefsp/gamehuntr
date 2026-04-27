# boardgame-tracker — Claude Instructions

**Project path:** `D:\The Brain\raw\projects\boardgame-tracker`

## Shell conventions

- **Bash:** Never `cd` + command — triggers a permission prompt. Use `uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" ...` instead.
- **PowerShell:** Use for process management and any command with leading-slash args (e.g. Telegram `/preco`) — Git Bash mangles them into filesystem paths.

## Common commands

| Task | Command |
|------|---------|
| Start PostgreSQL | `docker compose -f "raw/projects/boardgame-tracker/docker-compose.yml" up -d` |
| Run bot | `uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" python main.py` |
| Kill bot | PowerShell: `Get-Process python* \| Stop-Process -Force` |
| Run migration | `DATABASE_URL="postgresql+asyncpg://gamehunter:gamehunter@localhost:5432/gamehunter" uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" alembic upgrade head` |
| Test stack | `uv run --directory "D:/The Brain/raw/projects/boardgame-tracker" python scripts/test_preco.py "Castle Combo"` |
| Test via Telegram | PowerShell: `cd "D:\The Brain\raw\projects\boardgame-tracker"; uv run python scripts/test_telegram.py "/preco Castle Combo"` |
