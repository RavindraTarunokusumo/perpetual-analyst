# Commands Reference

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
.venv\Scripts\activate             # Windows PowerShell

pip install -e ".[dev]"
pip install -e ./Nexus             # Nexus submodule (Postgres memory substrate)
```

Or with `uv`:
```bash
uv venv && uv pip install -e ".[dev]" && uv pip install -e ./Nexus
```

Copy env files and fill in keys:
```bash
cp .env.example .env
cp Nexus/.env.example Nexus/.env
```

**Postgres** is required for the daily run. Set `DATABASE_URL` in `Nexus/.env`, then apply migrations:
```bash
cd Nexus && alembic upgrade head
```

`daily_run.py` loads `Nexus/.env` at startup so `QWEN_CLOUD_API_KEY`, `LLM_BASE_URL`, and `DATABASE_URL` are available to `substrate.py` and the Qwen client.

## CLI — `analyst` Commands

```bash
# Add a topic
analyst topic add "AI Frontier Labs" --brief "Track model releases, safety policy, compute trends"

# List topics
analyst topic list

# Add a source to a topic (starts in 'probation' status for 21 days)
analyst source add --topic ai-frontier-labs --type rss --url https://example.com/feed.xml

# List sources for a topic
analyst source list --topic ai-frontier-labs

# List pending source discovery candidates (read-only)
analyst source candidates
analyst source candidates --topic ai-frontier-labs

# Serve local source approval + quality dashboard
analyst web
analyst web --host 127.0.0.1 --port 8765

# Run analyst for all active topics (full pipeline — delegates to daily_run)
analyst run

# Run for a specific topic only
analyst run --topic ai-frontier-labs

# Dry-run: skip API calls and corpus ingest
analyst run --topic ai-frontier-labs --dry-run

# Grounded cross-session Q&A over a topic's corpus + analytical memory
analyst ask "What is the current view on open-weight models?" --topic ai-frontier-labs

# Expire overdue predictions and mark aged claims stale (no analyst call)
analyst score
analyst score --topic ai-frontier-labs
analyst score --stale-after 45

# Show today's report
analyst report show

# Show report for a specific date
analyst report show --date 2026-06-10

# Run weekly memory compaction + source discovery + quality scoring for all active topics
analyst weekly

# Run weekly for a specific topic only
analyst weekly --topic ai-frontier-labs

# Dry-run: skip model calls (compaction review + discovery); pure-SQL steps still run
analyst weekly --topic ai-frontier-labs --dry-run
```

## Daily Pipeline (Direct)

```bash
python -m perpetual_analyst.daily_run
python -m perpetual_analyst.daily_run --dry-run
python -m perpetual_analyst.daily_run --topic ai-frontier-labs
```

`analyst run` is a thin wrapper that calls `daily_run.main()`.

## Weekly Compaction (Direct)

```bash
python -m perpetual_analyst.weekly_run
python -m perpetual_analyst.weekly_run --dry-run
python -m perpetual_analyst.weekly_run --topic ai-frontier-labs
```

## Testing

```bash
pytest
pytest tests/test_memory.py -v
pytest -x -k "thesis"
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

**SQLite** (operational — initialized automatically by `daily_run.py`):
```bash
python -c "from perpetual_analyst.store.db import init_db; init_db('data/analyst.db')"
sqlite3 data/analyst.db
.tables
SELECT * FROM topics;
```

**Postgres** (memory — managed by Nexus Alembic):
```bash
cd Nexus && alembic upgrade head
# inspect with psql using DATABASE_URL from Nexus/.env
```

## Scheduler

**Linux/macOS cron** (daily at 7am + weekly compaction on Sundays at 8am):
```
0 7 * * * cd /path/to/perpetual-analyst && .venv/bin/python -m perpetual_analyst.daily_run >> logs/daily.log 2>&1
0 8 * * 0 cd /path/to/perpetual-analyst && .venv/bin/python -m perpetual_analyst.weekly_run >> logs/weekly.log 2>&1
```

Optional nightly lifecycle pass:
```
30 6 * * * cd /path/to/perpetual-analyst && .venv/bin/analyst score >> logs/score.log 2>&1
```

**Windows Task Scheduler** (basic via PowerShell):
```powershell
# Daily run
$action = New-ScheduledTaskAction -Execute "python" -Argument "-m perpetual_analyst.daily_run" -WorkingDirectory "C:\path\to\perpetual-analyst"
$trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
Register-ScheduledTask -TaskName "PerpetualAnalyst" -Action $action -Trigger $trigger

# Weekly compaction (Sundays at 8am)
$wAction = New-ScheduledTaskAction -Execute "python" -Argument "-m perpetual_analyst.weekly_run" -WorkingDirectory "C:\path\to\perpetual-analyst"
$wTrigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Sunday -At "08:00"
Register-ScheduledTask -TaskName "PerpetualAnalystWeekly" -Action $wAction -Trigger $wTrigger
```

## Environment Variables

**PA `.env`:**

Required:
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Optional:
```
ANALYST_DB_PATH=data/analyst.db      # default
ANALYST_REPORTS_DIR=data/reports     # default
OPENROUTER_API_KEY=sk-or-...         # only when discovery.provider=openrouter_web
PERPLEXITY_API_KEY=pplx-...          # only when discovery.provider=perplexity
```

**`Nexus/.env`** (loaded by `substrate.py` and `daily_run.py`):

Required for daily run:
```
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5434/nexus
QWEN_CLOUD_API_KEY=...
```

Optional:
```
LLM_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
T1_MODEL=BAAI/bge-small-en-v1.5
T2_MODEL=qwen3.6-flash
T3_MODEL=qwen3.7-max
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