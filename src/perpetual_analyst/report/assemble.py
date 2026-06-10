"""Merge per-topic sections into the daily report and write to DB. See SPEC §9."""

# TODO (Task 9): Implement
# - assemble_report(topic_analyses: dict[str, TopicAnalysis], date: str, db: Connection) -> str
#   - compose full markdown report from template (SPEC §9)
#   - call digest prompt to write exec summary (≤3,000 chars HTML)
#   - insert into reports table (report_date UNIQUE)
#   - write .md file to data/reports/brief-{date}.md
#   - return full_markdown
