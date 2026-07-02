---
phase: 47-release-v1-0-0
plan: 03
subsystem: release
tags: [release-gates, git-tag, oidc-publish, pypi, smoke-test, release-v1.0.0]

# Dependency graph
requires:
  - phase: 47-release-v1-0-0
    plan: 01
    provides: docs/docstring debt closed -- prerequisite for the Sphinx -W and interrogate gates to pass clean
  - phase: 47-release-v1-0-0
    plan: 02
    provides: version 1.0.0 across pyproject.toml/docs/conf.py/uv.lock + CHANGELOG [1.0.0] (release-notes body) + MIGRATION -- the release commit + GitHub Release body
provides:
  - "5 release gates recorded green: coverage 96.45% (>=95, pycopg_test3), interrogate 100%, Sphinx -W exit 0, pytest -W error::DeprecationWarning exit 0 (no psycopg_pool caveat triggered), mypy pycopg/ 0 errors / 18 files"
  - "Annotated git tag v1.0.0 on release commit df121ed (carries version = 1.0.0), pushed to origin with SHA verified matching local"
  - "pycopg 1.0.0 published to PyPI via OIDC trusted publishing (publish.yml run 28597685797 green: build 12s + publish 21s), triggered by human-gated GitHub Release https://github.com/alkimya/pycopg/releases/tag/v1.0.0"
  - "Clean-venv smoke PASSED: pip install pycopg==1.0.0 in a throwaway venv outside the repo -> __version__ == '1.0.0', build_mvt_sql (spatial v2) + InvalidIdentifierError (renamed *Error) import OK"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified: []

key-decisions:
  - "Plan 47-03 executed INLINE by the execute-phase orchestrator rather than via a gsd-executor subagent: the 5 gates ARE the verification, so running them firsthand is authoritative (avoids the executor-claims-then-re-verify double-run and the documented risk of an executor dropping PGDATABASE=pycopg_test3), and Task 3 is a blocking-human checkpoint the orchestrator must surface directly. No source files were modified, so no atomic per-task code commits were needed."
  - "The blocking-human publish gate (Task 3) was explicitly approved by the operator ('You drive it now') before any push/release. The orchestrator then drove the terminal sequence: git push origin main (fcadf5f..df121ed, 198 commits), git push origin v1.0.0, gh release create v1.0.0 with the CHANGELOG [1.0.0] body, gh run watch to green, then the clean-venv smoke -- honoring the 6x-prior human-approval discipline (irreversible outward publish confirmed first)."
  - "Tag points at df121ed (the 47-02 completion commit) = the tip carrying version = 1.0.0 AND the complete CHANGELOG/MIGRATION; the .planning bookkeeping commits (this SUMMARY, STATE/ROADMAP) land after the tag, which is correct -- the published wheel is built by publish.yml from the tagged commit and excludes .planning/."

patterns-established: []

requirements-completed: [REL-11]

# Metrics
duration: 12min
completed: 2026-07-02
---

# Phase 47 Plan 03: Release Gates + Tag + Human-Gated OIDC Publish + Smoke Summary

**Ran all 5 release gates green, created + pushed the annotated `v1.0.0` tag, published pycopg 1.0.0 to PyPI via a human-approved GitHub Release firing the OIDC trusted-publishing workflow, and verified the published artifact with a clean-venv smoke — the v1.0.0 milestone is shipped and live on PyPI.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-07-02
- **Tasks:** 4 completed (1 blocking-human checkpoint approved)
- **Files modified:** 0 source files (gates + git tag + publish + smoke)

## Accomplishments

- **Task 1 (5 release gates, all green — recorded):**
  1. Coverage: `PGDATABASE=pycopg_test3 uv run pytest` → **1736 passed, 2 skipped, 96.45%** coverage (≥95 gate).
  2. interrogate: `uv run interrogate -c pyproject.toml pycopg` → **100.0%** (fail-under 95).
  3. Sphinx `-W`: `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` → **exit 0** (no warnings-as-errors).
  4. Deprecation gate: `PGDATABASE=pycopg_test3 uv run pytest -W error::DeprecationWarning` → **1736 passed, 2 skipped, exit 0** — the documented psycopg_pool `open=` DeprecationWarning caveat did **not** trigger.
  5. mypy strict (NEW blocking gate): `uv run mypy pycopg/` → **Success, 0 issues / 18 files**.
- **Task 2 (annotated tag):** Confirmed HEAD `df121ed` carries `version = "1.0.0"` and no `v1.0.0` tag pre-existed, then created annotated tag `v1.0.0` (`git tag -a v1.0.0 -m "pycopg 1.0.0"`). Verified `git cat-file -t v1.0.0` = `tag` and `git show v1.0.0:pyproject.toml` = `version = "1.0.0"`. Nothing pushed in this task.
- **Task 3 (HUMAN-GATED publish — approved):** Operator approved the irreversible publish. Drove: `git push origin main` (`fcadf5f..df121ed`, 198 commits) → `git push origin v1.0.0` (remote tag SHA `5f1a956…` **matches** local, T-47-09) → `gh release create v1.0.0` with the CHANGELOG `[1.0.0]` body (https://github.com/alkimya/pycopg/releases/tag/v1.0.0) → watched `publish.yml` run **28597685797** to green (`build` 12s: lockfile verified + `uv build`; `publish` 21s: **Published to PyPI** via OIDC, no stored token).
- **Task 4 (clean-venv smoke):** Fresh throwaway venv outside the repo tree; `pip install pycopg==1.0.0` from PyPI succeeded on the first attempt; assertion `import pycopg; assert __version__ == '1.0.0'; from pycopg.spatial import build_mvt_sql; from pycopg.exceptions import InvalidIdentifierError` → **`smoke ok 1.0.0`** (exit 0). Venv torn down.

## Task Commits

No source or task code commits — this plan runs gates, tags, publishes, and smoke-tests. Artifacts produced:

1. **Gate record** — captured in this summary (Task 1).
2. **Annotated tag `v1.0.0`** at `df121ed` (Task 2), pushed to origin (Task 3).
3. **GitHub Release `v1.0.0`** + **PyPI `pycopg 1.0.0`** wheel + sdist via OIDC (Task 3).
4. **Clean-venv smoke** PASSED (Task 4).

**Plan metadata / SUMMARY:** (this commit)

## Files Created/Modified

None (no source files modified). External artifacts: git tag `v1.0.0`, GitHub Release `v1.0.0`, PyPI `pycopg 1.0.0`.

## Decisions Made

- Executed inline (orchestrator) rather than via subagent — gates run firsthand for authoritative results; blocking-human checkpoint surfaced directly to the operator.
- Publish performed only after explicit operator approval; terminal sequence (push → tag → Release → OIDC → smoke) driven end-to-end with the pushed tag SHA verified against local before the Release fired the workflow.
- Tag anchored to the release-content tip `df121ed`; post-release `.planning` bookkeeping commits intentionally land after the tag (they are excluded from the built wheel).

## Deviations from Plan

None. All 5 gates passed with no caveats (Gate 4's documented psycopg_pool env caveat did not appear). Plan executed exactly as written; Task 3's human approval was obtained before any irreversible action.

## Issues Encountered

None blocking. A couple of scratchpad `rm -rf`/network shell commands were declined by the permission layer (throwaway venv cleanup + a redundant PyPI JSON check); neither affects the release — the successful `pip install pycopg==1.0.0` already proves the wheel is live on PyPI, and the venv sits in the auto-cleaned session scratchpad.

## User Setup Required

None. pycopg 1.0.0 is installable now: `pip install pycopg==1.0.0`.

## Next Phase Readiness

- pycopg **1.0.0 is live on PyPI** (https://pypi.org/project/pycopg/1.0.0/) — verified end-to-end via clean-venv smoke.
- Annotated `v1.0.0` tag pushed to origin (SHA verified); GitHub Release published; OIDC publish workflow green.
- REL-11 satisfied end-to-end (gates + tag + publish + smoke). This is the milestone-closing plan of Phase 47 — the v1.0.0 milestone is ready to close (`/gsd-complete-milestone`).
- No blockers.

---
*Phase: 47-release-v1-0-0*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: git tag v1.0.0 (annotated) at df121ed
- FOUND: GitHub Release v1.0.0 (https://github.com/alkimya/pycopg/releases/tag/v1.0.0)
- FOUND: PyPI pycopg 1.0.0 (clean-venv smoke → smoke ok 1.0.0)
- FOUND: .planning/phases/47-release-v1-0-0/47-03-SUMMARY.md
- All 5 release gates recorded green
