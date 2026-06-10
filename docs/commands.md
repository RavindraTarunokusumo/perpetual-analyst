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
# Add a topic
analyst topic add "AI Frontier Labs" --brief "Track model releases, safety policy, compute trends"

# List topics
analyst topic list

# Add a source to a topic
analyst source add --topic ai-frontier-labs --type rss --url https://example.com/feed.xml

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

# Run weekly memory compaction for all active topics
analyst weekly

# Run weekly compaction for a specific topic only
analyst weekly --topic ai-frontier-labs

# Dry-run: print what the weekly review would do, skip writes
analyst weekly --topic ai-frontier-labs --dry-run
```

## Daily Pipeline (Direct)

```bash
python -m perpetual_analyst.daily_run
python -m perpetual_analyst.daily_run --dry-run
python -m perpetual_analyst.daily_run --topic ai-frontier-labs
```

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

**Linux/macOS cron** (daily at 7am + weekly compaction on Sundays at 8am):
```
0 7 * * * cd /path/to/perpetual-analyst && .venv/bin/python -m perpetual_analyst.daily_run >> logs/daily.log 2>&1
0 8 * * 0 cd /path/to/perpetual-analyst && .venv/bin/python -m perpetual_analyst.weekly_run >> logs/weekly.log 2>&1
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
