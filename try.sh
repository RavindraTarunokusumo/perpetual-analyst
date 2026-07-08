#!/usr/bin/env bash
# Convenience wrapper for scripts/pa_inspect.py: loads Nexus/.env (Postgres + Qwen
# secrets) and the unified venv, then runs the inspection harness.
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
[ -f Nexus/.env ] && . Nexus/.env
set +a
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
exec Nexus/.venv/bin/python scripts/pa_inspect.py "$@"
