---
phase: 49-incremental-etl-follow-ups
plan: 01
subsystem: etl
tags: [etl, incremental, watermark, postgres, sync-async-parity]

# Dependency graph
requires:
  - phase: 20 (v0.5.0 ETL Pipeline Runner)
    provides: Pipeline dataclass + ETLAccessor.run/AsyncETLAccessor.run + _read_watermark run-log seam
  - phase: 22 (v0.7.0 Incremental ETL)
    provides: incremental_column + watermark JSONB envelope + _build_incremental_extract_sql (WHERE col > %s)
provides:
  - "Pipeline.initial_watermark frozen field (datetime | int | str | Sequence[Any] | None = None)"
  - "__post_init__ construction guard: requires incremental_column (D-02), scalar {datetime,int,str} allowlist via _encode_watermark (bool/float rejected)"
  - "Seed-floor fallback at all four run() watermark-read call sites (sync real/dry + async real/dry), explicit is-None, D-01 seed-then-ignore"
affects: [49-02, 49-03, 49-04, 49-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Seed-floor fallback applied AT THE run() CALL SITE (wm is None → pipeline.initial_watermark); _read_watermark signature unchanged (PATTERNS.md Open Question 1)"
    - "Explicit `is None` fallback, never falsy — 0 is a valid watermark floor (RESEARCH §F01)"
    - "cast(\"datetime | int | str | None\", ...) documents the F01 scalar-only contract; composite Sequence seeding deferred to 49-04"

key-files:
  created: []
  modified:
    - pycopg/etl.py
    - tests/test_etl.py
    - tests/test_etl_accessor.py

key-decisions:
  - "initial_watermark is a frozen Pipeline field defaulting None → default reproduces pre-F01 behavior byte-identically (no breaking change)"
  - "D-01 seed-floor-only: the value is consulted ONLY when no stored watermark exists; after the first run records max(col) it is never used again — no persistent clamp, no max(initial, stored)"
  - "D-02 construction guard: initial_watermark without incremental_column raises ValueError; scalar type checked via _encode_watermark's {datetime,int,str} allowlist (bool-before-int, float rejected). Sequence branch of the guard intentionally UNvalidated here — lands in 49-03 (D-04) once incremental_column is widened to a tuple"
  - "C-04 sync/async parity: both run() occurrences edited in the same commit (they are ~280-line fully-duplicated blocks with NO shared helper — test_accessor_parity would NOT catch a missed async edit, RESEARCH Pitfall 6)"

patterns-established:
  - "First-run seed floor: `if pipeline.incremental_column is not None and wm is None: wm = initial_watermark` — reusable shape for the composite-seed wiring in 49-04"

# DEVIATIONS
deviations:
  - "Plan Task 2 specified live-DB integration tests in tests/test_etl.py::TestInitialWatermark. That file is deliberately DB-free (its own class docstring says so) and the db/async_db/etl_src fixtures live only in tests/test_etl_accessor.py. Followed the codebase's own pure-vs-live separation: construction guards stay in test_etl.py::TestInitialWatermark (8 tests), seed-floor sequence tests go in test_etl_accessor.py (TestInitialWatermarkSeedFloor sync + TestAsyncInitialWatermarkSeedFloor async, 6 tests) beside the existing incremental live-DB tests."
  - "Empty-batch re-seed (D-03) is proven observably via the extract filter (run 2 loads only rows above the seed) rather than via RunResult.watermark_used: a 0-row run returns through the pre-existing empty-batch early-exit (etl.py:1437-1439) which does not inject watermark_used, so that field stays None on an empty run regardless of the seed. Documented inline in the test."

requirements-completed: [ETL-INC-F01]

# Metrics
duration: 30min
completed: 2026-07-03
---

# Phase 49 Plan 01: Pipeline.initial_watermark (seed-floor first run) Summary

**Added `Pipeline.initial_watermark` so the first incremental run is a bounded/seeded load (`WHERE col > initial_watermark`) instead of a full initial load — seed-floor-only semantics (D-01): consulted once, ignored after the first recorded watermark, with full sync/async parity and default-None byte-identical behavior.**

## Performance

- **Duration:** ~30 min (Task 1 by prior executor; Task 2 + close-out inline after a session rate-limit interrupted the executor mid-plan)
- **Completed:** 2026-07-03
- **Tasks:** 2/2
- **Files modified:** 3 (pycopg/etl.py, tests/test_etl.py, tests/test_etl_accessor.py)

## Accomplishments

- **Task 1 (committed 82b1c9a RED + da8d793):** `initial_watermark` frozen field added to `Pipeline` after `incremental_column`; `Sequence` added to the `collections.abc` import; `__post_init__` guard requires `incremental_column` and type-checks the scalar via `_encode_watermark` ({datetime,int,str} allowlist, bool-before-int, float rejected). 8 DB-free construction-guard tests in `test_etl.py::TestInitialWatermark`.
- **Task 2 (committed d22feab):** Seed-floor fallback wired at all four `run()` watermark-read call sites — sync real (etl.py:1355-1356), sync dry (1268-1271), async real (2064-2065), async dry (1978-1980). Explicit `is None` (0 is a valid floor). Both `run()` occurrences edited in one commit (C-04). 6 live-DB sequence tests: seed bounds first run, seed ignored after first recorded watermark, 0-seed honored (falsy-trap regression), empty-batch re-seed (D-03) — sync + async mirror.

## Verification

- `pytest tests/test_etl.py -k initial_watermark` → 8 passed (construction guards).
- `pytest tests/test_etl_accessor.py -k "SeedFloor or seed"` → 6 passed (live-DB sync + async).
- `pytest tests/test_etl.py tests/test_etl_accessor.py tests/test_parity.py` → 269 passed (no regressions).
- `uv run mypy pycopg` → Success, 0 issues / 18 files.
- `uv run ruff check` → All checks passed.
- `grep -c "def run(" pycopg/etl.py` == 2, both edited (C-04 sync/async same commit).

## Notes for downstream plans

- The `initial_watermark` field type already includes `Sequence[Any]` for forward-compat, but the **Sequence branch of the `__post_init__` guard is not yet implemented** and the run() fallback casts to the scalar type. 49-03 (pure layer) must add composite length-match + per-element allowlist validation; 49-04 must make the composite seed observable in run() (replace the scalar `cast` with real composite handling).
- Seed-floor call-site shape (`wm is None → initial_watermark`) is the anchor 49-04 extends for the composite watermark.
