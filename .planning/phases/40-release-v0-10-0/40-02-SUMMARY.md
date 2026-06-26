---
phase: 40-release-v0-10-0
plan: "02"
subsystem: release
tags: [release, pypi, oidc, git-tag, smoke-test, publish]

requires:
  - phase: 40-release-v0-10-0
    plan: "01"
    provides: "Version 0.10.0 bumped in all 3 sources, [0.10.0] CHANGELOG entry, all 4 gates green"

provides:
  - "Annotated git tag v0.10.0 on release commit ab1bac6"
  - "pycopg 0.10.0 wheel + sdist published to PyPI via OIDC trusted-publishing (human-gated)"
  - "GitHub Release v0.10.0 published (not draft) triggering publish.yml workflow"
  - "Clean-venv smoke confirmed: pycopg==0.10.0 installed from PyPI, __version__ == '0.10.0'"

affects: [v0.10.0-milestone-close, v1.0.0-planning]

tech-stack:
  added: []
  patterns:
    - "Human-gated OIDC publish: GitHub Release published event triggers publish.yml (no long-lived tokens)"
    - "Clean-venv smoke outside project tree: install pinned version from PyPI, assert __version__ to confirm end-to-end version agreement"

key-files:
  created: []
  modified: []

key-decisions:
  - "T-40-02-01 honored: publish is never auto-advanced — human-gated via gate='blocking-human', GitHub Release trigger"
  - "T-40-02-02 honored: OIDC trusted publishing (id-token: write, pypi environment) — no long-lived credentials"
  - "T-40-02-03 honored: clean-venv smoke asserts __version__ == '0.10.0' from live PyPI artifact (end-to-end version agreement)"
  - "Clean-venv run from scratchpad dir (outside repo tree) to prevent editable install from masking PyPI artifact"

patterns-established:
  - "Release gate sequence: bump 3 sources → 4 gates → annotated tag → human GitHub Release → clean-venv smoke"

requirements-completed: [REL-10]

duration: 5min
completed: "2026-06-26"
---

# Phase 40 Plan 02: Release v0.10.0 Publish Summary

**pycopg v0.10.0 shipped to PyPI via OIDC trusted-publishing (human-gated GitHub Release), annotated tag v0.10.0 on commit ab1bac6, clean-venv smoke confirmed `__version__ == '0.10.0'` from the live PyPI artifact**

## Performance

- **Duration:** ~5 min (continuation agent — Tasks 1 and 2 pre-completed, Task 3 executed now)
- **Started:** 2026-06-26T22:55:00Z
- **Completed:** 2026-06-26T22:55:29Z
- **Tasks:** 3 (Task 1 and 2 pre-completed before continuation; Task 3 executed in this run)
- **Files modified:** 0 (release-only — git tag + PyPI publish + smoke; no source files touched)

## Accomplishments

- Annotated tag `v0.10.0` created on release commit `ab1bac6` ("pycopg v0.10.0 — Durcissement & Performance") — precondition for Task 2 confirmed before this continuation agent ran
- OIDC trusted-publishing GitHub workflow (`publish.yml`) ran green triggered by a human-published GitHub Release: steps `uv lock --check`, `uv build`, and `Publish to PyPI` all succeeded (36s run); PyPI shows latest=0.10.0 (wheel + sdist) — confirmed by orchestrator before resuming
- GitHub Release `v0.10.0` published (not draft) at `https://github.com/loc-cosnier/pycopg/releases/tag/v0.10.0`
- Clean-venv smoke (Task 3): fresh venv created in scratchpad dir (`/tmp/.../scratchpad/smoke-venv-40`) outside the project tree; `pip install -q pycopg==0.10.0` succeeded on first attempt (no CDN propagation delay); `__version__ == '0.10.0'` asserted and printed `smoke ok 0.10.0`; venv left in session-scoped scratchpad (sandbox prevented rm -rf but scratchpad is session-ephemeral)

## Task Commits

This is a terminal release plan — Task 1 (tag) and Task 2 (publish) produced no source commits; Task 3 (smoke) modifies no project files. Commits are the Plan 40-01 release commit and the plan metadata commit.

| Task | Name | Commit/Evidence | Type |
|------|------|-----------------|------|
| 1 | Create annotated v0.10.0 tag | `git tag -l v0.10.0` → annotated on `ab1bac6` | git tag (no file commit) |
| 2 | HUMAN-GATED publish to PyPI | publish.yml run green (36s); https://pypi.org/project/pycopg/0.10.0/ live | human-gated workflow |
| 3 | Clean-venv smoke | `smoke ok 0.10.0` from PyPI-installed package | automated smoke (no commit) |

**Plan metadata commit:** see Final Commit section.

## Smoke Test Details (Task 3)

```
Command: python3 -m venv $SCRATCH/smoke-venv-40
          $SCRATCH/smoke-venv-40/bin/pip install -q pycopg==0.10.0
          $SCRATCH/smoke-venv-40/bin/python -c \
            "import pycopg; assert pycopg.__version__ == '0.10.0', \
             pycopg.__version__; print('smoke ok', pycopg.__version__)"

Run from: /tmp/.../scratchpad (outside /home/loc/workspace/pycopg repo tree)

Output: smoke ok 0.10.0
Exit code: 0
```

The `__version__` attribute in `pycopg/__init__.py` uses `importlib.metadata.version("pycopg")` with a `"0.0.0+unknown"` fallback. A result of `0.10.0` confirms the installed metadata from PyPI is consistent with all three version sources (pyproject.toml, docs/conf.py, uv.lock) that were bumped in Plan 40-01.

## PyPI Publish Evidence (Task 2 — Human-Approved)

- **Trigger:** Human-published GitHub Release `v0.10.0` (not draft)
- **Workflow:** `.github/workflows/publish.yml` — `on: release: types: [published]`
- **Workflow run:** Success (36s), steps: `Verify lockfile is current` (uv lock --check), `Build package` (uv build), `Publish to PyPI` (pypa/gh-action-pypi-publish, OIDC, `pypi` environment, `id-token: write`)
- **PyPI URL:** https://pypi.org/project/pycopg/0.10.0/
- **Artifacts:** wheel + sdist for 0.10.0 confirmed present
- **latest on PyPI:** 0.10.0

## Files Created/Modified

None — this plan creates a git tag and a PyPI release. No source files were modified.

## Decisions Made

- **Human-gated discipline preserved:** Task 2 kept as `gate="blocking-human"` — publish is never auto-advanced. This is the 7th successful OIDC trusted-publishing run in the project (releases v0.4.0 through v0.10.0).
- **Smoke venv location:** Placed in session-scoped scratchpad (outside repo) to prevent the editable install in `pycopg/venv/` from masking the PyPI artifact during `import pycopg`.
- **Version agreement confirmed end-to-end:** Three sources (pyproject.toml `version = "0.10.0"`, docs/conf.py `release = '0.10.0'`, uv.lock pycopg entry) all agree; PyPI metadata confirms via `__version__`.

## Deviations from Plan

None — plan executed exactly as written. The clean-venv smoke succeeded on the first attempt with no CDN propagation wait needed. The venv teardown (`rm -rf`) was blocked by the execution sandbox; the scratchpad directory is session-ephemeral, so this has no impact on the project tree.

## Issues Encountered

- `rm -rf` of the smoke venv was blocked by the sandbox permission model. The scratchpad dir is session-scoped and isolated from the project, so this is cosmetic. No impact.

## Known Stubs

None — release plan with no UI or data components.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes. The OIDC publish used the pre-existing `pypi` trusted-publishing environment (T-40-02-02 disposition: OIDC, no long-lived token).

## Next Phase Readiness

- v0.10.0 is SHIPPED: tag present, PyPI live, smoke green. Milestone complete.
- Next milestone: v1.0.0 — spatial v2 + API freeze (planned post-v0.10.0 cadrage decision)
- No blockers. The deferred items from v0.10.0 (TSDB-F01..F04, ETL-INC-F01..F05, CRUD-F01..F03, INTRO-F01..F02) are tracked in STATE.md for v1.0.0 planning.

---
*Phase: 40-release-v0-10-0*
*Completed: 2026-06-26*
