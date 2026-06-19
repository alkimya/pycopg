---
phase: 25-alias-removal
plan: "01"
subsystem: pycopg.database
tags: [alias-removal, database, cleanup, in-02]
dependency_graph:
  requires: []
  provides: [database.py-clean-of-deprecated-alias-stubs]
  affects: [plans-25-02-through-25-05]
tech_stack:
  added: []
  patterns: [text-pattern-stub-deletion, orphaned-header-cleanup]
key_files:
  created: []
  modified:
    - pycopg/database.py
decisions:
  - D-02 enforced: stubs deleted by 3-line text-pattern regex (not line-range); DATAFRAME OPERATIONS block preserved intact
  - D-08 partial: database.py PostGIS guard updated to db.schema.create_extension; spatial.py + async_database.py + timescale.py handled in plans 25-02 and 25-04
metrics:
  duration: "2 minutes"
  completed: "2026-06-19T20:40:49Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
---

# Phase 25 Plan 01: Alias Stub Removal from database.py Summary

Hard-remove all 56 `@deprecated_alias` flat stub methods from `Database` class plus the `deprecated_alias` import line plus 11 orphaned section-header comments; fix the stale PostGIS guard error string to reference `db.schema.create_extension`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Delete 56 @deprecated_alias stubs + import line + orphaned headers | ed047e4 | pycopg/database.py |
| 2 | Fix stale PostGIS-guard flat-name error string (IN-02) | b4caee0 | pycopg/database.py |

## Verification Results

All acceptance criteria passed:

- `grep -c deprecated_alias pycopg/database.py` → `0` (was 57: 56 stubs + 1 import)
- `grep -c '\*args, \*\*kwargs' pycopg/database.py` → `0` (WR-01 / D-07: all varargs were alias stubs)
- DATAFRAME OPERATIONS methods preserved: `from_dataframe`, `to_dataframe`, `from_geodataframe`, `to_geodataframe` (count=4)
- Lifecycle methods preserved: `close`, `__enter__`, `__exit__` (count=3)
- `grep -c "db\.create_extension(" pycopg/database.py` → `0`
- `grep -c "db\.schema\.create_extension" pycopg/database.py` → `1`
- `uv run ruff check pycopg/database.py` → exits 0
- `uv run black --check pycopg/database.py` → exits 0
- `uv run python -c "import pycopg.database"` → OK

## Deviations from Plan

### Auto-fixed Issues

None.

### Expected Asymmetry (not a deviation)

After Task 1, `tests/test_parity.py::TestAsyncParity::test_known_exceptions_documented` fails because `Database` no longer has the 56 flat names while `AsyncDatabase` still does. This is the expected mid-wave state — per RESEARCH.md §3 and Pitfall #6, parity symmetry is restored when plan 25-02 removes the async stubs. This is not a regression introduced by plan 25-01.

## Implementation Notes

Used a Python regex script to remove stubs atomically, avoiding the line-range deletion risk (D-02 / Pitfall #2). The regex pattern:

```
    @deprecated_alias\([^\)]+\)\n    def \w+\(self, \*args, \*\*kwargs\):\n        """[^"]*"""\n
```

matched exactly 56 stubs and removed them cleanly, preserving the interleaved `DATAFRAME OPERATIONS` block (L983–L1192 in the original file).

The 11 orphaned section-header comment blocks were also removed by regex, keeping only `# DATAFRAME OPERATIONS` which contains real methods.

## Known Stubs

None. All removed content was deprecated delegation stubs with `*args/**kwargs` signatures. The 4 DATAFRAME OPERATIONS real methods and 3 lifecycle methods remain intact with proper typed signatures.

## Threat Flags

No new security-relevant surface introduced. This plan is a pure deletion — removing the `@deprecated_alias` delegation layer removes no security controls (T-25-01 accepted in plan threat model: the validation logic lives in accessor methods which are unchanged).

## Self-Check: PASSED

- `ed047e4` exists: verified (git log confirms)
- `b4caee0` exists: verified (git log confirms)
- `pycopg/database.py` modified: verified (1 file, 269 deletions in Task 1 commit)
- 0 `deprecated_alias` occurrences: verified
- 0 `*args, **kwargs` occurrences: verified
- 4 DATAFRAME methods: verified
- 3 lifecycle methods: verified
