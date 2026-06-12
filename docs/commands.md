# Commands Reference

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
.venv\Scripts\activate             # Windows PowerShell

pip install -e ".[dev]"
```

Or with `uv`:
```bash
uv venv && uv pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in keys:
```bash
cp .env.example .env
```

## CLI — `analyst` Commands

```bash
# Add a topic (appends to config/topics.yaml, then syncs to DB)
analyst topic add ai-frontier-labs --name "AI Frontier Labs" --brief "Track model releases, safety policy, compute trends"

# List topics
analyst topic list

# Add a source to a topic (appends to config/sources.yaml, then syncs to DB)
analyst source add --topic ai-frontier-labs --type rss --url https://example.com/feed.xml --name "Example Feed"

# Optional: non-default DB path
analyst topic add my-topic --name "My Topic" --db-path data/alt.db
analyst source add --topic my-topic --type rss --url https://example.com/feed.xml --name "Feed" --db-path data/alt.db

# List sources for a topic
analyst source list --topic ai-frontier-labs

# Run analyst for all active topics (full pipeline)
analyst run

# Run for a specific topic only
analyst run --topic ai-frontier-labs

# Dry-run: print assembled prompt, skip API call
analyst run --topic ai-frontier-labs --dry-run

# Show today's report
analyst report show

# Show report for a specific date
analyst report show --date 2026-06-10
```

## Daily Pipeline (Direct)

```bash
python -m perpetual_analyst.daily_run
python -m perpetual_analyst.daily_run --dry-run
python -m perpetual_analyst.daily_run --topic ai-frontier-labs
```

## Testing

The package is not pip-installed in dev; set PYTHONPATH so pytest can import it:
```bash
# Unit suite (smoke tests excluded by default via addopts in pyproject.toml)
PYTHONPATH=src pytest
PYTHONPATH=src pytest tests/test_memory.py -v
PYTHONPATH=src pytest -x -k "thesis"

# Windows PowerShell
$env:PYTHONPATH="src"; pytest

# Live end-to-end smoke test (requires OPENROUTER_API_KEY + network; uses data/smoke-phase2.db)
PYTHONPATH=src pytest -m smoke
```

## Lint and Format

```bash
ruff check . --fix
ruff format .
```

## Manual Inbox Drop

Drop documents for a topic into:
```
inbox/<topic-slug>/filename.pdf
inbox/<topic-slug>/filename.md
inbox/<topic-slug>/filename.txt
```

The next `analyst run` will pick them up.

## Database

Initialize (also called automatically by `daily_run.py`):
```bash
python -c "from perpetual_analyst.store.db import init_db; init_db('data/analyst.db')"
```

Inspect the DB:
```bash
sqlite3 data/analyst.db
.tables
SELECT * FROM topics;
SELECT count(*) FROM observations;
```

## Scheduler

**Linux/macOS cron** (run daily at 7am):
```
0 7 * * * cd /path/to/perpetual-analyst && .venv/bin/python -m perpetual_analyst.daily_run >> logs/daily.log 2>&1
```

**Windows Task Scheduler** (basic via PowerShell):
```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "-m perpetual_analyst.daily_run" -WorkingDirectory "C:\path\to\perpetual-analyst"
$trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
Register-ScheduledTask -TaskName "PerpetualAnalyst" -Action $action -Trigger $trigger
```

## Environment Variables

Required:
```
OPENROUTER_API_KEY=sk-or-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Optional:
```
ANALYST_DB_PATH=data/analyst.db      # default
ANALYST_REPORTS_DIR=data/reports     # default
```

## Git Notes

Attach a structured note to the latest commit:
```bash
git notes add -m "Task: <short task title>
Summary: <brief change summary and reason>
Docs: <docs paths updated, or N/A>
TODO: <TODO.md section/item reference>
Validation: ruff, pytest" $(git log -1 --format="%H")
```
