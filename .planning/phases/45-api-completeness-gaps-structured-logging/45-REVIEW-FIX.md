---
phase: 45-api-completeness-gaps-structured-logging
fixed_at: 2026-06-30T20:15:00Z
review_path: .planning/phases/45-api-completeness-gaps-structured-logging/45-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 45: Code Review Fix Report

**Fixed at:** 2026-06-30T20:15:00Z
**Source review:** `.planning/phases/45-api-completeness-gaps-structured-logging/45-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (WR-01, WR-02, WR-03, WR-04)
- Fixed: 4
- Skipped: 0

Out-of-scope per orchestrator decision: WR-05, IN-01, IN-02, IN-03, IN-04.

## Fixed Issues

### WR-04: `_decode_server_version` patch `%10000` + regression test

**Files modified:** `pycopg/base.py`, `tests/test_health.py`
**Commit:** 8d24a03
**Applied fix:** Changed `v % 100` to `v % 10000` in the PG >= 10 branch of
`_decode_server_version`. Added `test_server_version_decode_three_digit_patch`
to `tests/test_health.py` that asserts `_decode_server_version(140999) == "14.999"`
(was incorrectly `"14.99"` before the fix). Pre-10 three-part path (`% 100` for
the patch within the minor bucket) is unchanged.

### WR-01: `_num_transactions` guard catches only `TypeError`, not attribute absence

**Files modified:** `pycopg/database.py`, `pycopg/async_database.py`
**Commit:** 33bc2b8
**Applied fix:** Replaced the direct `self._session_conn._num_transactions > 0`
access with `ntx = getattr(self._session_conn, "_num_transactions", 0)` followed
by the existing `try: in_txn_block = ntx > 0 / except TypeError: in_txn_block = False`
guard. This means a future psycopg rename or removal of the private attribute
safely resolves to `0` (no open transaction) instead of raising `AttributeError`.
The `TypeError` fallback for mock objects is preserved unchanged. Applied
identically to `Database.cursor()` and `AsyncDatabase.cursor()`.

### WR-03: Non-session cursor branch unconditionally commits even after INERROR

**Files modified:** `pycopg/database.py`, `pycopg/async_database.py`
**Commit:** f4254e3
**Applied fix:** Replaced the unconditional `conn.commit()` / `await conn.commit()`
in the non-session `else` branch of `cursor()` with an INERROR status check
mirroring the session branch: if `conn.info.transaction_status == TransactionStatus.INERROR`
then rollback, else commit. Applied identically to `Database.cursor()` and
`AsyncDatabase.cursor()`. Uses the same `TransactionStatus` import already present
in both files.

### WR-02: `Database.health()` can block for seconds via `@retry` decorator

**Files modified:** `pycopg/database.py`, `pycopg/async_database.py`, `tests/test_health.py`
**Commit:** 49dc46f
**Applied fix:** Replaced `with self.connect() as conn:` / `async with self.connect() as conn:`
in both `health()` implementations with a direct `psycopg.connect(**self.config.connect_params())`
/ `await psycopg.AsyncConnection.connect(**self.config.connect_params())` call wrapped
in a `try/finally conn.close()` block. This bypasses `_connect_with_retry` so a down
database returns `connected=False` immediately without burning the 3-attempt exponential
retry budget. The never-raises contract (`except Exception`) and latency measurement
are preserved unchanged.

Updated `tests/test_health.py` to mock `pycopg.database.psycopg.connect` and
`pycopg.async_database.psycopg.AsyncConnection.connect` instead of `db.connect`
(which is no longer called by `health()`). All 11 unit/mocked health tests pass;
2 live-smoke integration tests that fail against the broken `pycopg_test` DB are
pre-existing infrastructure failures unrelated to these changes.

## Skipped Issues

None — all four in-scope findings were successfully fixed.

---

**Full test suite result (PGDATABASE=pycopg_test2):**
- 1718 passed, 17 failed, 3 skipped
- All 17 failures are pre-existing (10 GeoDataFrame tests require geopandas not
  installed in CI env; 6 spatial integration tests hit the same missing module;
  1 dotenv config test has an env var isolation issue)
- None of the failures are related to WR-01..WR-04 changes
- Coverage: 95.29% (gate: >= 95%) — PASSED
- `ruff check pycopg tests` — clean
- `black pycopg tests --check` — clean (all 54 files unchanged)

---

_Fixed: 2026-06-30T20:15:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
