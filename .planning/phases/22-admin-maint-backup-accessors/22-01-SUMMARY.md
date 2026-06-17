---
phase: 22-admin-maint-backup-accessors
plan: "01"
subsystem: accessor-modules
tags: [accessor, admin, maint, backup, v0.6.0, wave-1]
dependency_graph:
  requires: []
  provides:
    - pycopg.admin.AdminAccessor
    - pycopg.admin.AsyncAdminAccessor
    - pycopg.maint.MaintAccessor
    - pycopg.maint.AsyncMaintAccessor
    - pycopg.backup.BackupAccessor
    - pycopg.backup.AsyncBackupAccessor
  affects:
    - pycopg/database.py (Wave 2 wiring)
    - pycopg/async_database.py (Wave 2 wiring)
    - pycopg/__init__.py (Wave 2 exports)
tech_stack:
  added: []
  patterns:
    - accessor-pattern (TimescaleAccessor template, D-06 verbatim-move)
    - TYPE_CHECKING circular-import guard
    - sibling-accessor-routing (D-02, admin create_role only)
key_files:
  created:
    - pycopg/admin.py
    - pycopg/maint.py
    - pycopg/backup.py
  modified: []
decisions:
  - "D-02 applied: create_role sibling calls route through self._db.admin.role_exists/grant_role (4 occurrences: 2 sync + 2 async)"
  - "Bucket B rewrites applied uniformly: self.execute -> self._db.execute, self.config.* -> self._db.config.*, self.cursor() -> self._db.cursor()"
  - "asyncio imported at module level in backup.py (Pitfall 3 prevention)"
  - "_psql_restore moved as private companion to both BackupAccessor and AsyncBackupAccessor (Pitfall 2 prevention)"
  - "explain() params annotated as bare 'params=None' (no Sequence import needed since no runtime check)"
metrics:
  duration_seconds: 286
  completed: "2026-06-17T16:45:40Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 3
  files_modified: 0
---

# Phase 22 Plan 01: Admin/Maint/Backup Accessor Modules Summary

Three new accessor modules created — `pycopg/admin.py`, `pycopg/maint.py`, `pycopg/backup.py` — each holding both a sync and async accessor class, using the Phase 21 TimescaleAccessor pattern applied verbatim across 21 method bodies (11 admin + 6 maint + 4 backup public + 2 private _psql_restore companions).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create pycopg/admin.py (AdminAccessor + AsyncAdminAccessor, 11 methods each) | 8fb6a14 | pycopg/admin.py |
| 2 | Create pycopg/maint.py (MaintAccessor + AsyncMaintAccessor, 6 methods each) | a7b2ba5 | pycopg/maint.py |
| 3 | Create pycopg/backup.py (BackupAccessor + AsyncBackupAccessor, 4 public + _psql_restore) | 2314f36 | pycopg/backup.py |

## What Was Built

**pycopg/admin.py** — `AdminAccessor` + `AsyncAdminAccessor` (11 public methods each):
`create_role`, `drop_role`, `role_exists`, `list_roles`, `alter_role`, `grant_role`, `revoke_role`, `grant`, `revoke`, `list_role_members`, `list_role_grants`.

Critical: `create_role` sibling calls rewritten to `self._db.admin.role_exists(name)` / `self._db.admin.grant_role(role, name)` (D-02 — prevents internal DeprecationWarning from routing through the deprecated flat alias).

**pycopg/maint.py** — `MaintAccessor` + `AsyncMaintAccessor` (6 public methods each):
`size`, `table_size`, `table_sizes`, `vacuum`, `analyze`, `explain`. All Bucket B (no sibling calls). `self.config.database` rewritten to `self._db.config.database` in `size` (both sync and async, 4 total occurrences including pretty/non-pretty branches).

**pycopg/backup.py** — `BackupAccessor` + `AsyncBackupAccessor` (4 public methods + `_psql_restore`):
`pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv`. `_psql_restore` moved as private companion to both classes. `asyncio` imported at module level (required by `AsyncBackupAccessor.pg_dump`/`pg_restore`/`copy_to_csv`). Sync bodies preserve local `import subprocess`. No `shell=True`.

## Verification Results

- `uv run python -c "import pycopg.admin, pycopg.maint, pycopg.backup"` — exit 0
- AdminAccessor: 11 public methods; AsyncAdminAccessor: 11 public methods
- MaintAccessor: 6 public methods; AsyncMaintAccessor: 6 public methods
- BackupAccessor: 4 public methods + `_psql_restore`; AsyncBackupAccessor: same
- D-02 guard: `grep -nE 'self._db.(role_exists|grant_role)\(' pycopg/admin.py` — no matches
- `uv run pytest tests/test_sql_injection.py tests/test_subprocess_env.py -x -q -o addopts=""` — 102 passed

## Deviations from Plan

None — plan executed exactly as written.

The only minor adaptation: `explain()` params parameter typed as bare `params=None` without the `Sequence` annotation (the source bodies in `database.py` use `Sequence | None` from the class-level import, but `maint.py` has no `Sequence` import and the body itself doesn't perform any runtime type checks on params — it passes the value through to `self._db.execute(...)` directly). This is a cosmetic variance with zero behavioral effect.

## Known Stubs

None — all three modules contain complete method bodies moved verbatim from source. No placeholder text or empty implementations.

## Threat Flags

No new security-relevant surface introduced beyond what is already assessed in the plan's threat model. All SQL-injection validators travel with their bodies (T-22-01 mitigated). Subprocess list-form preserved, no `shell=True` (T-22-02 mitigated). D-02 sibling routing prevents internal deprecated-path traversal (T-22-03 mitigated).

## Self-Check: PASSED

Files exist:
- pycopg/admin.py — FOUND
- pycopg/maint.py — FOUND
- pycopg/backup.py — FOUND

Commits exist:
- 8fb6a14 (admin.py) — FOUND
- a7b2ba5 (maint.py) — FOUND
- 2314f36 (backup.py) — FOUND
