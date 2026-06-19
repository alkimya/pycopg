---
phase: 25-alias-removal
plan: "05"
subsystem: documentation
tags: [migration, changelog, docs, alias-removal, v0.7.0]

# Dependency graph
requires:
  - phase: 25-alias-removal/25-04
    provides: IN-02 guard strings fixed in source (spatial.py, timescale.py, test comment)
provides:
  - MIGRATION.md v0.6→v0.7 section with 56-row flat→accessor removal table
  - CHANGELOG.md [0.7.0] Breaking entry linking to MIGRATION anchor
  - All docs/*.md flat-name code examples corrected to accessor paths (IN-02 docs slice)
  - 4 deprecation notes updated from "will be removed" to "removed in v0.7.0"
affects: [25-alias-removal, Phase 29 release docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Migration guide pattern: new H1 section prepended to MIGRATION.md per version boundary"
    - "CHANGELOG [N.N.N] - TBD for unreleased breaking change documentation"

key-files:
  created: []
  modified:
    - MIGRATION.md
    - CHANGELOG.md
    - docs/index.md
    - docs/getting-started.md
    - docs/postgis.md
    - docs/async-database.md
    - docs/roles-permissions.md
    - docs/backup-restore.md
    - docs/timescaledb.md
    - docs/database.md

key-decisions:
  - "Reused existing v0.6.0 flat→accessor table verbatim for the v0.7.0 removal table (D-09)"
  - "CHANGELOG date stays TBD — no version bump (Phase 29 sets the version)"
  - "Deprecation notes in accessor docs updated to past-tense 'removed in v0.7.0'"

patterns-established:
  - "Accessor docs deprecation notes: use past tense 'removed in vX.Y.0' after removal"

requirements-completed: [ALIAS-RM-03, ALIAS-RM-04]

# Metrics
duration: 15min
completed: 2026-06-19
---

# Phase 25 Plan 05: Documentation (MIGRATION + CHANGELOG + Docs Examples) Summary

**MIGRATION.md v0.6→v0.7 section with 56-row removal table + CHANGELOG [0.7.0] Breaking entry + 10 stale flat-name code examples and 4 deprecation notes corrected across docs/**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-19T20:55:00Z
- **Completed:** 2026-06-19T21:10:00Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Added `Migration Guide: v0.6.0 → v0.7.0` section to MIGRATION.md with the complete
  56-row flat→accessor removal table (reused v0.6.0 table, reframed as "removed in v0.7.0
  — now raises AttributeError")
- Added `## [0.7.0] - TBD` Breaking section to CHANGELOG.md with anchor link to the
  MIGRATION v0.6→v0.7 section; date stays TBD (Phase 29 sets the version)
- Fixed all 10 stale flat-name code examples across docs/index.md, docs/getting-started.md,
  docs/postgis.md (4 sites), and docs/async-database.md (multiple sites) to use accessor paths
- Updated 4 deprecation-note callouts in docs/roles-permissions.md, docs/backup-restore.md,
  docs/timescaledb.md, docs/database.md from future-tense "will be removed" to past-tense "removed"

## Task Commits

1. **Task 1: MIGRATION v0.6→v0.7 section + CHANGELOG [0.7.0] Breaking entry** - `f8fb81b` (docs)
2. **Task 2: Fix stale flat-name code examples + deprecation notes in docs (IN-02)** - `72ee0ed` (docs)

## Files Created/Modified

- `MIGRATION.md` — new H1 section prepended: `Migration Guide: v0.6.0 → v0.7.0` with 56-row
  flat→accessor removal table and upgrade checklist
- `CHANGELOG.md` — new `## [0.7.0] - TBD` section with `### Breaking` entry linking to MIGRATION
- `docs/index.md` — Quick Example updated: list_schemas/list_tables/size → schema.*/maint.*
- `docs/getting-started.md` — Basic Operations updated: list_schemas/list_tables/table_info/size
- `docs/postgis.md` — 4 sites: create_extension/has_extension/create_index → schema.*
- `docs/async-database.md` — 10 sites: schema.*, maint.vacuum, backup.*, schema.create_database,
  admin.create_role/etc, timescale.*; also schema.table_sizes (Admin Operations section)
- `docs/roles-permissions.md` — deprecation note: "will be removed" → "removed in v0.7.0"
- `docs/backup-restore.md` — deprecation note: "will be removed" → "removed in v0.7.0"
- `docs/timescaledb.md` — deprecation note: "will be removed" → "removed in v0.7.0"
- `docs/database.md` — deprecation note: "will be removed" → "removed in v0.7.0"

## Decisions Made

- Reused the existing 56-row flat→accessor table from the v0.6.0 Migration Guide verbatim
  (D-09 direction: don't regenerate, reuse). Table headers updated to "removed in v0.7.0".
- CHANGELOG date set to `TBD` per plan (Phase 29 sets the actual version string).
- docs/async-database.md Schema Operations section required broader fix than the 3 lines
  in RESEARCH.md §5 — the full schema/table/column/extension sub-block had flat calls;
  all corrected consistently (auto-fix Rule 2: factually wrong post-v0.7.0 documentation).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Broader async-database.md schema section fix**
- **Found during:** Task 2 (docs/async-database.md)
- **Issue:** The RESEARCH.md §5 table listed 3 specific lines (L263/L266/L283) in the
  Schema Operations code block but the block contained additional flat calls (schema_exists,
  table_exists, table_info, list_columns, columns_with_types, row_count, list_extensions,
  has_extension). Leaving those unpatched would leave factually wrong documentation.
- **Fix:** Updated the entire Schema Operations code block consistently to accessor paths.
- **Files modified:** docs/async-database.md
- **Verification:** `grep -rn "db\\.create_extension(" docs/*.md` → 0
- **Committed in:** 72ee0ed (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — broader scope for documentation accuracy)
**Impact on plan:** Zero scope creep — purely documentation correctness. All accessor mappings
come from the same research-verified table.

## Issues Encountered

None — markdownlint warnings about multiple H1 headings in MIGRATION.md are pre-existing
(the file has always had one H1 per version guide section; Sphinx -W does not flag this).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 25-05 is the final plan in Phase 25 (alias-removal). All 5 plans complete.
- REQUIREMENTS ALIAS-RM-03 and ALIAS-RM-04 (docs slice) are now satisfied.
- Phase 25 verification gate: run `uv run pytest tests/test_alias_removal.py tests/test_parity.py`
  to confirm tests still pass before moving to Phase 26 (Incremental ETL).
- No blockers. Phase 26 planning can proceed.

---

*Phase: 25-alias-removal*
*Completed: 2026-06-19*
