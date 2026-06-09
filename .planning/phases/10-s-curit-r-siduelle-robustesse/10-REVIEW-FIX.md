---
phase: 10
fixed_at: 2026-06-09T00:00:00Z
review_path: .planning/phases/10-s-curit-r-siduelle-robustesse/10-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-06-09T00:00:00Z
**Source review:** `.planning/phases/10-s-curit-r-siduelle-robustesse/10-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (WR-01, WR-02 — Info findings IN-01/IN-02 excluded per scope)
- Fixed: 2
- Skipped: 0

---

## Fixed Issues

### WR-01: close() exception masks commit() exception in session() (sync and async)

**Files modified:** `pycopg/database.py`, `pycopg/async_database.py`
**Commit:** `6b507b0`
**Applied fix:** Captured the commit exception in `commit_exc` before re-raising. Wrapped `close()` (and `await close()` in async) in a `try/except`. When a commit exception is already in flight (`commit_exc is not None`), close errors are logged via `logger.warning()` instead of re-raised, so the original commit exception always propagates. When commit succeeded, close errors propagate normally. The `_session_conn = None` outer finally and all other behavior paths (autocommit branch, body exceptions) are unchanged.

**Test results:** 18 tests in `test_session_leak.py` + `test_session_edge_cases.py` — all pass. Ruff: no new errors.

---

### WR-02: PooledDatabase.execute_many — commit outside cursor context (sync and async)

**Files modified:** `pycopg/pool.py`
**Commit:** `ba0f8ba`
**Applied fix:** Moved `conn.commit()` from outside the cursor `with` block to inside it (at the end, after the loop), for both `PooledDatabase.execute_many` (sync) and `AsyncPooledDatabase.execute_many` (async). This is purely a placement change — commit still happens before the pool CM's `__exit__`. Now consistent with the `execute()` method pattern established by the B1 fix in phase 10.

**Test results:** 68 tests in `test_pool_commit.py` + `test_pool.py` + `test_pool_stress.py` + `test_session_leak.py` + `test_session_edge_cases.py` — all pass. Ruff: 23 pre-existing errors (unchanged), no new errors introduced.

---

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-06-09T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
