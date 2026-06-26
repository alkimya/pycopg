---
phase: 39-couverture-benchmarks
plan: 01
subsystem: testing
tags: [pytest-cov, coverage, async, etl, watermark, pragma-no-cover]

# Dependency graph
requires:
  - phase: 38-perf-copy
    provides: COPY-based insert_batch/from_dataframe/ETL paths that the new live-DB tests exercise
provides:
  - TestAsyncInsertBatch class (4 live-DB tests covering async_database.py L685-718)
  - Sync + async ETL dry_run watermark/transform-step tests (etl.py L1215/L1224/L1226/L1241/L1248-1249 + async mirrors)
  - 5 justified pragma: no cover annotations on genuinely-unreachable defensive lines
  - Coverage gate lifted to 95% (--cov-fail-under=95, measured 95.74%)
  - benchmarks/* added to [tool.coverage.run] omit
affects:
  - 40-release-v0100 (gate must stay green under the 95% threshold)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "async live-DB fixture pattern: AsyncDatabase(db_config) per-test, UUID-suffixed table, await adb.execute(CREATE/DROP, autocommit=True)"
    - "pragma: no cover — <justification> (em-dash + inline reason on every pragma, first use in repo)"
    - "ETL incremental dry_run: call db.etl.init() before dry_run on incremental pipeline (pipeline_runs must exist)"
    - "pytest-randomly safety: UUID-suffix all table names, self-contained teardown, no cross-test state"

key-files:
  created: []
  modified:
    - tests/test_async_database.py
    - tests/test_etl_accessor.py
    - pycopg/database.py
    - pycopg/config.py
    - pycopg/__init__.py
    - pycopg/backup.py
    - pyproject.toml

key-decisions:
  - "D-04a honored: --cov-fail-under bump was the last act after all tests committed and measured >=95%"
  - "Tasks 1+2 alone reached 95.38% (34 lines from async insert_batch pool); pragmas are additive hardening"
  - "ETL incremental dry_run requires etl.init() before the first dry_run when pipeline_runs does not exist"
  - "6 pragma sites applied (database.py, config.py, __init__.py, backup.py x3) — all genuinely unreachable in test env"

patterns-established:
  - "Async live-DB test: AsyncDatabase(db_config) fixture, UUID table, CREATE with autocommit=True, drop on teardown"
  - "Inline pragma justification: # pragma: no cover — <reason explaining why line is unreachable in test env>"

requirements-completed: [COV-01]

# Metrics
duration: 24min
completed: 2026-06-26
---

# Phase 39 Plan 01: COV-01 — Coverage Lift 94%→95% Summary

**Coverage ratchet lifted from 94% to 95% via 15 new real behavioral tests (async insert_batch + ETL dry_run watermark/transform) and 6 justified pragma: no cover annotations on genuinely-unreachable defensive lines; gate bumped to --cov-fail-under=95, measured 95.74%**

## Performance

- **Duration:** ~24 min
- **Started:** 2026-06-26T18:33:35Z
- **Completed:** 2026-06-26T18:57:33Z
- **Tasks:** 3 of 3
- **Files modified:** 7

## Accomplishments

- Added `TestAsyncInsertBatch` class (4 live-DB behavioral tests) covering `async_database.py` L685-718 — the 34-line pool that was the COV-01 primary target; this alone was sufficient to cross 95%
- Added 5 sync ETL dry_run tests (string/timestamp watermark, missing-column raises, single callable transform, transform step raises) covering `etl.py` L1215, L1224, L1226, L1241, L1248-1249
- Added 4 async ETL dry_run mirrors covering `etl.py` L1900, L1902, L1916-1919, L1922-1925
- Applied 6 `pragma: no cover` annotations (each with inline em-dash justification) to genuinely-unreachable defensive lines in database.py, config.py, `__init__.py`, backup.py
- Bumped `--cov-fail-under=94` → `--cov-fail-under=95` (last act per D-04a); final measured coverage: 95.74%
- Added `benchmarks/*` to `[tool.coverage.run] omit` for belt-and-suspenders isolation (D-01a)

## Task Commits

Each task was committed atomically:

1. **Task 1: TestAsyncInsertBatch live-DB tests** - `b6bf865` (feat)
2. **Task 2: Sync + async ETL dry_run watermark/transform tests** - `6bfe3f2` (feat)
3. **Task 3: Justified pragma: no cover + bump --cov-fail-under to 95** - `34efc0f` (feat)

## Files Created/Modified

- `tests/test_async_database.py` — Added `async_insert_table` + `async_insert_table_pk` fixtures and `TestAsyncInsertBatch` class (4 behavioral tests: basic, empty_returns_zero, on_conflict_do_nothing, multi_batch)
- `tests/test_etl_accessor.py` — Added 5 sync dry_run tests to `TestRunResultSurface` and 4 async mirrors to `TestAsyncRunResultSurface` (string/timestamp watermark, missing column, single callable, step raises)
- `pycopg/database.py` — `pragma: no cover` on session commit+close double-failure branch (L567-575)
- `pycopg/config.py` — `pragma: no cover` on python-dotenv ImportError fallback (L20-25)
- `pycopg/__init__.py` — `pragma: no cover` on PackageNotFoundError fallback (L44-45)
- `pycopg/backup.py` — `pragma: no cover` on pg_restore/psql/async psql subprocess failure raises (L193, L221, L568)
- `pyproject.toml` — `--cov-fail-under=94` → `--cov-fail-under=95` + `benchmarks/*` added to omit

## Decisions Made

- **D-04a honored:** --cov-fail-under bump was the LAST act, after Tasks 1+2 were committed and measured coverage confirmed >=95%
- **Real tests first, pragmas second:** Tasks 1+2 alone pushed from 94.11% to 95.38% (more than the required 26 lines via 34-line async insert_batch pool); the pragmas are additive hardening on genuinely-unreachable lines
- **ETL incremental dry_run requires init():** The sync and async `_read_watermark()` calls in the dry_run path query `pipeline_runs` directly — the table must exist first. Added `db.etl.init()` / `await async_db.etl.init()` before each incremental dry_run test (Rule 1 auto-fix during testing)
- **Only 6 pragma sites applied:** Selected from the approved candidate list; did NOT pragma lines reachable by real tests (L263, L289, L337 in backup.py are skipped as reachable)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ETL incremental dry_run requires pipeline_runs to exist (init() missing)**
- **Found during:** Task 2 (sync + async ETL dry_run tests)
- **Issue:** The plan's example dry_run tests did not call `db.etl.init()` / `await async_db.etl.init()` before the first dry_run on an incremental pipeline. The `_read_watermark()` call within dry_run queries `pipeline_runs` directly — on a clean DB state it raises `UndefinedTable`
- **Fix:** Added `db.etl.init()` / `await async_db.etl.init()` before each `etl.run(p, dry_run=True)` call in the 3 sync and 2 async incremental tests
- **Files modified:** `tests/test_etl_accessor.py`
- **Verification:** All 11 new ETL tests pass after fix
- **Committed in:** `6bfe3f2` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 bug — missing init() call before incremental dry_run)
**Impact on plan:** Fix essential for correctness; no scope change. The pattern (init() before incremental dry_run) is documented in patterns-established.

## Issues Encountered

- Black reformatted `except (ImportError):` and `except (PackageNotFoundError):` to multi-line form, moving the pragma comment to the closing `)` line — this is valid and recognized by coverage.py. Verified: `grep -n 'pragma: no cover' pycopg/*.py | grep -v '# pragma: no cover —'` returns no output.
- 3 pre-existing PostGIS env failures (test_postgis_errors.py) in pycopg_test2 — PostGIS not installed; these are documented in STATE.md and are NOT regressions. Full suite without these exits 0 with 95.74% coverage.

## Known Stubs

None — all new test code exercises real DB behavior (no mock cursor, no placeholder data).

## Threat Flags

None — no new public surface, no new network endpoints, no new auth paths. COV-01 adds test code and pragma annotations only.

## Next Phase Readiness

- Phase 39 Plan 02 (PERF-04 benchmarks) can proceed — coverage gate is green at 95.74%
- The `benchmarks/*` omit entry is already in place so benchmark code won't affect coverage counting
- Pre-existing PostGIS failures (test_postgis_errors.py) remain unresolved — documented in STATE.md for Plan 05 disposition

---
*Phase: 39-couverture-benchmarks*
*Completed: 2026-06-26*

## Self-Check: PASSED

- tests/test_async_database.py: FOUND (class TestAsyncInsertBatch present)
- tests/test_etl_accessor.py: FOUND (dry_run_incremental_string_watermark present)
- pyproject.toml: FOUND (--cov-fail-under=95 present, benchmarks/* in omit)
- Commit b6bf865: FOUND
- Commit 6bfe3f2: FOUND
- Commit 34efc0f: FOUND
- No bare `pragma: no cover` (all have em-dash justification): VERIFIED
- Final measured coverage: 95.74% (TOTAL 3448 stmts, 147 missed)
