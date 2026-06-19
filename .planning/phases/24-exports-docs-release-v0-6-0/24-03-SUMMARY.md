---
phase: 24-exports-docs-release-v0-6-0
plan: "03"
subsystem: release
tags: [pypi, github-release, oidc, semver, smoke-test, pycopg]

requires:
  - phase: 24-01
    provides: accessor documentation pages rewritten (docs/*.md + api-autodoc.md + README)
  - phase: 24-02
    provides: CHANGELOG [0.6.0] entry authored, MIGRATION v0.5→v0.6 section, exports verified
  - plan: 24-03-task1
    provides: version bumped to 0.6.0 in pyproject.toml + docs/conf.py, uv.lock refreshed, three gates green, dist artifacts built (7545b74)

provides:
  - git tag v0.6.0 created and pushed to origin
  - origin/main updated (54+ commits pushed)
  - GitHub Release v0.6.0 (https://github.com/alkimya/pycopg/releases/tag/v0.6.0)
  - pycopg 0.6.0 published to PyPI via OIDC publish.yml (completed success)
  - Clean-venv smoke test passed (pip install + import + accessor repr)
  - REORG-05 criterion #4 fully confirmed

affects: [v0.7.0-planning, v0.6.0-milestone-complete]

tech-stack:
  added: []
  patterns:
    - "OIDC trusted publishing via pypa/gh-action-pypi-publish (no long-lived token)"
    - "gh release create triggers publish.yml — mirrors v0.5.0 (Phase 20) playbook"
    - "Manual clean-venv smoke test (D-06) as post-publish release criterion"

key-files:
  created: []
  modified:
    - pyproject.toml  # version = 0.6.0
    - docs/conf.py    # release = '0.6.0'
    - uv.lock         # refreshed to pin pycopg 0.6.0

key-decisions:
  - "D-06 honoured: publish is irreversible on PyPI — required explicit human approval before gh release create"
  - "Smoke test run against local postgres/postgres on pycopg_test — import + accessor repr confirmed, connection succeeded"
  - "RTD expected to auto-rebuild from the v0.6.0 tag (consistent with v0.5.0 behaviour)"

requirements-completed: [REORG-05]

duration: 15min
completed: 2026-06-19
---

# Phase 24 Plan 03: Release v0.6.0 Summary

**pycopg 0.6.0 published to PyPI via GitHub OIDC publish.yml; git tag v0.6.0 + GitHub Release created; clean-venv `pip install pycopg==0.6.0` + `db.timescale` accessor smoke confirmed — REORG-05 criterion #4 satisfied**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-19T11:54Z (continuation from Task 1 commit 7545b74)
- **Completed:** 2026-06-19T12:15Z
- **Tasks:** 3 total (Task 1 done by prior executor; Tasks 2-3 done this run)
- **Files modified:** 0 new (all release files committed in Task 1 / prior waves)

## Accomplishments

- git tag `v0.6.0` created and pushed to `origin`
- `git push origin main` succeeded — origin/main brought up to date (54+ commits ahead)
- GitHub Release `v0.6.0 — Accessor reorganization` created at https://github.com/alkimya/pycopg/releases/tag/v0.6.0
- `publish.yml` OIDC workflow ran and completed with `success` (run ID 27824372705, 34s)
- PyPI confirmed: `pycopg 0.6.0` is the latest version (curl pypi.org/pypi/pycopg/json verified)
- Clean-venv smoke: `pip install pycopg==0.6.0` installed successfully; `/tmp/smoke-0.6.0/bin/python -c "from pycopg import Database; db = Database.from_env(); print(db.timescale)"` printed `<pycopg.timescale.TimescaleAccessor object at 0x7ff617e6aab0>` — import and accessor accessor resolved cleanly, DB connection succeeded
- RTD expected to auto-rebuild from v0.6.0 tag (same as v0.5.0; no manual trigger needed)

## Task Commits

Tasks 1 was committed by the prior executor. Tasks 2-3 were release/publish actions (no new code commits — the release sequence produces git tag + GitHub Release, not source commits):

1. **Task 1: Bump version to 0.6.0, refresh lockfile, run gates + build** - `7545b74` (chore)
2. **Task 2: Tag, push, GitHub Release, OIDC publish** - git tag `v0.6.0` + `origin/main` push + GitHub Release (no source commit — release actions)
3. **Task 3: Clean-venv smoke test** - manual verification (no source commit — throwaway venv)

**Plan metadata:** (see state update commit below)

## Files Created/Modified

No new files created or modified in Tasks 2-3. All version/doc/changelog files were committed in Task 1 (7545b74) and prior waves (24-01, 24-02).

**Release artifacts:**
- `dist/pycopg-0.6.0-py3-none-any.whl` — published to PyPI
- `dist/pycopg-0.6.0.tar.gz` — published to PyPI (sdist)

## Release Sequence Steps

| Step | Result |
|------|--------|
| `git tag v0.6.0` | Tag created locally |
| `git push origin main` | 54+ commits pushed; origin/main at 7545b74 |
| `git push origin v0.6.0` | New tag pushed to origin |
| `gh release create v0.6.0` | Release created: https://github.com/alkimya/pycopg/releases/tag/v0.6.0 |
| `publish.yml` OIDC run | Completed: `success` (run 27824372705, 34s) |
| PyPI confirmation | `pycopg 0.6.0` is latest version on PyPI |
| Clean-venv install | `pip install pycopg==0.6.0` succeeded |
| Accessor smoke | `print(db.timescale)` -> `<TimescaleAccessor object>` |
| Venv cleanup | `/tmp/smoke-0.6.0` removed |

## Decisions Made

- D-06 respected: publish was not automated — waited for explicit human "approved" before executing the release sequence.
- Smoke test DB: used local postgres/postgres on pycopg_test (per project memory); `from_env()` read connection from env vars; connection succeeded (full accessor resolution, not just import).
- RTD: expected to auto-rebuild from the pushed v0.6.0 tag — no manual trigger required (same behaviour as v0.5.0, Phase 20).

## Deviations from Plan

None — plan executed exactly as written. The release sequence followed the PATTERNS "Release Sequence" verbatim. The smoke test matched the task3 spec. The publish.yml completed in a single run without retries.

## Issues Encountered

None. All steps succeeded on first attempt:
- `git push origin main` accepted without conflict (no force-push needed)
- `publish.yml` completed in 34s (consistent with prior releases: v0.5.0=43s, v0.4.0=41s)
- PyPI CDN propagation was immediate — no retry needed for `pip install pycopg==0.6.0`
- DB connection for smoke test succeeded (postgres/postgres on pycopg_test reachable)

## Pre-existing Flaky Tests (not related to this plan)

Two named pre-existing flaky DB tests remain (documented in STATE.md):
- `test_async_transaction_fix`
- `test_create_spatial_index_name_parameter`

These are fixture-isolation bugs predating v0.6.0, confirmed unrelated to this plan's scope.

## Known Stubs

None — this is a release plan. No stub content shipped.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The publish boundary (local → PyPI) was the intended security surface, mitigated by:
- T-24-06: Blocking human-verify checkpoint honoured (D-06)
- T-24-07: Wheel inspection done by prior executor (confirmed secret-free)
- T-24-08: Both version sources confirmed 0.6.0 before publish
- T-24-SC: OIDC trusted publishing — no long-lived token

## Next Phase Readiness

v0.6.0 milestone is COMPLETE. The v0.6.0 accessor reorganization is fully shipped:
- All 5 accessor namespaces (timescale/admin/maint/backup/schema) + spatial relocation
- 56 deprecated flat names with DeprecationWarning (removal scheduled v0.7.0)
- Full sync/async parity
- Documentation, CHANGELOG, MIGRATION guide, and PyPI release

Next milestone: `/gsd-complete-milestone v0.6.0` to close out the milestone tracking, then plan v0.7.0 (flat-name removal + any open WR carry-forwards).

---
*Phase: 24-exports-docs-release-v0-6-0*
*Completed: 2026-06-19*

## Self-Check: PASSED

- git tag v0.6.0: FOUND (`git tag --list v0.6.0` returns v0.6.0)
- GitHub Release: FOUND (https://github.com/alkimya/pycopg/releases/tag/v0.6.0)
- PyPI pycopg 0.6.0: FOUND (curl pypi.org/pypi/pycopg/json confirms latest=0.6.0)
- Smoke test: PASSED (`db.timescale` accessor repr printed in clean venv)
- Task 1 commit 7545b74: FOUND (git log confirms)
