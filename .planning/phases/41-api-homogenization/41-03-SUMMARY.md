---
phase: 41-api-homogenization
plan: "03"
subsystem: spatial
tags: [spatial, where-filter-rename, deprecation-shim, tdd, freeze-01, d-04, d-09, d-10, d-11]
dependency_graph:
  requires:
    - "41-01 (-W error::DeprecationWarning gate + test scaffold)"
    - "41-02 (exception *Error renames — spatial.py already updated)"
  provides:
    - "filter= canonical parameter on all 11 build_*_sql builders (clean, no shim)"
    - "filter=/where= deprecation shim on all 22 accessor methods (11 sync + 11 async)"
    - "DeprecationWarning(stacklevel=2) when where= is used (D-09)"
    - "TypeError when both filter= and where= supplied"
    - "46 new parametrized shim tests covering all 22 accessor methods"
  affects:
    - "pycopg/spatial.py (builders + 22 accessor method signatures + bodies)"
    - "tests/test_spatial.py (builder-level where= kwargs renamed to filter=)"
    - "tests/test_deprecations.py (TestWhereDeprecation xfail removed + 46 new tests)"
tech_stack:
  added: []
  patterns:
    - "Clean rename on builder public surface (D-04: builders are frozen API, no backward compat)"
    - "Shim pattern: filter= canonical, where= emits DeprecationWarning(stacklevel=2) + filter=where reassignment"
    - "TypeError guard: both filter= and where= supplied raises before any warn/forward"
    - "Internal callers use filter= only — -W error gate enforces no internal routing through shim"
    - "TDD RED/GREEN/REFACTOR cycle: xfail removal (RED) → shim implementation (GREEN) → lint fix (REFACTOR)"
key_files:
  created: []
  modified:
    - pycopg/spatial.py
    - tests/test_deprecations.py
decisions:
  - "D-04 enforced: builders get clean rename only, no backward-compat shim — builder is frozen public surface"
  - "Accessor shim placement: shim fires BEFORE _check_postgis() call so TypeError/warn never hits DB"
  - "46 parametrized tests added to cover all 22 accessor method shim paths (warn + TypeError) for both sync and async"
  - "within method handled separately in parametrized tests (distinct two-table signature)"
  - "N806 noqa added to TestExceptionAliases OldName variables (pre-existing, intentional uppercase class alias)"
metrics:
  duration: "~90 minutes (continuation from prior context)"
  completed: "2026-06-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 2
---

# Phase 41 Plan 03: FREEZE-01 Spatial where= → filter= Rename Summary

**One-liner:** Builders get clean `filter=` rename (no shim); all 22 accessor methods get `filter=/where=` deprecation shim with `stacklevel=2` warning + TypeError guard; 46 parametrized tests cover all shim paths.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rename where=→filter= on _append_tail + 11 build_*_sql builders | b010784 | spatial.py, test_spatial.py |
| 2 RED | Remove xfail from TestWhereDeprecation (RED gate) | 26b305c | test_deprecations.py |
| 2 GREEN | Add filter=/where= shim to all 22 accessor methods | 028735e | spatial.py, test_deprecations.py |
| 2 REFACTOR | Fix import sort + noqa for N806 | 8cac5ae | test_deprecations.py |

## What Was Built

### Task 1: Builder Rename (Clean, No Shim)

**`pycopg/spatial.py` — builder surface:**
- `_append_tail(sql, where, ...)` → `_append_tail(sql, filter, ...)` (param rename, body updated)
- 11 `build_*_sql` functions: `where: str | None = None` → `filter: str | None = None` in all signatures
- Docstrings updated from `where :` to `filter :` in all 11 builders
- `build_nearest_sql`: inline `if where:` → `if filter:` (this builder uses direct `if` not `_append_tail`)
- All `_append_tail(sql, where, ...)` calls in builder bodies updated to pass the `filter` variable
- Module docstring (line 21): `"The ``where=`` parameter..."` → `"The ``filter=`` parameter..."`
- Accessor forwarding calls (22 methods): `filter=where` (passing old `where` param into new `filter=`) to ensure builders still get the value while accessor signatures remain unchanged for Task 2

**`tests/test_spatial.py`:**
- All builder-level `where=` kwargs in test calls renamed to `filter=`
- Docstrings updated from "where=" to "filter="

**Verification:**
- `python -c "from pycopg.spatial import build_contains_sql; build_contains_sql('t', point=(0,0), where='x')"` → `TypeError: got an unexpected keyword argument 'where'` (D-04 confirmed)
- `grep -c 'validate_identifiers' pycopg/spatial.py` → 27 (T-41-06 unchanged)
- 112 spatial tests passed

### Task 2 TDD: Accessor Shim

**RED gate (commit 26b305c):**
- Removed 2 `@pytest.mark.xfail` markers from `TestWhereDeprecation.test_where_deprecation_points_to_caller` and `test_filter_and_where_both_supplied_raises`
- Tests failed with `TypeError: SpatialAccessor.contains() got an unexpected keyword argument 'filter'` confirming RED state

**GREEN gate (commit 028735e):**

Added `filter: str | None = None` before `where: str | None = None` in all 22 accessor method signatures (11 `SpatialAccessor` + 11 `AsyncSpatialAccessor`).

Shim block added at the top of each method body (before `_check_postgis()`):
```python
if where is not None:
    if filter is not None:
        raise TypeError(
            "Cannot specify both 'filter' and 'where'; use 'filter=' only."
        )
    warnings.warn(
        "The 'where' keyword argument is deprecated and will be removed in "
        "pycopg 2.0. Use 'filter=' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    filter = where
```

All forwarding calls changed from `filter=where` to `filter=filter` after shim is in place.

Docstrings updated in all 22 methods: `where : str, optional` → `filter : str, optional` (canonical) + `where : str, optional — Deprecated. Use filter= instead.`

**46 new tests in `tests/test_deprecations.py`:**
- `test_sync_where_warns_for_all_methods` — parametrized over 10 methods (all except `within`)
- `test_sync_filter_and_where_both_raises_for_all_methods` — parametrized over 10 methods
- `test_sync_within_where_warns` — `within` separate (two-table signature)
- `test_sync_within_filter_and_where_raises` — `within` separate
- `test_async_where_warns_for_all_methods` — parametrized over 10 async methods
- `test_async_filter_and_where_both_raises_for_all_methods` — parametrized over 10 async methods
- `test_async_within_where_warns` — async `within` separate
- `test_async_within_filter_and_where_raises` — async `within` separate

**REFACTOR gate (commit 8cac5ae):**
- Fixed `unittest.mock` import into stdlib block (ruff I001)
- Added `# noqa: N806` to `OldName` assignments in `TestExceptionAliases` (pre-existing intentional class alias)

## Verification Results

- `uv run ruff check pycopg/spatial.py tests/test_deprecations.py` → All checks passed
- `PGDATABASE=pycopg_test2 uv run pytest tests/test_deprecations.py::TestWhereDeprecation tests/test_parity.py -o "addopts=" -x -q` → 28 passed
- Sync/async parity check — all 11 method signatures match between SpatialAccessor and AsyncSpatialAccessor
- `grep -n 'filter=where\|where=where' pycopg/spatial.py` → 0 lines (all forwarding updated)
- `grep -c 'validate_identifiers' pycopg/spatial.py` → 27 (T-41-06 unchanged)
- `-W error::DeprecationWarning` gate: `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py tests/test_parity.py -q -o "addopts=" -W error::DeprecationWarning` → 146 passed (no internal callers trigger shim)
- `PGDATABASE=pycopg_test2 uv run pytest -q` → **1477 passed, 2 skipped, 1 xfailed; 96.34% coverage (gate ≥95%)**

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (`test(41-03)`) | 26b305c | PASSED — tests failed before implementation |
| GREEN (`feat(41-03)`) | 028735e | PASSED — all tests pass after shim |
| REFACTOR (`refactor(41-03)`) | 8cac5ae | PASSED — lint clean, tests still pass |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Coverage gate failure from uncovered shim branches**
- **Found during:** Task 2 GREEN — full suite showed 94% coverage (below 95% gate)
- **Issue:** 22 shim blocks (11 sync + 11 async) added new branches; existing tests only exercised `filter=` path, leaving the `if where is not None:` branches uncovered for 21 of 22 methods
- **Fix:** Added 46 parametrized tests in `TestWhereDeprecation` covering `where=` warn path and `filter= + where=` TypeError path for all 22 accessor methods; coverage rose from 94% to 96.34%
- **Files modified:** `tests/test_deprecations.py`
- **Commit:** 028735e (included with GREEN gate commit)

**2. [Rule 1 - Bug] Pre-existing N806 ruff violations in test_deprecations.py**
- **Found during:** REFACTOR lint check
- **Issue:** Two `OldName = exceptions.InvalidIdentifier` assignments violated N806 (variable in function should be lowercase); these were introduced in Plan 02 but the lint was not run on the test file then
- **Fix:** Added `# noqa: N806 — intentional class alias` to both lines
- **Files modified:** `tests/test_deprecations.py`
- **Commit:** 8cac5ae

**3. [Rule 1 - Bug] Ruff I001 on new import in test_deprecations.py**
- **Found during:** REFACTOR lint check
- **Issue:** `from unittest.mock import AsyncMock, MagicMock` was placed after `import pytest` instead of in the stdlib block
- **Fix:** Moved `from unittest.mock import ...` into stdlib import block before `import pytest`
- **Files modified:** `tests/test_deprecations.py`
- **Commit:** 8cac5ae

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The changes are pure Python parameter renames and deprecation shim additions.

**T-41-06 (validate_identifiers count):** CONFIRMED SAFE — `validate_identifiers` count in `pycopg/spatial.py` is 27 both before and after this plan.

**T-41-07 (no internal callers route through deprecated where= path):** CONFIRMED — `-W error::DeprecationWarning` gate GREEN with 146 spatial+parity tests passing.

**T-41-08 (stacklevel=2 points to caller):** CONFIRMED — `test_where_deprecation_points_to_caller` verifies `w.filename.endswith("test_deprecations.py")`.

## Known Stubs

None — all shim implementations are complete and wired throughout both accessor classes.

## Self-Check: PASSED
