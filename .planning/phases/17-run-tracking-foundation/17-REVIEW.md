---
phase: 17-run-tracking-foundation
reviewed: 2026-06-15T10:59:57Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - pycopg/database.py
  - pycopg/etl.py
  - tests/test_etl_accessor.py
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-06-15T10:59:57Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the Phase 17 run-tracking foundation: the new `ETLAccessor` class in `pycopg/etl.py`,
the lazy `db.etl` property and `self._etl` field in `pycopg/database.py`, and the new test module
`tests/test_etl_accessor.py`. Scope was limited to phase-introduced symbols per the scope note.

The code is clean, well-documented (numpydoc), and the SQL builders correctly parameterize all
user values. The status-literal and param-order invariants are well tested. However, the central
design invariant of this phase — "every run-log write commits independently of the load
transaction on a dedicated autocommit connection" (D-04/D-05) — is **not honored when a session
is active**. Because all run-log writes route through `db.execute(..., autocommit=True)`, and
`Database.cursor()` reuses a non-autocommit session connection without committing when
`autocommit=True` is passed, a `status='failed'` row written inside a `db.session()` block is
neither committed independently nor isolated. This is the one BLOCKER. The remaining findings are
robustness and coverage gaps.

## Critical Issues

### CR-01: Run-log writes are NOT independently committed when a `db.session()` is active

**File:** `pycopg/etl.py:330,349-353,396-408` (writes) → `pycopg/database.py:318-336` (routing)
**Issue:**
The entire phase rests on the invariant (D-04/D-05, ETL-08/ETL-09) that run-log writes use a
"fresh short-lived autocommit connection per write ... so a failed run row commits even when the
load transaction rolls back." All three write methods (`init`, `_start_run`, `_end_run`) implement
this by calling `self._db.execute(..., autocommit=True)`.

But `Database.execute(autocommit=True)` does NOT guarantee a fresh autocommit connection. It routes
through `Database.cursor()`:

```python
if self._session_conn is not None:                       # session active
    with self._session_conn.cursor(row_factory=dict_row) as cur:
        yield cur
        if not autocommit:        # autocommit=True -> SKIPPED entirely
            ... commit / rollback ...
else:
    with self.connect(autocommit=autocommit) as conn:    # fresh conn, real autocommit
        ...
```

When a `db.session()` is open with the default `autocommit=False` (the common case), `_session_conn`
is a **transactional** connection. Passing `autocommit=True` does not switch that connection to
autocommit mode — it merely *skips the commit block*. So inside a session:

1. `_start_run` / `_end_run` execute on the session's open transaction (not a dedicated connection).
2. `execute` never commits them (the `if not autocommit:` block is skipped).
3. If the surrounding load logic later raises and the session rolls back, the `status='failed'`
   row is rolled back with it — the exact data-loss scenario D-04/D-05 exist to prevent.

The passing integration test `test_failed_run_commits_despite_load_rollback` does NOT catch this:
it never opens a `db.session()`, so `_session_conn` is `None` and the `else` branch (genuine fresh
autocommit connection) is taken. The bug is latent precisely in the session code path the test omits.

**Fix:** Run-log writes must use a connection that is genuinely independent of `_session_conn`.
Either bypass the session entirely in the accessor (open a dedicated connection), e.g.:

```python
# in ETLAccessor, instead of self._db.execute(..., autocommit=True):
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.ETL_INSERT_RUN, [name, "running", datetime.now(UTC)])
        return cur.fetchone()["run_id"]
```

or make `Database.cursor()`/`execute()` honor `autocommit=True` even mid-session by opening a fresh
connection (not reusing `_session_conn`) when `autocommit=True` is requested. Add a regression test
that wraps `db.etl.run(...)` / `_start_run` + failing load inside `with db.session():` and asserts
the run row survives the rollback.

## Warnings

### WR-01: `_start_run` indexes `rows[0]` with no guard against an empty result

**File:** `pycopg/etl.py:349-354`
**Issue:**
```python
rows = self._db.execute(queries.ETL_INSERT_RUN, [...], autocommit=True)
return rows[0]["run_id"]
```
`execute` returns `[]` when `cur.description` is falsy or no rows are returned. If the
`RETURNING run_id` ever yields nothing (driver edge case, a future change to `execute`, or a
mocked/instrumented `execute` returning `[]`), this raises an opaque `IndexError` rather than a
meaningful error. Given this `run_id` is the handle the entire run lifecycle depends on, the failure
mode should be explicit.

**Fix:**
```python
rows = self._db.execute(queries.ETL_INSERT_RUN, [...], autocommit=True)
if not rows:
    raise RuntimeError("ETL_INSERT_RUN returned no run_id row")
return rows[0]["run_id"]
```

### WR-02: `_end_run` does not validate `status`, allowing CHECK-constraint violations to surface as raw DB errors

**File:** `pycopg/etl.py:356-408`
**Issue:**
The docstring states `status` must be `'success'` or `'failed'`, but the method accepts any string
and passes it straight to the UPDATE. A caller passing `'error'`, `'ok'`, or a typo gets a raw
PostgreSQL `CheckViolation` from deep inside `execute`, far from the call site. The phase deliberately
constrains statuses to `running`/`success`/`failed` (D-07); the public-facing `_end_run` is the right
place to enforce that contract proactively rather than relying on the DB CHECK to reject it after the
fact (and, given CR-01, possibly after a partial transaction).

**Fix:** Validate early, mirroring `_validate_load_mode`:
```python
_VALID_END_STATUSES = ("success", "failed")
if status not in _VALID_END_STATUSES:
    raise ValueError(f"status must be one of {_VALID_END_STATUSES}, got {status!r}")
```

### WR-03: `_FakeDatabase` is not autocommit-aware, so unit tests cannot detect CR-01-class regressions

**File:** `tests/test_etl_accessor.py:39-48`
**Issue:**
The fake records `(sql, params, autocommit)` and always returns `[{"run_id": 42}]`. It models
`execute` as if `autocommit=True` always means "committed independently," which is exactly the
assumption that CR-01 shows to be false in the real `cursor()` routing. The unit suite therefore
asserts the *intent* (`autocommit is True`) but can never observe whether the real connection routing
actually delivers an independent commit. The fake also silently tolerates the `_start_run` empty-result
path (WR-01) because it always returns a non-empty list.

**Fix:** Add a real-DB regression test for the session path (see CR-01 fix), and add a unit test that
points `_FakeDatabase.execute` at a variant returning `[]` to assert `_start_run` raises cleanly once
WR-01 is fixed.

### WR-04: Integration tests assert `status in (...)` instead of the exact terminal status

**File:** `tests/test_etl_accessor.py:192`
**Issue:**
`test_run_writes_full_row` calls `db.etl.run("demo")` (which always ends in `'success'`) but asserts
`row["status"] in ("running", "success", "failed")`. That predicate is satisfied by literally any
valid status, including `'running'` — meaning a regression where `_end_run` silently no-ops (e.g.
CR-01 leaving the UPDATE uncommitted, or an UPDATE that matched zero rows) would still pass. The test
should pin the deterministic outcome.

**Fix:** `assert row["status"] == "success"`. Pinning the exact status also turns this test into a
partial guard for the `_end_run` commit path.

## Info

### IN-01: `_end_run` does not check that the UPDATE affected a row

**File:** `pycopg/etl.py:396-408`
**Issue:** If `run_id` does not exist (stale id, double-finalize after CR-01 rollback removed the
`running` row, manual misuse), the UPDATE matches zero rows and `_end_run` returns silently — the
run is reported "finalized" while no row changed. `execute` discards `rowcount`, so this is invisible.
**Fix:** Surface zero-row updates, e.g. switch to a path that inspects `cur.rowcount` and warns/raises
when it is `0`, or add `RETURNING run_id` and assert a row came back.

### IN-02: `ETLAccessor` and `Pipeline` are not exported from `pycopg/__init__.py`

**File:** `pycopg/__init__.py` (absent), used via `pycopg/etl.py`
**Issue:** Consumers and the test reach in via `from pycopg.etl import ETLAccessor`. The public
surface for this milestone is `db.etl`, so the missing top-level export is acceptable for an internal
accessor, but `Pipeline` is documented as the public descriptor and is also unexported. Confirm this
is intentional for Phase 17 (Phase 18 may wire it) rather than an oversight.
**Fix:** If `Pipeline` is meant to be public, add it to `pycopg/__init__.py` `__all__`; otherwise note
the deferral explicitly.

### IN-03: `datetime.now(UTC)` is passed from Python while the DDL already defaults `started_at` to `now()`

**File:** `pycopg/etl.py:351` vs `pycopg/queries.py:253`
**Issue:** `started_at` has `DEFAULT now()` (DB clock) but `_start_run` overrides it with the client
clock `datetime.now(UTC)`. Mixing client- and server-side timestamps across `started_at` (client) and
`finished_at` (also client, in `_end_run`) is internally consistent here, but diverges from the DDL
default and from server time, which can skew duration math if clients are clock-skewed. Minor;
flagging for consistency. **Fix:** Either drop the explicit `started_at` value and rely on the DB
default, or document that all run timestamps are deliberately client-sourced for monotonicity within a run.

---

_Reviewed: 2026-06-15T10:59:57Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
