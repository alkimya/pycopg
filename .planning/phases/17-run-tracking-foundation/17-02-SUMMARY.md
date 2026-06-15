---
phase: 17-run-tracking-foundation
plan: "02"
subsystem: etl
tags: [gap-closure, run-tracking, session-isolation, structural-fix]
dependency_graph:
  requires: [17-01]
  provides: [ETL-08, ETL-09]
  affects: [pycopg/etl.py, tests/test_etl_accessor.py]
tech_stack:
  added: []
  patterns:
    - "Dedicated db.connect(autocommit=True) per run-log write bypasses session-aware cursor()"
    - "row_factory=dict_row on direct psycopg cursor for dict-keyed RETURNING row access"
    - "Gap-catching regression test: fresh out-of-band read confirms committed isolation"
key_files:
  created: []
  modified:
    - pycopg/etl.py
    - tests/test_etl_accessor.py
decisions:
  - "Verifier option A chosen: ETLAccessor write methods open db.connect(autocommit=True) directly, bypassing Database.cursor() session-reuse entirely (structural fix, not conditional)"
  - "Database.cursor() left unchanged — session/cursor contract preserved for all other library consumers (Verifier option B rejected)"
  - "Gap-catching test uses out-of-band fresh connection to confirm _start_run row is durably committed BEFORE session closes — the only reliable way to prove session-path isolation given that session() commits in finally"
metrics:
  duration: "~8 minutes"
  completed: "2026-06-15T11:52:09Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
  tests_added: 1
  tests_total: 11
---

# Phase 17 Plan 02: Session-Path Isolation Gap Closure Summary

**One-liner:** Structural run-log isolation via dedicated db.connect(autocommit=True) per write — bypasses session-aware cursor() so run rows commit independently on any path including active db.session().

## What Was Built

This plan closed the single verified gap from 17-VERIFICATION.md (status: `gaps_found`). The gap: `ETLAccessor.init`/`_start_run`/`_end_run` called `self._db.execute(..., autocommit=True)` which routes through `Database.cursor()`. When `db.session()` is active, `cursor()` reuses `_session_conn` (a transactional connection) and skips the commit block — making run-log writes part of the session transaction rather than independent autocommit operations.

**Fix:** All three write methods now open a dedicated connection via `self._db.connect(autocommit=True)` and run their SQL on a `row_factory=dict_row` cursor from that connection. This bypasses `Database.cursor()`'s session-reuse logic entirely. Isolation is now structural, not conditional.

**Regression test:** `test_failed_run_commits_inside_session` confirms the invariant on the session-active path: it calls `_start_run` inside `with db.session():`, then reads the pipeline_runs row via a fresh out-of-band connection BEFORE the session closes, asserting the row is already committed. This test FAILS against pre-fix etl.py (row is pending on session connection, not visible from outside) and PASSES after the fix.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Make run-log writes structurally isolated | 9098861 | pycopg/etl.py |
| 2 | Regression test + _FakeDatabase update | f7b7b17 | tests/test_etl_accessor.py |

## Commits

- `9098861` — `fix(17-02): make run-log writes structurally isolated via dedicated connect(autocommit=True)`
- `f7b7b17` — `test(17-02): update _FakeDatabase for connect()+cursor protocol; add session-path regression test`

## Changes in Detail

### pycopg/etl.py

- Added `from psycopg.rows import dict_row` import (same path as database.py).
- `init()`: body replaced with `with self._db.connect(autocommit=True) as conn: with conn.cursor(row_factory=dict_row) as cur: cur.execute(queries.ETL_INIT_PIPELINE_RUNS)`. Docstring updated to note literal `db.connect(autocommit=True)` mechanism (D-04).
- `_start_run()`: body replaced with `connect(autocommit=True)` + `cursor(row_factory=dict_row)` + `cur.execute(ETL_INSERT_RUN, [name, "running", datetime.now(UTC)])` + `return cur.fetchone()["run_id"]`. Still returns int run_id from RETURNING row. Docstring updated (D-04/D-05).
- `_end_run()`: body replaced with same pattern + `cur.execute(ETL_UPDATE_RUN, [status, datetime.now(UTC), rows_extracted, rows_loaded, error_message, error_traceback, run_id])`. Docstring updated (D-04/D-05/ETL-08/ETL-09).
- `pycopg/database.py` NOT modified.

### tests/test_etl_accessor.py

- `_FakeDatabase` refitted: removed `execute()`, added `connect(autocommit=False)` returning a context manager yielding a fake connection. Fake connection's `cursor()` returns a fake cursor whose `execute()` appends `(sql, params, autocommit_flag)` to `self.calls` and whose `fetchone()` returns `{"run_id": 42}`. The 6 existing unit tests' assertions (param order, `autocommit is True`, returns 42, no `'error'` literal) are unchanged.
- Added `from psycopg.rows import dict_row` import for the out-of-band read in the new integration test.
- Added `test_failed_run_commits_inside_session` to `TestETLAccessorIntegration`: opens a session, calls `_start_run` inside it, then reads pipeline_runs via `db.connect(autocommit=True)` (a fresh out-of-band connection), asserts the row is immediately visible (committed). Then calls `_end_run` with `status='failed'` inside a failed `db.transaction()`, reads again via fresh connection, asserts `status='failed'`. Also asserts the in-transaction sentinel row (999) was rolled back while baseline (1) persists.

## Deviations from Plan

### Design Clarification (not a deviation)

The plan described causing a session rollback by "raising inside `with db.session():`". The actual `session()` implementation commits in its `finally` block regardless of exceptions — so raising does not roll back the session. The test was therefore structured to use a fresh out-of-band connection to prove the run-log row is committed INDEPENDENTLY during the session (not pending on it) — a stronger and more direct proof of the D-04 invariant than checking post-session. The test still uses `with db.session()` and `with db.transaction()` inside to demonstrate the rollback of the load mutation (sentinel 999), satisfying both assertions (a) and (b) from the plan's acceptance criteria.

## Gap Closure Confirmation

The verified gap from 17-VERIFICATION.md Truth #4 (SC-4 PARTIAL) is now FULLY CLOSED:

| Path | Pre-fix | Post-fix |
|------|---------|---------|
| No-session path | PASS (test_failed_run_commits_despite_load_rollback) | PASS |
| Session-active path | FAIL (row pending on session conn, invisible from outside) | PASS (row committed immediately on own conn) |

## Threat Surface Scan

No new security-relevant surface introduced. The fix only changes WHICH connection runs the existing `%s`-parameterized SQL constants — no new network endpoints, no new auth paths, no schema changes. T-17-04 (connection entanglement) is now mitigated as documented in the threat register.

## Self-Check: PASSED

Commits verified:
- `9098861`: `git log --oneline -5` shows `fix(17-02): make run-log writes structurally isolated via dedicated connect(autocommit=True)`
- `f7b7b17`: `git log --oneline -5` shows `test(17-02): update _FakeDatabase for connect()+cursor protocol; add session-path regression test`
- `pycopg/database.py` not in `git diff --name-only HEAD~2 HEAD`
- `uv run pytest tests/test_etl_accessor.py -o addopts="" -q`: 11 passed
- `uv run ruff check pycopg/etl.py tests/test_etl_accessor.py`: All checks passed
- `uv run black --check pycopg/etl.py tests/test_etl_accessor.py`: 2 files would be left unchanged
