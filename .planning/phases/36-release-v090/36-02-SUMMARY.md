---
phase: 36-release-v090
plan: "02"
subsystem: release
tags: [pypi, github-release, oidc, publish, smoke-test, v0.9.0]

requires:
  - phase: 36-01
    provides: version-0.9.0-content (version bump, CHANGELOG, docs, gates baseline)
provides:
  - git tag v0.9.0 at commit 065a942
  - GitHub Release v0.9.0 (https://github.com/alkimya/pycopg/releases/tag/v0.9.0)
  - PyPI release pycopg 0.9.0 (wheel + sdist via OIDC trusted publishing)
  - Clean-venv smoke: pip install pycopg==0.9.0 from PyPI resolves and passes surface assertions
affects: [v1.0.0-spatial-v2]

tech-stack:
  added: []
  patterns: [oidc-trusted-publishing, lightweight-git-tag, gh-release-create-notes-file]

key-files:
  created: []
  modified: []

key-decisions:
  - "D-36-02: publish gated behind blocking human checkpoint (user responded 'approved') — IRREVERSIBLE PyPI step requires human sign-off"
  - "D-36-02b: --notes-file used for gh release create (lightweight tag has no annotation, --notes-from-tag not applicable)"
  - "D-36-02c: publish workflow (run 28171811187) used OIDC trusted publishing — no long-lived PyPI token"

patterns-established:
  - "Release pattern: gates -> build -> human checkpoint -> tag + push -> gh release create --notes-file -> watch workflow -> smoke"

requirements-completed: [REL-09]

duration: ~8min
completed: 2026-06-25
---

# Phase 36 Plan 02: Release v0.9.0 (Tag + Publish + Smoke) Summary

**pycopg 0.9.0 tagged, pushed, published to PyPI via GitHub Actions OIDC trusted publishing, and clean-venv smoke confirmed `__version__ == "0.9.0"` with CRUD (`upsert`, `count`) and introspection (`SchemaAccessor.describe`) surface present.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-25T12:55:00Z
- **Completed:** 2026-06-25T13:00:17Z
- **Tasks:** 2 (Tasks 2 + 3; Task 1 was completed by prior executor)
- **Files modified:** 0 (release artifacts only — no repo-file edits)

## Accomplishments

- git tag v0.9.0 created at HEAD (065a942) and pushed to origin
- origin/main pushed (was 9 commits ahead of origin; push accepted, non-fast-forward not triggered)
- GitHub Release v0.9.0 published with CHANGELOG [0.9.0] section as body (3127 chars)
- Publish workflow run 28171811187 completed SUCCEEDED: build job (7s) + publish job (21s) via OIDC pypa/gh-action-pypi-publish@release/v1
- Clean-venv smoke: `pip install --no-cache-dir pycopg==0.9.0` resolved immediately from PyPI (no propagation lag); `SMOKE-OK version=0.9.0`

## Gate Re-Confirm (from Task 1 — prior executor, 36-01-SUMMARY.md baseline)

| Gate | Target | Measured | Status |
|------|--------|----------|--------|
| GATE A: Coverage | >=94% | 94.11% | GREEN |
| GATE B: interrogate | >=95% | 100% | GREEN |
| GATE C: Sphinx -W | clean | exits 0 | GREEN |
| GATE D: DeprecationWarning | clean | exits 0 | GREEN |
| uv lock --check | exits 0 | exits 0 | GREEN |
| uv build | dist/*.whl + *.tar.gz | pycopg-0.9.0* built | GREEN |

## Release Sequence

| Step | Command | Result |
|------|---------|--------|
| Tag | `git tag v0.9.0` | Tag created at 065a942 |
| Push main | `git push origin main` | 1c0d636..065a942 main -> main |
| Push tag | `git push origin v0.9.0` | * [new tag] v0.9.0 -> v0.9.0 |
| GitHub Release | `gh release create v0.9.0 --title "v0.9.0" --notes-file <file>` | https://github.com/alkimya/pycopg/releases/tag/v0.9.0 |
| Publish workflow | run 28171811187 | SUCCEEDED (build 7s + publish 21s) |

## Publish Workflow Detail (run 28171811187)

- **Trigger:** `on: release: types: [published]`
- **build job** (83437703322): checkout -> install uv -> `uv lock --check` -> `uv build` -> upload artifacts -> SUCCESS in 7s
- **publish job** (83437735251): download artifacts -> `pypa/gh-action-pypi-publish@release/v1` OIDC -> SUCCESS in 21s
- **Conclusion:** success

## Clean-Venv Smoke Test

```
venv: /tmp/pycopg-smoke (python3, outside project)
pip install --no-cache-dir pycopg==0.9.0  => Downloaded pycopg-0.9.0-py3-none-any.whl from PyPI
python -c "import pycopg; assert pycopg.__version__ == '0.9.0', pycopg.__version__; \
  from pycopg import Database; assert hasattr(Database,'upsert') and hasattr(Database,'count'); \
  from pycopg.schema import SchemaAccessor; assert hasattr(SchemaAccessor,'describe'); \
  print('SMOKE-OK version=' + pycopg.__version__)"
=> SMOKE-OK version=0.9.0
```

All assertions passed:
- `pycopg.__version__ == "0.9.0"` — version metadata resolves correctly from installed wheel
- `Database.upsert` present — CRUD ergonomics surface (Phase 34)
- `Database.count` present — CRUD read helpers surface (Phase 34)
- `SchemaAccessor.describe` present — schema introspection compose helper (Phase 35)

## Task Commits

This plan produced no source commits (release actions only — git tag, push, GitHub Release, PyPI publish):

| Step | Action | Result |
|------|--------|--------|
| Task 2 | `git tag v0.9.0` | lightweight tag at 065a942 |
| Task 2 | `git push origin main` | pushed (9 commits ahead) |
| Task 2 | `git push origin v0.9.0` | new tag pushed |
| Task 2 | `gh release create v0.9.0` | GitHub Release published |
| Task 2 | publish workflow | run 28171811187 SUCCEEDED |
| Task 3 | clean-venv smoke | SMOKE-OK version=0.9.0 |

Prior executor commits (Task 1, from 36-01 wave):
- 065a942: docs(36-01): complete release-content plan — gates green
- e405f8e: test(36-01): add async schema introspection tests + fix Sphinx -W warnings
- a93f465: chore(36-01): clear stale pycopg.aliases xrefs from accessor module docstrings
- 03dfbdc: docs(36-01): update docs surfaces for v0.9.0 CRUD + introspection methods
- 4dc7b70: docs(36-01): write CHANGELOG [0.9.0] Added-only section with exact signatures
- 482b648: chore(36-01): bump version to 0.9.0 across canonical sources

## Decisions Made

- Used `--notes-file` (not `--notes-from-tag`) for `gh release create` — the tag is lightweight (no annotation), so `--notes-from-tag` would produce empty release notes.
- CHANGELOG [0.9.0] section body (3127 chars, covering 12 new methods across CRUD + introspection families) was written to a scratchpad file and passed as the notes body verbatim.
- PyPI propagation lag was not encountered — `pip install pycopg==0.9.0` resolved immediately after workflow success.

## Deviations from Plan

None — plan executed exactly as written. The release sequence (tag -> push main -> push tag -> gh release create -> monitor workflow -> clean-venv smoke) proceeded without deviation.

Note: `/tmp/pycopg-smoke` cleanup (`rm -rf`) was denied by sandbox permissions. The temporary venv remains at that path; it can be removed manually (`rm -rf /tmp/pycopg-smoke`).

## Known Stubs

None — this plan delivers release artifacts, not source files.

## Threat Flags

None — the publish used OIDC trusted publishing (no long-lived token; T-36-02 mitigated). The release is gated by the human-approved checkpoint (blocking sign-off obtained before tagging).

## Next Phase Readiness

- v0.9.0 milestone is COMPLETE: Phase 34 (CRUD ergonomics), Phase 35 (schema introspection), Phase 36 (release) all shipped.
- PyPI: `pip install pycopg==0.9.0` resolves.
- GitHub Release: https://github.com/alkimya/pycopg/releases/tag/v0.9.0
- Next milestone: v1.0.0 spatial v2 (as noted in memory context).

## Self-Check: PASSED

- git tag v0.9.0: `git tag -l | grep v0.9` => v0.9.0 (present)
- origin/main pushed: `git push origin main` => 1c0d636..065a942 (accepted)
- origin v0.9.0 pushed: `git push origin v0.9.0` => [new tag] (accepted)
- GitHub Release: `gh release view v0.9.0` URL = https://github.com/alkimya/pycopg/releases/tag/v0.9.0
- Publish workflow: run 28171811187 => conclusion: success
- Smoke result: SMOKE-OK version=0.9.0 (all 3 surface assertions passed)

---
*Phase: 36-release-v090*
*Completed: 2026-06-25*
