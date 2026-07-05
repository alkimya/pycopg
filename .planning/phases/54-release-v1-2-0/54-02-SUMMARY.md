---
phase: 54-release-v1-2-0
plan: 02
subsystem: release-prep
tags: [changelog, version-bump, release-gates, semver]

# Dependency graph
requires:
  - phase: 54-01
    provides: "DOC-14 + TOOL-01 release hygiene (docs corrections + vulture CI gate) shipped and committed before this version bump"
provides:
  - "pyproject.toml, docs/conf.py, uv.lock all at version 1.2.0 (uv lock --check passes)"
  - "CHANGELOG.md [1.2.0] Added section, code-exact against pycopg/spatial.py + database.py + schema.py, covering Phase 52 (SPAT-F01..F06) + Phase 53 (CRUD-F04..F06, INTRO-F03/F04)"
  - "Compare-link footer updated (Unreleased -> v1.2.0...HEAD, new [1.2.0] -> v1.1.0...v1.2.0)"
  - "All 5 release gates verified green on the release-prep commit"
affects: [54-release-v1-2-0 plan 03 (annotated tag + PyPI publish + smoke)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Front-loaded CHANGELOG code-review (read source signatures directly, not SUMMARY prose) run BEFORE the tag, per the Phase 51 lesson (avoids a post-tag force-push)"

key-files:
  created: []
  modified:
    - pyproject.toml
    - docs/conf.py
    - uv.lock
    - CHANGELOG.md

key-decisions:
  - "Task 2 required zero code changes — the front-loaded code-review cross-checked all 13 documented symbols (6 spatial + 5 CRUD + 2 introspection) against pycopg/spatial.py/database.py/schema.py and found zero signature drift; all 5 gates were already green from Task 1's state, so Task 2 produced no new commit."
  - "length's unit=\"m\" parameter (not explicitly called out in the plan's read_first prose) was read directly from source and included in the CHANGELOG signature — confirming the byte-exact-from-source rule over relying on plan prose."
  - "overlaps/touches/crosses/disjoint share one identical signature (mechanically mirror intersects) — verified by reading all four function definitions in pycopg/spatial.py, not assumed from the disjoint-only read_first line reference."

patterns-established: []

requirements-completed: [REL-13]

# Metrics
duration: ~35min
completed: 2026-07-05
---

# Phase 54 Plan 02: Version Bump + CHANGELOG [1.2.0] + Release Gates Summary

**Bumped pycopg to 1.2.0 across pyproject.toml/docs/conf.py/uv.lock, wrote a code-exact `[1.2.0]` CHANGELOG Added section covering all 13 Phase 52 + Phase 53 symbols (verified byte-for-byte against source, zero drift), updated the compare-link footer, and confirmed all 5 release gates green — one clean commit ready for the 54-03 annotated tag.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-07-05T18:10:00Z (approx.)
- **Completed:** 2026-07-05T18:48:31Z
- **Tasks:** 2/2 completed
- **Files modified:** 4

## Accomplishments

- Version bumped 1.1.0 -> 1.2.0 in `pyproject.toml:7`, `docs/conf.py:17`, and `uv.lock` (via `uv lock`, which resolved cleanly without needing a sandbox bypass — network reachable). `git diff --stat uv.lock` confirms a minimal 1-line diff (pycopg's own self-entry only).
- Added `## [1.2.0] - 2026-07-05` directly under `## [Unreleased]` in CHANGELOG.md, with an intro paragraph mirroring the `[1.1.0]` style and an `### Added` block grouped into **Spatial**, **CRUD**, and **Introspection** subsections, covering all 13 new/changed symbols: `grid_size=` on `union`/`difference`/`intersection`, `length`, `envelope`, `point_on_surface`, `is_valid`/`is_valid_reason`, `overlaps`/`touches`/`crosses`/`disjoint` (Spatial, SPAT-F01..F06); `select_where`/`find`, `get`/`find_one`, `insert` (CRUD, CRUD-F04..F06); `column_exists`, `table_size` (Introspection, INTRO-F03/F04).
- Every signature was read directly from `pycopg/spatial.py`, `pycopg/database.py`, and `pycopg/schema.py` source (not copied from SUMMARY prose) — confirmed `grid_size` (snake_case, not `gridSize`), `length`'s `unit="m"` parameter, and that `overlaps`/`touches`/`crosses`/`disjoint` share one identical signature.
- Compare-link footer updated: `[Unreleased]` now compares `v1.2.0...HEAD`; new line `[1.2.0]: https://github.com/alkimya/pycopg/compare/v1.1.0...v1.2.0` added directly beneath it.
- All 5 release gates verified green (see Gate Results below).
- Front-loaded CHANGELOG code-review performed BEFORE any tag: cross-checked all 13 documented symbols against source signatures — zero drift found, zero `gridSize` matches, footer links correct, date `2026-07-05` correct on both the header and footer entries.

## Task Commits

Each task was committed atomically:

1. **Task 1: Version bump (3 sources) + code-exact [1.2.0] CHANGELOG entry + compare-link footer** - `a491f2b` (chore)
2. **Task 2: Run all 5 release gates green + front-loaded CHANGELOG code-review** - no new commit (verification-only; zero drift found, no fixes required — the code-review confirmed Task 1's commit is already clean and correct)

## Files Created/Modified

- `pyproject.toml` - `version = "1.1.0"` -> `"1.2.0"`
- `docs/conf.py` - `release = '1.1.0'` -> `'1.2.0'`
- `uv.lock` - pycopg self-entry regenerated to `1.2.0` via `uv lock` (1-line diff)
- `CHANGELOG.md` - new `## [1.2.0] - 2026-07-05` section (Added block, 3 grouped subsections, 13 symbols) + updated compare-link footer (2 lines)

## Gate Results (all 5 GREEN)

| # | Gate | Command | Result |
|---|------|---------|--------|
| 1 | Coverage >=95% | `PGDATABASE=pycopg_test3 uv run pytest` | **PASS** — 2406 passed, 2 skipped, **96.83%** coverage (>= 95% floor, baseline 96.83%) |
| 2 | mypy --strict 0 errors | `uv run mypy pycopg/` | **PASS** — "Success: no issues found in 18 source files" |
| 3 | interrogate 100.0% | `uv run interrogate pycopg` | **PASS** — "RESULT: PASSED (minimum: 95.0%, actual: 100.0%)" |
| 4 | Sphinx `-W` clean | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | **PASS** — exit 0, "La compilation a réussi" (build succeeded), 0 warnings |
| 5 | `-W error::DeprecationWarning` | `PGDATABASE=pycopg_test3 uv run pytest -W error::DeprecationWarning` | **PASS** — 2406 passed, 2 skipped, 96.83% coverage, no DeprecationWarning raised as an error |

`git status --short` after all gate runs shows clean (docs/_build/ and htmlcov/ are gitignored) — confirming no unintended files were left modified/untracked.

## Decisions Made

- Task 2 produced no additional commit: the code-review found zero signature drift in Task 1's CHANGELOG entry, and all 5 gates were already green (no fixes were needed, so there was nothing new to stage). This differs from the plan's `<files>` list for Task 2 (`CHANGELOG.md, pyproject.toml, docs/conf.py`) which anticipated possible fixes — none were required.
- `uv lock` resolved successfully without a network-sandbox issue, so no `dangerouslyDisableSandbox` fallback was needed for that step.

## Deviations from Plan

None - plan executed exactly as written. Task 1 produced the version bump + CHANGELOG entry + footer exactly per spec; Task 2's front-loaded code-review found zero drift (no CHANGELOG/signature fixes were needed) and all 5 gates passed on the first run, so no additional commit was required beyond Task 1's `a491f2b`.

## Known Stubs

None - this plan modifies only version metadata and documentation (CHANGELOG.md); no application code, no stub/placeholder data paths.

## Threat Flags

None - no new network endpoints, auth paths, file-access patterns, or schema changes were introduced. The plan's own threat register (T-54-04 CHANGELOG drift, T-54-05 lockfile mismatch, T-54-06 broken footer) is the relevant scope here, and all three are CLOSED per the Gate Results and code-review above: `uv lock --check` passes (T-54-05), the front-loaded review found zero signature drift (T-54-04), and the footer was explicitly verified correct (T-54-06).

## Issues Encountered

None. `uv lock` resolved cleanly on the first attempt (no network/sandbox issue encountered). All 5 gates passed on the first run with no fix-and-rerun cycles needed.

## User Setup Required

None - no external service configuration required. NO tag, publish, or push was performed in this plan (reserved for 54-03).

## Next Phase Readiness

- Version is 1.2.0 in all 3 sources (`pyproject.toml`, `docs/conf.py`, `uv.lock`), `uv lock --check` passes.
- CHANGELOG.md has a code-exact `[1.2.0]` Added section (13 symbols, zero drift verified) and a correct compare-link footer.
- All 5 release gates are green on commit `a491f2b`.
- The release-prep commit is clean and ready for 54-03's annotated tag + PyPI publish + clean-venv smoke test. No tag/publish/push was performed here per this plan's scope boundary.

---
*Phase: 54-release-v1-2-0*
*Plan: 02*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: .planning/phases/54-release-v1-2-0/54-02-SUMMARY.md
- FOUND: commit a491f2b (Task 1: version bump + CHANGELOG)
- FOUND: commit ada569e (Summary doc commit)
- FOUND: pyproject.toml version = "1.2.0"
- FOUND: docs/conf.py release = '1.2.0'
