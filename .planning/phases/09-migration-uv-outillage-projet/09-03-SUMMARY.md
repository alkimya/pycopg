---
phase: 09-migration-uv-outillage-projet
plan: "03"
subsystem: ci
tags: [uv, github-actions, publish, oidc, trusted-publishing, build]
dependency_graph:
  requires: ["09-01"]
  provides: ["publish.yml build job uses uv build + setup-uv@v8.2.0"]
  affects: [".github/workflows/publish.yml"]
tech_stack:
  added: ["astral-sh/setup-uv@v8.2.0", "uv build"]
  patterns: ["uv as build frontend delegating to hatchling", "OIDC trusted publishing preserved"]
key_files:
  modified: [".github/workflows/publish.yml"]
decisions:
  - "D-13: build job replaced setup-python@v5 + pip install build + python -m build with astral-sh/setup-uv@v8.2.0 + uv build"
  - "D-14: publish job (pypa/gh-action-pypi-publish@release/v1 + id-token: write) kept byte-for-byte unchanged"
  - "D-15: actions/*@v4 pins not bumped (Node 20->24 deferred to Phase 15)"
metrics:
  duration_seconds: 48
  completed: "2026-06-06T18:54:12Z"
  tasks_completed: 2
  files_modified: 1
---

# Phase 09 Plan 03: Publish Workflow — uv Build Migration Summary

**One-liner:** Replaced `setup-python@v5 + pip install build + python -m build` with `astral-sh/setup-uv@v8.2.0 + uv build` in the publish.yml build job; OIDC trusted publishing path left untouched.

## What Was Built

Modified `.github/workflows/publish.yml` — build job only. The change removes the three-step old toolchain (setup-python, pip install build, python -m build) and replaces it with two steps: install uv via `astral-sh/setup-uv@v8.2.0`, then run `uv build`. The `publish` job (`pypa/gh-action-pypi-publish@release/v1` + `permissions: id-token: write`) is preserved byte-for-byte per D-14 (OIDC trusted publishing).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Replace publish.yml build job with uv build | 0d86866 | .github/workflows/publish.yml |
| 2 | Validate uv build produces valid wheel + sdist | (part of same commit — local validation) | — |

## Verification Results

### Automated checks (all passed)

- `grep -q 'astral-sh/setup-uv@v8.2.0'` — PASS
- `grep -qE '^\s*run:\s*uv build'` — PASS
- `! grep -q 'python -m build'` — PASS
- `! grep -q 'pip install build'` — PASS
- `! grep -q 'setup-python'` — PASS
- `grep -q 'gh-action-pypi-publish@release/v1'` — PASS
- `grep -q 'id-token: write'` — PASS
- `! grep -q 'setup-uv@v6'` — PASS

### Local uv build validation (Task 2)

```
Building source distribution...
Building wheel from source distribution...
Successfully built dist/pycopg-0.3.1.tar.gz
Successfully built dist/pycopg-0.3.1-py3-none-any.whl
```

`uv build` exits 0 and produces both `dist/pycopg-0.3.1-py3-none-any.whl` and `dist/pycopg-0.3.1.tar.gz` via hatchling backend (unchanged). The `dist/` output path is unchanged — existing `actions/upload-artifact@v4 path: dist/` step in the build job and `actions/download-artifact@v4 path: dist/` step in the publish job remain compatible.

**CI workflow_dispatch validation:** Not executed in this run (requires GitHub Actions runner). The plan notes this as a CI observation step — run URL to be provided when triggered via workflow_dispatch. No accidental PyPI publish occurred.

## Deviations from Plan

None — plan executed exactly as written.

The two tasks (replace build job, validate uv build) were implemented atomically in a single commit since the validation (Task 2) is a local assertion rather than a code change.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The existing OIDC trusted publishing surface (`id-token: write` + `pypa/gh-action-pypi-publish@release/v1`) is preserved unchanged — not expanded or altered. The new `astral-sh/setup-uv@v8.2.0` reference is pinned to a full-version immutable tag (T-09-CI-PUB mitigated).

## Known Stubs

None.

## Self-Check: PASSED

- `.github/workflows/publish.yml` — FOUND (modified)
- Commit `0d86866` — FOUND in git log
- `uv build` local validation — PASSED (both formats produced)
