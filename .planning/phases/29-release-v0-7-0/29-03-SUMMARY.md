---
phase: 29-release-v0-7-0
plan: "03"
subsystem: release
tags: [pypi, oidc, publish, release, smoke-test, github-actions]

# Dependency graph
requires:
  - phase: 29-release-v0-7-0-plan-01
    provides: version 0.7.0 bump in pyproject.toml + docs/conf.py, CHANGELOG [0.7.0], MIGRATION incremental-ETL note
  - phase: 29-release-v0-7-0-plan-02
    provides: all 4 quality gates green (coverage 95.11%, interrogate 100%, Sphinx -W clean, DeprecationWarning exit 0)
provides:
  - git tag v0.7.0 pushed to origin
  - GitHub Release v0.7.0 published (https://github.com/alkimya/pycopg/releases/tag/v0.7.0)
  - OIDC publish workflow succeeded (run 27953179349)
  - pycopg 0.7.0 live on PyPI (https://pypi.org/project/pycopg/0.7.0/)
  - clean-venv pip install pycopg==0.7.0 smoke passed
  - 29-03-RELEASE-LOG.md recording all release artifacts
affects: [v0.7.0-milestone-close, future-release-phases]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "OIDC trusted publishing via GitHub Release published event -> publish.yml"
    - "Clean-venv smoke test as final acceptance gate for each release"

key-files:
  created:
    - .planning/phases/29-release-v0-7-0/29-03-RELEASE-LOG.md
  modified: []

key-decisions:
  - "REL-07 satisfied: v0.7.0 tagged, published to PyPI via OIDC, clean-venv import confirmed"
  - "No reset API for watermarks (D-A5 honored) — manual SQL only; initial_watermark deferred v0.8.0"

patterns-established:
  - "Release pattern: lock-check + build + tag + GitHub Release + OIDC publish + clean-venv smoke"

requirements-completed: [REL-07]

# Metrics
duration: ~15min (human-gated tasks)
completed: 2026-06-22
---

# Phase 29 Plan 03: Release v0.7.0 Summary

**pycopg 0.7.0 tagged, published to PyPI via OIDC trusted publishing, and verified via clean-venv pip install — REL-07 and Success Criterion 1 satisfied**

## Performance

- **Duration:** ~15 min (includes human-gated tag/publish + smoke steps)
- **Started:** 2026-06-22T12:28:16Z
- **Completed:** 2026-06-22T12:44:34Z
- **Tasks:** 3 of 3
- **Files modified:** 1 (29-03-RELEASE-LOG.md)

## Accomplishments

- Local build mirrored CI: `uv lock --check` PASS, `uv build` produced `pycopg-0.7.0.tar.gz` + `pycopg-0.7.0-py3-none-any.whl`
- Git tag `v0.7.0` created and pushed; GitHub Release published at https://github.com/alkimya/pycopg/releases/tag/v0.7.0 (2026-06-22T12:37:43Z)
- OIDC publish workflow (run 27953179349) completed with conclusion: success — both wheel and sdist live on PyPI
- Clean-venv smoke: `pip install pycopg==0.7.0` from live PyPI succeeded; `import pycopg; print(pycopg.__version__)` => `0.7.0`, exit 0

## Task Commits

1. **Task 1: Commit release artifacts and verify build locally** - `0217c7d` (chore)
2. **Task 2: Tag v0.7.0 and publish GitHub Release** - human action (no code commit)
3. **Task 3: Clean-venv smoke test** - human verify (no code commit)

**Plan metadata:** (this summary commit)

## Files Created/Modified

- `.planning/phases/29-release-v0-7-0/29-03-RELEASE-LOG.md` - Full release log: local build results, tag, GitHub Release URL, workflow run URL, PyPI URL, smoke install output

## Decisions Made

- REL-07 satisfied in full: version 0.7.0 in both sources (Plan 01), tagged `v0.7.0`, published to PyPI via OIDC GitHub Actions (no API token), clean-venv import confirmed version 0.7.0.
- Publishing via GitHub Release `published` event trigger — no manual token management needed.

## Deviations from Plan

None - plan executed exactly as written. All three tasks (auto + human-action + human-verify) completed in the intended sequence.

## Issues Encountered

None. All gates passed on first attempt: `uv lock --check` exit 0, `uv build` clean, OIDC workflow success, smoke test exit 0.

## User Setup Required

None - no external service configuration required beyond the GitHub Release already created.

## Next Phase Readiness

- Phase 29 complete — all 3 plans done, all 3 waves done.
- v0.7.0 milestone (Alias Removal + Incremental ETL) fully shipped: 5 phases, 13 plans, 17 requirements.
- pycopg 0.7.0 is live on PyPI and verified importable.
- Next action: `/gsd-complete-milestone v0.7.0` to audit, close, and archive the milestone.

---
*Phase: 29-release-v0-7-0*
*Completed: 2026-06-22*
