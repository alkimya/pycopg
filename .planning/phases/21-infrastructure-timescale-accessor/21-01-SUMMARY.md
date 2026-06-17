---
phase: 21-infrastructure-timescale-accessor
plan: "01"
subsystem: timescale-accessor
tags: [accessor, deprecated-alias, timescale, decorator, refactor]
dependency_graph:
  requires: []
  provides:
    - pycopg.aliases.deprecated_alias
    - pycopg.timescale.TimescaleAccessor
    - pycopg.timescale.AsyncTimescaleAccessor
  affects:
    - plan-02 (wires accessors into Database/AsyncDatabase)
    - plan-03 (alias tests + call-site migration)
tech_stack:
  added: []
  patterns:
    - deprecated_alias decorator factory with sync/async branch (iscoroutinefunction)
    - Lazy accessor __init__(self, db) pattern (mirrors ETLAccessor)
    - TYPE_CHECKING guard for circular-import avoidance
key_files:
  created:
    - pycopg/aliases.py
    - pycopg/timescale.py
  modified: []
decisions:
  - "Added docstrings to inner functions (decorator, async_wrapper, sync_wrapper) to satisfy interrogate 100% — inner nested functions are counted by interrogate with no ignore-nested-functions config option"
metrics:
  duration: "3 minutes"
  completed: "2026-06-17T12:14:36Z"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
---

# Phase 21 Plan 01: Infrastructure & Timescale Accessor — Foundation Modules Summary

Two new stand-alone modules establish the v0.6.0 accessor pattern proof: `deprecated_alias` decorator with sync+async branch, and `TimescaleAccessor`/`AsyncTimescaleAccessor` with 6 verbatim-moved methods each.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create deprecated_alias decorator module | 15c4ccc | pycopg/aliases.py |
| 2 | Create timescale.py with TimescaleAccessor + AsyncTimescaleAccessor | 73ad1c6 | pycopg/timescale.py |

## What Was Built

### Task 1: `pycopg/aliases.py`

Defines `deprecated_alias(target_path: str)` — a decorator factory used across all v0.6.0 phases (21-24) to replace flat `db.*` method bodies with warn-then-delegate wrappers.

Key properties:
- `target_path` resolved via `str.split(".", 1)` + `getattr(self, accessor_name)` only — no `eval`/`exec` (threat T-21-01)
- `inspect.iscoroutinefunction(fn)` branch: async stubs get an `async def` wrapper preserving `iscoroutinefunction(wrapper) is True`
- `stacklevel=2` in `warnings.warn` so the warning points at the caller's file (Footgun 2)
- `functools.wraps(fn)` copies `__name__`, `__doc__`, `__qualname__` from stub

### Task 2: `pycopg/timescale.py`

Defines `TimescaleAccessor` and `AsyncTimescaleAccessor`, each exposing 6 methods moved verbatim from `database.py`/`async_database.py` with `self.` → `self._db.` rewrites only:

- `create_hypertable`, `enable_compression`, `add_compression_policy`
- `add_retention_policy`, `list_hypertables`, `hypertable_info`

All `validate_identifiers`, `validate_interval`, `validate_identifier` guards and `has_extension("timescaledb")` checks travel with the bodies (threat T-21-02). `TYPE_CHECKING` guard avoids circular imports at runtime (Pitfall 5).

## Verification Results

```
uv run python -c "from pycopg.aliases import deprecated_alias; from pycopg.timescale import TimescaleAccessor, AsyncTimescaleAccessor"
→ exits 0

uv run ruff check pycopg/aliases.py pycopg/timescale.py
→ All checks passed

uv run interrogate pycopg --fail-under 95
→ PASSED (100.0%)

Method set assertion (TimescaleAccessor == AsyncTimescaleAccessor == expected 6 methods)
→ PASSED

git diff --name-only (only new files, no database.py edits)
→ CONFIRMED
```

## Acceptance Criteria Check

| Criterion | Result |
|-----------|--------|
| `grep -c 'def deprecated_alias(' pycopg/aliases.py` == 1 | PASS (1) |
| file contains `stacklevel=2` | PASS (2 occurrences — sync + async) |
| file contains `inspect.iscoroutinefunction(` | PASS (1) |
| `grep -v '^#' pycopg/aliases.py \| grep -c 'eval(\|exec('` == 0 | PASS (0) |
| import exits 0 | PASS |
| ruff exits 0 | PASS |
| interrogate ≥ 95% | PASS (100%) |
| `class TimescaleAccessor` AND `class AsyncTimescaleAccessor` in timescale.py | PASS |
| `grep -c 'self\.has_extension(\|self\.execute(' pycopg/timescale.py` == 0 | PASS (0) |
| `grep -c 'self\._db\.execute(' pycopg/timescale.py` ≥ 6 | PASS (12 = 6 sync + 6 async) |
| `grep -c 'validate_interval(\|validate_identifiers(' pycopg/timescale.py` ≥ 4 | PASS (14) |
| Both accessors expose exactly the 6 method names (set equality) | PASS |
| timescale.py ≥ 200 lines | PASS (531 lines) |
| No edits to database.py / async_database.py / __init__.py | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added docstrings to inner nested functions**
- **Found during:** Task 1 verification (interrogate reported 40% coverage, failing --fail-under 95)
- **Issue:** interrogate counts inner nested functions (`decorator`, `async_wrapper`, `sync_wrapper`) as separate items; no `ignore-nested-functions` config option exists in pyproject.toml
- **Fix:** Added single-line docstrings to all three inner functions: `decorator`, `async_wrapper`, `sync_wrapper`
- **Files modified:** pycopg/aliases.py
- **Commit:** 15c4ccc (included in task commit)

None other — plan executed as designed.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced.
Both modules are pure-Python additions with no external I/O.
T-21-01 mitigated: no `eval`/`exec` in aliases.py.
T-21-02 mitigated: all validate_* guards travel with moved method bodies.

## Self-Check: PASSED

Files exist:
- /home/loc/workspace/pycopg/.claude/worktrees/agent-aea2630e915257900/pycopg/aliases.py — FOUND
- /home/loc/workspace/pycopg/.claude/worktrees/agent-aea2630e915257900/pycopg/timescale.py — FOUND

Commits exist:
- 15c4ccc (feat(21-01): create deprecated_alias decorator module) — FOUND
- 73ad1c6 (feat(21-01): create timescale.py with TimescaleAccessor + AsyncTimescaleAccessor) — FOUND
