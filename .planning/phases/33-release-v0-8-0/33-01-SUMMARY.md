---
phase: 33-release-v0-8-0
plan: "01"
subsystem: release
tags: [version-bump, changelog, lockfile]
dependency_graph:
  requires: []
  provides: [version-0.8.0-sources, changelog-0.8.0-entry, lockfile-current]
  affects: [pyproject.toml, docs/conf.py, CHANGELOG.md, uv.lock]
tech_stack:
  added: []
  patterns: [keep-a-changelog, semantic-versioning, uv-lock-regen]
key_files:
  created: []
  modified:
    - pyproject.toml
    - docs/conf.py
    - CHANGELOG.md
    - uv.lock
decisions:
  - "D-01: version 0.8.0 set in pyproject.toml (line 7) and docs/conf.py (line 17) — the only two canonical sources"
  - "D-04: uv.lock regenerated after version bump (pycopg 0.7.0 → 0.8.0 recorded in lockfile)"
  - "D-08: CHANGELOG [0.8.0] section is Added-only — no ### Breaking (purely additive release)"
  - "D-09: Added grouped into three families: chunk+dimension (4), cagg lifecycle (3), query helpers (2)"
  - "D-10: scope-fence grep over [0.8.0] section: zero banned deferred-capability keywords"
  - "D-11: MIGRATION.md not edited — v0.8.0 has zero breaking changes"
metrics:
  duration: "2m 1s"
  completed_date: "2026-06-23"
  tasks_completed: 3
  files_modified: 4
---

# Phase 33 Plan 01: Version Bump & CHANGELOG Summary

**One-liner:** Version bumped to 0.8.0 in both canonical sources; CHANGELOG [0.8.0] Added-only entry written covering 9 new TimescaleDB methods grouped by the three feature families; lockfile regenerated.

## What Was Done

### Task 1 — Bump version to 0.8.0 in both canonical sources (D-01)
- `pyproject.toml` line 7: `version = "0.7.0"` → `version = "0.8.0"`
- `docs/conf.py` line 17: `release = '0.7.0'` → `release = '0.8.0'`
- No other version-shaped strings altered (`target-version = "py311"` and `python_version = "3.11"` left unchanged)
- Commit: `330c43c`

### Task 2 — Write CHANGELOG [0.8.0] Added-only, family-grouped entry (D-08, D-09)
- New `## [0.8.0] - 2026-06-23` section inserted between `## [Unreleased]` and `## [0.7.0]`
- Single `### Added` subsection — no `### Breaking`, `### Changed`, `### Deprecated`, or `### Removed`
- Three family groups per D-09:
  - **Chunk & dimension management**: `show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy`
  - **Continuous aggregate lifecycle**: `create_continuous_aggregate`, `refresh_continuous_aggregate`, `add_continuous_aggregate_policy`
  - **Query helpers**: `time_bucket`, `time_bucket_gapfill`
- Parity statement: all 9 methods on `AsyncTimescaleAccessor` too; zero new runtime dependencies
- Updated `[Unreleased]` comparison link to `v0.8.0...HEAD`; added `[0.8.0]` link `v0.7.0...v0.8.0`
- `MIGRATION.md` untouched (D-11)
- Commit: `d19f090`

### Task 3 — Scope-fence grep + lockfile verification (D-10, D-04)
- D-10 scope-fence grep over extracted `[0.8.0]` section: ZERO matches for all banned keywords
  (`initial_watermark`, CDC, WAL, `drop_continuous_aggregate`, `remove_continuous_aggregate_policy`,
  `compress_chunk`, `decompress_chunk`, `origin`, `created_before`, `created_after`)
- `uv lock --check` detected drift after pyproject.toml version bump → ran `uv lock` to regenerate
  (`pycopg v0.7.0 → v0.8.0` recorded in uv.lock); post-regen `uv lock --check` passes
- Commit: `0f48ea8`

## Commits

| Task | Commit | Message |
|------|--------|---------|
| Task 1 | `330c43c` | `chore(33-01): bump version to 0.8.0 in both canonical sources` |
| Task 2 | `d19f090` | `docs(33-01): write CHANGELOG [0.8.0] Added-only, family-grouped entry` |
| Task 3 | `0f48ea8` | `chore(33-01): regenerate uv.lock after version bump to 0.8.0` |

## Verification Results

| Check | Status |
|-------|--------|
| `grep -c 'version = "0.8.0"' pyproject.toml` = 1 | PASS |
| `grep -c 'version = "0.7.0"' pyproject.toml` = 0 | PASS |
| `grep -c "release = '0.8.0'" docs/conf.py` = 1 | PASS |
| `grep -c "release = '0.7.0'" docs/conf.py` = 0 | PASS |
| `grep -c 'target-version = "py311"' pyproject.toml` = 1 (unchanged) | PASS |
| CHANGELOG has `## [0.8.0]` section | PASS |
| `[0.8.0]` section has `### Added` | PASS |
| `[0.8.0]` section has no `### Breaking` | PASS |
| All 9 method names present in `[0.8.0]` section | PASS |
| Three family labels present in `[0.8.0]` section | PASS |
| D-10 scope-fence: zero banned keywords | PASS |
| `MIGRATION.md` unchanged | PASS |
| `uv lock --check` passes | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] uv.lock regeneration required after version bump**
- **Found during:** Task 3
- **Issue:** `uv lock --check` detected lockfile drift after pyproject.toml version bump (D-04 explicitly states: if out of date, run `uv lock` and include uv.lock in changes)
- **Fix:** Ran `uv lock` which updated the single `pycopg` entry from `0.7.0` to `0.8.0` (43 packages, zero new dependencies)
- **Files modified:** `uv.lock`
- **Commit:** `0f48ea8`

This is expected and anticipated by D-04 — not a true deviation but a planned consequence of the version bump.

## Known Stubs

None — this is a release-only plan with no UI components or data-rendering code.

## Threat Flags

None — no new code paths, network endpoints, or user input handling introduced. The trust boundary check (T-33-01) was validated by the D-10 scope-fence grep: zero deferred-capability keywords in the CHANGELOG [0.8.0] section.

## Self-Check: PASSED

- `pyproject.toml` exists and contains `version = "0.8.0"`: FOUND
- `docs/conf.py` exists and contains `release = '0.8.0'`: FOUND
- `CHANGELOG.md` exists and contains `## [0.8.0]`: FOUND
- `uv.lock` exists and `uv lock --check` passes: FOUND
- Commits 330c43c, d19f090, 0f48ea8 present in git log: FOUND
