---
phase: 22-admin-maint-backup-accessors
plan: "02"
subsystem: accessor-wiring
tags: [accessor, admin, maint, backup, database-wiring, v0.6.0, wave-2]
dependency_graph:
  requires:
    - pycopg.admin.AdminAccessor (Wave 1)
    - pycopg.admin.AsyncAdminAccessor (Wave 1)
    - pycopg.maint.MaintAccessor (Wave 1)
    - pycopg.maint.AsyncMaintAccessor (Wave 1)
    - pycopg.backup.BackupAccessor (Wave 1)
    - pycopg.backup.AsyncBackupAccessor (Wave 1)
  provides:
    - Database.admin (lazy property → AdminAccessor)
    - Database.maint (lazy property → MaintAccessor)
    - Database.backup (lazy property → BackupAccessor)
    - AsyncDatabase.admin (lazy property → AsyncAdminAccessor)
    - AsyncDatabase.maint (lazy property → AsyncMaintAccessor)
    - AsyncDatabase.backup (lazy property → AsyncBackupAccessor)
    - 21 @deprecated_alias stubs on Database
    - 21 async @deprecated_alias stubs on AsyncDatabase
    - pycopg.__all__ exports for 6 accessor classes
  affects:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/__init__.py
    - Wave 3 (tests wire against these properties)
tech_stack:
  added: []
  patterns:
    - timescale-accessor-wiring (replicated 3x for admin/maint/backup)
    - deprecated_alias stub pattern (D-06)
    - lazy-cached property pattern
key_files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/__init__.py
decisions:
  - "Lazy property pattern mirrored verbatim from timescale: if self._<name> is None guard + lazy import + cache"
  - "All 21 flat names stubbed with @deprecated_alias — 11 admin + 6 maint + 4 backup (private _psql_restore NOT stubbed)"
  - "async_database.py had two separate role sections (ROLES + ROLE MANAGEMENT); merged into single ROLES & USERS + ROLE MANAGEMENT header for consistency"
  - "TYPE_CHECKING imports alphabetically sorted (admin, backup, etl, maint, spatial, timescale)"
metrics:
  duration_seconds: 600
  completed: "2026-06-17T19:19:06Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 0
  files_modified: 3
---

# Phase 22 Plan 02: Accessor Wiring (Database/AsyncDatabase/__init__) Summary

Three-file wiring wave that connects the Wave 1 accessor modules into `Database`, `AsyncDatabase`, and `pycopg.__init__`. After this wave `db.admin.*` / `db.maint.*` / `db.backup.*` (and async equivalents) route to the real implementations, while all 21 legacy flat names emit a `DeprecationWarning` and delegate to the accessor.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wire sync Database (cache fields, 3 lazy properties, 21 deprecated_alias stubs) | b4bed2a | pycopg/database.py |
| 2 | Wire async AsyncDatabase (cache fields, 3 lazy properties, 21 async deprecated_alias stubs) | 70ec89b | pycopg/async_database.py |
| 3 | Export the 6 new accessor classes from pycopg/__init__.py | 0966c9b | pycopg/__init__.py |

## What Was Built

**pycopg/database.py** changes:
- TYPE_CHECKING block: added `AdminAccessor`, `BackupAccessor`, `MaintAccessor` imports
- `__init__`: added `self._admin`, `self._maint`, `self._backup` cache fields (typed `| None = None`)
- 3 new lazy `@property` blocks (`admin`, `maint`, `backup`) after `timescale` property, each with numpydoc docstring + `if self._<name> is None:` guard + lazy module import + cache + return
- Replaced 11 admin method bodies (`create_role`…`list_role_grants`) with `@deprecated_alias("admin.<method>")` stubs
- Replaced 6 maint method bodies (`size`…`explain`) with `@deprecated_alias("maint.<method>")` stubs
- Replaced 4 backup method bodies (`pg_dump`…`copy_from_csv`) with `@deprecated_alias("backup.<method>")` stubs
- Deleted `_psql_restore` entirely (private companion now lives only on BackupAccessor)

**pycopg/async_database.py** changes:
- Same pattern as above, using `AsyncAdminAccessor`/`AsyncMaintAccessor`/`AsyncBackupAccessor`
- All 21 stubs use `async def` per the timescale async stub template
- `async _psql_restore` deleted
- Note: async_database.py had admin methods split across two sections (ROLES + ROLE MANAGEMENT); the ROLES section (role_exists + list_roles) was stubbed in-place preserving the section header

**pycopg/__init__.py** changes:
- Added 3 import lines: `from pycopg.admin import AdminAccessor, AsyncAdminAccessor`, `from pycopg.backup import AsyncBackupAccessor, BackupAccessor`, `from pycopg.maint import AsyncMaintAccessor, MaintAccessor`
- Added 6 names to `__all__` under `# Admin`, `# Maint`, `# Backup` comment groups

## Verification Results

- `uv run python -c "import pycopg"` — exit 0
- Sync introspect: 11 admin + 6 maint + 4 backup stubs on Database; `_psql_restore` count = 0
- Async introspect: 11 admin + 6 maint + 4 backup async stubs on AsyncDatabase; `_psql_restore` count = 0
- `pycopg.__all__` contains all 6 accessor names; all 6 are importable as `pycopg.<Name>`
- `uv run pytest tests/test_parity.py -x -q -o addopts=""` — 19 passed, 2 expected DeprecationWarnings

## Deviations from Plan

None — plan executed exactly as written.

The only minor structural observation: `async_database.py` had the admin methods split into two section headers (`# ROLES` and `# ROLE MANAGEMENT`). `role_exists` and `list_roles` were in the ROLES section; the remaining 9 methods were in ROLE MANAGEMENT. Both sections were stubbed independently, preserving the existing section headers. This is consistent with the pre-existing file structure and does not affect the stub count (11 total admin stubs).

## Known Stubs

All 21 `@deprecated_alias` stubs are intentional by design (D-06) — they are thin delegation wrappers, not placeholder implementations. The real bodies live in the Wave 1 accessor modules. These stubs are permanent until v0.7.0 removes them.

No unintentional stubs or empty placeholder values.

## Threat Flags

No new security-relevant surface introduced. T-22-05 mitigated: `_psql_restore` is absent from both `database.py` and `async_database.py` (grep count = 0 confirmed). T-22-04 accepted: stubs are generic `(*args, **kwargs)` passthroughs with no parsing.

## Self-Check: PASSED

Files modified:
- pycopg/database.py — FOUND
- pycopg/async_database.py — FOUND
- pycopg/__init__.py — FOUND

Commits:
- b4bed2a (database.py) — FOUND
- 70ec89b (async_database.py) — FOUND
- 0966c9b (__init__.py) — FOUND
