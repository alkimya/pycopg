---
phase: 25-alias-removal
plan: "02"
subsystem: pycopg.async_database
tags: [alias-removal, async-database, cleanup, in-02]
dependency_graph:
  requires: [database.py-clean-of-deprecated-alias-stubs]
  provides: [async_database.py-clean-of-deprecated-alias-stubs]
  affects: [plans-25-03-through-25-05, test_parity.py-symmetry-restored]
tech_stack:
  added: []
  patterns: [text-pattern-stub-deletion, orphaned-header-cleanup]
key_files:
  created: []
  modified:
    - pycopg/async_database.py
decisions:
  - D-02 enforced: stubs deleted by 3-line text-pattern regex (not line-range); all 4 interleaved real-method sections preserved (DATAFRAME, BATCH, STREAMING, LISTEN/NOTIFY)
  - D-07 / WR-01 closed: 0 *args/**kwargs remain on AsyncDatabase public surface
  - D-08 partial: async_database.py PostGIS guard updated to db.schema.create_extension
metrics:
  duration: "4 minutes"
  completed: "2026-06-19T20:55:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
---

# Phase 25 Plan 02: Alias Stub Removal from async_database.py Summary

Hard-remove all 56 `@deprecated_alias` flat stub methods from `AsyncDatabase` class plus the `deprecated_alias` import line plus 11 orphaned section-header comments; fix the stale PostGIS guard error string to reference `db.schema.create_extension`; restore sync/async parity symmetry after plan 25-01.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Delete 56 @deprecated_alias stubs + import line + orphaned headers | 2b9aede | pycopg/async_database.py |
| 2 | Fix stale PostGIS-guard flat-name error string (IN-02) | 61d6277 | pycopg/async_database.py |

## Verification Results

All acceptance criteria passed:

- `grep -c deprecated_alias pycopg/async_database.py` → `0` (was 57: 56 stubs + 1 import)
- `grep -c '\*args, \*\*kwargs' pycopg/async_database.py` → `0` (WR-01 / D-07: all varargs were alias stubs)
- DATAFRAME OPERATIONS methods preserved: `to_dataframe`, `from_dataframe`, `to_geodataframe`, `from_geodataframe` (count=4)
- BATCH + STREAMING + LISTEN/NOTIFY methods preserved: `insert_many`, `upsert_many`, `stream`, `listen`, `notify` (count=5)
- Lifecycle methods preserved: `close`, `__aenter__`, `__aexit__` (count=3)
- `grep -c "db\.create_extension(" pycopg/async_database.py` → `0`
- `grep -c "db\.schema\.create_extension('postgis')" pycopg/async_database.py` → `1`
- `uv run ruff check pycopg/async_database.py` → exits 0
- `uv run black --check pycopg/async_database.py` → exits 0
- `uv run python -c "import pycopg.async_database"` → OK
- `uv run pytest tests/test_parity.py -v -o addopts=""` → 24/24 passed (parity symmetry restored)

## Deviations from Plan

### Auto-fixed Issues

None.

### Expected State (not a deviation)

After this plan, `tests/test_admin_aliases.py` (and the other 5 alias test files) will fail when run — they assert that stubs WARN and DELEGATE, but both sync and async stubs are now gone. This is the expected mid-wave state. Plan 25-03 will delete all 6 alias test files and replace them with `test_alias_removal.py`. This is documented per RESEARCH.md §3 and Pitfall #6.

The 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) failed as expected — fixture-isolation bug unrelated to this plan, pre-existing since v0.6.0.

## Implementation Notes

Used a Python regex script to remove stubs atomically, avoiding the line-range deletion risk (D-02 / Pitfall #3). The async file has MORE interleaving than the sync file — 4 real-method sections (DATAFRAME, BATCH, STREAMING, LISTEN/NOTIFY) embedded within the alias region. The regex pattern:

```
    @deprecated_alias\([^\)]+\)\n    async def \w+\(self, \*args, \*\*kwargs\):\n        """[^"]*"""\n
```

matched exactly 56 stubs and removed them cleanly.

The 11 orphaned section-header comment blocks were removed by regex. The first 43 stubs (L732–L938) were under headers SCHEMAS & TABLES, CONSTRAINTS & INDEXES, EXTENSIONS, POSTGIS SPATIAL OPERATIONS, TIMESCALEDB OPERATIONS, ROLES & USERS, ROLE MANAGEMENT, and SIZE & STATS. After the 4 interleaved real-method sections, the remaining 13 stubs (L1289–L1340) were under DATABASE ADMINISTRATION, UTILITY, and BACKUP & RESTORE.

## Known Stubs

None. All removed content was deprecated delegation stubs with `*args/**kwargs` signatures. All real methods in the 4 interleaved sections and 3 lifecycle methods remain intact with proper typed signatures.

## Threat Flags

No new security-relevant surface introduced. This plan is a pure deletion — removing the `@deprecated_alias` delegation layer removes no security controls (T-25-03 accepted in plan threat model: validation logic lives in unchanged async accessors). T-25-04 mitigation verified: all 4 interleaved real-method sections + lifecycle preserved via acceptance grep assertions.

## Self-Check: PASSED

- `2b9aede` exists: verified (git log confirms)
- `61d6277` exists: verified (git log confirms)
- `pycopg/async_database.py` modified: verified (269 deletions in Task 1 commit + 1 line fix in Task 2)
- 0 `deprecated_alias` occurrences: verified
- 0 `*args, **kwargs` occurrences: verified
- 4 DATAFRAME methods: verified
- 5 BATCH+STREAMING+LISTEN/NOTIFY methods: verified
- 3 lifecycle methods: verified
- 0 `db.create_extension(` occurrences: verified
- 1 `db.schema.create_extension('postgis')` occurrence: verified
- test_parity.py: 24/24 passed
