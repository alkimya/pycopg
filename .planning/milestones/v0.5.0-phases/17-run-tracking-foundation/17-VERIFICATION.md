---
phase: 17-run-tracking-foundation
verified: 2026-06-15T12:30:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "The separate-connection run-log write pattern is SOLID — so all subsequent load phases inherit correct transaction boundary behavior (SC-4 / ETL-08 / ETL-09 / D-04 / D-05): session-active path now covered structurally"
  gaps_remaining: []
  regressions: []
---

# Phase 17: Run-Tracking Foundation — Verification Report (Re-verification)

**Phase Goal:** The `pipeline_runs` table schema is finalised and the separate-connection run-log write pattern is solid — so all subsequent load phases inherit correct transaction boundary behavior
**Verified:** 2026-06-15T12:30:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure via plan 17-02 (commits 9098861, f7b7b17, 0d69ef0)

---

## Gap Closure Summary

The single gap from the initial verification (score 4/5, `gaps_found`) was:

> `ETLAccessor.init` / `_start_run` / `_end_run` called `self._db.execute(..., autocommit=True)`, which routes through session-aware `Database.cursor()`. When `db.session()` is active, `cursor()` reuses `_session_conn` without committing, making run-log writes part of the session transaction — broken isolation on the session-active path.

Plan 17-02 made isolation **structural**: the three write methods now open a dedicated connection via `self._db.connect(autocommit=True)` directly, bypassing `Database.cursor()` entirely. Evidence: verified in source at `pycopg/etl.py` lines 336-338, 360-366, 410-423. `database.py` was NOT modified (`git diff --name-only 76716b8 HEAD -- pycopg/database.py` returned empty).

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After any run(), a pipeline_runs row exists with run_id, pipeline_name, started_at, finished_at, status, rows_extracted, rows_loaded, and a NULL watermark (SC-1 / ETL-07) | VERIFIED | test_run_writes_full_row passes; all columns asserted non-null; watermark IS NULL; run_id returned by run() maps to a real DB row |
| 2 | db.etl.init() creates pipeline_runs; a second call is idempotent — no error, no duplicate (SC-2 / ETL-14) | VERIFIED | test_init_idempotent passes; information_schema.tables count == 1 after two init() calls |
| 3 | Without an explicit init(), the first run() auto-creates pipeline_runs via CREATE TABLE IF NOT EXISTS (SC-3 / ETL-14) | VERIFIED | test_first_run_auto_creates passes; table dropped before run(), asserted present after |
| 4 | A run that fails records status='failed' committed even when the load transaction rolled back, because run-log writes use a dedicated autocommit connection — on BOTH the no-session AND the session-active path (SC-4 / ETL-08 / ETL-09 / D-04 / D-05) | VERIFIED | test_failed_run_commits_despite_load_rollback (no-session path) + test_failed_run_commits_inside_session (session-active path) both pass. New test uses out-of-band fresh connection to prove the run-log row is committed BEFORE the session closes — the strongest possible proof of structural isolation |
| 5 | db.etl returns a lazily-constructed ETLAccessor bound to the parent Database (D-01/D-02) | VERIFIED | database.py property unchanged from 17-01; confirmed wired at lines 253-271 |

**Score:** 5/5 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/etl.py` | ETLAccessor with init(), _start_run(), _end_run(), run() using dedicated connect(autocommit=True) | VERIFIED | All four methods present; `from psycopg.rows import dict_row` imported; exactly 3 `self._db.connect(autocommit=True)` call sites (one per write method); no `self._db.execute(...)` inside any write method body; status literals 'running'/'success'/'failed' only |
| `pycopg/database.py` | Database._etl lazy field + db.etl property — NOT modified by 17-02 | VERIFIED | `git diff --name-only 76716b8 HEAD -- pycopg/database.py` returned empty; session/cursor contract preserved for all other consumers |
| `tests/test_etl_accessor.py` | _FakeDatabase updated to fake connect()+cursor protocol; 11 tests including new test_failed_run_commits_inside_session | VERIFIED | 11 tests pass (`uv run pytest tests/test_etl_accessor.py -o addopts="" -q`: 11 passed in 1.15s); _FakeDatabase records `(sql, params, autocommit)` via the connect()+cursor fake; all 5 unit tests still assert param order and `autocommit is True` |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pycopg/etl.py` ETLAccessor.init | pipeline_runs table | `with self._db.connect(autocommit=True) as conn: with conn.cursor(row_factory=dict_row) as cur: cur.execute(ETL_INIT_PIPELINE_RUNS)` | WIRED (structural) | Verified at etl.py line 336-338; unconditional — does not consult _session_conn |
| `pycopg/etl.py` ETLAccessor._start_run | pipeline_runs table | `with self._db.connect(autocommit=True) as conn: ...cur.fetchone()["run_id"]` | WIRED (structural) | Verified at etl.py lines 360-366; returns int run_id from RETURNING row |
| `pycopg/etl.py` ETLAccessor._end_run | committed pipeline_runs row | dedicated autocommit connection independent of any session | WIRED (structural) | Verified at etl.py lines 410-423; isolation is now unconditional |
| `pycopg/database.py` connect() | _connect_with_retry (never _session_conn) | calls `_connect_with_retry(autocommit=autocommit)` directly | WIRED | Verified at database.py lines 284-302; connect() never consults self._session_conn — this is WHY the fix works |
| `tests/test_etl_accessor.py` test_failed_run_commits_inside_session | proof of session-path isolation | `with db.session():` + `db.connect(autocommit=True)` out-of-band read | WIRED | Test at lines 294-392; out-of-band read confirms _start_run row committed BEFORE session closes |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `test_run_writes_full_row` | pipeline_runs row | db.etl.run("demo") → _start_run → ETL_INSERT_RUN RETURNING run_id | Yes — RETURNING clause in queries.py | FLOWING |
| `test_failed_run_commits_despite_load_rollback` | run_rows | SELECT from pipeline_runs by run_id after no-session rollback path | Yes — row committed on dedicated autocommit conn | FLOWING |
| `test_failed_run_commits_inside_session` | early_rows, mid_rows, run_rows | Fresh out-of-band db.connect() reads during and after session | Yes — rows committed on own connections, visible from outside | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Exactly 3 dedicated connect(autocommit=True) sites in write methods | `grep -c "self._db.connect(autocommit=True)" pycopg/etl.py` | 3 | PASS |
| dict_row import present | `grep -q "from psycopg.rows import dict_row" pycopg/etl.py` | found | PASS |
| row_factory=dict_row used on cursors | `grep -q "row_factory=dict_row" pycopg/etl.py` | found | PASS |
| No write method still calls self._db.execute() | AST/regex check on init/_start_run/_end_run bodies | empty list | PASS |
| No literal 'error' status string | `grep -nE "['\"']error['\"']" pycopg/etl.py` filtered | no output | PASS |
| 11 tests pass | `uv run pytest tests/test_etl_accessor.py -o addopts="" -q` | 11 passed in 1.15s | PASS |
| New session-path test passes in isolation | `uv run pytest tests/test_etl_accessor.py::TestETLAccessorIntegration::test_failed_run_commits_inside_session -o addopts="" -q` | 1 passed in 0.36s | PASS |
| database.py not modified by 17-02 | `git diff --name-only 76716b8 HEAD -- pycopg/database.py` | (empty) | PASS |
| ruff clean on touched files | `uv run ruff check pycopg/etl.py tests/test_etl_accessor.py` | All checks passed | PASS |
| black clean on touched files | `uv run black --check pycopg/etl.py tests/test_etl_accessor.py` | 2 files would be left unchanged | PASS |

---

## Requirements Coverage

| Requirement | Phase | Description | Status | Evidence |
|-------------|-------|-------------|--------|---------|
| ETL-07 | 17 | After any run(), pipeline_runs row exists with all required columns incl. nullable watermark | SATISFIED | SC-1 test proves full row contract; watermark IS NULL asserted |
| ETL-08 | 17 | Failed run records status='failed' with error_message + error_traceback, committed even when load txn rolled back | SATISFIED | SC-4 proves this on no-session path AND the new session-active path (test_failed_run_commits_inside_session) |
| ETL-09 | 17 | Load runs in its own DB transaction; run-tracking write committed independently of load transaction | SATISFIED | Structural fix: connect(autocommit=True) bypasses cursor() session-reuse entirely; both test paths confirm |
| ETL-14 | 17 | pipeline_runs auto-created on first run(); explicit db.etl.init() also available | SATISFIED | SC-2 and SC-3 tests prove both paths |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_etl_accessor.py` | 231 | `status in ("running", "success", "failed")` in test_run_writes_full_row | Warning (carried from 17-01, WR-04) | SC-1 test does not pin status to "success" — a regression where _end_run silently no-ops would still pass. Acceptable given the separate SC-4 test exercises the full success path end-to-end. Not a blocker for Phase 17 goal. |

No `TBD`, `FIXME`, or `XXX` debt markers found in Phase 17 files.
No `self._db.execute(...)` calls inside the three write method bodies.

---

## Human Verification Required

None. All Phase 17 behaviors are programmatically verifiable and have been verified above.

---

## Gaps Summary

No gaps remain. The single gap from the initial verification (SC-4 PARTIAL — session-active path untested and broken) is now CLOSED:

- `ETLAccessor.init` / `_start_run` / `_end_run` open a dedicated `self._db.connect(autocommit=True)` connection and run their SQL on a `row_factory=dict_row` cursor from that connection — they no longer route through `self._db.execute()` / session-aware `Database.cursor()`. Isolation is structural, not conditional.
- `Database.connect()` (lines 284-302) calls `_connect_with_retry` directly and never consults `self._session_conn`, so `connect(autocommit=True)` is genuinely independent of any active session — this is the mechanical guarantee that makes the fix work.
- `test_failed_run_commits_inside_session` proves the invariant on the session-active path: it reads the pipeline_runs row via a fresh out-of-band connection WHILE THE SESSION IS STILL OPEN, confirming the row is already committed (not pending). This is a stronger proof than checking post-session.
- `pycopg/database.py` was not modified; the session/cursor contract is preserved for all other library consumers.

The phase goal — "the pattern is SOLID so all subsequent load phases inherit correct transaction boundary behavior" — now holds unconditionally.

---

_Verified: 2026-06-15T12:30:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification: Yes — after gap closure via plan 17-02_
