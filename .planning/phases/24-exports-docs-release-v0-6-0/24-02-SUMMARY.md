---
phase: 24-exports-docs-release-v0-6-0
plan: "02"
subsystem: docs-release
tags: [changelog, migration, exports, deprecation, v0.6.0]
dependency_graph:
  requires: [24-01]
  provides: [CHANGELOG [0.6.0] entry, MIGRATION.md v0.5→v0.6 section, exports criterion #1 confirmed]
  affects: [CHANGELOG.md, MIGRATION.md]
tech_stack:
  added: []
  patterns: [Keep-a-Changelog three-bucket shape, prepend-migration pattern, live-grep alias table]
key_files:
  created: []
  modified:
    - CHANGELOG.md
    - MIGRATION.md
decisions:
  - "D-04 executed: v0.5→v0.6 migration section prepended above existing v0.2→v0.3 content in MIGRATION.md"
  - "D-05 executed: [0.6.0] CHANGELOG entry with Added/Deprecated/Changed buckets, live counts (admin 11/schema 27), v0.7.0 removal notice, D-06 PostGIS-guard note"
  - "Criterion #1 confirmed verify-only: all 10 accessor classes importable from pycopg; __init__.py untouched"
metrics:
  duration: ~15min
  completed: 2026-06-19
---

# Phase 24 Plan 02: CHANGELOG + MIGRATION + Exports Verification Summary

**One-liner:** CHANGELOG `[0.6.0]` entry (Added/Deprecated/Changed) + prepended v0.5→v0.6 MIGRATION section with live-verified 56-name flat→accessor table; exports criterion #1 confirmed.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Verify exports (smoke-test, verify-only) | — (no commit; no files modified) | `pycopg/__init__.py` verified untouched |
| 2 | Prepend v0.5→v0.6 Migration Guide to MIGRATION.md | a78729a | `MIGRATION.md` (+172 lines prepended) |
| 3 | Write CHANGELOG [0.6.0] entry (Added/Deprecated/Changed) | 26295e6 | `CHANGELOG.md` (+37 lines, footer updated) |

## What Was Built

### Task 1 — Exports verified (no code changes)

Ran the full 10-class import smoke test:

```
from pycopg import TimescaleAccessor, AsyncTimescaleAccessor, AdminAccessor,
    AsyncAdminAccessor, MaintAccessor, AsyncMaintAccessor, BackupAccessor,
    AsyncBackupAccessor, SchemaAccessor, AsyncSchemaAccessor
```

Result: `All 10 accessor classes importable - OK`. `git diff --stat pycopg/__init__.py` shows zero changes. Criterion #1 (REORG-05) confirmed satisfied from prior phases.

Live alias count cross-check: `grep -c '@deprecated_alias' pycopg/database.py` = **56**. Matches PATTERNS.md table exactly.

### Task 2 — MIGRATION.md prepended section

Prepended `# Migration Guide: v0.5.0 → v0.6.0` as the new first section above the existing `# Migration Guide: v0.2.0 to v0.3.0` (line 173 in the updated file). The new section contains:

- Intro paragraph naming 5 accessor namespaces and "removed in v0.7.0" deprecation
- Before/after `python` examples for all 6 accessor groups (timescale/admin/schema/maint/backup/spatial)
- D-06 PostGIS-guard note: deprecated flat `db.create_spatial_index` / `db.list_geometry_columns` now raises `ExtensionNotAvailable` early when PostGIS absent
- Complete 56-row flat→accessor table with regeneration command
- Upgrade checklist and Getting Help section

Table counts verified against live source: admin 11, schema 27, timescale 6, maint 6, backup 4, spatial 2 = 56. `docs/migrations.md` untouched (confirmed via `git diff`).

### Task 3 — CHANGELOG [0.6.0] entry

Added `## [0.6.0]` section under `## [Unreleased]` (date stamp deferred to 24-03) with three Keep-a-Changelog buckets:

- **Added:** 5 accessor namespaces with live method counts + 10 exported accessor classes
- **Deprecated:** all 56 flat `db.*` names emit `DeprecationWarning`, removal in v0.7.0, pointer to MIGRATION.md
- **Changed:** D-06(P23) refinement — deprecated spatial flat path raises `ExtensionNotAvailable` early via `db.spatial` PostGIS guard

Updated compare-link footer: `[Unreleased]` now points to `v0.6.0...HEAD`; added `[0.6.0]: .../compare/v0.5.0...v0.6.0` line.

## Verification

```
grep -c '@deprecated_alias' pycopg/database.py   # 56
from pycopg import TimescaleAccessor, AsyncSchemaAccessor; print('OK')  # OK
uv run interrogate pycopg --fail-under 95        # PASSED (actual: 100.0%)
grep -c '## \[0.6.0\]' CHANGELOG.md             # 1
grep -c 'Migration Guide: v0.5.0' MIGRATION.md  # 1
grep -c '| `db\.' MIGRATION.md                  # 56 (table rows)
```

## Deviations from Plan

None — plan executed exactly as written. Task 1 required no commit (verify-only; no files modified). The MD024 linter warning in CHANGELOG.md (`no-duplicate-heading` on `### Added`/`### Changed`) is a pre-existing false positive for Keep-a-Changelog format — the same heading names appear in every prior version entry; this is expected and not a regression.

## Known Stubs

None. This plan produces documentation only; no data sources or UI components.

## Threat Flags

None. Files edited are Markdown only; no runtime code paths, no user input, no credentials.

## Self-Check: PASSED

- [x] `MIGRATION.md` starts with `# Migration Guide: v0.5.0 → v0.6.0` (line 1) — confirmed
- [x] `CHANGELOG.md` contains `## [0.6.0]` — confirmed (`grep -c` = 1)
- [x] 56-row table in MIGRATION.md — confirmed (`grep -c '| \`db\.'` = 56)
- [x] `pycopg/__init__.py` unchanged — confirmed (`git diff --stat` = no output)
- [x] `docs/migrations.md` unchanged — confirmed (`git diff` = no output)
- [x] Commits exist: a78729a (MIGRATION.md), 26295e6 (CHANGELOG.md) — confirmed via git log
