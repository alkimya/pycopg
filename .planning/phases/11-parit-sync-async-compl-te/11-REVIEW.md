---
status: clean
phase: 11-parit-sync-async-compl-te
depth: standard
reviewed: 2026-06-09
files_reviewed:
  - pycopg/config.py
  - pycopg/database.py
  - pycopg/async_database.py
findings:
  critical: 0
  warning: 0
  info: 1
---

# Phase 11 Code Review — Parité sync/async complète

**Verdict: CLEAN.** No Critical or Warning findings. The phase's 949-line source delta
(13 mirrored methods, C1/C2 fixes, signature alignment, 2 latent-bug fixes) is consistent,
correctly validated, and matches its sync/async twins. One Info note below.

## Scope
- `pycopg/config.py` — `async_url` property.
- `pycopg/database.py` — sync `insert_many`/`upsert_many`/`stream`/`notify`; `copy_to_csv` and
  `hypertable_info` bug fixes.
- `pycopg/async_database.py` — 9 async DDL/admin methods + constructors; C1/C2 fixes;
  `create_extension`/`create_schema` signature alignment; `copy_to_csv`/`hypertable_info` fixes;
  `notify` pg_notify fix.

## Security review (SQL injection surface)
All new methods that interpolate identifiers into SQL validate them first via the Phase-10
helpers (`validate_identifiers`/`validate_identifier`/`validate_extension_name`) BEFORE any
f-string interpolation; row VALUES and lookup keys use `%s` placeholders, never f-strings:

| Method | Identifier validation | Values |
|--------|----------------------|--------|
| insert_many / upsert_many | `validate_identifiers(table, schema, *columns)` | `%s` placeholders via execute_many |
| stream | caller-owned SQL (same contract as `execute`) | `%s` |
| notify | `validate_identifier(channel)` + `SELECT pg_notify(%s, %s)` | `%s` |
| add_primary_key / add_unique_constraint | `validate_identifiers(table, schema, *columns)` (+ name) | n/a |
| add_foreign_key | full `validate_identifiers(...)` + `valid_actions` allow-set on ON DELETE/UPDATE | n/a |
| truncate_table | `validate_identifiers(name, schema)` | n/a |
| database_exists / list_databases | `%s` placeholder for name | `%s` |
| create / create_from_env | `validate_identifier(name/owner/template)` + `%s` existence check | `%s` |
| create_extension / create_schema | `validate_extension_name`/`validate_identifier` (+ schema/owner) | n/a |

The FK `on_delete`/`on_update` allow-set rejects anything outside
`{NO ACTION, RESTRICT, CASCADE, SET NULL, SET DEFAULT}` with `ValueError` before SQL — matching
the sync twin. The async engine credential handling mirrors sync (no credential added to repr/logs).

## Correctness
- 2 latent bugs surfaced by the new coverage and fixed in BOTH sync and async (parity preserved):
  - `copy_to_csv`: psycopg yields `memoryview` chunks — old `isinstance(data, bytes)` was always
    False → `TypeError`. Fixed to `bytes(data).decode(encoding)`.
  - `hypertable_info`: `format('%I.%I', %s, %s)` tripped psycopg's placeholder parser and lacked
    inferable param types. Fixed to `format('%%I.%%I', %s::text, %s::text)`.
- C1: async `from_dataframe`/`from_geodataframe` now apply `primary_key` (was log-and-ignore).
- C2: async `close()` disposes the engine (was a no-op), with a None-guard for idempotence.
- `notify` (both sides) uses `pg_notify` — raw `NOTIFY x, %s` is invalid SQL.

## Findings

### Info (1)
- **INFO-1 — `drop_extension` does not validate the extension name** (`pycopg/database.py`,
  `pycopg/async_database.py`). The name is double-quoted (`f'DROP EXTENSION "{name}"'`) but not
  passed through `validate_extension_name`. This is a **faithful D-01 mirror of the pre-existing
  sync `drop_extension`** (not introduced by Phase 11) — the matching `create_extension` does
  validate. Low risk (extension names are developer-supplied, not end-user input; the value is
  quoted). Recommend aligning both `drop_extension`s to call `validate_extension_name` in a future
  hardening pass (Phase 12/13), not a blocker for this phase.

## Quality notes (non-blocking)
- Pre-existing ruff findings remain in `tests/test_async_database.py` (F841 unused vars, one I001
  module import-block ordering) and the deprecated top-level ruff settings warning. These predate
  Phase 11 and are Phase-12 cleanup. New phase code is ruff/black clean.

## Conclusion
No action required to advance the phase. INFO-1 is an optional future hardening item carried over
from pre-Phase-11 code.
