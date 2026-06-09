---
status: complete
phase: 11-parit-sync-async-compl-te
source: [11-01-SUMMARY.md, 11-02-SUMMARY.md, 11-03-SUMMARY.md, 11-04-SUMMARY.md, 11-05-SUMMARY.md, 11-06-SUMMARY.md, 11-07-SUMMARY.md]
started: 2026-06-09T13:25:52Z
updated: 2026-06-09T13:32:30Z
---

## Current Test

[testing complete]

## Tests

### 1. Full test suite green at the 90% gate
expected: `uv run pytest` passes; terminal reports "Required test coverage of 90% reached. Total coverage: ~91.6%". The only 2 failures are the documented pre-existing ones (test_async_transaction_fix, test_create_spatial_index_name_parameter) — not Phase 11 regressions.
result: pass

### 2. Async constraint DDL works (PAR-01)
expected: On `AsyncDatabase`, `await adb.add_primary_key(...)`, `add_foreign_key(... on_delete="CASCADE")`, `add_unique_constraint(...)`, and `truncate_table(...)` apply real constraints on the live DB — FK cascade deletes children, a duplicate insert into the unique column is rejected, and an invalid `on_delete` action raises `ValueError`.
result: pass

### 3. Async admin methods + async constructors (PAR-02)
expected: `await adb.database_exists("pycopg_test")` → True; `await adb.list_databases()` includes it; `await adb.drop_extension(...)` is idempotent; and `await AsyncDatabase.create(...)` / `create_from_env(...)` return a connected async instance (creating the DB if absent).
result: pass

### 4. Sync batch / stream / notify (PAR-03)
expected: On `Database`, `db.insert_many(...)` / `db.upsert_many(...)` write rows, `db.stream("SELECT ...")` yields rows lazily in batches, and `db.notify(channel, payload)` fires a NOTIFY (via pg_notify) without error. `listen` is intentionally NOT on the sync class (async-only by design).
result: pass

### 5. C1 — async DataFrame load applies primary_key (PAR-04)
expected: `await adb.from_dataframe(df, "tbl", primary_key="id")` (and `from_geodataframe`) actually creates the primary key on the table — no more "primary_key ignored" warning. Querying the table's constraints shows the PK present.
result: pass

### 6. C2 — async close() releases the engine (PAR-05)
expected: After `await adb.close()`, the async engine is disposed and pooled connections are released; calling `close()` again is a harmless no-op (idempotent). Previously `close()` did nothing.
result: pass

### 7. C3 — async uses the async driver (PAR-06)
expected: `Config(...).async_url` returns a string starting `postgresql+psycopg_async://`, while `Config(...).url` is unchanged (`postgresql+psycopg://`). `AsyncDatabase(...).async_engine.url` reflects the async driver.
result: pass

### 8. Signature alignment sync ↔ async (PAR-07)
expected: `await adb.create_extension("postgis", schema="public")` and `await adb.create_schema("s", owner="somerole")` accept the same `schema`/`owner` params the sync API has; `table_info` and `list_roles` return identical fields on both sides.
result: pass

### 9. Parity is guaranteed by tests (PAR-08)
expected: `uv run pytest tests/test_parity.py` passes (17 tests) — every method this phase touched is asserted to behave identically sync vs async on the real DB, and the allow-lists are minimal (only `engine`/`async_engine` plus the by-design async-only `listen` remain documented exceptions).
result: pass

### 10. drop_extension rejects a malicious name (T-11-07 security guard)
expected: `db.drop_extension('postgis"; DROP DATABASE x; --')` (and the async form) raises `InvalidIdentifier` before any SQL runs, while a legitimate hyphenated name like `"uuid-ossp"` is accepted. Verified by `uv run pytest tests/test_sql_injection.py -k drop_extension` (3 green).
result: pass

## Summary

total: 10
passed: 10
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
