---
phase: 51-release-v1-1-0
plan: 03
subsystem: infra
tags: [release, pypi, oidc, git-tag, trusted-publishing, smoke-test]

requires:
  - phase: 51-release-v1-1-0
    provides: 51-02 version bump + [1.1.0] CHANGELOG + 5 green gates (the tagged release commit)
provides:
  - annotated git tag v1.1.0 on release commit 6e47cf7, pushed to origin
  - published PyPI distribution pycopg 1.1.0 (human-gated GitHub Release -> OIDC publish.yml)
  - green clean-venv smoke (pip install pycopg==1.1.0; __version__ + Page/TableDescription/paginate_keyset)
affects: [v1.1.0-milestone-close]

tech-stack:
  added: []
  patterns:
    - "Phase 47 release mechanism reused: annotated tag -> human-published GitHub Release -> publish.yml OIDC trusted publishing (uv build, no tests) -> clean-venv smoke"

key-files:
  created: []
  modified: []

key-decisions:
  - "Publish is human-gated (D-07): executor created + pushed the tag but STOPPED at the GitHub Release checkpoint; the user published, triggering OIDC publish.yml. Executor never published autonomously."
  - "Code review (phase gate) was front-loaded BEFORE tagging so the tag reflects reviewed code; its one WARNING (missing CHANGELOG [1.1.0] compare-link footer) was fixed in 6e47cf7 before the tag was cut — no force-push needed."

patterns-established:
  - "Front-load the code-review gate before an irreversible tag/publish so any fix lands in the tagged commit."

requirements-completed: [REL-12]

duration: 20min
completed: 2026-07-04
---

# Phase 51 Plan 03: Ship v1.1.0 Summary

**pycopg v1.1.0 shipped to PyPI: annotated tag `v1.1.0` on `6e47cf7` pushed to origin, user-published GitHub Release triggered OIDC trusted publishing, and a clean-venv smoke confirms the published wheel reports `__version__ == "1.1.0"` and exposes the Phase 48-50 surface.**

## Performance

- **Duration:** ~20 min (incl. human publish gate)
- **Tasks:** 3
- **Files modified:** 0 repo files (tag + PyPI publish + throwaway venv)

## Accomplishments
- **Task 1 (D-07)** — annotated tag `v1.1.0` (tag object `ca354b4`) created on release commit `6e47cf7` and pushed to `origin` (`alkimya/pycopg`). Verified: `cat-file -t` = `tag`, `v1.1.0^{commit}` == HEAD, `refs/tags/v1.1.0` present on remote. No pre-existing tag collision.
- **Task 2 (D-07, human-action gate)** — STOPPED at the checkpoint; the user drafted the GitHub Release from tag `v1.1.0` and published it, firing `release: published` → `publish.yml` OIDC trusted publishing (`uv lock --check` + `uv build`, no tests, no secrets). The executor did not publish autonomously.
- **Task 3 (D-07)** — clean-venv smoke: fresh venv, `pip install --no-cache-dir pycopg==1.1.0` from the real PyPI index (installed with all deps), then asserted `pycopg.__version__ == "1.1.0"`, `from pycopg import Page, TableDescription`, and `hasattr(pycopg.Database, "paginate_keyset")`. Printed `smoke ok 1.1.0`.

## Task Commits

1. **Task 1: Create + push annotated tag v1.1.0 (D-07)** - tag `v1.1.0` → `6e47cf7` (no source commit)
2. **Task 2: Human gate — GitHub Release → OIDC publish (D-07)** - published by user (no repo commit)
3. **Task 3: Clean-venv smoke (D-07)** - verification-only (no commit)

_(The tagged release commit `6e47cf7` also carries the code-review WARNING fix landed during the pre-tag review gate.)_

## Files Created/Modified
None in the repo. Produced: git tag `v1.1.0`, PyPI distribution `pycopg 1.1.0`, and a throwaway smoke venv under the scratch dir.

## Decisions Made
- Human-gated publish honored (D-07): tag pushed autonomously; Release + publish left entirely to the user.
- Code review front-loaded before the tag; its WARNING (CHANGELOG compare-link footer) fixed in the tagged commit.

## Deviations from Plan
None - plan executed exactly as written. (The smoke install ran with the sandbox's network egress enabled for the plan-authorized PyPI install into a throwaway venv; no retry loop was needed since the release was already visible on PyPI.)

## Issues Encountered
None. Install + smoke passed first try after the release was confirmed live.

## User Setup Required
The GitHub Release publish (Task 2) was the human-gated step — completed by the user.

## Next Phase Readiness
- **v1.1.0 is live on PyPI** — REL-12 satisfied and the v1.1.0 milestone is shipped.
- Ready for phase verification + milestone close (`/gsd-complete-milestone`).
- Note: local `main` branch commits are not yet pushed to origin (branching strategy `none`); only the tag is on the remote. Push `main` when convenient.

---
*Phase: 51-release-v1-1-0*
*Completed: 2026-07-04*
