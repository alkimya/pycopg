---
phase: 45-api-completeness-gaps-structured-logging
reviewed: 2026-06-30T19:04:43Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - pycopg/logging.py
  - pycopg/base.py
  - pycopg/__init__.py
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/pool.py
  - pycopg/etl.py
  - pycopg/backup.py
  - pycopg/migrations.py
  - tests/test_logging_module.py
  - tests/test_transaction_isolation.py
  - tests/test_savepoints.py
  - tests/test_named_params.py
  - tests/test_health.py
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 45: Code Review Report

**Reviewed:** 2026-06-30T19:04:43Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Reviewed the Phase 45 changes (API completeness gaps + structured logging) across
both sync and async database surfaces, the pool, ETL, backup, migrations, and the
new `pycopg.logging` module, plus the five new test files.

The phase-specific concerns were verified directly:

- **`_num_transactions` private-attribute guard (45-02):** confirmed that
  `_num_transactions` is a real psycopg instance attribute (set in
  `psycopg/_connection_base.py:110`, incremented/decremented in
  `psycopg/transaction.py`) and that `MagicMock()._num_transactions > 0` raises
  `TypeError` exactly as the fallback assumes. The guard logic is *behaviourally*
  correct today. However the `except TypeError`-only catch is narrower than the
  documented intent ("mock / unexpected type") and is brittle against a future
  psycopg rename/removal — see WR-01.
- **`health()` never-raises (HEALTH-01):** the broad `except Exception` covers all
  four implementations and only `str(exc)` (the raw psycopg message) is surfaced —
  no DSN/credential leak (T-45-07 holds). One robustness gap remains: the sync
  `Database.health()` path is subject to the `@retry` decorator and can block for
  seconds before returning `connected=False` — see WR-02.
- **PARAM-01 (`Params` widening):** confirmed annotation-only; no new
  interpolation. All `execute`/`fetch_*` paths pass `params` straight to
  `cur.execute(sql, params)`, so `%(name)s` binding goes through psycopg
  parameterization. The `to_dataframe` `:name`-vs-`%(name)s` divergence is
  documented in the docstring and pinned by a test. No injection surface added.
- **`log_operation` (LOG-01):** the context manager emits in a `finally` and never
  swallows or rethrows, never touches the yielded value, and is applied only to
  coarse operations (`from_dataframe`, `from_geodataframe`, `etl.run`,
  `backup.*`, `migrations.migrate`, `health`) — never on `execute`/`fetch_*`. Hot
  path is clean.
- **Sync/async parity:** the changed methods mirror each other faithfully. One
  pre-existing parity asymmetry in the session-cursor rollback path is noted in
  WR-03 (it is symmetric between sync and async, so it is not a regression of this
  phase, but it is now exercised by the new savepoint/session code).

No critical issues found. Five warnings and four info items follow.

## Warnings

### WR-01: `_num_transactions` guard catches only `TypeError`, not attribute absence

**File:** `pycopg/database.py:500-505`, `pycopg/async_database.py:509-514`
**Issue:** The session-cursor commit guard reads a **private** psycopg attribute:

```python
try:
    in_txn_block = self._session_conn._num_transactions > 0
except TypeError:
    in_txn_block = False  # mock / unexpected type — behave as before
```

The comment claims the fallback handles "mock / unexpected type", but only
`TypeError` is caught. `_num_transactions` is an undocumented private attribute of
`psycopg._connection_base`. If a future psycopg release renames or removes it (a
real risk for a 1.0 library that must survive driver upgrades), the access raises
`AttributeError`, which is **not** caught — it would propagate out of the cursor
context-manager exit and break every `db.session()` commit path. Relying on a
private attribute at all is fragile; the narrow catch makes it worse.

**Fix:** Use `getattr` with a safe default so both the mock case and any future
attribute removal degrade to the documented "behave as before" path, and widen the
guarded scope:

```python
in_txn_block = bool(getattr(self._session_conn, "_num_transactions", 0))
```

`getattr` returns the `MagicMock` child for a mock (truthy) — so to preserve the
mock-as-`False` behaviour, coerce explicitly:

```python
ntx = getattr(self._session_conn, "_num_transactions", 0)
try:
    in_txn_block = ntx > 0
except TypeError:
    in_txn_block = False
```

This keeps the mock fallback *and* makes a missing attribute resolve to `0`
(no open transaction block) instead of crashing. Apply identically to both
sync and async to preserve parity.

### WR-02: `Database.health()` can block for seconds via the `@retry` decorator

**File:** `pycopg/database.py:745-764` (via `_connect_with_retry`, lines 445-454);
async mirror `pycopg/async_database.py:685-704`
**Issue:** `health()` calls `self.connect()`, which calls `_connect_with_retry`,
which is decorated with `@retry(stop=stop_after_attempt(3),
wait=wait_exponential(multiplier=1, min=1, max=10), ...)`. On a down database the
probe will retry 3 times with exponential backoff before the final
`OperationalError` is caught and converted to `connected=False`. The docstring
sells `health()` as a probe that "monitoring loops can call it unconditionally" and
reports `latency_ms`, but a single failing call can stall the caller for several
seconds. The `PooledDatabase.health()` path is *not* affected (it goes through the
pool's own `timeout`), creating an inconsistency between the two surfaces.

**Fix:** Bypass the retry wrapper for the health probe so a down DB fails fast,
e.g. open the connection directly without the `@retry`-decorated helper:

```python
conn = psycopg.connect(**self.config.connect_params())
try:
    ...
finally:
    conn.close()
```

or document explicitly that `health()` inherits the connection-retry budget and
may block up to ~`max` seconds. At minimum, align sync `Database.health()` with the
pooled behaviour.

### WR-03: Non-session cursor branch unconditionally commits even after an in-error transaction

**File:** `pycopg/database.py:514-519`, `pycopg/async_database.py:523-528`
**Issue:** The session branch was carefully taught (this phase) to inspect
`transaction_status` and choose commit vs. rollback vs. skip. The non-session
`else` branch was not:

```python
else:
    with self.connect(autocommit=autocommit) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur
            if not autocommit:
                conn.commit()   # <-- unconditional
```

If the yielded cursor leaves the connection in `INERROR` (a statement raised but
the caller swallowed it), `conn.commit()` itself raises rather than rolling back —
masking the original error with a confusing commit-time failure. This is
pre-existing, but Phase 45 deliberately hardened the parallel session branch for
exactly this case, leaving the two branches asymmetric. For a 1.0 freeze the two
commit paths should behave consistently.

**Fix:** Mirror the status check (or at least guard the commit) in the
non-session branch:

```python
if not autocommit:
    if conn.info.transaction_status == TransactionStatus.INERROR:
        conn.rollback()
    else:
        conn.commit()
```

Apply identically sync + async.

### WR-04: `_decode_server_version` truncates PG ≥ 10 patch numbers with `% 100`

**File:** `pycopg/base.py:47-51`
**Issue:** For PostgreSQL ≥ 10 the version integer is `major * 10000 + patch`
(minor is always 0), so the patch component is `v % 10000`, not `v % 100`:

```python
if major >= 10:
    return f"{major}.{v % 100}"   # truncates patch >= 100
```

`_decode_server_version(140999)` returns `"14.99"` instead of `"14.999"`. Today's
real PG minor numbers stay under 100 so this is latent rather than active, but it
is a correctness defect baked into a method that exists specifically to format the
server version for `health()` output and is unit-tested with hard-coded values.

**Fix:**

```python
if major >= 10:
    return f"{major}.{v % 10000}"
```

(`160001 % 10000 == 1`, `100023 % 10000 == 23` — both still correct; the change
only fixes the >99 case.) Add a regression test for a 3-digit patch.

### WR-05: `pg_dump`/`pg_restore` failure messages echo raw `stderr` into the exception

**File:** `pycopg/backup.py:114-115, 201-204, 465-466, 554-555` (and `_psql_restore`
234, 588)
**Issue:** On non-zero exit the accessors raise
`RuntimeError(f"pg_dump failed: {result.stderr}")`. `PGPASSWORD` is passed via the
environment (good — not on the argv), but `pg_dump`/`psql` can echo the connection
string (host, port, user, dbname) and server-side error detail into stderr, which
is then surfaced verbatim in an exception that may be logged or returned to a user.
This is a milder cousin of the T-45-07 concern that `health()` was explicitly
hardened against; the backup path got no equivalent treatment. Not a credential
leak (the password is never in stderr), but it can disclose connection metadata.

**Fix:** Either trim/normalize the stderr surfaced in the exception, or document
that backup exceptions may include subprocess stderr so callers handle them as
sensitive. Lowest-effort option: keep the full stderr in a DEBUG log via
`log_operation`/logger and raise a generic `RuntimeError("pg_dump failed (exit
{code}); see logs")`.

## Info

### IN-01: `_num_transactions` reliance should be replaced by a public API or guarded helper

**File:** `pycopg/database.py:501`, `pycopg/async_database.py:510`
**Issue:** Beyond WR-01's narrow-catch problem, depending on a private driver
attribute at a 1.0 freeze is an architectural smell. psycopg exposes
`Transaction` objects but no public "am I inside a transaction block?" predicate;
if one is added in a later psycopg, this code should migrate to it. Centralize the
access behind a single private helper (e.g. `_in_txn_block(conn)`) shared by both
classes so the eventual fix is one-line and parity is structural rather than
copy-pasted.
**Fix:** Extract a shared helper in `base.py` and call it from both `cursor()`
implementations.

### IN-02: `log_operation` for DataFrame loads reports input row count, not rows loaded

**File:** `pycopg/database.py:1521`, `pycopg/async_database.py:1280`,
`pycopg/database.py:1643`, `pycopg/async_database.py:1408`
**Issue:** `with log_operation("database.from_dataframe", rows=len(df)):` records
the *input* frame length. For `if_exists="append"` with a partial COPY failure, or
when `index=True` changes the shape, the logged `rows` can diverge from what was
actually written. The field name `rows` reads as "rows affected" (matching
`etl.run` semantics elsewhere). Minor observability inaccuracy, not a correctness
bug.
**Fix:** Either rename the intent in the docstring to "input rows" or move the
`rows=` to reflect the COPY return value where available.

### IN-03: `health()` returns dict without an `error` key on success, with it on failure — asymmetric shape

**File:** `pycopg/database.py:753-764`, `pycopg/async_database.py:693-704`,
`pycopg/pool.py:273-286, 557-570`
**Issue:** The success dict omits `error`; the failure dict omits nothing relative
to success but the success dict lacks the key entirely. Consumers must use
`"error" in result` rather than `result["error"] is None`. The tests assert
`"error" not in result`, locking in the asymmetry. Harmless but slightly awkward
for typed consumers / dashboards.
**Fix:** Optionally include `"error": None` on success for a uniform schema (this
would require updating the `"error" not in result` assertions in `test_health.py`).

### IN-04: `_decode_server_version` lacks a guard for malformed/zero input

**File:** `pycopg/base.py:47-51`
**Issue:** A `0` or negative `server_version` (seen with some pre-handshake or
proxy connections) yields nonsensical strings like `"0.0.0"` without signalling the
anomaly. Since this only feeds `health()` display output it is low-impact, but a
1.0 surface could note the contract (input is assumed valid libpq encoding).
**Fix:** Document the precondition, or return `"unknown"` for `v <= 0`.

---

_Reviewed: 2026-06-30T19:04:43Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
