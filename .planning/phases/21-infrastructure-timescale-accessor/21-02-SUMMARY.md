---
phase: 21-infrastructure-timescale-accessor
plan: "02"
subsystem: timescale-accessor
tags: [accessor, deprecated-alias, timescale, database, wiring, refactor]
dependency_graph:
  requires:
    - plan-01 (pycopg.aliases.deprecated_alias + pycopg.timescale.TimescaleAccessor + AsyncTimescaleAccessor)
  provides:
    - Database.timescale lazy property
    - AsyncDatabase.timescale lazy property
    - Database._timescale cache field
    - AsyncDatabase._timescale cache field
    - 6 sync @deprecated_alias stubs on Database
    - 6 async @deprecated_alias stubs on AsyncDatabase (iscoroutinefunction=True)
    - TimescaleAccessor + AsyncTimescaleAccessor in pycopg.__all__
  affects:
    - plan-03 (alias tests + call-site migration)
tech_stack:
  added: []
  patterns:
    - Lazy accessor property pattern (mirrors _spatial/_etl; lazy import + cache)
    - @deprecated_alias stub replacing full method body
    - TYPE_CHECKING guard for forward-reference type hints
key_files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/__init__.py
decisions:
  - "Removed validate_interval from database.py and async_database.py imports — the only callers were the 6 timescale methods now replaced by stubs; ruff F401 auto-fix (Rule 1)"
  - "Stubs use *args/**kwargs with one-line docstring to satisfy interrogate 100% — same approach as plan-01 inner functions"
metrics:
  duration: "8 minutes"
  completed: "2026-06-17T12:30:00Z"
  tasks_completed: 3
  files_created: 0
  files_modified: 3
---

# Phase 21 Plan 02: Infrastructure & Timescale Accessor — Wiring & Export Summary

Lazy `timescale` accessor property wired into `Database` and `AsyncDatabase` (mirroring `_spatial`/`_etl` pattern), 6 sync + 6 async flat method bodies replaced with thin `@deprecated_alias` stubs, and `TimescaleAccessor`/`AsyncTimescaleAccessor` exported from `pycopg.__all__`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wire timescale into Database (sync) | fad0cd7 | pycopg/database.py |
| 2 | Wire timescale into AsyncDatabase (async) | 426d628 | pycopg/async_database.py |
| 3 | Export TimescaleAccessor + AsyncTimescaleAccessor from pycopg | 82006f3 | pycopg/__init__.py |

## What Was Built

### Task 1: `pycopg/database.py`

- Added `from pycopg.aliases import deprecated_alias` to module-top imports
- Added `from pycopg.timescale import TimescaleAccessor` under `TYPE_CHECKING`
- Added `self._timescale: TimescaleAccessor | None = None` cache field in `__init__`
- Added lazy `timescale` property after `etl` property — copies the exact `_spatial`/`_etl` shape with numpydoc docstring + lazy import + cache assignment
- Replaced 6 full TIMESCALEDB method bodies with thin stubs:
  - `create_hypertable`, `enable_compression`, `add_compression_policy`
  - `add_retention_policy`, `list_hypertables`, `hypertable_info`
  - Each: `@deprecated_alias("timescale.<method>")` + `def <method>(self, *args, **kwargs):` + one-line docstring
- Removed now-unused `validate_interval` import (auto-fix: Rule 1 — ruff F401)

### Task 2: `pycopg/async_database.py`

Mirrors Task 1 exactly with async differences:
- `AsyncTimescaleAccessor` in TYPE_CHECKING block
- `self._timescale: AsyncTimescaleAccessor | None = None` cache field
- Lazy `timescale` property (plain `def`, not `async def` — same as `etl`)
- 6 stubs use `async def` — this is CRITICAL: `inspect.iscoroutinefunction(fn)` is True when the decorator processes them, selecting the `async_wrapper` branch in `deprecated_alias`, so the wrapped methods remain coroutine functions (Pitfall 1 / Footgun 3 from PATTERNS.md)
- Removed now-unused `validate_interval` import (auto-fix: Rule 1)

### Task 3: `pycopg/__init__.py`

- Added `from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor` after the spatial import line
- Added `"TimescaleAccessor"` and `"AsyncTimescaleAccessor"` to `__all__` under a `# TimescaleDB` comment block after the ETL block
- Export-precedent only — README/Sphinx/CHANGELOG hardening deferred to Phase 24

## Verification Results

```
from pycopg import Database, AsyncDatabase, TimescaleAccessor, AsyncTimescaleAccessor
→ exits 0 (no circular import)

inspect.iscoroutinefunction(AsyncDatabase.create_hypertable)
→ True (async stubs stay coroutine functions via async_wrapper branch)

inspect.iscoroutinefunction(Database.create_hypertable)
→ False (sync stubs use sync_wrapper)

isinstance(inspect.getattr_static(Database, 'timescale'), property)
→ True

isinstance(inspect.getattr_static(AsyncDatabase, 'timescale'), property)
→ True

'TimescaleAccessor' in pycopg.__all__ and 'AsyncTimescaleAccessor' in pycopg.__all__
→ True

uv run ruff check pycopg/database.py pycopg/async_database.py pycopg/__init__.py
→ All checks passed

uv run interrogate pycopg --fail-under 95
→ PASSED (100.0%)

pytest tests/ -x -q -o addopts="" (excl. test_integration.py + test_parity.py)
→ 673 passed, 1 pre-existing failure (test_create_spatial_index_name_parameter)
```

## Acceptance Criteria Check

| Criterion | Result |
|-----------|--------|
| `grep -c 'deprecated_alias' pycopg/database.py` == 7 (1 import + 6 decorators) | PASS |
| `grep -c 'def timescale(' pycopg/database.py` == 1 | PASS |
| `grep -c '_timescale = TimescaleAccessor' pycopg/database.py` == 1 | PASS |
| `grep -c 'SELECT create_hypertable(' pycopg/database.py` == 0 | PASS |
| `grep -c 'deprecated_alias' pycopg/async_database.py` == 7 (1 import + 6 decorators) | PASS |
| `grep -c 'async def create_hypertable' pycopg/async_database.py` == 1 | PASS |
| `grep -c 'def timescale(' pycopg/async_database.py` == 1 | PASS |
| `grep -c '_timescale = AsyncTimescaleAccessor' pycopg/async_database.py` == 1 | PASS |
| `inspect.iscoroutinefunction(AsyncDatabase.create_hypertable)` is True | PASS |
| `from pycopg import TimescaleAccessor, AsyncTimescaleAccessor` exits 0 | PASS |
| Both in `pycopg.__all__` | PASS |
| `grep -c 'from pycopg.timescale import' pycopg/__init__.py` == 1 | PASS |
| ruff exits 0 for all 3 files | PASS |
| interrogate ≥ 95% | PASS (100%) |
| No circular import | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug/Cleanup] Removed unused `validate_interval` from database.py imports**
- **Found during:** Task 1 ruff check
- **Issue:** `validate_interval` was imported in `database.py` but only used by the 6 timescale methods — which are now stubs with no body. ruff F401 flagged it.
- **Fix:** Removed `validate_interval` from the `from pycopg.utils import (...)` block
- **Files modified:** pycopg/database.py
- **Commit:** fad0cd7 (included in task commit)

**2. [Rule 1 - Bug/Cleanup] Removed unused `validate_interval` from async_database.py imports**
- **Found during:** Task 2 ruff check
- **Issue:** Same as above — async timescale stubs no longer call `validate_interval`
- **Fix:** Removed `validate_interval` from the `from pycopg.utils import (...)` block
- **Files modified:** pycopg/async_database.py
- **Commit:** 426d628 (included in task commit)

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced.

T-21-03 mitigated: lazy import inside the `timescale` property avoids circular import between `database.py`/`async_database.py` and `timescale.py`.
T-21-02 mitigated: stubs carry no SQL; all SQL + validate_* guards live in plan-01 `timescale.py`.
T-21-01 mitigated: all 6 `target_path` strings are hardcoded source literals.

## Known Stubs

None — the deprecated stubs are intentional aliases (not placeholder data). All 6 methods fully delegate to `self.timescale.*` via the `deprecated_alias` decorator.

## Self-Check: PASSED
