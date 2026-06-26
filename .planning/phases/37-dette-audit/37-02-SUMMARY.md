---
phase: 37-dette-audit
plan: "02"
subsystem: tests
tags: [lint, ruff, debt, monkeypatch, housekeeping]
dependency_graph:
  requires: [37-01]
  provides: [ruff-clean-tests, debt-04-resolved]
  affects: []
tech_stack:
  added: []
  patterns: [bare-except-to-exception, unused-var-removal, trailing-whitespace-fix]
key_files:
  modified:
    - tests/setup_test_db.py
    - tests/test_async_database.py
    - tests/test_database.py
    - tests/test_pool.py
    - tests/test_pool_stress.py
    - tests/test_session_edge_cases.py
    - tests/test_postgis_errors.py
    - tests/test_sql_injection.py
    - tests/test_database_integration.py
decisions:
  - "D-01b applied: 34 ruff errors fixed mechanically (no suppressions)"
  - "D-04 resolved: two dead flat-method monkeypatches removed from async_db fixture"
metrics:
  duration: "~8 minutes"
  completed: "2026-06-26"
  tasks_completed: 2
  files_modified: 9
---

# Phase 37 Plan 02: Test-Side Lint & Dead Code Cleanup Summary

**One-liner:** Mechanical fix of 34 ruff errors in tests/ (W291/F841/E722) + removal of two dead v0.7.0 monkeypatches from the SQL injection async fixture — `uv run ruff check pycopg tests` now exits 0.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix all ruff errors in tests/ (W291, F841, E722) | 5fea8a4 | 8 test files |
| 2 | Remove dead flat-method monkeypatches (DEBT-04) | 09f6d7d | tests/test_sql_injection.py |

## What Was Built

**Task 1 — 34 ruff errors fixed across 8 files (vs 31 predicted; 3 extra F841 found at runtime):**

- **W291 (5 instances):** Stripped trailing whitespace from SQL string literals in `tests/setup_test_db.py` (lines 103-105, 116-117).
- **F841 (24 instances):** Removed unused variable bindings in mock-based tests where the return value was never inspected:
  - `test_async_database.py`: `db` (line 65), `conn` (line 131), `result` (line 169)
  - `test_database.py`: `db` (line 39), `conn` (line 68), `cur` (line 104), `result` (lines 144, 594), `session` (line 610)
  - `test_pool.py`: `db` (lines 17, 28, 50, 63, 282, 296, 306), `result` (line 129)
  - `test_pool_stress.py`: `conn3` (line 40)
  - `test_session_edge_cases.py`: `inner_session` (line 54), `exc_info` (line 68)
  - `test_database_integration.py`: `pd` (line 291 — `pytest.importorskip` used for skip behavior only)
- **E722 (5 instances):** Replaced bare `except:` with `except Exception:` at cleanup blocks in `test_pool_stress.py` (lines 48, 128) and `test_postgis_errors.py` (lines 50, 146, 182). Pattern preserves `KeyboardInterrupt`/`SystemExit` propagation.

All side-effecting calls preserved: context-manager entries (`with db.connect()`, `with db.cursor()`, `with db.session()`) kept as bare `with` when the bound variable was unused.

**Task 2 — Dead monkeypatches removed (DEBT-04 / WR-02):**

In `tests/test_sql_injection.py`, the `async_db` fixture had two dead patches:
```python
db.role_exists = AsyncMock(return_value=False)   # removed
db.has_extension = AsyncMock(return_value=True)  # removed
```

These have been no-ops since v0.7.0 when the flat `role_exists`/`has_extension` names were removed from `AsyncDatabase`. The live patch `real_schema.has_extension = AsyncMock(return_value=True)` is preserved — `SpatialAccessor._check_postgis()` reads through the accessor object, not the top-level `db` attribute.

## Verification Results

- `uv run ruff check pycopg tests` → `All checks passed!` (0 errors)
- `uv run pytest tests/ --collect-only -q -o addopts=""` → 1346 tests collected, 0 errors
- `PGDATABASE=pycopg_test2 uv run pytest tests/test_sql_injection.py -x -q -o addopts=""` → 92 passed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Live ruff run found 3 additional F841 errors not in RESEARCH.md**

- **Found during:** Task 1
- **Issue:** The research noted "ruff output was truncated at 27 F841 results" — the live run exposed 3 more: `db` in `test_pool.py:17,28` and `pd` in `test_database_integration.py:291`.
- **Fix:** Applied the same F841 pattern (remove unused binding, keep side-effecting call). For `test_database_integration.py:291`, `pytest.importorskip("pandas")` is used for its skip-on-missing-pandas side effect only, so the `pd =` binding was dropped.
- **Files modified:** `tests/test_pool.py`, `tests/test_database_integration.py`
- **Commit:** 5fea8a4

## Known Stubs

None — all changes are mechanical lint fixes and dead code removal with no stub patterns introduced.

## Threat Flags

No new threat surface. All edits are inside the test suite with no runtime impact. The security-relevant `test_sql_injection.py` file retains the live `real_schema.has_extension` patch, preserving full SQL injection test coverage.

## Self-Check: PASSED

- tests/setup_test_db.py: FOUND
- tests/test_async_database.py: FOUND
- tests/test_database.py: FOUND
- tests/test_pool.py: FOUND
- tests/test_pool_stress.py: FOUND
- tests/test_session_edge_cases.py: FOUND
- tests/test_postgis_errors.py: FOUND
- tests/test_sql_injection.py: FOUND
- tests/test_database_integration.py: FOUND
- Commit 5fea8a4: FOUND
- Commit 09f6d7d: FOUND
- `uv run ruff check pycopg tests` exits 0: VERIFIED
