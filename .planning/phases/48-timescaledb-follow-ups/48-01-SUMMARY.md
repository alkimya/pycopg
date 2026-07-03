---
phase: 48-timescaledb-follow-ups
plan: 01
subsystem: database
tags: [timescaledb, postgres, sync-async-parity, sql-builder]

# Dependency graph
requires:
  - phase: 30-32 (v0.8.0 TimescaleDB avancé)
    provides: create_continuous_aggregate / refresh_continuous_aggregate / add_continuous_aggregate_policy lifecycle + add_reorder_policy plain-execute pattern to mirror
provides:
  - "db.timescale.drop_continuous_aggregate(view_name, *, cascade=False, if_exists=False, schema='public') -> None (sync + async)"
  - "db.timescale.remove_continuous_aggregate_policy(view_name, *, if_exists=True, schema='public') -> None (sync + async)"
  - "test_timescale_v110_surface frozenset seed (extended by 48-02/48-03)"
affects: [48-02, 48-03, 49, 50]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Plain transaction-safe self._db.execute for cagg DROP/policy-removal (NOT the autocommit seam reserved for create/refresh)"
    - "Boolean flags rendered as fixed SQL literals (true/false, IF EXISTS, CASCADE), never bound as %s, matching add_reorder_policy/add_continuous_aggregate_policy idiom"

key-files:
  created: []
  modified:
    - pycopg/timescale.py
    - tests/test_timescale.py
    - tests/test_parity.py

key-decisions:
  - "drop_continuous_aggregate and remove_continuous_aggregate_policy both use the plain execute path per RESEARCH D-05 (DROP MATERIALIZED VIEW is ordinary transaction-safe DDL, unlike CREATE/REFRESH's multi-batch materialization)"
  - "remove_continuous_aggregate_policy binds the CURRENT if_exists param name (TSDB 2.8+), never the deprecated if_not_exists name (RESEARCH Pitfall 1) — enforced by a dedicated negative assertion in the mock test"
  - "if_exists defaults False on drop_continuous_aggregate (destructive op explicit) and True on remove_continuous_aggregate_policy (symmetric with add_continuous_aggregate_policy's if_not_exists=True default), per CONTEXT D-03"

patterns-established:
  - "Cagg teardown pair mirrors add_reorder_policy (guard+plain-execute shape) and drop_chunks (destructive .. note:: docstring callout)"

requirements-completed: [TSDB-F01]

# Metrics
duration: 15min
completed: 2026-07-03
---

# Phase 48 Plan 01: Continuous-Aggregate Teardown Pair Summary

**Added `drop_continuous_aggregate` + `remove_continuous_aggregate_policy` to both `TimescaleAccessor` and `AsyncTimescaleAccessor`, completing the v0.8.0 cagg lifecycle with plain transaction-safe execute (not the autocommit seam).**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-03T10:26:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `TimescaleAccessor.drop_continuous_aggregate` / `AsyncTimescaleAccessor.drop_continuous_aggregate` — emits `DROP MATERIALIZED VIEW [IF EXISTS ]schema.view[ CASCADE]` via plain `self._db.execute`, `validate_identifiers` first, `ExtensionNotAvailableError` guard, keyword-only, returns `None`.
- `TimescaleAccessor.remove_continuous_aggregate_policy` / async twin — emits `SELECT remove_continuous_aggregate_policy('schema.view', if_exists => true/false)` using the CURRENT `if_exists` param name (never the deprecated `if_not_exists`).
- Full mock SQL-shape + guard + injection test coverage (10 new tests: 5 per method, sync + async + no-extension guard + injection guard).
- `test_timescale_v110_surface` seeded in `tests/test_parity.py` with the 2 F01 method names, asserted on both accessor classes.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add drop_continuous_aggregate + remove_continuous_aggregate_policy to both accessor classes** - `51cfd03` (feat)
2. **Task 2: Add F01 mock SQL-shape / guard / injection tests + seed test_timescale_v110_surface** - `26d2d3e` (test)

## Files Created/Modified
- `pycopg/timescale.py` - 2 new methods x 2 classes (sync `TimescaleAccessor` + async `AsyncTimescaleAccessor`); both plain-execute, validate_identifiers-first, return None
- `tests/test_timescale.py` - `TestDropContinuousAggregateMock` + `TestRemoveContinuousAggregatePolicyMock` (5 tests each, sync+async+guards+injection); `InvalidIdentifierError` added to the top-level import
- `tests/test_parity.py` - `test_timescale_v110_surface` (new function, frozenset seed)

## Decisions Made
- Both new methods use the plain `self._db.execute` path per RESEARCH D-05 (confirmed live against TSDB 2.28.2 — `DROP MATERIALIZED VIEW` is ordinary transaction-safe DDL; `remove_continuous_aggregate_policy` is a plain scalar function call, structurally identical to the already-shipped `add_continuous_aggregate_policy`). Neither uses the `connect(autocommit=True)` seam reserved for `create_continuous_aggregate`/`refresh_continuous_aggregate`.
- `remove_continuous_aggregate_policy` binds `if_exists` (current TSDB 2.8+ name), not `if_not_exists` (deprecated) — verified by a dedicated negative SQL-shape assertion (Pitfall 1 guard).
- `if_exists` defaults `False` on `drop_continuous_aggregate` (destructive, explicit per D-03) and `True` on `remove_continuous_aggregate_policy` (symmetric with `add_continuous_aggregate_policy`'s `if_not_exists=True`).

## Deviations from Plan

None - plan executed exactly as written. Docstrings and body shapes match the plan's Code Examples/Pattern Map exemplars verbatim (mirroring `add_reorder_policy` for guard order and `drop_chunks` for the DESTRUCTIVE `.. note::` callout).

One incidental fix applied during execution: `black --fast --target-version py312` reformatted `tests/test_timescale.py` (line-wrapping of the new import block and a long assert line) — pure formatting, no behavior change, folded into the Task 2 commit before it was made (not a separate deviation, just normal formatting pass before commit).

## Issues Encountered

Running the plan's full `<verification>` command (`PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py tests/test_parity.py -x -q`, without `-o addopts=""`) triggers the whole-suite `--cov-fail-under=95` gate against a 2-file subset (35.79% measured) — this is the documented, expected subset-coverage artifact (see project memory `pycopg-flaky-db-tests` / CLAUDE.md test guidance), not a regression. All 155 tests passed in both the targeted (`-o addopts=""`) and full-subset runs. The coverage gate is a phase/wave-level concern, not a per-plan one.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- TSDB-F01 (continuous-aggregate teardown) fully complete: sync+async parity, mypy-strict clean (0 errors), interrogate 100%, ruff clean, injection-safe.
- `test_timescale_v110_surface` frozenset is ready for 48-02 (F02 time_bucket origin/offset — no new method name, param-only) and 48-03 (F03 compress_chunk/decompress_chunk — will extend this frozenset with 2 more names) to build on.
- No blockers for 48-02/48-03.

---
*Phase: 48-timescaledb-follow-ups*
*Completed: 2026-07-03*
