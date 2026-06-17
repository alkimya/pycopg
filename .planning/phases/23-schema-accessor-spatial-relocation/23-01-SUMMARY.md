---
phase: 23-schema-accessor-spatial-relocation
plan: "01"
subsystem: schema-accessor
tags: [accessor, schema, ddl, introspection, refactor, v0.6.0]
dependency_graph:
  requires: []
  provides:
    - pycopg.schema.SchemaAccessor
    - pycopg.schema.AsyncSchemaAccessor
  affects:
    - pycopg/database.py (wired in plan 02)
    - pycopg/async_database.py (wired in plan 02)
tech_stack:
  added: []
  patterns:
    - accessor-module shape (mirrors admin.py/maint.py/backup.py/timescale.py)
    - D-04 self.X → self._db.X rewrite
    - TYPE_CHECKING guard for circular-import avoidance
key_files:
  created:
    - pycopg/schema.py
  modified: []
decisions:
  - D-04 rewrite applied: self.execute → self._db.execute (24 methods per class); self.config → self._db.config (3 DB-level methods per class)
  - D-07 honoured: no new queries.py builders extracted; SQL travelled verbatim
  - No sibling-schema self-calls found (research confirmed ZERO — no self._db.schema.<m> rewrites needed)
metrics:
  duration_seconds: 140
  completed: "2026-06-17"
  tasks_total: 2
  tasks_completed: 2
  files_created: 1
  files_modified: 0
---

# Phase 23 Plan 01: Schema Accessor Module Summary

**One-liner:** New `pycopg/schema.py` module with `SchemaAccessor` + `AsyncSchemaAccessor`, 27 DDL/introspection methods verbatim-moved from `Database`/`AsyncDatabase` with full D-04 self→self._db rewrites and security validators preserved.

## What Was Built

Created `/home/loc/workspace/pycopg/pycopg/schema.py` — the new home for the 27 schema DDL and introspection methods, following the same accessor-module shape established in Phases 21/22 (mirrors `pycopg/admin.py` exactly).

### SchemaAccessor (sync)

27 public methods in 5 groups:

| Group | Methods |
|-------|---------|
| Databases (4) | `create_database`, `drop_database`, `database_exists`, `list_databases` |
| Extensions (4) | `create_extension`, `drop_extension`, `list_extensions`, `has_extension` |
| Schemas (4) | `create_schema`, `drop_schema`, `list_schemas`, `schema_exists` |
| Tables + Columns (8) | `list_tables`, `table_exists`, `list_columns`, `columns_with_types`, `drop_table`, `truncate_table`, `table_info`, `row_count` |
| Constraints + Indexes (7) | `add_primary_key`, `add_foreign_key`, `add_unique_constraint`, `create_index`, `drop_index`, `list_indexes`, `list_constraints` |

### AsyncSchemaAccessor (async)

Identical 27-method public surface; all methods are `async def` with `await self._db.execute(...)`. The 3 DB-level methods (`create_database`, `drop_database`, `database_exists`) use `psycopg.AsyncConnection.connect(...)` verbatim (D-07: move-don't-improve — no conversion to `psycopg3` patterns).

### D-04 Rewrite Map Applied

- `self.execute(...)` → `self._db.execute(...)` — 24 methods per class (48 total)
- `self.config.with_database("postgres")` → `self._db.config.with_database("postgres")` — 3 methods per class (`create_database`, `drop_database`, `database_exists`)
- Zero sibling-schema self-calls found (research confirmed) — no `self._db.schema.<m>` rewrites needed

### Security Invariant (T-23-01)

All `validate_identifier`, `validate_identifiers`, `validate_extension_name`, and `validate_index_method` guards travelled verbatim with the moved bodies. No SQL-injection vector was introduced.

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| Task 1 + 2 | Create pycopg/schema.py (SchemaAccessor + AsyncSchemaAccessor, 27 methods each) | 9554b44 |

Both tasks committed together since they create a single coherent file.

## Verification Results

All acceptance criteria passed:

| Check | Result |
|-------|--------|
| `SchemaAccessor` has exactly 27 public methods | PASS |
| `AsyncSchemaAccessor` has exactly 27 public methods | PASS |
| Sync↔async parity (same 27 names) | PASS |
| All async methods are coroutines | PASS |
| `grep -nE 'self\.(execute|config)\b' pycopg/schema.py` → 0 matches | PASS |
| `grep -c 'self._db.config' pycopg/schema.py` → 6 (≥3) | PASS |
| `grep -c 'validate_index_method' pycopg/schema.py` → 3 (≥1) | PASS |
| `grep -c 'validate_identifiers' pycopg/schema.py` → 15 (≥1) | PASS |
| No flat-alias self-call leaks | PASS |
| `uv run ruff check pycopg/schema.py` | PASS |
| `uv run black --check pycopg/schema.py` | PASS |
| `uv run interrogate pycopg/schema.py -f 95` → 100% | PASS |

## Deviations from Plan

None — plan executed exactly as written.

The research had confirmed zero sibling-schema self-calls, which held true during implementation. No unexpected rewrites were needed beyond the documented D-04 map.

## Known Stubs

None. This plan creates only the implementation module — no stubs, no wiring. The flat `db.*` methods in `database.py`/`async_database.py` are unchanged; they remain the original implementations until plan 02 replaces them with `@deprecated_alias` stubs.

## Threat Flags

None. This plan introduces no new I/O surface, no new SQL, and no new user-input paths. The verbatim-move invariant preserved all existing `validate_*` guards (T-23-01 mitigated).

## Self-Check: PASSED

- [x] `pycopg/schema.py` exists: FOUND
- [x] Commit 9554b44 exists: FOUND
- [x] 27 public methods on both accessor classes: VERIFIED
- [x] No `self.execute`/`self.config` leaks: VERIFIED (0 grep matches)
- [x] Validators present: VERIFIED
- [x] ruff + black + interrogate clean: VERIFIED
