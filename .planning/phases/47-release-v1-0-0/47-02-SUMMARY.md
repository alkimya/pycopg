---
phase: 47-release-v1-0-0
plan: 02
subsystem: release
tags: [version-bump, changelog, migration, release-v1.0.0]

# Dependency graph
requires:
  - phase: 47-release-v1-0-0
    plan: 01
    provides: docs/docstring debt closed (InvalidIdentifierError typos, where=/filter= audit, as_text PostGIS 3.1 note) -- CHANGELOG/MIGRATION content in this plan builds on that corrected state
  - phase: 41-api-homogenization
    provides: filter= rename, 4 *Error exception renames, kw-only enforcement -- the 3 of 4 breaking changes documented in this plan
  - phase: 42-spatial-v2-processing-helpers
    provides: union/difference/intersection/simplify/convex_hull/make_valid signatures cited code-exact in CHANGELOG
  - phase: 43-spatial-v2-spatial-aggregates
    provides: collect_geometries/union_aggregate/extent signatures cited code-exact in CHANGELOG
  - phase: 44-spatial-v2-serialization-mvt
    provides: as_geojson/as_text/as_mvt signatures cited code-exact in CHANGELOG
  - phase: 45-api-completeness-gaps-structured-logging
    provides: TXN-01/02 transaction+session+savepoint, PARAM-01 Params widening, HEALTH-01 health(), LOG-01 pycopg/logging.py -- all cited code-exact in CHANGELOG
  - phase: 46-mypy-strict-py-typed-gate
    provides: complete py.typed + mypy --strict 0 errors, CI mypy step now blocking -- cited in CHANGELOG Added/Changed and MIGRATION type-checking note
provides:
  - "Version 1.0.0 across pyproject.toml (canonical) / docs/conf.py (Sphinx release) / uv.lock (regenerated); pycopg/__init__.py untouched (stays dynamic)"
  - "CHANGELOG.md ## [1.0.0] - 2026-07-02 section: Added (12 spatial v2 methods + TXN-01/02 + PARAM-01 + HEALTH-01 + LOG-01 + py.typed) / Changed-Breaking (5 items) / Deprecated (where= shims + 4 exception aliases) + compare-link footer"
  - "MIGRATION.md v0.10.x -> 1.0.0 section final-reviewed (confirmed accurate, no rewrite) + new item 5 (mypy-strict-blocking, symmetry with CHANGELOG) + type-checking consumer note"
affects: [47-03-release-v1-0-0]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - pyproject.toml
    - docs/conf.py
    - uv.lock
    - CHANGELOG.md
    - MIGRATION.md

key-decisions:
  - "D-36-03 signature-drift guard applied literally: every method signature written into the CHANGELOG Added section was copied from the live def in pycopg/spatial.py / pycopg/database.py / pycopg/logging.py -- not paraphrased from SUMMARY prose. Verified via direct Read of each implementation (not the @overload stub triplets)."
  - "MIGRATION.md breaking-change symmetry: CHANGELOG lists mypy--strict-now-blocking-in-CI as a 5th Changed/Breaking item (a CI policy change, not a runtime API break). To satisfy the plan's explicit no-asymmetry acceptance criterion, added a short item 5 to MIGRATION.md noting it is not a runtime break, rather than omitting it or downgrading the CHANGELOG entry."
  - "MIGRATION.md edit was purely additive (19 insertions, 0 deletions) -- confirmed via git diff --stat before committing, honoring the plan's do-NOT-rewrite-existing-sections constraint."

patterns-established: []

requirements-completed: [REL-11]

# Metrics
duration: 15min
completed: 2026-07-02
---

# Phase 47 Plan 02: Version 1.0.0 + CHANGELOG + MIGRATION Final Review Summary

**Bumped pycopg to 1.0.0 across pyproject.toml/docs/conf.py/uv.lock (dynamic `__init__.py` untouched), assembled a code-exact CHANGELOG `[1.0.0]` section covering the entire Phases 41-46 milestone, and final-reviewed MIGRATION.md confirming all 4 documented breaking changes match live code plus a new type-checking consumer note.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-02T14:07:00Z
- **Completed:** 2026-07-02T14:12:53Z
- **Tasks:** 3 completed
- **Files modified:** 5 (pyproject.toml, docs/conf.py, uv.lock, CHANGELOG.md, MIGRATION.md)

## Accomplishments

- **Task 1 (D-36-01 version bump):** Set `version = "1.0.0"` in `pyproject.toml` (canonical) and `release = '1.0.0'` in `docs/conf.py`, then regenerated `uv.lock` via `uv lock` (never hand-edited). `pycopg/__init__.py` is unchanged — `__version__` resolves dynamically via `importlib.metadata.version`. Verified live: `PGDATABASE=pycopg_test3 uv run python -c "import pycopg; assert pycopg.__version__ == '1.0.0'"` succeeds.
- **Task 2 (D-47-01 CHANGELOG assembly):** Wrote `## [1.0.0] - 2026-07-02` above `[0.10.1]` with `### Added` (all 12 new `db.spatial.*` methods with full code-exact signatures, TXN-01/02, PARAM-01, HEALTH-01, LOG-01, complete `py.typed`), `### Changed` (5 breaking items: spatial `filter=`, 4 exception renames, kw-only enforcement, timescale `filter=`, mypy-strict-now-blocking), and `### Deprecated` (the `where=` shims + 4 exception aliases, removal in 2.0). Added the compare-link footer `[1.0.0]: .../compare/v0.10.1...v1.0.0` and repointed `[Unreleased]` to `.../compare/v1.0.0...HEAD`.
- **Task 3 (D-47-02 MIGRATION final review):** Confirmed every before/after rename in the existing `v0.10.x -> 1.0.0` section matches live code (4 `*Error` classes + aliases in `pycopg/exceptions.py`, `filter=` in `pycopg/spatial.py` and `pycopg/timescale.py`, kw-only carve-out list in `pycopg/database.py`/`async_database.py`) — zero drift found, zero rewrites needed. Added a new item 5 (mypy-strict-now-blocking, non-runtime) for CHANGELOG-breaking-set symmetry, plus a short "type-checking consumers" note (py.typed / mypy --strict, no `ignore_missing_imports` needed) and one matching checklist line.

## Task Commits

Each task was committed atomically:

1. **Task 1: Bump version to 1.0.0 across the 3 sources + refresh uv.lock** - `9770342` (chore)
2. **Task 2: Assemble CHANGELOG [1.0.0] from the 6 per-phase SUMMARY sets with code-exact signatures** - `ea8baff` (docs)
3. **Task 3: Final-review MIGRATION.md + add type-checking note** - `0224275` (docs)

**Plan metadata:** (this commit)

## Files Created/Modified

- `pyproject.toml` — `version = "1.0.0"` (line 7, canonical source)
- `docs/conf.py` — `release = '1.0.0'` (line 17, Sphinx)
- `uv.lock` — regenerated via `uv lock`; `pycopg` entry now `version = "1.0.0"`
- `CHANGELOG.md` — new `## [1.0.0] - 2026-07-02` section (Added/Changed/Deprecated) + compare-link footer (`[1.0.0]` and repointed `[Unreleased]`)
- `MIGRATION.md` — confirmed-accurate `v0.10.x -> 1.0.0` section, new item 5 (mypy-strict-blocking), and a new "type-checking consumers" note + checklist line (purely additive, 19 insertions / 0 deletions)

## Decisions Made

- Applied the D-36-03 signature-drift guard literally: read the actual `def` (not the `@overload` stub triplets) for every one of the 12 new spatial v2 methods plus `transaction`/`session`/`savepoint`/`health`/`get_logger`/`log_operation` directly from `pycopg/spatial.py`, `pycopg/database.py`, and `pycopg/logging.py` before writing each CHANGELOG entry.
- Resolved a symmetry question between the plan's own two acceptance criteria: the CHANGELOG Changed/Breaking section explicitly required listing "mypy-strict now blocking in CI" (per D-47-01 and the 47-CONTEXT.md decision text), but MIGRATION.md's existing 4-item breaking-change list didn't cover it. Rather than dropping the 5th CHANGELOG item (contradicts the plan's own required content) or fabricating a false runtime-breaking claim in MIGRATION.md, added a clearly-labeled 5th item to MIGRATION.md stating it is a CI-only, non-runtime change — achieving exact 1:1 correspondence between the two documents' breaking-change sets without misleading readers.
- Verified the MIGRATION.md diff was purely additive (`git diff --stat` showed 19 insertions, 0 deletions) before committing, confirming no existing section was rewritten per the plan's explicit constraint.

## Deviations from Plan

None — plan executed exactly as written. The MIGRATION.md item-5 addition was anticipated by the plan itself (Task 3 acceptance criteria explicitly require breaking-set symmetry with CHANGELOG), not an unplanned deviation.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Version is 1.0.0 across all 3 sources, `uv lock --check` is current, and `pycopg.__version__` resolves dynamically and correctly.
- CHANGELOG `[1.0.0]` is complete, code-exact, and has a correct compare-link footer.
- MIGRATION.md is confirmed accurate against live code and against the CHANGELOG breaking set, with a type-checking note added.
- Ready for Plan 47-03: the 5 release gates (coverage/interrogate/Sphinx/DeprecationWarning/mypy), tag `v1.0.0`, human-gated OIDC publish, and clean-venv smoke.
- No blockers.

---
*Phase: 47-release-v1-0-0*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: pyproject.toml, docs/conf.py, uv.lock, CHANGELOG.md, MIGRATION.md
- FOUND: .planning/phases/47-release-v1-0-0/47-02-SUMMARY.md
- FOUND: commit 9770342 (Task 1)
- FOUND: commit ea8baff (Task 2)
- FOUND: commit 0224275 (Task 3)
