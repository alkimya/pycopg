---
phase: 48-timescaledb-follow-ups
plan: 02
subsystem: database
tags: [timescaledb, postgres, sync-async-parity, sql-builder]

# Dependency graph
requires:
  - phase: 48-01 (cagg teardown pair)
    provides: test_timescale_v110_surface frozenset seed + established plain-execute pattern
provides:
  - "db.timescale.time_bucket(..., origin=datetime|None, offset=str|None) -> DataFrame|list[dict] (sync + async), keyword-only bucket alignment"
  - "_build_time_bucket_sql(..., origin=, offset=) client-side mutual-exclusion ValueError guard (param-only extension, no new method name)"
affects: [48-03, 49, 50]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Param-presence dispatch (not type dispatch) inside a shared builder: origin is always datetime-or-None, offset is always str-or-None, mutually exclusive"
    - "Client-side ValueError guard before any SQL build, mirroring drop_chunks both-None guard"

key-files:
  created: []
  modified:
    - pycopg/timescale.py
    - tests/test_timescale.py

key-decisions:
  - "_build_time_bucket_sql extended in place (not a new builder) with origin/offset appended after schema; mutual-exclusion guard lives in the builder (D-07), not the accessor, so it stays unit-testable in isolation"
  - "origin binds as a bare typed %s (psycopg infers timestamptz/timestamp from the datetime); offset binds as %s::interval; the two are dispatched by param presence (if origin is not None / elif offset is not None), matching the confirmed separate PostgreSQL time_bucket overloads (RESEARCH D-06/§3)"
  - "\"offset\" quoted defensively as a named-argument label in the SQL fragment (harmless, matches RESEARCH's noted psql-renderer convention) — does not affect binding or injection safety"
  - "Both-None path byte-identical to the pre-existing v0.8.0 SQL shape and params list — additive/non-breaking, proven by a dedicated test"

patterns-established:
  - "F02 is the first Phase 48 surface that is a param addition to an EXISTING method name (not a new method) — no frozenset entry needed in test_timescale_v110_surface; parity coverage comes automatically from test_accessor_parameter_kind_parity once both classes' signatures change identically"

requirements-completed: [TSDB-F02]

# Metrics
duration: 20min
completed: 2026-07-03
---

# Phase 48 Plan 02: time_bucket origin/offset Alignment Summary

**Extended `db.timescale.time_bucket` with keyword-only `origin`/`offset` bucket-alignment params on both sync and async accessors, guarded by a client-side `ValueError` for the mutually-exclusive case, with the both-None default path byte-identical to the shipped v0.8.0 SQL shape.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-03T11:05:00Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- `_build_time_bucket_sql` (pycopg/timescale.py) extended in place with `origin: datetime | None = None` and `offset: str | None = None` params, a client-side mutual-exclusion `ValueError` guard fired before any SQL is built, and param-presence dispatch producing `, origin => %s` (bare typed bind) or `, "offset" => %s::interval` (interval-cast bind) — both-None path unchanged.
- All 8 `time_bucket` signatures (3 `@overload` stubs + 1 impl, on both `TimescaleAccessor` and `AsyncTimescaleAccessor`) gained `origin=`/`offset=` in identical keyword-only position (mypy-strict KIND-parity, v1.0.0 Phase 46 pattern). Both impl call-sites forward `origin=origin, offset=offset` to the builder.
- `time_bucket_gapfill` left completely untouched (out of scope, D-08); the existing `where=`→`filter=` `DeprecationWarning` shim in both impls is byte-unchanged.
- `TestTimeBucketOriginOffsetMock` (tests/test_timescale.py): 5 new tests covering origin-only SQL shape, offset-only SQL shape, both-None-unchanged shape, mutual-exclusion guard (`db.execute`/`db.to_dataframe` both asserted not-called), and an async mirror for the origin case.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend _build_time_bucket_sql with origin/offset + mutual-exclusion guard** - `1935775` (feat)
2. **Task 2: Thread origin/offset through all 8 time_bucket signatures (sync+async) + wire call-sites** - `0a82dcc` (feat)
3. **Task 3: Add TestTimeBucketOriginOffsetMock SQL-shape + mutual-exclusion tests (sync+async)** - `2c46ddb` (test)

## Files Created/Modified

- `pycopg/timescale.py` - `_build_time_bucket_sql` gains origin/offset + guard; `TimescaleAccessor.time_bucket` and `AsyncTimescaleAccessor.time_bucket` (all 8 signatures + both call-sites + docstrings) updated
- `tests/test_timescale.py` - `TestTimeBucketOriginOffsetMock` (5 tests: origin sql-shape, offset sql-shape, both-none-unchanged, mutual-exclusion, async origin mirror)

## Decisions Made

- Mutual-exclusion guard placed inside the pure builder (`_build_time_bucket_sql`), not the public accessor method — keeps it unit-testable in isolation and matches the `add_dimension`/`drop_chunks` guard-placement convention already in the codebase.
- `origin`/`offset` dispatch is param-presence based (`if origin is not None: ... elif offset is not None: ...`), not type-based — mirrors the RESEARCH-confirmed fact that these are genuinely separate PostgreSQL `time_bucket` overloads with no 4-arg variant accepting both.
- F02 does NOT get a new entry in `test_timescale_v110_surface` (that frozenset tracks new method *names*; F02 only adds params to the existing `time_bucket` name) — parity is instead enforced automatically by the existing `test_accessor_parameter_kind_parity`, which now covers the 2 new params on both classes.

## Deviations from Plan

None - plan executed exactly as written. `black --fast --target-version py312` formatting warnings are expected local-toolchain noise (Python 3.12 running, code formatted for a newer target) — `black --check` and `ruff check` both passed with no changes needed.

## Issues Encountered

None. All verification commands passed on the first attempt:
- `uv run mypy pycopg/timescale.py` → 0 errors (both after Task 1 and Task 2)
- `PGDATABASE=pycopg_test3 uv run pytest tests/test_parity.py::test_accessor_parameter_kind_parity -x -q -o addopts=""` → 7 passed
- `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py -k "time_bucket and (origin or offset or mutual)" -x -q -o addopts=""` → 5 passed
- `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py tests/test_parity.py -x -q -o addopts=""` → 160 passed
- `uv run interrogate pycopg/timescale.py` → 100% (gate ≥95%)
- `grep -c "origin: datetime | None = None" pycopg/timescale.py` → 9 (1 builder + 8 signatures, as required)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TSDB-F02 (time_bucket origin/offset alignment) fully complete: sync+async parity, mypy-strict clean (0 errors), interrogate 100%, ruff/black clean, mutual-exclusion guard proven before any DB round-trip.
- `test_timescale_v110_surface` frozenset unchanged (F02 is param-only, no new method name) — ready for 48-03 (F03 compress_chunk/decompress_chunk) to extend it with 2 new method names.
- No blockers for 48-03.

---
*Phase: 48-timescaledb-follow-ups*
*Completed: 2026-07-03*

## Self-Check: PASSED

- FOUND: `.planning/phases/48-timescaledb-follow-ups/48-02-SUMMARY.md`
- FOUND: `pycopg/timescale.py`
- FOUND: `tests/test_timescale.py`
- FOUND commit: `1935775` (Task 1 feat)
- FOUND commit: `0a82dcc` (Task 2 feat)
- FOUND commit: `2c46ddb` (Task 3 test)
