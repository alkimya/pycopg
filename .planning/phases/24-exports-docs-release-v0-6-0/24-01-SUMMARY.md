---
phase: 24-exports-docs-release-v0-6-0
plan: "01"
subsystem: docs
tags: [docs, accessor, sphinx, readme, autodoc, deprecation]
dependency_graph:
  requires: [23-exports-docs-release-v0-6-0]
  provides: [accessor-docs, sphinx-gate-green]
  affects: [README.md, docs/api-autodoc.md, docs/roles-permissions.md, docs/backup-restore.md, docs/timescaledb.md, docs/database.md]
tech_stack:
  added: []
  patterns: [accessor-path docs, MyST Sphinx autodoc, deprecation notice box]
key_files:
  created: []
  modified:
    - docs/api-autodoc.md
    - docs/roles-permissions.md
    - docs/backup-restore.md
    - docs/timescaledb.md
    - docs/database.md
    - README.md
decisions:
  - "MIGRATION.md links use GitHub absolute URL (not ../MIGRATION.md) — Sphinx does not resolve root-level files as doc sources; absolute URL avoids myst.xref_missing warnings"
metrics:
  duration: "~25 minutes"
  completed: "2026-06-19"
  tasks_completed: 3
  files_modified: 6
---

# Phase 24 Plan 01: Accessor Docs + README Namespaces Summary

Autodoc'd all 5 new accessor modules in `docs/api-autodoc.md`, rewrote flat-method
examples to accessor paths in 4 per-topic Sphinx prose pages, and added the
"Accessor Namespaces" overview table to README with live method counts (admin 11,
schema 27). Sphinx `-W` gate and `interrogate >=95` both pass.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Add 5 accessor automodule blocks to api-autodoc.md | 74aa0c1 | docs/api-autodoc.md |
| 2 | Rewrite flat examples to accessor paths in 4 prose pages | b825465 | docs/roles-permissions.md, docs/backup-restore.md, docs/timescaledb.md, docs/database.md |
| 3 | Rewrite README flat sections + add Accessor Namespaces overview | e03ff11 | README.md |

## Verification Results

```
rm -rf docs/_build/
uv run sphinx-build -W --keep-going -b html docs docs/_build/html  # exit 0
uv run interrogate pycopg --fail-under 95 --quiet                   # exit 0
```

Both gates passed after all edits.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MIGRATION.md relative link caused Sphinx xref warnings**
- **Found during:** Task 2 — first `-W` build after adding deprecation notices
- **Issue:** `[MIGRATION.md](../MIGRATION.md)` in the 4 doc pages produced `myst.xref_missing` warnings because `MIGRATION.md` is at repo root, outside the `docs/` Sphinx source tree. With `-W` (warnings-as-errors), this broke the build.
- **Fix:** Replaced `../MIGRATION.md` with `https://github.com/alkimya/pycopg/blob/main/MIGRATION.md` in all 4 deprecation notices. External URL resolves without Sphinx cross-reference lookup.
- **Files modified:** docs/roles-permissions.md, docs/backup-restore.md, docs/timescaledb.md, docs/database.md
- **Commit:** b825465

## Key Decisions

- MIGRATION.md links must be absolute GitHub URLs in Sphinx prose pages (Sphinx treats `../MIGRATION.md` as a document cross-reference and errors with `-W` when the file is outside the source tree).

## Artifacts Produced

| Artifact | Status | Contains |
| -------- | ------ | -------- |
| docs/api-autodoc.md | Modified | 5 new automodule blocks (timescale/admin/maint/backup/schema) |
| docs/roles-permissions.md | Modified | db.admin.* accessor paths + v0.6.0→v0.7.0 deprecation notice |
| docs/backup-restore.md | Modified | db.backup.* accessor paths + v0.6.0→v0.7.0 deprecation notice |
| docs/timescaledb.md | Modified | db.timescale.* accessor paths + v0.6.0→v0.7.0 deprecation notice |
| docs/database.md | Modified | db.schema.*/db.maint.* accessor paths + v0.6.0→v0.7.0 deprecation notice |
| README.md | Modified | "Accessor Namespaces" overview (live counts) + all flat sections rewritten |

## Known Stubs

None — all accessor paths are live (methods exist in the shipped accessor modules from Phases 21-23).

## Threat Flags

None — this plan edits Markdown/RST docs only; no new runtime code path or security surface introduced.

## Self-Check: PASSED

- docs/api-autodoc.md contains 5 automodule blocks: VERIFIED (grep count = 5)
- docs/roles-permissions.md contains db.admin. + v0.7.0: VERIFIED
- docs/backup-restore.md contains db.backup. + v0.7.0: VERIFIED
- docs/timescaledb.md contains db.timescale. + v0.7.0: VERIFIED
- docs/database.md contains db.schema. + db.maint.: VERIFIED
- README.md contains "Accessor Namespaces" + admin 11 methods + schema 27 methods: VERIFIED
- README.md still shows db.execute/db.session/db.to_dataframe flat: VERIFIED
- Commits 74aa0c1, b825465, e03ff11 exist: VERIFIED
- Sphinx -W cleared-cache build exits 0: VERIFIED
- interrogate --fail-under 95 exits 0: VERIFIED
