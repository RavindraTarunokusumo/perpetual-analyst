"""SQLite connection and schema initialization. See SPEC §5 for full DDL."""

# TODO (Task 1): Implement
# - init_db(path: str = "data/analyst.db") -> sqlite3.Connection
#   - create all tables with CREATE TABLE IF NOT EXISTS
#   - create FTS5 virtual tables: items_fts, observations_fts
#   - create sync triggers for items_fts (INSERT/UPDATE/DELETE on items)
#   - create sync triggers for observations_fts (INSERT/UPDATE/DELETE on observations)
#   - enable WAL mode: PRAGMA journal_mode=WAL
#   - enable foreign keys: PRAGMA foreign_keys=ON
#
# - get_connection(path: str | None = None) -> sqlite3.Connection
#   - returns a module-level cached connection, or creates one
#   - path defaults to env var ANALYST_DB_PATH or "data/analyst.db"
#
# Full DDL is in SPEC.md §5. Reproduce it exactly here.
# FTS5 sync triggers pattern:
#   CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN
#     INSERT INTO items_fts(rowid, title, raw_text) VALUES (new.id, new.title, new.raw_text);
#   END;
#   (plus UPDATE and DELETE variants)
