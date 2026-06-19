---
phase: 25-alias-removal
plan: "04"
subsystem: source-fixes
tags: [in-02, guard-strings, spatial, timescale, comment-fix]
dependency_graph:
  requires: [25-01, 25-02]
  provides: [IN-02-complete-spatial-timescale]
  affects: [pycopg/spatial.py, pycopg/timescale.py, tests/test_sql_injection.py]
tech_stack:
  added: []
  patterns: [sed-uniform-substitution, comment-accuracy]
key_files:
  created: []
  modified:
    - pycopg/spatial.py
    - pycopg/timescale.py
    - tests/test_sql_injection.py
decisions:
  - "Uniform sed substitution used for all 13 guard string sites across 2 files"
  - "Comment updated to accurately describe SpatialAccessor.__init__ PostGIS guard, not alias routing"
metrics:
  duration: "~3 minutes"
  tasks_completed: 2
  files_modified: 3
  completed_date: "2026-06-19"
---

# Phase 25 Plan 04: IN-02 Guard Strings + Comment Fix Summary

**One-liner:** Closed remaining IN-02 sites — 13 guard strings in spatial.py (1) and timescale.py (12) now reference `db.schema.create_extension`, and the stale alias-routing comment in test_sql_injection.py is corrected.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix PostGIS guard (spatial.py) + 12 TimescaleDB guards (timescale.py) | adf8e23 | pycopg/spatial.py, pycopg/timescale.py |
| 2 | Correct stale alias-routing comment in test_sql_injection.py | 91855a5 | tests/test_sql_injection.py |

## What Was Built

### Task 1: IN-02 Guard String Fixes

Applied uniform substitution `Run db.create_extension` → `Run db.schema.create_extension` to:
- `pycopg/spatial.py`: the `_POSTGIS_GUARD_MSG` constant (1 site, L966)
- `pycopg/timescale.py`: 12 `ExtensionNotAvailable(...)` guard messages (L80, 124, 177, 214, 240, 268, 332, 376, 431, 468, 494, 522)

No method logic or signatures changed — only the human-readable remediation hint in error strings.

### Task 2: Stale Comment Fix

In `tests/test_sql_injection.py`, the `sync_db` fixture docstring comment at ~L38 previously read:

> "This is necessary because the deprecated flat spatial aliases now route through the PostGIS-guarded SpatialAccessor (D-06)."

Replaced with accurate post-removal description:

> "This is necessary because SpatialAccessor.__init__ performs a PostGIS guard check (via has_extension), so the fixture patches it to return True."

Test bodies, fixture logic, imports, and assertions are all unchanged. All 92 tests in `test_sql_injection.py` pass green.

## Verification

- `grep -c "db\.create_extension(" pycopg/spatial.py` → 0 (PASS)
- `grep -c "db\.create_extension(" pycopg/timescale.py` → 0 (PASS)
- `grep -c "db\.schema\.create_extension('postgis')" pycopg/spatial.py` → 1 (PASS)
- `grep -c "db\.schema\.create_extension('timescaledb')" pycopg/timescale.py` → 12 (PASS)
- `grep -c "flat spatial aliases now route" tests/test_sql_injection.py` → 0 (PASS)
- `uv run pytest tests/test_sql_injection.py -q -o addopts=""` → 92 passed (PASS)
- `uv run ruff check pycopg/spatial.py pycopg/timescale.py` → All checks passed (PASS)
- `uv run black --check pycopg/spatial.py pycopg/timescale.py` → 2 files would be left unchanged (PASS)

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

None — only string literal and comment text changes; no new network endpoints, auth paths, file access patterns, or schema changes.

## Known Stubs

None — no stubs created in this plan.

## Self-Check: PASSED

- [x] pycopg/spatial.py modified and committed (adf8e23)
- [x] pycopg/timescale.py modified and committed (adf8e23)
- [x] tests/test_sql_injection.py modified and committed (91855a5)
- [x] adf8e23 exists in git log
- [x] 91855a5 exists in git log
