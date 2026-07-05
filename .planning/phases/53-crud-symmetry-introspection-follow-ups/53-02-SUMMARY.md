---
phase: 53-crud-symmetry-introspection-follow-ups
plan: 02
subsystem: database
tags: [crud, single-row-insert, sync-async-parity, postgresql, sql-injection]

# Dependency graph
requires:
  - phase: 53-01
    provides: "select_where/find + get/find_one predicate reads (used by insert's live-DB conflict-verification tests via db.get)"
  - phase: 50-crud-introspection-follow-ups
    provides: "_build_insert_sql (base.py:169) + upsert's RETURNING * tail (database.py:1007-1013), reused verbatim"
provides:
  - "Database.insert / AsyncDatabase.insert — single-row RETURNING * insert, dict|None, on_conflict= raw passthrough"
  - "test_crud_v120_surface — named frozenset locking select_where/find/get/find_one/insert on both flat-core classes"
affects: [53-03, 54-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-row write composition: _build_insert_sql(table, columns, schema, on_conflict) -> + RETURNING * -> cursor.execute/fetchone, no conflict-column computation (contrast with upsert)"

key-files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_database.py
    - tests/test_async_database.py
    - tests/test_sql_injection.py
    - tests/test_database_integration.py
    - tests/test_parity.py

key-decisions:
  - "D-06: insert(table, row, *, schema='public', on_conflict=None) mirrors insert_many's on_conflict shape — a raw passthrough string threaded verbatim, NOT computed from conflict_columns/update_columns like upsert"
  - "D-07: insert returns dict | None — the inserted row on success, None under on_conflict='DO NOTHING' when a pre-existing row conflicts (RETURNING * yields no row)"

patterns-established:
  - "insert is the singular twin of insert_many/upsert: same _build_insert_sql + RETURNING * tail as upsert, minus the conflict_columns/update_columns computation upsert performs before calling it"

requirements-completed: [CRUD-F06]

# Metrics
duration: ~20min
completed: 2026-07-05
---

# Phase 53 Plan 02: single-row insert (CRUD-F06) Summary

**Added `Database.insert` / `AsyncDatabase.insert` — a single-row `RETURNING *` insert that is the singular twin of `insert_many`/`upsert`, reusing `_build_insert_sql` verbatim with `on_conflict=` as a raw passthrough string (no conflict-column computation), returning `dict | None`.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-05T07:08:38Z (session start)
- **Completed:** 2026-07-05T07:27:17Z
- **Tasks:** 2/2 completed
- **Files modified:** 7 (2 source, 5 test)

## Accomplishments

- `insert` shipped on both `Database` and `AsyncDatabase` with the exact signature `insert(table, row, *, schema="public", on_conflict=None) -> dict | None` (D-06) — mirrors `upsert`'s build → append `RETURNING *` → bind → `fetchone()` tail (database.py:1007-1013) but skips the `conflict_columns`/`update_columns` computation, since `on_conflict` is a raw passthrough string like `insert_many`'s.
- Live-verified `dict | None` return: `RETURNING *` yields the inserted row as a dict on success; `on_conflict="DO NOTHING"` on a pre-existing conflicting row returns `None` without raising (D-07); a non-conflicting row under the same `on_conflict="DO NOTHING"` still returns its dict.
- Identifier injection guarded: table / schema / row-key (column) identifiers raise `InvalidIdentifierError` before any SQL executes (via `_build_insert_sql`'s internal `validate_identifiers` call) — verified with parametrized sync + async tests mirroring `insert_many`'s existing column-injection precedent.
- `test_crud_v120_surface` added to `tests/test_parity.py` — a named frozenset (`select_where`, `find`, `get`, `find_one`, `insert`) asserted as a subset of `inspect.getmembers` for both `Database` and `AsyncDatabase`, locking in the full Phase 53 flat-core read+write surface.
- Full standing-bar gates green: `uv run pytest` 2340 passed/2 skipped @ 96.80% coverage (up from 96.79% baseline), `mypy --strict` 0 errors/18 files, `ruff check` clean, interrogate 100%, Sphinx `-W` clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: insert single-row (sync + async) + unit + injection tests** - `b374e6a` (feat)
2. **Task 2: live-DB insert behavior + v1.2.0 flat-core surface test** - `d08047b` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified

- `pycopg/database.py` - added `insert` (sync), adjacent to `upsert`
- `pycopg/async_database.py` - added `async insert`, adjacent to `async upsert`
- `tests/test_database.py` - `TestInsertSingleRow` mocked unit tests
- `tests/test_async_database.py` - `TestAsyncInsertSingleRow` mocked unit tests
- `tests/test_sql_injection.py` - `TestInsertIdentifierInjection` (table/schema/row-key, sync + async)
- `tests/test_database_integration.py` - `TestInsertSingleRowIntegration` live-DB tests (RETURNING * dict + DO NOTHING -> None + DO NOTHING non-conflicting dict, sync + async)
- `tests/test_parity.py` - `test_crud_v120_surface` (new)

## Decisions Made

Both decisions were pre-locked in `53-CONTEXT.md` (D-06, D-07) and followed exactly:

- `insert`'s `on_conflict=` is a raw passthrough string mirroring `insert_many`'s shape, not a conflict/update-column computation like `upsert`'s.
- `insert` returns `dict | None`, with `None` documented as the `on_conflict="DO NOTHING"` conflict path (mirrors `upsert`'s existing documented `dict | None` wording).

## Deviations from Plan

None - plan executed exactly as written. Both tasks, all `must_haves.truths`, and all threat-model mitigations (T-53-01 identifier validation, T-53-02 value binding, T-53-03 documented `on_conflict` raw-SQL passthrough) were implemented and tested as specified.

## Known Stubs

None - `insert` is fully wired to real SQL execution against `cursor.execute`/`cursor.fetchone`; no placeholder or mock data paths ship in production code.

## Threat Flags

None - the threat model in `53-02-PLAN.md` (T-53-01, T-53-02, T-53-03) fully covers the new surface (identifiers validated via `_build_insert_sql`, values bound as `%s`, `on_conflict` documented as a caller-owned escape hatch matching `insert_many`/`upsert`'s existing trust model). No new trust boundary was introduced beyond what the plan anticipated.

## Issues Encountered

None. The working tree was confirmed clean at the start of this plan (a prior mid-flight attempt had been fully reverted before this session began) — both tasks were implemented from scratch as instructed, and `test_parity.py`'s `test_crud_v120_surface` was added fresh (no pre-existing partial registration found).

## Next Phase Readiness

- `insert` is live on both `Database` and `AsyncDatabase`, completing CRUD-F06; ready for Plan 03 (`column_exists`/`table_size` introspection, INTRO-F03/F04) to proceed independently.
- Standing bar held: coverage 96.80% (>=95% ratchet), mypy strict 0/18, ruff clean, interrogate 100%, Sphinx `-W` clean, full parity gate green (including the new `test_crud_v120_surface`).

---
*Phase: 53-crud-symmetry-introspection-follow-ups*
*Plan: 02*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: pycopg/database.py
- FOUND: pycopg/async_database.py
- FOUND: tests/test_database.py
- FOUND: tests/test_async_database.py
- FOUND: tests/test_sql_injection.py
- FOUND: tests/test_database_integration.py
- FOUND: tests/test_parity.py
- FOUND commit: b374e6a (Task 1: insert single-row + unit + injection tests)
- FOUND commit: d08047b (Task 2: live-DB insert integration tests + v1.2.0 surface test)
