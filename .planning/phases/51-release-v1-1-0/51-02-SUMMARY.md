---
phase: 51-release-v1-1-0
plan: 02
subsystem: infra
tags: [release, versioning, changelog, uv-lock, coverage, mypy, sphinx, interrogate]

requires:
  - phase: 51-release-v1-1-0
    provides: 51-01 DOC-13 D-03 (api-reference *Error names) — gate #4 prerequisite; WR-01 Fixed entry
provides:
  - version 1.1.0 across pyproject.toml + docs/conf.py + uv.lock (D-01)
  - code-exact CHANGELOG [1.1.0] - 2026-07-04 (Added Phases 48-50 + one Fixed WR-01) (D-06)
  - recorded green run of all 5 release gates (D-08) — REL-12 verification contract satisfied
affects: [51-03, tag-and-publish]

tech-stack:
  added: []
  patterns:
    - "Version bumped in exactly 2 hand-edited sources (pyproject, docs/conf.py); uv.lock regenerated via uv lock; __init__.py resolves version from installed metadata (no hardcode)"

key-files:
  created: []
  modified:
    - pyproject.toml
    - docs/conf.py
    - uv.lock
    - CHANGELOG.md

key-decisions:
  - "Task 3 modified no files — all 5 gates were green on the first run; no gate was weakened and no fail-under threshold lowered."

patterns-established:
  - "5-gate release contract (cov>=95, interrogate 100, Sphinx -W, -W error::DeprecationWarning, mypy --strict) run on the exact HEAD that 51-03 tags."

requirements-completed: [REL-12]

duration: 10min
completed: 2026-07-04
---

# Phase 51 Plan 02: Version bump + CHANGELOG + 5 release gates Summary

**Version bumped to 1.1.0 across pyproject/docs/uv.lock, a code-exact `[1.1.0]` CHANGELOG (Added: Phases 48-50; one Fixed: WR-01), and all five release gates proven green — the REL-12 verification contract for tag/publish.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-04T10:22Z
- **Completed:** 2026-07-04T10:32Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- **D-01** — `pyproject.toml` `version = "1.1.0"`, `docs/conf.py` `release = '1.1.0'`, `uv.lock` regenerated (local pycopg pin `1.0.0` → `1.1.0` only; `uv lock --check` green; zero dependency-pin churn). `pycopg/__init__.py` and `docs/stability.md` untouched (verified).
- **D-06** — CHANGELOG `## [1.1.0] - 2026-07-04` with a fresh `## [Unreleased]` above it. `### Added` documents the Phase 48-50 shipped surface, code-exact (every name verified against a real `pycopg/` definition); exactly one `### Fixed` (WR-01); no `### Changed/Removed/Deprecated`; MIGRATION.md untouched.
- **D-08** — all 5 gates green (recorded below).

## Release gate results (D-08)

| # | Gate | Command | Result |
|---|------|---------|--------|
| 1 | Coverage ≥ 95% | `PGDATABASE=pycopg_test3 uv run pytest` | **96.65%** — 2021 passed, 2 skipped |
| 2 | interrogate 100% | `uv run interrogate pycopg` | **100.0%** (PASSED) |
| 3 | Sphinx `-W` | `uv run sphinx-build -W -b html docs docs/_build/html` | **0 warnings** (build succeeded) |
| 4 | `-W error::DeprecationWarning` | `PGDATABASE=pycopg_test3 uv run pytest -W error::DeprecationWarning` | **clean** (exit 0) |
| 5 | mypy `--strict` | `uv run mypy pycopg` | **0 errors / 18 files** |

## Task Commits

1. **Task 1: Version bump to 1.1.0 (D-01)** - `2510588` (chore)
2. **Task 2: CHANGELOG [1.1.0] code-exact Added + one Fixed (D-06)** - `0bfc306` (docs)
3. **Task 3: Run the 5 release gates (D-08)** - no commit (verification-only; all green first pass)

## Files Created/Modified
- `pyproject.toml` - version 1.1.0 (D-01)
- `docs/conf.py` - release 1.1.0 (D-01)
- `uv.lock` - local pycopg pin 1.1.0 (D-01)
- `CHANGELOG.md` - [1.1.0] Added + one Fixed (D-06)

## Decisions Made
- No files changed in Task 3 — gates passed on the first run, so no code/doc fix or threshold change was needed. The `error::DeprecationWarning` gate passes precisely because 51-01 D-03 removed the deprecated aliases from the docs import example.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None. (One transient operator error while running gate 4 — an added `-p no:cov` conflicted with the `--cov` addopts; re-ran the plan's exact command and it passed. No product change.)

## User Setup Required
None in this plan. (51-03 has the human-gated GitHub Release publish.)

## Next Phase Readiness
- The exact HEAD carrying the version bump + `[1.1.0]` CHANGELOG has all 5 gates green — safe to tag.
- 51-03 can proceed: create + push annotated tag `v1.1.0`, then STOP at the human gate for the GitHub Release → OIDC publish, then clean-venv smoke.

---
*Phase: 51-release-v1-1-0*
*Completed: 2026-07-04*
