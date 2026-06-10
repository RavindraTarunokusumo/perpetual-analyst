"""Telegram send: HTML digest (≤3,000 chars) + .md file attachment. See SPEC §10."""

# TODO (Task 10): Implement
# - send_report(report_id: int, db: Connection) -> None
#   - read report row from DB
#   - send digest_text as HTML message (≤3,000 chars)
#   - send full_markdown as document (brief-YYYY-MM-DD.md)
#   - set reports.delivered_at = datetime('now') on success
#   - raise on Telegram error (caller handles retry)
#
# - retry_undelivered(db: Connection) -> None
#   - find reports WHERE delivered_at IS NULL AND created_at < datetime('now', '-1 hour')
#   - attempt send for each; log failures
#
# V1: send-only. No inbound commands, no polling listener.
