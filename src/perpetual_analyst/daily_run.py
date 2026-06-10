"""Daily pipeline orchestrator. See SPEC §12 Phase 3."""

# TODO (Task 10): Implement
# Entry point: python -m perpetual_analyst.daily_run
#
# Pipeline:
# 1. init_db()
# 2. retry_undelivered() — catch up any yesterday failures
# 3. For each active topic:
#    a. ingest (inbox, then RSS if Phase 2+)
#    b. triage new items (Phase 2+)
#    c. run_topic(topic_id, dry_run=dry_run)  ← wrapped in try/except, isolated
# 4. assemble_report(topic_analyses, date)
# 5. send_report(report_id)
#
# CLI flags (via typer or argparse):
#   --dry-run: print assembled prompts, skip API calls and Telegram
#   --topic SLUG: run for one topic only
#
# Error isolation: one failing topic must NOT kill the run for others.
# Log each topic's outcome. Exit 0 even if some topics failed (partial success).
