---
status: issues_found
phase: 10
depth: standard
files_reviewed: 4
findings: 4
critical: 0
warning: 2
info: 2
reviewed: 2026-06-08T22:00:00Z
files_reviewed_list:
  - pycopg/pool.py
  - pycopg/migrations.py
  - pycopg/database.py
  - pycopg/async_database.py
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-08T22:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found (2 warnings, 2 info — no blockers)

---

## Summary

Phase 10 delivered four security fixes: B1 (pool commit-before-return), B2 (session close-on-commit-failure), B3 (migration atomicity), and B5 (subprocess env). All four core fixes are **logically correct** — the intended defects are closed. No regressions were introduced by the restructures.

Two warnings were found: one pre-existing design weakness that the B2 fix did not fully eliminate (exception masking in the close path), and one correctness gap in `PooledDatabase.execute_many` that was not touched by this phase. Two info-level items cover minor code quality observations.

---

## Warnings

### WR-01: close() exception masks commit() exception in session() (sync and async)

**File:** `pycopg/database.py:390-401`, `pycopg/async_database.py:224-235`

**Issue:** The B2 fix guarantees `close()` always runs when `commit()` raises, which is correct. However, the chosen `try/finally` structure means that if `close()` itself raises after a `commit()` failure, the close exception replaces the commit exception as the one seen by the caller:

```python
try:
    self._session_conn.commit()   # raises CommitError
finally:
    self._session_conn.close()    # if this also raises, CommitError is silently discarded
```

In the failing-commit scenario (e.g. network drop), `close()` on the same dead connection is very likely to also raise. The caller then catches `CloseError` instead of `CommitError`, making it hard to diagnose whether data was lost or the session was simply torn down uncleanly.

**Fix:** Use exception chaining to attach the close error as a context, preserving the original commit error:

```python
# In the finally block, instead of a bare finally:
commit_exc = None
try:
    self._session_conn.commit()
except Exception as e:
    commit_exc = e
    raise
finally:
    try:
        self._session_conn.close()
    except Exception as close_exc:
        if commit_exc is not None:
            # close failure is secondary; don't mask commit failure
            logger.warning("close() failed after commit() failure: %s", close_exc)
        else:
            raise
```

Or more simply: wrap the `close()` call in a bare `try/except` that only logs when a commit exception is already in flight, to avoid masking.

---

### WR-02: PooledDatabase.execute_many — commit outside cursor context but inside connection context (pre-existing, not addressed by phase)

**File:** `pycopg/pool.py:170-176`

**Issue:** In the sync `PooledDatabase.execute_many`, `conn.commit()` is called at line 175 — inside `with self.connection() as conn:` but **outside** the cursor `with` block. This is functionally correct today. However, the psycopg_pool `connection()` CM calls `with conn:` on the psycopg connection, which means psycopg's `conn.__exit__` will commit on clean exit. For the non-autocommit case this produces a harmless double-commit (commit on IDLE is a no-op per `_commit_gen`). But it creates an inconsistency: `execute()` now explicitly commits before the pool CM can, while `execute_many()` relies on the pool CM's implicit commit as a fallback if the explicit one is somehow skipped.

The phase 10 B1 fix touched `execute()` but not `execute_many()`. The `execute_many` pattern was pre-existing and is functionally safe, but the explicit `conn.commit()` at line 175 is placed inside the connection CM rather than inside the cursor CM (as done in the fixed `execute()`). If the cursor context manager ever raised during `__exit__`, the commit at line 175 would be skipped and the pool CM would roll back. This is consistent with correct error handling, but the inconsistent placement between `execute` and `execute_many` could confuse future maintainers about which commit "counts."

**Fix:** No immediate behavioral fix required, but note for consistency: either document that `execute_many` relies on the pool CM's implicit commit as a fallback (and the explicit `conn.commit()` is belt-and-suspenders), or move the commit inside the cursor block as done in `execute()`:

```python
with self.connection() as conn:
    with conn.cursor() as cur:
        for params in params_seq:
            cur.execute(sql, params)
            total += cur.rowcount
        conn.commit()   # explicit commit before pool CM runs
return total
```

---

## Info

### IN-01: B1 fix produces double-commit on every execution path (benign but surprising)

**File:** `pycopg/pool.py:152-157`, `pycopg/pool.py:350-355`

**Issue:** After the B1 fix, `PooledDatabase.execute` calls `conn.commit()` explicitly, then the pool's `connection()` CM exits via `with conn:`, and psycopg's `conn.__exit__` calls `conn.commit()` again. The second commit is a no-op when `transaction_status == IDLE` (confirmed in psycopg's `_commit_gen`: `if self.pgconn.transaction_status == IDLE: return`). This is safe, but every successful `execute()` call sends two commit attempts to the library machinery. The same applies to `AsyncPooledDatabase.execute`.

This is not a bug — it is a natural consequence of using the pool's high-level `connection()` CM (which handles commit/rollback) while also explicitly committing inside it. Future readers may be confused by what appears to be redundant state.

**Fix:** Consider switching `execute()` to use `autocommit=True` at the pool level to eliminate the double-commit, or add a comment explaining why the explicit commit is necessary (for RETURNING rows) even though the pool CM also commits.

---

### IN-02: _ensure_table() called twice by migrate() (pre-existing, not introduced by phase)

**File:** `pycopg/migrations.py:202-203`

**Issue:** `migrate()` calls `self._ensure_table()` at line 202, then calls `self.pending()` at line 203, and `pending()` calls `self._get_applied()` which calls `self._ensure_table()` again at line 144. This results in two `CREATE TABLE IF NOT EXISTS` DDL executions per `migrate()` invocation. This is idempotent and harmless, but it adds a redundant round-trip to the database.

This was not introduced by phase 10; the B3 fix correctly wraps the `_apply` transaction and does not affect the `_ensure_table` call pattern.

**Fix:** Remove the direct `self._ensure_table()` call from `migrate()` at line 202 (it is redundant with the one inside `pending()`) or add a comment explaining why both calls are intentional.

---

## Verification of Phase 10 Security Fixes

### B1 (SEC-01): Pool commit-before-return — CORRECT

Both sync (`pool.py:152-157`) and async (`pool.py:350-355`) paths now capture rows, commit, then return. The pool CM's second commit is a no-op on IDLE. RETURNING rows are committed before the connection returns to the pool and its `_reset_connection()` can roll back any open transaction. Fix is logically correct.

### B2 (SEC-02): Session close-on-commit-failure — CORRECT (with caveat noted in WR-01)

`close()` now runs unconditionally when `commit()` raises via a nested `try/finally`. `_session_conn` is reset to `None` in the outer `finally` regardless of what commit or close do. The commit exception propagates. The autocommit branch also closes unconditionally. Fix is logically correct; WR-01 notes the secondary exception masking risk.

### B3 (SEC-03): Migration atomicity — CORRECT

`_apply` wraps `(UP SQL + INSERT version)` in `self.db.transaction()`. `rollback` wraps `(DOWN SQL + DELETE version)` in `self.db.transaction()`. The `database.py:transaction()` CM uses `conn.transaction()` which commits on clean exit and rolls back on exception. A mid-pair failure leaves no partial trace. Fix is logically correct.

The `_ensure_table()` calls before `_apply` use `self.db.execute()` (not inside the atomic transaction), which is correct — the version table must exist before the transaction that inserts into it begins.

### B5 (SEC-04): subprocess.os.environ — CORRECT

All three sites in `database.py` (`pg_dump:2178`, `pg_restore:2273`, `_psql_restore:2292`) now use `os.environ` from the top-level `import os` at line 10. `subprocess.os` is no longer referenced anywhere in the package. The async equivalents in `async_database.py` use `asyncio.create_subprocess_exec` with `{**os.environ}`, which was already correct before this phase.

---

## Files Reviewed

- `pycopg/pool.py`
- `pycopg/migrations.py`
- `pycopg/database.py`
- `pycopg/async_database.py`

---

_Reviewed: 2026-06-08T22:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
