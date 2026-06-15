---
phase: 17-run-tracking-foundation
verified: 2026-06-15T12:00:00Z
status: gaps_found
score: 4/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "The separate-connection run-log write pattern is SOLID — so all subsequent load phases inherit correct transaction boundary behavior"
    status: failed
    reason: |
      ETLAccessor._start_run / _end_run / init all call self._db.execute(..., autocommit=True),
      which routes through Database.cursor(autocommit=True). When db.session() is active
      (_session_conn is not None), cursor() reuses the session's transactional connection and
      skips the commit block (the 'if not autocommit:' guard is bypassed without opening a
      fresh connection). Run-log writes issued inside an active session therefore execute on the
      session transaction and are rolled back with it if the session rolls back — exactly the
      data-loss scenario D-04/D-05 exist to prevent. SC-4's
      test_failed_run_commits_despite_load_rollback only exercises the no-session path
      (db.transaction() without db.session()) so the bug is invisible to the test suite.
      Phase 18 will build real load logic on this primitive; if it uses db.session() to
      reuse a connection across extract + load steps, the SC-4 invariant silently breaks.
      The PLAN's CRITICAL note acknowledges the constraint ("as long as run-log writes are
      NEVER issued inside a db.session(...) that wraps the load") but this is an unenforced
      negative consumer constraint, not a structural guarantee. The phase goal's framing —
      "pattern is SOLID so all subsequent load phases INHERIT correct behavior" — is not
      satisfied when the correctness depends on a usage constraint that is invisible at the
      API call site and untested.
    artifacts:
      - path: "pycopg/database.py"
        issue: "cursor(autocommit=True) does not open a fresh connection when _session_conn is not None; it reuses the session connection without committing"
      - path: "pycopg/etl.py"
        issue: "All three write methods (_start_run, _end_run, init) rely on self._db.execute(..., autocommit=True) to deliver connection isolation, but that guarantee is conditional on no active session"
      - path: "tests/test_etl_accessor.py"
        issue: "test_failed_run_commits_despite_load_rollback only exercises the no-session else-branch of cursor(); no test covers the session-active path"
    missing:
      - "Either: ETLAccessor write methods must bypass cursor() entirely and open a dedicated connection via self._db.connect(autocommit=True), making isolation unconditional; OR Database.cursor(autocommit=True) must open a fresh connection even when a session is active"
      - "A regression test must wrap db.etl._start_run + a failing load inside with db.session(): and assert the pipeline_runs row survives the session rollback — this is the missing coverage for the session-path"
---

# Phase 17: Run-Tracking Foundation — Verification Report

**Phase Goal:** The `pipeline_runs` table schema is finalised and the separate-connection run-log write pattern is solid — so all subsequent load phases inherit correct transaction boundary behavior
**Verified:** 2026-06-15T12:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After any run(), a pipeline_runs row exists with run_id, pipeline_name, started_at, finished_at, status, rows_extracted, rows_loaded, and a NULL watermark (SC-1 / ETL-07) | VERIFIED | test_run_writes_full_row passes; all columns confirmed non-null; watermark asserted IS NULL; run_id returned by run() maps to a real DB row |
| 2 | db.etl.init() creates pipeline_runs; a second call is idempotent — no error, no duplicate (SC-2 / ETL-14) | VERIFIED | test_init_idempotent passes; information_schema.tables count == 1 after two init() calls |
| 3 | Without an explicit init(), the first run() auto-creates pipeline_runs via CREATE TABLE IF NOT EXISTS (SC-3 / ETL-14) | VERIFIED | test_first_run_auto_creates passes; table dropped before run(), asserted present after |
| 4 | A run that fails during load records status='failed' with non-null error_message + error_traceback, committed even when the load transaction rolled back, because run-log writes use a dedicated autocommit connection (SC-4 / ETL-08 / ETL-09) | PARTIAL | test_failed_run_commits_despite_load_rollback passes on the no-session path (db.transaction() without db.session()). The invariant fails on the session path: cursor(autocommit=True) reuses _session_conn without committing when a session is active. The test does not cover this path. See gap detail below. |
| 5 | db.etl returns a lazily-constructed ETLAccessor bound to the parent Database (D-01/D-02) | VERIFIED | database.py lines 253-271: @property etl with None-check → in-property import → ETLAccessor(self) → store in self._etl → return. Property identity check confirmed structurally; pattern mirrors db.spatial exactly. |

**Score:** 4/5 truths verified (SC-4 is PARTIAL — tested no-session path only)

---

## CR-01 Assessment: Session-Path Isolation (from 17-REVIEW.md)

**Finding:** The code review raised CR-01 as a BLOCKER. This verification independently confirms it.

**Mechanism (verified in source):**

`Database.cursor()` at `pycopg/database.py:318-336`:

```python
if self._session_conn is not None:          # session active
    with self._session_conn.cursor(...) as cur:
        yield cur
        if not autocommit:                  # autocommit=True → this block SKIPPED
            ... commit / rollback ...
else:
    with self.connect(autocommit=autocommit) as conn:   # genuine fresh conn
        ...
```

When `db.session()` is active: `cursor(autocommit=True)` hands back a cursor on `_session_conn` (a transactional connection) and skips the commit. The connection is not switched to autocommit — `autocommit=True` is only an instruction to skip explicit commit/rollback management, not to open a dedicated connection.

**ETLAccessor write chain:** `init()` / `_start_run()` / `_end_run()` all call `self._db.execute(..., autocommit=True)` → `cursor(autocommit=True)`. On the no-session path (`_session_conn is None`), the `else` branch opens a fresh `connect(autocommit=True)` connection — genuinely independent. On the session path, all writes share `_session_conn` and are rolled back with the session.

**Phase 17 run() stub:** The stub does not open a session, so Phase 17's own delivered surface is safe. The 10 tests all pass, including SC-4.

**Why this is a gap against the phase goal:** The goal says the pattern is "solid — so all subsequent load phases inherit correct transaction boundary behavior." Phase 18 will implement real extract + load. If Phase 18's developer uses `db.session()` to reuse a connection across extract and load steps (a natural optimization following the `db.session` pattern documented in the library), run-log writes will silently lose their isolation. The API surface — `self._db.execute(..., autocommit=True)` — looks identical from Phase 18's perspective regardless of whether a session is active. There is no in-code enforcement of the PLAN's CRITICAL constraint. The phase goal's "solid foundation" claim requires the pattern to be safe under any consumer usage, not under a specific restricted usage documented only in plan comments.

**Not a deferred item:** Phase 18's success criteria address load-mode transactional correctness (SC 18-3: TRUNCATE+INSERT atomic), but none address run-log isolation under session. Phase 19 and 20 do not cover this either. The gap carries forward unaddressed.

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/etl.py` | ETLAccessor class with init(), _start_run(), _end_run(), run() | VERIFIED | All four methods present; numpydoc docstrings; autocommit=True on all writes; status literals 'running'/'success'/'failed' — no 'error' |
| `pycopg/database.py` | Database._etl lazy field + db.etl property mirroring db.spatial | VERIFIED | self._etl: ETLAccessor \| None = None in __init__ (line 86); etl @property at lines 253-271; TYPE_CHECKING import at line 58; mirrors spatial property shape exactly |
| `tests/test_etl_accessor.py` | Unit tests for param order/status string + DB integration tests SC-1..SC-4 | VERIFIED (partial) | 10 tests present and passing; 6 unit + 4 integration. SC-4 test exercises no-session path only. WR-04: status assertion in SC-1 test is `status in ("running", "success", "failed")` not pinned to "success". |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pycopg/database.py` db.etl property | `pycopg.etl.ETLAccessor` | in-property import + ETLAccessor(self) | WIRED | Confirmed at lines 267-270 |
| `pycopg/etl.py` ETLAccessor.init | pipeline_runs table | self._db.execute(queries.ETL_INIT_PIPELINE_RUNS, autocommit=True) | WIRED (conditional) | Works when no session active; silently breaks isolation when session active |
| `pycopg/etl.py` ETLAccessor._start_run | pipeline_runs table | self._db.execute(queries.ETL_INSERT_RUN, [...], autocommit=True) | WIRED (conditional) | Same session-path caveat |
| `pycopg/etl.py` ETLAccessor._end_run failure path | committed pipeline_runs row | autocommit connection separate from load txn | PARTIAL | No-session path: guaranteed. Session path: not guaranteed. |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `test_run_writes_full_row` | pipeline_runs row | db.etl.run("demo") → _start_run → ETL_INSERT_RUN RETURNING run_id | Yes — RETURNING clause confirmed in queries.py | FLOWING |
| `test_failed_run_commits_despite_load_rollback` | run_rows | SELECT from pipeline_runs by run_id | Yes — real DB row committed on autocommit conn (no-session path) | FLOWING on tested path |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ETLAccessor importable + all methods present | `python -c "from pycopg.etl import ETLAccessor; assert all(hasattr(ETLAccessor,m) for m in ('init','_start_run','_end_run','run'))"` | exit 0 | PASS |
| Database.etl property exists + ETLAccessor accessible | `python -c "from pycopg import Database; from pycopg.etl import ETLAccessor; assert hasattr(Database, 'etl')"` | exit 0 | PASS |
| No 'error' status literal in etl.py | `grep -nE "['\""]error['\""]" pycopg/etl.py \| grep -vi "error_message\|error_traceback\|raise\|except\|#"` | no output (exit 1 from grep = no match) | PASS |
| 10 tests pass in isolated run | `uv run pytest tests/test_etl_accessor.py -o addopts="" -q` | `10 passed in 0.75s` | PASS |
| Phase 17 files: ruff clean | `uv run ruff check pycopg/etl.py pycopg/database.py tests/test_etl_accessor.py` | `All checks passed!` | PASS |
| Phase 17 files: black clean | `uv run black --check pycopg/etl.py pycopg/database.py tests/test_etl_accessor.py` | `3 files would be left unchanged` | PASS |

Note: `uv run ruff check pycopg tests` (full-suite) exits 1 due to pre-existing violations in files not modified by Phase 17 (config.py, migrations.py, pool.py, test_*.py). This is a pre-existing baseline condition, not a Phase 17 regression. The PLAN's success criterion #6 specifies `uv run ruff check pycopg tests`; Phase 17 files individually are clean.

---

## Requirements Coverage

| Requirement | Phase | Description | Status | Evidence |
|-------------|-------|-------------|--------|---------|
| ETL-07 | 17 | After any run(), pipeline_runs row exists with all required columns incl. nullable watermark | SATISFIED | SC-1 test proves full row contract; watermark IS NULL asserted |
| ETL-08 | 17 | Failed run records status='failed' with error_message + error_traceback, committed even when load txn rolled back | PARTIAL | SC-4 proves this on no-session path; session-path is untested and broken |
| ETL-09 | 17 | Load runs in its own DB transaction; run-tracking write committed independently of load transaction | PARTIAL | Same as ETL-08 — no-session path works, session path does not |
| ETL-14 | 17 | pipeline_runs auto-created on first run(); explicit db.etl.init() also available | SATISFIED | SC-2 and SC-3 tests prove both paths |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_etl_accessor.py` | 192 | `status in ("running", "success", "failed")` | Warning (WR-04 from review) | SC-1 test does not pin status to "success" — a regression where _end_run silently no-ops (e.g. due to CR-01 leaving the UPDATE uncommitted in a session) would still pass |
| `pycopg/etl.py` | 354 | `return rows[0]["run_id"]` with no guard | Info (WR-01 from review) | IndexError if execute returns [] |

No `TBD`, `FIXME`, or `XXX` debt markers found in Phase 17 files.

---

## Human Verification Required

None. All phase-17-specific behaviors are programmatically verifiable.

---

## Gaps Summary

**One gap blocks the phase goal:**

The phase goal claims the separate-connection run-log write pattern is "solid" and that "all subsequent load phases inherit correct transaction boundary behavior." This claim is false when `db.session()` is active: `Database.cursor(autocommit=True)` reuses `_session_conn` without committing, making run-log writes part of the session transaction rather than an independent autocommit connection.

**What passes:** All 4 success criteria are satisfied as literally tested (no-session path). SC-1, SC-2, SC-3 are fully satisfied. SC-4 is satisfied on the tested path. The 10 tests pass. Ruff and black are clean on Phase 17 files. Commits 4a5458f and 69158bc exist as documented.

**What fails:** The phase goal's "solid foundation" framing requires the isolation invariant to hold regardless of how Phase 18/19 calls the primitives. The conditional nature of `autocommit=True` (only effective when no session is active) is not enforced at the API level and is not tested. This is a latent correctness risk for every subsequent load phase that the phase goal promises to prevent.

**Suggested fix for Phase 18 planning:** Before Phase 18 implements load logic, ETLAccessor write methods should be changed to bypass `self._db.execute()` and call `self._db.connect(autocommit=True)` directly, making isolation structural rather than conditional. A regression test should then assert the SC-4 invariant holds inside `with db.session():`.

---

_Verified: 2026-06-15T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
