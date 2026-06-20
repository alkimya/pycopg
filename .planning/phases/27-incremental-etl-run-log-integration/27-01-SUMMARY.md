---
phase: 27-incremental-etl-run-log-integration
plan: "01"
subsystem: database
tags: [etl, incremental, watermark, jsonb, psycopg, pandas, timescaledb]

# Dependency graph
requires:
  - phase: 26-incremental-etl-pure-layer
    provides: _encode_watermark, _decode_watermark, Pipeline.incremental_column validation, _WATERMARK_SUPPORTED allowlist

provides:
  - ETL_GET_LAST_WATERMARK SQL constant (success-only, watermark IS NOT NULL read)
  - ETL_UPDATE_RUN_WATERMARK SQL constant (dedicated success-path UPDATE with watermark col)
  - ETLAccessor._read_watermark(name) method — reads+decodes last successful non-NULL watermark
  - ETLAccessor._end_run(..., watermark=None) extended with JSONB write on success path
  - run() max(col) capture from raw batch before transforms, with D-07 coercion and D-06 guard
  - 6 live-DB integration tests proving SC-1..SC-4 + D-04 + D-06

affects:
  - 28-incremental-etl-extract-runresult-async — consumes _read_watermark for the WHERE-filter wiring (ETL-INC-03)

# Tech tracking
tech-stack:
  added:
    - "psycopg.types.json.Jsonb — psycopg3 JSONB write adapter (zero new deps, already a pinned dep)"
  patterns:
    - "Dedicated success-path SQL constant: ETL_UPDATE_RUN_WATERMARK keeps the failed/empty UPDATE structurally incapable of touching watermark"
    - "Call-site coercion (D-07): int()/to_pydatetime()/str() before _encode_watermark, encoder frozen"
    - "Autocommit+dict_row read pattern (mirrors last_run) for _read_watermark"
    - "D-03 query predicate: status='success' AND watermark IS NOT NULL makes empty-batch-preserves fall out of the read query"

key-files:
  created: []
  modified:
    - pycopg/queries.py
    - pycopg/etl.py
    - tests/test_etl_accessor.py

key-decisions:
  - "Dedicated ETL_UPDATE_RUN_WATERMARK constant rather than adding watermark param to ETL_UPDATE_RUN — failed/empty paths structurally incapable of setting watermark (no-advance-on-failure by SQL design)"
  - "D-07 call-site coercion: int()/to_pydatetime()/str() at run() before _encode_watermark; encoder stays frozen"
  - "WR-01/WR-02 decode hardening DEFERRED to Phase 28 — every envelope Phase 27 reads back is written by own strict encoder, permissive/opaque branches unreachable"
  - "_read_watermark exists and is tested but NOT yet applied as an extract filter — WHERE col > watermark is Phase 28 (ETL-INC-03)"
  - "Roundtrip test uses fresh table with PK + non-conflict column per parametrize case to satisfy upsert SQL validity"

patterns-established:
  - "success-only watermark persist: _end_run(watermark=wm_env) only on success path; failed/empty callers pass no watermark"
  - "D-06 ETLError guard: raise before load when incremental_column absent from df.columns"

requirements-completed: [ETL-INC-02, ETL-INC-05, ETL-INC-06, ETL-INC-10]

# Metrics
duration: 18min
completed: 2026-06-20
---

# Phase 27 Plan 01: Run-Log Integration Summary

**Watermark persistence wired through sync run-log: _read_watermark + _end_run(watermark=) + max(col) capture with JSONB roundtrip proven for int/str/datetime via 6 live-DB tests**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-20T14:16:00Z (approx)
- **Completed:** 2026-06-20T14:34:29Z
- **Tasks:** 3 of 3
- **Files modified:** 3

## Accomplishments

- Added `ETL_GET_LAST_WATERMARK` (success-only, `watermark IS NOT NULL` predicate makes empty-batch-preserves and no-advance-on-failure fall out of the query) and `ETL_UPDATE_RUN_WATERMARK` (dedicated success-path constant, frozen existing `ETL_UPDATE_RUN` for failed/empty paths) to `pycopg/queries.py`
- Extended `ETLAccessor._end_run` with `watermark: dict | None = None` kwarg that wraps the already-encoded envelope in `Jsonb(...)` only on the non-None branch; added `ETLAccessor._read_watermark(name)` via autocommit+dict_row read mirroring `last_run`
- Wired `max(col)` capture from the raw batch before the transform chain in `run()`, with per-type coercion (D-07: `int()/to_pydatetime()/str()`), a D-06 `ETLError` guard for missing `incremental_column`, and success-only persist via `_encode_watermark`
- Proved four invariants (SC-1..SC-4) + D-04 + D-06 with 6 live-DB integration tests, all green

## Task Commits

1. **Task 1: Add SQL constants** - `cfe8f1e` (feat)
2. **Task 2: Wire _read_watermark, _end_run(watermark=), run() max(col)** - `7e96a4a` (feat)
3. **Task 3: 6 live-DB integration tests** - `682de82` (test)

## Files Created/Modified

- `pycopg/queries.py` — Added `ETL_GET_LAST_WATERMARK` and `ETL_UPDATE_RUN_WATERMARK` after `ETL_GET_RUN` (22 lines added, no modifications to existing constants)
- `pycopg/etl.py` — Added `Jsonb` import; extended `_end_run` signature+body; added `_read_watermark` method; inserted max(col) capture block in `run()` with coercion+D-06 guard; updated success `_end_run` call to pass encoded envelope
- `tests/test_etl_accessor.py` — Added `ETLError` to import line 13; added 6 integration test methods to `TestRunPipelineIntegration` (8 test cases total including 3 parametrize)

## Decisions Made

- **Dedicated SQL constant:** `ETL_UPDATE_RUN_WATERMARK` rather than extending `ETL_UPDATE_RUN` — the failed/empty `_end_run` callers pass no watermark, making the no-advance-on-failure invariant enforceable by the SQL layer, not just a runtime branch
- **D-07 call-site coercion:** `int()` for `numpy.int64`, `.to_pydatetime()` for `pd.Timestamp`, `str()` for `numpy.str_` — all at the `run()` call-site; frozen `_encode_watermark` stays untouched (verified live: `isinstance(np.int64(5), int)` is `False`)
- **WR-01/WR-02 deferred:** Decode hardening (`ETLError` on missing/unknown `type` tag in `_decode_watermark`) deferred to Phase 28 — every envelope Phase 27 reads was written by `_encode_watermark`, so the permissive/opaque branches are unreachable with Phase-27-produced data
- **Roundtrip test design:** Each parametrize case (int/str/datetime) uses a fresh unique table with `PK + non-conflict column`; `load_mode="upsert"` required (append/replace + incremental_column is forbidden at construction); assert against coerced `max()` not hand-literals (Pitfall 4)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] etl_table fixture lacks PRIMARY KEY for upsert tests**
- **Found during:** Task 3 (integration tests)
- **Issue:** `etl_table` fixture creates `(id INTEGER, val TEXT)` without a unique constraint; upsert with `conflict_columns=["id"]` raises `psycopg.errors.InvalidColumnReference`
- **Fix:** Tests that need upsert semantics create their own tables with `id INTEGER PRIMARY KEY` inline (using the same pattern as `test_upsert_inserts_new_no_duplicates`); tests that only need D-06 guard (fires before load) continue to use `etl_table`
- **Files modified:** `tests/test_etl_accessor.py`
- **Verification:** All 8 test cases pass
- **Committed in:** `682de82` (Task 3 commit)

**2. [Rule 1 - Bug] Roundtrip test: upsert with single-column table yields empty SET clause**
- **Found during:** Task 3 (integration tests), roundtrip parametrize case with `SELECT 42 AS qty`
- **Issue:** `ON CONFLICT (qty) DO UPDATE SET ` with no non-conflict columns is a SQL syntax error (`SyntaxError: erreur de syntaxe à la fin de l'entrée`)
- **Fix:** Each parametrize case adds a second non-conflict column (`tag TEXT` / `n INTEGER`) to both source SQL and target DDL so the upsert SET clause is non-empty
- **Files modified:** `tests/test_etl_accessor.py`
- **Verification:** All 3 roundtrip parametrize cases pass
- **Committed in:** `682de82` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — test design bugs discovered during green phase)
**Impact on plan:** Both fixes necessary for correct test execution. No scope creep; the invariants being tested are unchanged.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## Known Stubs

None. `_read_watermark` is fully wired and tested. The only intentional scope deferral is the WHERE-filter wiring (Phase 28 / ETL-INC-03) — `_read_watermark` exists and is tested, just not yet applied as an extract bound. This is documented in the method's docstring.

## Threat Flags

No new threat surface beyond what the plan's `<threat_model>` covers. All four STRIDE threats (T-27-01..T-27-05) have been verified:
- T-27-01: `Jsonb(watermark)` wraps the dict natively at the binding site — no string interpolation of the value into SQL
- T-27-02: `pipeline_name` bound as `%s` param in `_read_watermark`
- T-27-03: Neither new constant carries a trailing `;`
- T-27-SC: Zero new runtime dependencies (psycopg.types.json.Jsonb is a submodule of the already-pinned psycopg)

## Next Phase Readiness

- Phase 28 (ETL-INC-03): `_read_watermark(name)` is available and tested; wire it as the `WHERE col > last_watermark` extract bound in `run()`
- Phase 28 (ETL-INC-07): `RunResult.watermark_used` / `watermark_recorded` — `_row_to_result` deliberately drops `watermark` (ETL-INC-07 deferred)
- Phase 28 (ETL-INC-11): `AsyncETLAccessor` incremental mirror + `TestEtlParity` parity
- WR-01/WR-02 carry-forward: harden `_decode_watermark` in Phase 28 when `history()`/`last_run()` start surfacing arbitrary historical rows

---
*Phase: 27-incremental-etl-run-log-integration*
*Completed: 2026-06-20*
