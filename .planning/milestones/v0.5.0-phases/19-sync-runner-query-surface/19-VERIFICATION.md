---
phase: 19-sync-runner-query-surface
verified: 2026-06-15T00:00:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred:
  - truth: "async_db.etl property and async ETL parity (ETL-12/ETL-13)"
    addressed_in: "Phase 20"
    evidence: "Phase 20 goal: async ETL parity; ETL-12/13 are traceability-mapped to Phase 20 in REQUIREMENTS.md. The 4 pre-existing full-suite failures include test_parity::test_all_database_public_methods_exist_in_async (etl property missing on AsyncDatabase) and test_parity::test_known_exceptions_documented — both are scoped out of v0.5.0 sync-runner milestone per 19-CONTEXT.md."
human_verification: []
---

# Phase 19: Sync Runner & Query Surface — Verification Report

**Phase Goal:** Deliver the user-facing return/query surface for the sync ETL runner — `RunResult` value object, `run() -> RunResult` upgrade, `dry_run` early fork, `history()`, and `last_run()` — covering ETL-10, ETL-11, ETL-15, ETL-17.
**Verified:** 2026-06-15
**Status:** PASSED
**Re-verification:** No — initial verification.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `RunResult` is a `@dataclass(frozen=True)` with exactly 8 fields in D-02 order (D-01/D-02) | VERIFIED | `etl.py:202-236` — `@dataclass(frozen=True)`, fields `[run_id, pipeline_name, status, rows_extracted, rows_loaded, started_at, finished_at, error]`, no `watermark`/`error_traceback`; programmatic field-order check passes |
| 2 | `_row_to_result` maps `pipeline_runs` dict to `RunResult`, renaming `error_message -> error`, dropping `error_traceback` and `watermark` (D-10) | VERIFIED | `etl.py:480-505` — pure function; `error=row["error_message"]`; only 8 fields constructed; `TestRowToResult` (5 tests, all green) confirms rename + drops + frozen invariant |
| 3 | `ETL_GET_RUN` selects a single `pipeline_runs` row keyed on `run_id`, no `LIMIT` (D-11) | VERIFIED | `queries.py:297-301` — `SELECT * FROM pipeline_runs WHERE run_id = %s`, no `LIMIT`; programmatic check passes |
| 4 | `db.etl.run(pipeline)` returns a `RunResult` re-SELECTed from the just-written row (ETL-10/D-11) | VERIFIED | `etl.py:933,1004` — both `return run_id` sites replaced by `return self._fetch_run_result(run_id)`; `_fetch_run_result` at `etl.py:644-664` uses `ETL_GET_RUN`; `TestRunResultSurface::test_run_result_fields_match_pipeline_runs_row` cross-checks result fields vs direct DB query by `run_id` — passes |
| 5 | `db.etl.run(pipeline, dry_run=True)` forks before `init()`, writes no `pipeline_runs` row, returns `RunResult(status='dry_run', rows_loaded=0, run_id=None)` (ETL-15/D-08/D-09) | VERIFIED | `etl.py:799-862` — dry-run block at position before `self.init()` (line 864); returns `RunResult(run_id=None, status="dry_run", rows_loaded=0, ...)`; shape check confirms `i_dry < i_init`; `test_dry_run_writes_no_pipeline_runs_row` asserts `COUNT(*)=0` — passes; `test_dry_run_target_table_unchanged` confirms no load |
| 6 | `db.etl.history(name, limit=100)` returns `list[RunResult]`, newest-first, via `ETL_LIST_RUNS` (ETL-11/D-06) | VERIFIED | `etl.py:666-693` — `autocommit=True`, `dict_row`, executes `queries.ETL_LIST_RUNS` with `[name, limit]`, returns `[_row_to_result(row) for row in rows]`; `test_history_two_runs_returns_two_entries_newest_first` asserts `hist[0].run_id == result2.run_id` — passes |
| 7 | `db.etl.last_run(name)` returns most-recent `RunResult` or `None` when no runs, via `ETL_GET_LAST_RUN` (ETL-17/D-07) | VERIFIED | `etl.py:695-719` — `autocommit=True`, `dict_row`, executes `queries.ETL_GET_LAST_RUN` with `[name]`, `fetchone()`, returns `_row_to_result(row) if row is not None else None`; `test_last_run_returns_none_when_no_runs` asserts `None` — passes; `test_last_run_returns_most_recent` asserts equals `history[0]` — passes |
| 8 | Phase 17 run-log isolation and Phase 18 atomic load write paths are unchanged | VERIFIED | `etl.py` `init`/`_start_run`/`_end_run` bodies untouched; all pre-existing `TestETLAccessorIntegration` and `TestRunPipelineIntegration` tests (41 tests) pass without modification |

**Score:** 8/8 truths verified

---

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | `async_db.etl` property + `AsyncETLAccessor.run/history/last_run/dry_run` returning `RunResult` (ETL-12/ETL-13) | Phase 20 | REQUIREMENTS.md traceability: ETL-12 and ETL-13 mapped to Phase 20; 19-CONTEXT.md §"Out of scope": "AsyncETLAccessor, lazy `async_db.etl` property, TestEtlParity — Phase 20 (ETL-12/13)" |
| 2 | Pre-existing parity test failures: `test_async_transaction_fix`, `test_all_database_public_methods_exist_in_async` (missing `etl` on AsyncDatabase), `test_known_exceptions_documented`, `test_postgis_errors::test_create_spatial_index_name_parameter` | Phase 20 / later | Orchestrator-confirmed pre-existing on commit `9f18adf` (pre-phase-19). The async `etl` property gap is a Phase 20 deliverable. |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/queries.py` | `ETL_GET_RUN` constant | VERIFIED | Lines 297-301: `SELECT * FROM pipeline_runs WHERE run_id = %s`, no `LIMIT` |
| `pycopg/etl.py` | `RunResult` frozen dataclass (8 fields) | VERIFIED | Lines 202-236: `@dataclass(frozen=True)`, all 8 D-02 fields, no extras |
| `pycopg/etl.py` | `_row_to_result(row: dict) -> RunResult` mapper | VERIFIED | Lines 480-505: pure function, `error=row["error_message"]`, drops `error_traceback`/`watermark` |
| `pycopg/etl.py` | `_fetch_run_result(self, run_id: int) -> RunResult` | VERIFIED | Lines 644-664: uses `ETL_GET_RUN`, `autocommit=True`, `dict_row` |
| `pycopg/etl.py` | `run(pipeline, dry_run=False) -> RunResult` (upgraded) | VERIFIED | Lines 721-1004: dry-run early fork + two `_fetch_run_result` return sites; no `return run_id` remains |
| `pycopg/etl.py` | `history(name, limit=100) -> list[RunResult]` | VERIFIED | Lines 666-693: `ETL_LIST_RUNS`, `autocommit=True`, mapper applied per row |
| `pycopg/etl.py` | `last_run(name) -> RunResult \| None` | VERIFIED | Lines 695-719: `ETL_GET_LAST_RUN`, `autocommit=True`, `None` when no row |
| `tests/test_etl.py` | `TestRowToResult` — DB-free unit class | VERIFIED | Lines 424-481: 5 tests (all-8-fields, rename, error_traceback-dropped, watermark-dropped, frozen); all pass |
| `tests/test_etl_accessor.py` | `TestRunResultSurface` — SC-1..SC-4 integration class | VERIFIED | Lines 1062-1307: 16 tests covering all 4 success criteria; all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `ETLAccessor.run()` | `queries.ETL_GET_RUN` | `_fetch_run_result`, `dict_row` cursor, `[run_id]` | WIRED | `etl.py:662`; both return sites wired; shape check confirms |
| `ETLAccessor.history()` | `queries.ETL_LIST_RUNS` | `dict_row` cursor, `[name, limit]`, `_row_to_result` per row | WIRED | `etl.py:691`; `fetchall()` + list comprehension |
| `ETLAccessor.last_run()` | `queries.ETL_GET_LAST_RUN` | `dict_row` cursor, `[name]`, `_row_to_result` or `None` | WIRED | `etl.py:717-719`; `fetchone()` + None guard |
| `_row_to_result` | `RunResult` | constructs `RunResult`, `error=row["error_message"]` | WIRED | `etl.py:496-505`; 5 unit tests confirm rename + drops |
| `TestRunResultSurface` | `db.etl.run/history/last_run` | real `pycopg_test` DB fixtures | WIRED | All 16 integration tests pass against live DB |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `ETLAccessor.run()` | `RunResult` from `_fetch_run_result` | `ETL_GET_RUN` → `pipeline_runs` DB row post-`_end_run` | Yes — re-SELECTs the actual persisted row | FLOWING |
| `ETLAccessor.history()` | `list[RunResult]` from `fetchall()` | `ETL_LIST_RUNS` → `pipeline_runs` rows for `pipeline_name` | Yes — full `ORDER BY started_at DESC LIMIT %s` query | FLOWING |
| `ETLAccessor.last_run()` | `RunResult \| None` from `fetchone()` | `ETL_GET_LAST_RUN` → one row or `None` | Yes — real DB query; `None` path proven by test | FLOWING |
| `dry_run` branch in `run()` | In-memory `RunResult` | Extract+transform in-memory; no DB write | By design (D-08/D-09) — `run_id=None`, no row | FLOWING (expected) |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `RunResult` field names match D-02 spec | `python -c "from pycopg.etl import RunResult,_row_to_result; ..."` | All 8 fields in order, frozen, rename confirmed | PASS |
| `ETL_GET_RUN` shape | `python -c "from pycopg import queries; ..."` | `WHERE run_id = %s`, no `LIMIT` | PASS |
| `run()` shape: dry_run before `init()`, no `return run_id` | `python -` inline script | `i_dry < i_init`, no stale return | PASS |
| `TestRowToResult` (5 DB-free unit tests) | `uv run pytest tests/test_etl.py -o addopts=""` | 115 passed | PASS |
| `TestRunResultSurface` (16 integration tests) | `uv run pytest tests/test_etl_accessor.py -o addopts=""` | 57 passed | PASS |
| Full ETL targeted suite | `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -o addopts=""` | 172 passed, 0 failed | PASS |

---

### Probe Execution

No `probe-*.sh` files declared or conventional for this phase. Step 7c: SKIPPED (no probes defined).

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ETL-10 | Plans 01/02/03 | `run()` returns `RunResult` with 8 fields | SATISFIED | `_fetch_run_result` re-SELECTs by `run_id`; `TestRunResultSurface::test_run_result_fields_match_pipeline_runs_row` cross-verifies against DB row |
| ETL-11 | Plans 01/02/03 | `history("name")` returns `list[RunResult]`, newest-first | SATISFIED | `ETL_LIST_RUNS` `ORDER BY started_at DESC`; `test_history_two_runs_returns_two_entries_newest_first` asserts order |
| ETL-15 | Plans 01/02/03 | `run(p, dry_run=True)` skips load, writes no record | SATISFIED | Dry-run fork before `self.init()`; `test_dry_run_writes_no_pipeline_runs_row` (COUNT=0) + `test_dry_run_target_table_unchanged` |
| ETL-17 | Plans 01/02/03 | `last_run("name")` returns most-recent or `None` | SATISFIED | `ETL_GET_LAST_RUN`; `test_last_run_returns_none_when_no_runs` + `test_last_run_not_the_older_run_when_two_exist` |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | No anti-patterns found |

All 4 phase-19 files (`pycopg/etl.py`, `pycopg/queries.py`, `tests/test_etl.py`, `tests/test_etl_accessor.py`) scanned for `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER`, `return null`, `return []`, `return {}`, and stub indicators. None found. `ruff check` on all 4 files: clean.

No bare `run_id = db.etl.run(` capture sites remain in `tests/test_etl_accessor.py` (0 matches). No `isinstance(run_id, int)` assertion remains (0 matches). All migrated to `result = db.etl.run(p); run_id = result.run_id` pattern.

---

### Human Verification Required

None. All Phase 19 behaviors have automated verification (SC-1..SC-4 are integration-testable against `pycopg_test`; D-10 mapper is pure unit-testable). The VALIDATION.md "Manual-Only Verifications" table has no entries.

---

### Gaps Summary

No gaps. All 8 must-have truths verified. All 4 requirements (ETL-10, ETL-11, ETL-15, ETL-17) satisfied with green tests. Phase 17 and 18 write-path invariants confirmed non-regressed (41 pre-existing tests pass). The 4 full-suite failures are pre-existing and scoped to Phase 20 (async parity).

---

_Verified: 2026-06-15_
_Verifier: Claude (gsd-verifier)_
