#!/usr/bin/env bash
# Convenience wrapper for scripts/pa_inspect.py: loads repo .env (Firecrawl, etc.)
# and Nexus/.env (Postgres + Qwen secrets), then runs the inspection harness.
#
#   ./try.sh run  --topic demo --url https://example.com/article
#   ./try.sh run  --topic demo            # paste text, end with Ctrl-D
#   ./try.sh show --topic demo
#   ./try.sh ask  --topic demo "What is the biggest risk?"
#   ./try.sh reset --topic demo
set -euo pipefail
cd "$(dirname "$0")"
set -a
# shellcheck disable=SC1091
[ -f .env ] && . .env
[ -f Nexus/.env ] && . Nexus/.env
set +a
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="Nexus/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "try.sh: Nexus/.venv not found. Create it and run: $PYTHON -m pip install -e . -e ./Nexus" >&2
  exit 1
fi
if ! "$PYTHON" -c "import firecrawl" >/dev/null 2>&1; then
  echo "try.sh: installing perpetual-analyst deps (firecrawl-py) into Nexus/.venv..." >&2
  "$PYTHON" -m pip install -e ".[dev]" -q
fi
exec "$PYTHON" scripts/pa_inspect.py "$@"
