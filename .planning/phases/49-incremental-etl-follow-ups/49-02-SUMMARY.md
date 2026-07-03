---
phase: 49-incremental-etl-follow-ups
plan: 02
subsystem: etl
tags: [etl, incremental, watermark, lookback, postgres, sync-async-parity]

# Dependency graph
requires:
  - phase: 49-01
    provides: run() seed-floor call-site pattern (wm resolution) that lookback extends
  - phase: 22 (v0.7.0 Incremental ETL)
    provides: _build_incremental_extract_sql (WHERE col > %s) + _do_extract sync/async
provides:
  - "Pipeline.incremental_inclusive: bool = False (>= boundary when True, D-05)"
  - "Pipeline.incremental_lookback: timedelta | int | None = None (read-window overlap, D-06)"
  - "_build_incremental_extract_sql keyword-only inclusive param (op = '>=' if inclusive else '>')"
  - "_apply_lookback(watermark, lookback) pure helper — datetime/int dispatch, str/type-mismatch → ETLError"
  - "run() read-floor arithmetic at all four forks (sync+async real+dry); recorded watermark stays true max (D-07)"
affects: [49-03, 49-04, 49-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "read_floor = wm - lookback computed in Python before binding; the recorded max(col) capture block is untouched (D-07 — widen read, never regress record)"
    - "RunResult.watermark_used reflects the lookback-adjusted read floor actually applied (documents what was read), not the original stored/seed floor"
    - "Pure _apply_lookback helper shared across the 4 duplicated run() forks — mypy-safe isinstance dispatch (datetime→timedelta, int→int); str/mismatch raises ETLError (runtime, type only known at run time — D-06)"
    - "inclusive operator is a literal chosen from a bool (never user text) — injection surface unchanged, validate_identifiers stays line 1 of the builder"

key-files:
  created: []
  modified:
    - pycopg/etl.py
    - tests/test_etl.py
    - tests/test_etl_accessor.py

key-decisions:
  - "Two orthogonal keyword-only fields; defaults (False, None) reproduce today's exact SQL byte-identically (D-05)"
  - "incremental_lookback construction guard: timedelta or non-bool int only (bool rejected via the extract_limit subclass-trap idiom); the str-watermark incompatibility is a RUNTIME ETLError in _apply_lookback (D-06) because the watermark type is only known after the read"
  - "D-07 enforced: lookback widens the READ floor only; the recorded high-water mark is always the true max(col) — proven live (read col > 90, recorded == 137)"
  - "D-08 replay safety documented inline: inclusive/lookback overlap re-read is a safe idempotent ON CONFLICT no-op because incremental requires upsert (C-01) — no dedup machinery added"
  - "C-04: both run() occurrences + both _do_extract occurrences edited in the same commit per task"

patterns-established:
  - "_apply_lookback: reusable pure floor-arithmetic helper (isinstance dispatch, ETLError on str/type-mismatch)"

# DEVIATIONS
deviations:
  - "Live-DB floor/record-divergence tests placed in tests/test_etl_accessor.py (TestIncrementalBoundaryLive sync + TestAsyncIncrementalBoundaryLive async) beside the db/async_db fixtures; the plan named tests/test_etl.py but that file is DB-free. Builder-shape + construction guards (inclusive >=/> cases, injection, lookback bool/str rejects, defaults) DO live in test_etl.py::TestBuildIncrementalExtractSql + TestIncrementalBoundaryConstruction as the plan specified. Same split rationale as 49-01."
  - "_apply_lookback also guards datetime+int and int+timedelta type mismatches (→ ETLError), not just the str case the plan named — a cleaner runtime contract than letting Python's TypeError surface. datetime watermark requires a timedelta lookback; int requires an int."

requirements-completed: [ETL-INC-F02]

# Metrics
duration: 25min
completed: 2026-07-03
---

# Phase 49 Plan 02: Configurable incremental boundary (inclusive >= + lookback) Summary

**Added `Pipeline.incremental_inclusive` (>= boundary) and `incremental_lookback` (read-window overlap for late-arriving rows) — the lookback subtracts from the read floor in Python while the recorded high-water mark stays the true `max(col)` (widen read, never regress record, D-07), with a runtime `ETLError` for str-typed watermarks, full sync/async parity, and default `(False, None)` byte-identical behavior.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-03
- **Tasks:** 2/2
- **Files modified:** 3 (pycopg/etl.py, tests/test_etl.py, tests/test_etl_accessor.py)

## Accomplishments

- **Task 1 (committed 49d2593):** Two frozen fields after `initial_watermark`; `timedelta` import; `__post_init__` lookback guard (timedelta/non-bool int); `_build_incremental_extract_sql` gains keyword-only `inclusive` (`op = ">=" if inclusive else ">"`) in both source-kind branches; threaded through both sync + async `_do_extract`. DB-free tests: inclusive builder cases (both source kinds), default-`>` regression, inclusive-path injection guard, boundary construction defaults/guards.
- **Task 2 (committed ea6fb76):** Pure `_apply_lookback` helper (mypy-safe isinstance dispatch, str/type-mismatch → `ETLError`); wired at all four `run()` forks; recorded watermark untouched (D-07); `watermark_used` reflects the adjusted read floor; D-08 replay safety documented. Live-DB tests: read widens to `col > 90` while recorded stays true max 137, lookback=None baseline, inclusive re-includes boundary row, str+lookback ETLError — sync + async mirror.

## Verification

- `pytest tests/test_etl.py -k "inclusive or TestBuildIncrementalExtractSql or Boundary"` → all green (builder shapes + construction guards).
- `pytest tests/test_etl_accessor.py -k "BoundaryLive or lookback or inclusive_reincludes or str_watermark"` → 5 passed (live sync + async).
- `pytest tests/test_etl.py tests/test_etl_accessor.py tests/test_parity.py` → 284 passed (no regressions).
- `uv run mypy pycopg` → 0 issues / 18 files. `uv run ruff check` → clean.
- `grep -c "def run(" pycopg/etl.py` == 2, both edited (C-04).
- Full-suite coverage ≥95% gate deferred to phase-49 verification (run once across all 5 plans).

## Notes for downstream plans

- `_apply_lookback` currently dispatches on scalar `datetime | int | str`. When 49-03/04 introduce the composite (tuple) watermark, lookback semantics for a composite floor are undefined — 49-04 should decide whether lookback applies per-element or is rejected for composite watermarks (likely reject / not-applicable).
- The seed-floor + lookback call-site shape (`read_floor = wm; if lookback: read_floor = _apply_lookback(...)`) is the anchor 49-04 extends for composite wiring.
