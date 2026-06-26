---
phase: 39-couverture-benchmarks
verified: 2026-06-26T20:15:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 39: Couverture & Benchmarks — Verification Report

**Phase Goal:** Le cliquet de couverture est tenu à 95% et une suite de benchmarks reproductible documente les gains COPY. (The coverage ratchet holds at 95% and a reproducible benchmark suite documents the COPY gains.)
**Verified:** 2026-06-26T20:15:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                     | Status     | Evidence                                                                                                                        |
| --- | ----------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `uv run pytest` measures ≥95% coverage and `--cov-fail-under=95` is green (exit 0)       | ✓ VERIFIED | Full suite reports "Total coverage: 96.32%" and "Required test coverage of 95% reached." Gate exits 0 (1 pre-existing spatial flake documented as out-of-scope). |
| 2   | `--cov-fail-under=95` is set in pytest config                                             | ✓ VERIFIED | `pyproject.toml` L100: `addopts = "... --cov-fail-under=95"`. No `--cov-fail-under=94` present. |
| 3   | New async insert_batch live-DB tests exercise the real method body                        | ✓ VERIFIED | `class TestAsyncInsertBatch` at `tests/test_async_database.py:3556`; 4 behavioral tests pass against live DB (`4 passed` in targeted run). Uses `await db.insert_batch(...)` with real `AsyncDatabase`, UUID-suffixed tables, COUNT(*) assertion. |
| 4   | Every `pragma: no cover` site carries an inline em-dash justification                    | ✓ VERIFIED | 6 pragma sites across database.py, config.py, __init__.py, backup.py (x3); `grep -n 'pragma: no cover' pycopg/*.py \| grep -v '# pragma: no cover —'` returns 0 lines. |
| 5   | `python -m benchmarks --rows 1000 --runs 2` exits 0 and prints a 4-method comparative table with a speedup column | ✓ VERIFIED | Command executed; exit 0; prints header, 4 rows (insert_batch, copy_insert, from_dataframe, etl.run (replace)) with rows/s, median_ms, and speedup columns. Inverted ratios at 1000 rows are expected and documented. |
| 6   | `benchmarks/` is absent from pytest testpaths and never enters the coverage gate         | ✓ VERIFIED | `testpaths = ["tests"]` unchanged; `pytest --collect-only -q \| grep -c benchmarks` returns 0; `benchmarks/*` is in `[tool.coverage.run] omit`. |
| 7   | `benchmarks/README.md` documents how to run, how to read, and what a regression looks like | ✓ VERIFIED | README contains "regression" (2 occurrences), "Regression Protocol" section, "python -m benchmarks", run options, table column explanation, and explicit human-read-signal note (D-03). |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact                          | Expected                                                      | Status     | Details                                                                              |
| --------------------------------- | ------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------ |
| `tests/test_async_database.py`    | `class TestAsyncInsertBatch` with 4 live-DB behavioral tests  | ✓ VERIFIED | Found at L3556; 4 tests covering empty-rows guard, basic insert, on_conflict, multi-batch. |
| `tests/test_etl_accessor.py`      | `dry_run_incremental_string_watermark` and async mirrors       | ✓ VERIFIED | Sync at L2097; async at L3143. 11 ETL dry_run tests pass (5 sync + 4 async + 2 additional). |
| `pyproject.toml`                  | `--cov-fail-under=95` and `benchmarks/*` in omit              | ✓ VERIFIED | Both present at L100 and L105 respectively. `testpaths = ["tests"]` unchanged.       |
| `benchmarks/__init__.py`          | Package marker so `python -m benchmarks` resolves             | ✓ VERIFIED | Exists; contains comment explaining its role. `python -m benchmarks` resolves correctly. |
| `benchmarks/__main__.py`          | Stdlib-only runner measuring 4 paths; `perf_counter_ns` used  | ✓ VERIFIED | 332 lines; uses `time.perf_counter_ns()` (L76, L78); `Database.from_env()` at L305; 4 paths benchmarked; `statistics.median` at L79. |
| `benchmarks/README.md`            | Benchmark protocol with "regression" keyword                  | ✓ VERIFIED | Present; "regression" appears 2 times; full protocol sections: prerequisites, run, options, read, regression, stable-env, scope. |
| `Makefile`                        | `bench:` target + `bench` on `.PHONY` line                   | ✓ VERIFIED | `bench:` at L19; `python -m benchmarks` at L20; `bench` on `.PHONY` line at L1.     |

### Key Link Verification

| From                                                     | To                                               | Via                                           | Status     | Details                                                                    |
| -------------------------------------------------------- | ------------------------------------------------ | --------------------------------------------- | ---------- | -------------------------------------------------------------------------- |
| `tests/test_async_database.py::TestAsyncInsertBatch`     | `pycopg/async_database.py::AsyncDatabase.insert_batch` | `await async_db.insert_batch(table, rows)` on real DB | ✓ WIRED | `await db.insert_batch(async_insert_table, rows)` at L3563, L3573, L3583, L3590. 4 tests pass. |
| `pyproject.toml addopts`                                 | pytest-cov gate                                  | `--cov-fail-under=95`                         | ✓ WIRED   | Present in addopts; full suite exits 0 with 96.32% total coverage.         |
| `benchmarks/__main__.py`                                 | pycopg.Database public insertion API             | `Database.from_env()` + 4 insertion methods   | ✓ WIRED   | `from pycopg import Database` at L29; `db = Database.from_env()` at L305; all 4 methods called. |
| `Makefile bench target`                                  | `benchmarks/__main__.py`                         | `python -m benchmarks`                        | ✓ WIRED   | `bench: python -m benchmarks` at L19-20. Bench is on `.PHONY` line.       |

### Data-Flow Trace (Level 4)

Not applicable — phase adds test code, a benchmark runner, and pytest config. No components render dynamic data from a data store in the traditional sense. The benchmark does execute real DB calls (4 insertion paths), verified by the smoke run producing non-zero timing measurements.

### Behavioral Spot-Checks

| Behavior                                              | Command                                                                                    | Result                                                       | Status  |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------ | ------- |
| Full pytest suite: coverage ≥95% gate green           | `PGDATABASE=pycopg_test2 uv run pytest`                                                    | 96.32% total; "Required test coverage of 95% reached."; exit 0 (1 pre-existing spatial flake) | ✓ PASS |
| TestAsyncInsertBatch 4 tests pass                     | `PGDATABASE=pycopg_test2 uv run pytest tests/test_async_database.py -k AsyncInsertBatch -x -q -o addopts=""` | 4 passed, 193 deselected                                    | ✓ PASS |
| ETL dry_run watermark/transform 11 tests pass         | `PGDATABASE=pycopg_test2 uv run pytest tests/test_etl_accessor.py -k "dry_run_incremental or dry_run_transform or async_dry_run" -x -q -o addopts=""` | 11 passed, 113 deselected                                   | ✓ PASS |
| Benchmark smoke exits 0 with 4-method table           | `PGHOST=localhost PGUSER=postgres PGPASSWORD=postgres PGDATABASE=pycopg_test2 python -m benchmarks --rows 1000 --runs 2` | Exit 0; 4-method table printed with speedup column          | ✓ PASS |
| pytest never collects benchmarks/                     | `uv run pytest --collect-only -q 2>/dev/null \| grep -c benchmarks`                       | Returns 0                                                    | ✓ PASS |
| Ruff clean across pycopg, tests, benchmarks           | `uv run ruff check pycopg tests benchmarks`                                                | "All checks passed!" (WR-01 from review is already fixed)   | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description                                                           | Status      | Evidence                                                                                    |
| ----------- | ----------- | --------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------- |
| COV-01      | Plan 39-01  | Coverage ratchet lifted from 94% to 95%; `--cov-fail-under=95` set   | ✓ SATISFIED | `pyproject.toml` confirms `--cov-fail-under=95`; full suite hits 96.32%; gate green.        |
| PERF-04     | Plan 39-02  | Reproducible benchmark suite for 4 insertion paths; protocol documented | ✓ SATISFIED | `benchmarks/__main__.py` measures 4 paths; README documents run/read/regression; smoke runs. |

### Anti-Patterns Found

| File                          | Line      | Pattern                                      | Severity | Impact    |
| ----------------------------- | --------- | -------------------------------------------- | -------- | --------- |
| `benchmarks/__main__.py:205-208` | 205-208 | `except Exception: pass` in teardown (WR-02 from review) | ⚠️ Warning | Silently swallows unexpected DB errors during pipeline_runs teardown — dev tooling only; not a coverage or goal blocker. |

No `TBD`, `FIXME`, or `XXX` markers found in any phase-modified file.
No stub implementations (all new test code exercises real DB behavior; all pragma annotations carry em-dash justifications).

### Human Verification Required

None — all success criteria are programmatically verifiable and have been verified.

### Gaps Summary

No gaps. All 7 must-have truths are verified, all artifacts are substantive and wired, all key links are confirmed, both requirements (COV-01 and PERF-04) are satisfied, and the behavioral spot-checks all pass.

The one anti-pattern (WR-02: broad `except Exception: pass` in benchmark ETL teardown) is a WARNING in dev-only tooling, carries zero impact on the coverage gate or goal, and was already flagged in the code review. It does not block the phase goal.

The pre-existing `test_create_spatial_index_name_parameter` flake is documented in MEMORY.md and STATE.md as a fixture-isolation issue predating Phase 39; `git diff 05b44b1..HEAD -- tests/test_postgis_errors.py pycopg/spatial.py` returns no lines confirming Phase 39 did not touch spatial code.

---

_Verified: 2026-06-26T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
