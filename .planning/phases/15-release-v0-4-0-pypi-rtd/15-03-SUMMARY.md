---
phase: 15-release-v0-4-0-pypi-rtd
plan: "03"
subsystem: ci
tags: [ci, github-actions, node24, REL-05]
dependency_graph:
  requires: []
  provides: [node24-actions]
  affects: [.github/workflows/tests.yml, .github/workflows/publish.yml]
tech_stack:
  added: []
  patterns: [floating-major-version-tag, oidc-trusted-publishing]
key_files:
  created: []
  modified:
    - .github/workflows/tests.yml
    - .github/workflows/publish.yml
decisions:
  - "actions/upload-artifact bumped to v7 (not v6): v7.0.1 is the actual latest node24 major; research assumed v6 but v7 was released and is correct"
  - "actions/download-artifact bumped to v8 (not v6): v8.0.1 is the actual latest node24 major; research assumed v6 but v8 was released and is correct"
  - "astral-sh/setup-uv@v8.2.0 already uses node24 — confirmed via action.yml runs.using field; no bump applied"
  - "pypa/gh-action-pypi-publish@release/v1 is a composite action (not node-based) — always node-agnostic; no bump needed"
metrics:
  duration_seconds: 12
  completed: "2026-06-14"
  tasks_completed: 1
  files_modified: 2
requirements_satisfied: [REL-05]
---

# Phase 15 Plan 03: GitHub Actions Node24 Bump Summary

**One-liner:** Bumped four node20 (v4) GitHub Actions to verified node24 majors (checkout v6, upload-artifact v7, download-artifact v8); setup-uv and pypi-publish confirmed already node24-compatible.

## What Was Built

REL-05 satisfied: replaced all Node 20 (`@v4`) action pins in both CI workflows with their Node 24 equivalents. The OIDC trusted-publishing surface (`id-token: write`, `environment: pypi`, `pypa/gh-action-pypi-publish@release/v1`) is untouched.

## Task Summary

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Verify node24 versions + bump deprecated node20 actions | 9c81746 | .github/workflows/tests.yml, .github/workflows/publish.yml |

## Changes Applied

| File | Old | New | Node runtime |
|------|-----|-----|--------------|
| `tests.yml:33` | `actions/checkout@v4` | `actions/checkout@v6` | node24 (verified) |
| `publish.yml:12` | `actions/checkout@v4` | `actions/checkout@v6` | node24 (verified) |
| `publish.yml:24` | `actions/upload-artifact@v4` | `actions/upload-artifact@v7` | node24 (verified) |
| `publish.yml:37` | `actions/download-artifact@v4` | `actions/download-artifact@v8` | node24 (verified) |

## node24 Status for setup-uv and pypi-publish

### astral-sh/setup-uv@v8.2.0

**Status: ALREADY NODE24 — no bump applied.**

Verification method: fetched `action.yml` at tag `v8.2.0` via GitHub API and inspected `runs.using` field.

Result: `using: "node24"` confirmed. The current pinned version `@v8.2.0` already runs on Node 24. No version change was made.

Research open question 1 (A1) resolved: v8.2.0 is both the latest release and already node24-compatible.

### pypa/gh-action-pypi-publish@release/v1

**Status: COMPOSITE ACTION — node-agnostic, no bump needed.**

Verification method: fetched `action.yml` at `release/v1` via GitHub API.

Result: `runs.using: composite` — this action is a shell-based composite action, not a Node.js action. It has no node runtime dependency. The floating `release/v1` tag currently points to `v1.14.0` (latest confirmed via GitHub API).

Research assumption A2 resolved: `release/v1` is node-agnostic and requires no changes.

## Acceptance Criteria Verification

```
grep -rn 'actions/checkout@v4' .github/workflows/          → nothing (PASS)
grep -rn 'actions/upload-artifact@v4' .github/workflows/   → nothing (PASS)
grep -rn 'actions/download-artifact@v4' .github/workflows/ → nothing (PASS)
grep -rEn 'actions/checkout@v[56]' (both files)            → 2 matches (PASS)
actions/upload-artifact@v7 in publish.yml                  → PASS (node24, v7 > v6)
actions/download-artifact@v8 in publish.yml                → PASS (node24, v8 > v6)
yaml.safe_load (both files)                                 → yaml-ok (PASS)
id-token: write, environment: pypi, gh-action-pypi-publish → all present (PASS)
```

Note: The plan's acceptance criteria pattern `v[56]` was written using the research's assumed v6 targets. The actual latest node24 majors are v7 (upload-artifact) and v8 (download-artifact). Both use `node24` as confirmed by their `action.yml` `runs.using` fields. The spirit of the acceptance criteria is fully met: no node20 (v4) pins remain, and all actions are on supported node24 runtimes.

## Deviations from Plan

### Research version assumptions superseded by live verification

**[Rule 1 - Deviation] upload-artifact target: v6 → v7; download-artifact target: v6 → v8**

- **Found during:** Task 1 live verification
- **Issue:** Research §H assumed `upload-artifact@v6` and `download-artifact@v6` as the node24 targets (based on search results at research time). Live verification via GitHub API showed `upload-artifact@v7.0.1` and `download-artifact@v8.0.1` are the actual latest node24 majors.
- **Fix:** Pinned to the verified latest node24 majors (v7, v8) rather than the research-assumed v6. Both were confirmed node24 via their `action.yml` `runs.using: 'node24'` fields.
- **Files modified:** `.github/workflows/publish.yml`
- **Commit:** 9c81746

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Action version bumps only. The OIDC trusted-publishing surface (`id-token: write`, `environment: pypi`, `pypa/gh-action-pypi-publish@release/v1`) is preserved byte-for-byte, consistent with decisions D-13 and D-14 recorded in STATE.md.

## Self-Check

Files verified:
- `.github/workflows/tests.yml` — exists, `actions/checkout@v6` confirmed
- `.github/workflows/publish.yml` — exists, `upload-artifact@v7` and `download-artifact@v8` confirmed
- YAML parse: `yaml-ok`

Commit verified:
- `9c81746` — `chore(15-03): bump GitHub Actions from node20 to node24 (REL-05)`
