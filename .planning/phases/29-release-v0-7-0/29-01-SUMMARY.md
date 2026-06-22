---
phase: 29-release-v0-7-0
plan: "01"
subsystem: release
tags: [release, version-bump, changelog, migration, incremental-etl]
dependency_graph:
  requires: []
  provides: [version-0.7.0-artifacts]
  affects: [pyproject.toml, docs/conf.py, CHANGELOG.md, MIGRATION.md]
tech_stack:
  added: []
  patterns: [keep-a-changelog, semantic-versioning]
key_files:
  created: []
  modified:
    - pyproject.toml
    - docs/conf.py
    - CHANGELOG.md
    - MIGRATION.md
decisions:
  - "CHANGELOG Added entry covers shipped incremental-ETL surface only — no deferred items (initial_watermark, CDC, scheduler)"
  - "Footer reference links updated: [Unreleased] now compares against v0.7.0; [0.7.0] link added"
  - "MIGRATION incremental note placed before 'Getting Help', after upgrade checklist — additive subsection, 56-name table intact"
metrics:
  duration: "92s"
  completed: "2026-06-22"
  tasks: 3
  files: 4
---

# Phase 29 Plan 01: Version Bump and Release Artifacts Summary

Version bumped to 0.7.0 in both sources, CHANGELOG [0.7.0] finalized with Breaking + Added (dated 2026-06-22), and MIGRATION v0.6 to v0.7 augmented with an incremental-ETL upgrade note.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Bump version to 0.7.0 in both source-of-truth files | a734653 | pyproject.toml, docs/conf.py |
| 2 | Add CHANGELOG [0.7.0] Added section and finalize release date | bccbdb2 | CHANGELOG.md |
| 3 | Add incremental-usage upgrade note to MIGRATION v0.6 to v0.7 | 388594e | MIGRATION.md |

## Verification Results

All acceptance criteria passed:

- `grep '^version = "0.7.0"' pyproject.toml` → exits 0
- `grep "release = '0.7.0'" docs/conf.py` → exits 0
- `grep '"0.6.0"' pyproject.toml` → exits non-zero (no stray version)
- `## [0.7.0] - 2026-06-22` present; no `[0.7.0] - TBD` remains
- `[0.7.0]` block contains both `### Breaking` and `### Added`
- `[0.7.0]` Added block references `docs/etl.md`; no out-of-scope items (initial_watermark, CDC, scheduler, multi-column)
- MIGRATION v0.6 to v0.7 section mentions incremental loading, links to docs/etl.md
- 56-name flat-to-accessor table intact (112 `| \`db.` rows confirmed)
- Footer reference links updated: `[Unreleased]` now compares against `v0.7.0`; `[0.7.0]` link added

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — this plan touches only documentation and metadata files; no new code or network surface introduced.

## Self-Check: PASSED

- pyproject.toml version = "0.7.0": confirmed
- docs/conf.py release = '0.7.0': confirmed
- CHANGELOG.md [0.7.0] - 2026-06-22: confirmed
- MIGRATION.md incremental note present: confirmed
- Commits a734653, bccbdb2, 388594e: all exist in git log
