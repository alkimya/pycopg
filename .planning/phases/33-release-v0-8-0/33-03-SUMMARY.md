---
phase: 33-release-v0-8-0
plan: "03"
subsystem: release
tags: [pypi, oidc, publish, quality-gates, sphinx, coverage, interrogate]

# Dependency graph
requires:
  - phase: 33-01
    provides: version bump (0.8.0 in pyproject.toml + docs/conf.py) + CHANGELOG [0.8.0] Added entry
  - phase: 33-02
    provides: rewritten timescaledb.md, api-reference.md +9 rows, README (15 methods) — all Sphinx-clean

provides:
  - 4 quality gates green (GATES.md): coverage 95.11%, interrogate 100%, Sphinx -W clean, import green
  - 0.8.0 sdist+wheel built and verified (uv lock --check + uv build)
  - Tag v0.8.0 pushed, GitHub Release published, OIDC publish.yml succeeded (run 28044147070)
  - pycopg 0.8.0 live on PyPI (https://pypi.org/project/pycopg/0.8.0/)
  - Clean-venv smoke confirmed: pip install pycopg==0.8.0 + import printed 0.8.0
  - GATES.md + RELEASE-LOG.md artifacts complete

affects: [v0.8.0 milestone close, /gsd-complete-milestone]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "4-gate quality ratchet (pytest/coverage, interrogate, sphinx -W, -W DeprecationWarning) unchanged from v0.7.0 — stable baseline for v0.9.0"
    - "OIDC trusted publish via release:published event — no long-lived API token (T-33-06/07 mitigated)"
    - "human-gated release: executor delivers clean tree + GATES.md; human creates tag+Release; OIDC fires automatically"

key-files:
  created:
    - .planning/phases/33-release-v0-8-0/GATES.md
    - .planning/phases/33-release-v0-8-0/RELEASE-LOG.md
    - .planning/phases/33-release-v0-8-0/33-03-SUMMARY.md
  modified: []

key-decisions:
  - "D-02/D-12/D-13: 4 gates unchanged from v0.7.0 (no new gate added); coverage ≥94, interrogate ≥95, Sphinx -W, -W DeprecationWarning — all measured and recorded in GATES.md"
  - "D-03: release is human-gated (autonomous:false); executor delivers clean tree, human creates tag v0.8.0 + GitHub Release firing OIDC publish.yml; no API token involved"
  - "D-04: uv lock --check + uv build succeed before tagging; all doc/version changes committed; clean tree verified"

patterns-established:
  - "Release gate pattern: 4-gate quality check → build artifacts → human-gated tag → OIDC publish → clean-venv smoke → RELEASE-LOG.md"

requirements-completed: [REL-08]

# Metrics
duration: 45min
completed: 2026-06-23
---

# Phase 33 Plan 03: Release v0.8.0 Gates + Publish Summary

**4 quality gates green (coverage 95.11%, interrogate 100%, Sphinx -W clean, import green), 0.8.0 sdist+wheel built, OIDC publish to PyPI succeeded in 32s via human-gated GitHub Release, clean-venv smoke confirmed `__version__ == 0.8.0`**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-06-23T16:00:00Z
- **Completed:** 2026-06-23T18:00:00Z
- **Tasks:** 3 (Task 1 + Task 2 auto; Task 3 human-gated checkpoint resolved)
- **Files modified:** 2 artifacts (GATES.md, RELEASE-LOG.md)

## Accomplishments

- All 4 quality gates passed at or above baseline: coverage 95.11% (≥94), interrogate 100% (≥95), Sphinx -W clean (0 warnings on 15 pages including rewritten timescaledb.md), DeprecationWarning import guard green
- `uv lock --check` + `uv build` produced `pycopg-0.8.0.tar.gz` and `pycopg-0.8.0-py3-none-any.whl` from the locked, committed release state
- Tag `v0.8.0` (commit `5ce5d0063dd1684425c6075266e10f6f5080ea1c`) pushed by human; GitHub Release published firing OIDC `publish.yml` (run 28044147070, no API token, 32s); PyPI page live; clean-venv smoke printed `0.8.0`

## Task Commits

1. **Task 1: Run 4 quality gates + record GATES.md** - `9c12bd1` (chore)
2. **Task 2: Verify lockfile + build, start RELEASE-LOG.md** - `1e00c1e` (chore)
3. **Task 3: Human-gated checkpoint — STATE/ROADMAP updated at pause** - `a464739` (docs)
4. **Task 3 continuation: Finalize RELEASE-LOG.md with publish outcome** - `3f69514` (docs)

## Files Created/Modified

- `.planning/phases/33-release-v0-8-0/GATES.md` — 4-gate measurement record (commands, exit codes, measured values)
- `.planning/phases/33-release-v0-8-0/RELEASE-LOG.md` — full release trail: build artifacts, release commit SHA, tag, workflow run URL, PyPI URL, smoke outcome

## Decisions Made

- D-02/D-12/D-13: gates held identical to v0.7.0 (no new gate) — clean comparison baseline for future milestones
- D-03: human-gated release honored strictly; executor did not create tag or GitHub Release
- RELEASE-LOG.md structured to capture the full audit trail per T-33-09 (release provenance)

## Deviations from Plan

None — plan executed exactly as written. The human-gated checkpoint was resolved by the human performing all publish steps (tag, GitHub Release, OIDC publish, clean-venv smoke) and signaling "approved".

## Issues Encountered

None. Two pre-existing flaky tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) appeared in the Gate 1 full-suite run as expected; documented in GATES.md as non-regressions.

## User Setup Required

None — release is complete. v0.8.0 is live on PyPI at https://pypi.org/project/pycopg/0.8.0/

## Next Phase Readiness

- v0.8.0 milestone is 100% feature-complete and published; ready for `/gsd-complete-milestone v0.8.0`
- All 11 v0.8.0 requirements (TS-ADV-01..10 + REL-08) are satisfied
- No blockers; 2 named pre-existing flaky tests unchanged since Phase 32

---
*Phase: 33-release-v0-8-0*
*Completed: 2026-06-23*

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| GATES.md exists | FOUND: `.planning/phases/33-release-v0-8-0/GATES.md` |
| RELEASE-LOG.md exists | FOUND: `.planning/phases/33-release-v0-8-0/RELEASE-LOG.md` |
| Commit 9c12bd1 exists | FOUND (Task 1 — GATES.md) |
| Commit 1e00c1e exists | FOUND (Task 2 — RELEASE-LOG.md started) |
| Commit 3f69514 exists | FOUND (Task 3 — RELEASE-LOG.md finalized) |
| Tag v0.8.0 | Confirmed by human (SHA 5ce5d00) |
| PyPI 0.8.0 live | Confirmed by human (HTTP 200) |
| Clean-venv smoke | Confirmed by human (printed 0.8.0) |
