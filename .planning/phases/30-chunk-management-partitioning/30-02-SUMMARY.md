---
phase: 30-chunk-management-partitioning
plan: "02"
subsystem: timescaledb
tags: [chunk-management, show-chunks, drop-chunks, dry-run, capture-before-drop, tdd, wave-2]
dependency_graph:
  requires:
    - pycopg.exceptions.TimescaleError (Plan 01)
    - pycopg.queries.TSDB_SHOW_CHUNKS (Plan 01)
    - pycopg.queries.TSDB_DROP_CHUNKS (Plan 01)
    - tests/test_timescale.py ts_db/async_ts_db fixtures (Plan 01)
  provides:
    - pycopg.timescale.TimescaleAccessor.show_chunks
    - pycopg.timescale.TimescaleAccessor.drop_chunks
    - pycopg.timescale.AsyncTimescaleAccessor.show_chunks
    - pycopg.timescale.AsyncTimescaleAccessor.drop_chunks
    - tests/test_timescale.py mock + live tests for show_chunks/drop_chunks
  affects:
    - Plan 03 (add_dimension + add_reorder_policy build on same accessor pattern)
tech_stack:
  added: []
  patterns:
    - "type-driven %s cast: str -> %s::interval, datetime -> bare %s, None -> omit (D-02)"
    - "capture-before-drop: run TSDB_SHOW_CHUNKS first while chunks exist, then drop (D-03/D-05)"
    - "_build_chunk_bound_fragments() shared helper: older-then-newer lockstep param build"
    - "both-None ValueError before any DB round-trip (D-03 safety guard)"
    - "dry_run short-circuits after capture, before drop execute"
    - "async methods: await has_extension + await execute; ValueError stays sync"
    - "two-layer tests: mock SQL-shape (no live DB) + live-DB integration (ts_db gated)"
key_files:
  created: []
  modified:
    - pycopg/timescale.py
    - pycopg/queries.py
    - tests/test_timescale.py
decisions:
  - "Shared private helper _build_chunk_bound_fragments() used by both show_chunks and drop_chunks to avoid D-02 param-order footgun duplication"
  - "drop_chunks issues TSDB_SHOW_CHUNKS-shaped capture query (not TSDB_DROP_CHUNKS) for the preview, then TSDB_DROP_CHUNKS for the drop — same builder, two calls, returns captured list"
  - "ValueError guard for both-None fires BEFORE has_extension check (pure Python, never needs DB)"
  - "TSDB_SHOW_CHUNKS/TSDB_DROP_CHUNKS format placeholders corrected from {{schema}}/{{table}} (double-brace, produced literal text) to {schema}/{table} (single-brace, substituted by .format())"
metrics:
  duration_seconds: 480
  completed_date: "2026-06-22"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
---

# Phase 30 Plan 02: show_chunks + drop_chunks — Sync and Async

**One-liner:** show_chunks + drop_chunks on TimescaleAccessor + AsyncTimescaleAccessor with capture-before-drop, type-driven %s cast, both-None ValueError guard, and two-layer mock+live test coverage.

## What Was Built

### Task 1 — show_chunks + drop_chunks on sync and async accessors (commit `f4494ae`)

Added a shared private helper `_build_chunk_bound_fragments(older_than, newer_than)` to
`pycopg/timescale.py` that encapsulates the D-02 type-driven cast and D-02 param-order guard:
- `str` bound → SQL fragment `, older_than => %s::interval` + param
- `datetime` bound → SQL fragment `, older_than => %s` (bare) + param
- `None` → no fragment, no param
- Params list is always built older-then-newer (matching fragment append order)

Added `TimescaleAccessor.show_chunks(table, older_than=None, newer_than=None, schema="public") -> list[str]`:
- Guard: `has_extension("timescaledb")` (sync)
- Validate: `validate_identifiers(table, schema)`
- Build SQL via `TSDB_SHOW_CHUNKS.format(schema=..., table=..., older_arg=..., newer_arg=...)`
- Execute + return `[r["chunk_name"] for r in rows]` (ordered oldest-first by DB `ORDER BY range_start ASC`)

Added `TimescaleAccessor.drop_chunks(table, older_than=None, newer_than=None, schema="public", dry_run=False) -> list[str]`:
- D-03 guard FIRST (before has_extension): `ValueError` when both bounds are None
- Guard: `has_extension("timescaledb")` (sync)
- Validate: `validate_identifiers(table, schema)`
- Capture-before-drop: run `TSDB_SHOW_CHUNKS`-shaped query to get ordered list while chunks exist
- `dry_run=True` → return captured list (no drop)
- `dry_run=False` → execute `TSDB_DROP_CHUNKS`, return captured list
- Docstring marks DESTRUCTIVE/IRREVERSIBLE

Added `AsyncTimescaleAccessor.show_chunks` and `AsyncTimescaleAccessor.drop_chunks` as exact
async mirrors: both `await self._db.schema.has_extension(...)` and `await self._db.execute(...)`;
the ValueError guard and `_build_chunk_bound_fragments()` stay plain (no await).

All 4 methods have numpydoc docstrings with full Parameters / Returns / Raises sections.

### Task 2 — Tests for show_chunks + drop_chunks (commit `6e908d0`)

Replaced Wave 0 xfail stubs with real tests; Wave 0 add_dimension/add_reorder_policy stubs intact.

**Bug fix included (Rule 1):** `TSDB_SHOW_CHUNKS` and `TSDB_DROP_CHUNKS` in `pycopg/queries.py`
used double-brace `{{schema}}.{{table}}` placeholders. Python's `.format()` converts `{{` → `{`
(literal brace) — leaving `{schema}` as un-substituted text in the SQL. Fixed to single-brace
`{schema}.{table}` so `.format(schema=..., table=...)` correctly substitutes the values.
The `%%I` inside the SQL `format('%I.%I', ...)` call is unaffected (psycopg handles `%%` → `%`
at query-send time, not at Python `.format()` time).

**Also fixed (Rule 3):** `db` fixture used `database.disconnect()` (no such method); corrected
to match `test_database_integration.py` pattern (session conn close on teardown only if open).
Async live tests used `async_ts_db._config`; corrected to `async_ts_db.config`.

**Mock SQL-shape unit tests (Layer 2 — no live DB):**
- `TestShowChunksMock`: no-bounds SQL shape, str-bound `%s::interval`, datetime-bound bare `%s`,
  params-order assertion `[older, newer]`, no-extension raises (sync); async equivalents.
- `TestDropChunksMock`: both-None raises + execute never called, dry_run one-call (no drop SQL),
  real-drop two-call (show then drop), both-None before extension-guard; async equivalents.

**Live-DB integration tests (Layer 1 — ts_db gated):**
- `TestShowChunksLive`: non-empty list, fully-qualified names, oldest-first by chunk-ID sequence
  (not lexical — verifies `_hyper_N_10` after `_hyper_N_9`), older_than filter subset assertion;
  async equivalent.
- `TestDropChunksLive`: both-None raises, dry_run count-unchanged, real-drop reduces count +
  dropped names disjoint from remaining, returned list oldest-first; async equivalent.

## Verification Results

- `uv run pytest tests/test_timescale.py -k "show_chunks or drop_chunks" -q -o addopts=""` → 24 passed
- `uv run pytest tests/test_timescale.py -q -o addopts=""` → 24 passed, 6 xfailed (add_dimension/reorder stubs)
- `uv run pytest tests/test_parity.py -k accessor_parity -q -o addopts=""` → 7 passed (no asymmetry)
- `uv run ruff check pycopg/timescale.py pycopg/queries.py tests/test_timescale.py` → clean

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TSDB_SHOW_CHUNKS / TSDB_DROP_CHUNKS format placeholders (double → single brace)**
- **Found during:** Task 2 (live-DB tests failed with `SyntaxError: erreur de syntaxe sur ou près de «{»`)
- **Issue:** Plan 01 created constants with `{{schema}}.{{table}}` (double-brace). Python's `.format()` expands `{{` to literal `{`, leaving `{schema}` as unresolved text in the SQL string passed to psycopg, which then errored on `{`.
- **Fix:** Changed to single-brace `{schema}.{table}{older_arg}{newer_arg}` in both `TSDB_SHOW_CHUNKS` and `TSDB_DROP_CHUNKS` in `pycopg/queries.py`.
- **Files modified:** `pycopg/queries.py`
- **Commit:** `6e908d0`

**2. [Rule 3 - Blocking] Fixed db fixture teardown (disconnect → close pattern)**
- **Found during:** Task 2 (all live-DB teardown errored with `AttributeError: 'Database' object has no attribute 'disconnect'`)
- **Fix:** Replaced `database.connect(); yield; database.disconnect()` with the `test_database_integration.py` pattern (no pre-connect; conditional `_session_conn.close()` on teardown).
- **Files modified:** `tests/test_timescale.py`
- **Commit:** `6e908d0`

**3. [Rule 3 - Blocking] Fixed async live test config attribute (_config → .config)**
- **Found during:** Task 2 (`AttributeError: 'AsyncDatabase' object has no attribute '_config'`)
- **Fix:** Changed `async_ts_db._config` to `async_ts_db.config` in both async live tests.
- **Files modified:** `tests/test_timescale.py`
- **Commit:** `6e908d0`

## Known Stubs

Wave 0 xfail stubs for `add_dimension` and `add_reorder_policy` remain in `tests/test_timescale.py`
(6 stubs, 6 xfailed). These are intentional scaffolding for Plan 03. They do not block Plan 02's goals.

## Threat Flags

No new threat surface beyond T-30-03/T-30-04/T-30-05 already in the plan's threat model.

- T-30-03: `validate_identifiers(table, schema)` called before any SQL interpolation — mitigated.
- T-30-04: `ValueError` before any DB call when both bounds None — mitigated; dry_run preview added; docstring marks DESTRUCTIVE.
- T-30-05: async `await` audit confirmed — both async methods await `has_extension` AND `execute`; verified by reading source and by `test_show_chunks_async_*` / `test_drop_chunks_async_*` mock tests.

## Self-Check: PASSED

- `pycopg/timescale.py` contains `def show_chunks` (sync): FOUND
- `pycopg/timescale.py` contains `def drop_chunks` (sync): FOUND
- `pycopg/timescale.py` contains `async def show_chunks`: FOUND
- `pycopg/timescale.py` contains `async def drop_chunks`: FOUND
- `tests/test_timescale.py` contains real show_chunks tests: FOUND
- Commit `f4494ae` exists: FOUND
- Commit `6e908d0` exists: FOUND
