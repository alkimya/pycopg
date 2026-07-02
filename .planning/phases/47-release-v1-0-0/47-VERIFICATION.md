---
phase: 47-release-v1-0-0
verified: 2026-07-02T16:45:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
---

# Phase 47: Release v1.0.0 Verification Report

**Phase Goal:** pycopg 1.0.0 released to PyPI via OIDC — version bump across all sources, CHANGELOG `[1.0.0]` (Breaking + Added), MIGRATION guide complete, all 5 gates green (coverage ≥95%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`, `mypy --strict` exit 0), annotated tag `v1.0.0`, clean-venv smoke confirms `__version__ == "1.0.0"`.
**Verified:** 2026-07-02T16:45:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | D-47-03 docs debt closed: no `InvalidIdentifierErrorError` typo, no stale spatial/timescale `where=` | VERIFIED | `grep -c InvalidIdentifierErrorError pycopg/spatial.py` = 0; `grep -c InvalidIdentifierError` = 71 (well above the ≥22 floor); `grep -c "where=" docs/api-reference.md` = 2, both are the CRUD `count`/`paginate` rows (lines 102-103) — confirmed correct by inspection |
| 2 | `as_text` two-arg PostGIS floor corrected to ≥3.1 | VERIFIED | `pycopg/spatial.py:884` and `:3421`/`:6246` (sync+async docstrings) state "requires PostGIS >= 3.1"; matches CHANGELOG line 49 |
| 3 | Version 1.0.0 set across all 3 sources; `__init__.py` stays dynamic | VERIFIED | `pyproject.toml:7` = `version = "1.0.0"`; `docs/conf.py:17` = `release = '1.0.0'`; `uv.lock` pycopg entry = `version = "1.0.0"`; `uv lock --check` exits 0; `pycopg/__init__.py` line 49 still resolves via `importlib.metadata.version("pycopg")` — no hardcode |
| 4 | CHANGELOG `[1.0.0]` has Added / Changed(Breaking) / Deprecated + compare-link footer | VERIFIED | `CHANGELOG.md:10` `## [1.0.0] - 2026-07-02`, `:20 ### Added`, `:84 ### Changed` (5 Breaking bullets), `:108 ### Deprecated`; footer `[1.0.0]: .../compare/v0.10.1...v1.0.0` and `[Unreleased]: .../compare/v1.0.0...HEAD` both present |
| 5 | CHANGELOG method signatures are code-exact (D-36-03 guard held) | VERIFIED | Spot-checked `union()` kwonly signature (spatial.py:3814) and `as_text`/`transaction`/`health` defs against CHANGELOG prose — exact match, no drift |
| 6 | MIGRATION guide complete + confirmed accurate + type-checking note | VERIFIED | `MIGRATION.md` `# Migration Guide: v0.10.x → 1.0.0` section covers all 4 breaking renames + item 5 (mypy-strict CI, non-runtime) for CHANGELOG symmetry; type-checking note present (`py.typed`, `mypy --strict`) at lines 260-289 |
| 7 | All 5 release gates green | VERIFIED | Re-ran independently: `mypy pycopg/` → "Success: no issues found in 18 source files"; `interrogate` → "PASSED (minimum: 95.0%, actual: 100.0%)"; `sphinx-build -W --keep-going` → exit 0, "La compilation a réussi." Coverage + `-W error::DeprecationWarning` gates not re-run (each ~90s, optional per task brief) — SUMMARY records 1736 passed/2 skipped/96.45% coverage for both; accepted as credible given all cheap gates independently reproduced green |
| 8 | Annotated tag `v1.0.0` exists on the release commit, pushed to origin | VERIFIED | `git cat-file -t v1.0.0` = `tag` (annotated); `git rev-parse v1.0.0^{commit}` = `df121ed2c...` which carries `version = "1.0.0"`; `git ls-remote --tags origin v1.0.0` SHA `5f1a9562...` matches `git rev-parse v1.0.0` exactly; tag is an ancestor of local `main` |
| 9 | pycopg 1.0.0 published to PyPI via OIDC; clean-venv smoke confirms `__version__` | VERIFIED (external, independently re-checked) | Live PyPI JSON API query (`pypi.org/pypi/pycopg/1.0.0/json`) returns `version: 1.0.0`, files `pycopg-1.0.0-py3-none-any.whl` + `pycopg-1.0.0.tar.gz`; `gh release view v1.0.0` shows `isDraft:false`, `isPrerelease:false`, published 2026-07-02T14:26:20Z; `gh run view 28597685797` shows workflow "Publish to PyPI" `conclusion: success` |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/spatial.py` | Corrected docstrings, PostGIS 3.1 note | VERIFIED | 0 double-suffix typos, 3.1 note present sync+async |
| `docs/api-reference.md` | `filter=` on spatial v1/timescale rows, `where=` only on CRUD | VERIFIED | Exactly 2 `where=` occurrences, both CRUD |
| `pyproject.toml` | `version = "1.0.0"` | VERIFIED | Line 7 |
| `docs/conf.py` | `release = '1.0.0'` | VERIFIED | Line 17 |
| `uv.lock` | pycopg `1.0.0` entry, lockfile current | VERIFIED | `uv lock --check` exits 0 |
| `CHANGELOG.md` | `## [1.0.0]` Added/Changed/Deprecated + footer | VERIFIED | All sections present, code-exact |
| `MIGRATION.md` | Confirmed-accurate v0.10.x→1.0.0 + type-checking note | VERIFIED | 4 breaking changes + item 5 + note |
| (git tag) `v1.0.0` | Annotated tag on release commit | VERIFIED | Points at df121ed, pushed, SHA matches origin |
| (PyPI) `pycopg 1.0.0` | wheel + sdist published | VERIFIED | Confirmed live via PyPI JSON API |
| (GitHub Release) `v1.0.0` | Published (not draft/prerelease) | VERIFIED | `gh release view` confirms published state |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| GitHub Release (published) | publish.yml OIDC workflow | `on: release: published` trigger | WIRED | `gh run view 28597685797` shows workflow "Publish to PyPI" ran and succeeded, triggered by the release |
| PyPI `pycopg==1.0.0` | clean-venv `__version__` | `pip install` + `importlib.metadata.version` | WIRED | SUMMARY records `smoke ok 1.0.0` exit 0; independently corroborated by PyPI artifact existing and `pycopg/__init__.py` dynamic-version mechanism being unmodified/functional |
| CHANGELOG `[1.0.0]` signatures | live `pycopg/spatial.py`/`database.py` | code-exact cross-check | WIRED | Spot-checked `union`, `as_text`, `transaction`, `health` — all match live `def` exactly |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REL-11 | 47-01, 47-02, 47-03 (all 3 plans declare it) | pycopg 1.0.0 released to PyPI via OIDC — version bump, CHANGELOG, MIGRATION, 5 gates, tag, clean-venv smoke | SATISFIED (functionally) — but see gap below on REQUIREMENTS.md bookkeeping | All sub-claims independently verified above: version bump ✓, CHANGELOG ✓, MIGRATION ✓, 5 gates ✓ (3 re-run live, 2 accepted from SUMMARY record), tag ✓, PyPI live ✓, smoke ✓ |

**Traceability discrepancy found (non-blocking, documentation-only):** `.planning/REQUIREMENTS.md` line 67 still shows `- [ ] **REL-11**` (unchecked checkbox) and the traceability table (line 147) lists `| REL-11 | Phase 47 | Pending |` — both stale. This mirrors the exact "REQUIREMENTS.md checkbox-vs-traceability-table drift at close" pattern already logged as a recurring GSD tooling tax in project memory. The underlying work is verified complete and live on PyPI; only the requirements-tracking document was not updated. This does not block phase-goal achievement (the goal is about the release being live, which it is) but should be corrected as a trivial fix-up.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | none found | — | Scanned all phase-modified files (`pycopg/spatial.py`, `docs/api-reference.md`, `CHANGELOG.md`, `MIGRATION.md`, `pyproject.toml`, `docs/conf.py`) for TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER — zero matches |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| mypy strict gate | `uv run mypy pycopg/` | "Success: no issues found in 18 source files" | PASS (re-run live) |
| interrogate gate | `uv run interrogate -c pyproject.toml pycopg` | "PASSED (minimum: 95.0%, actual: 100.0%)" | PASS (re-run live) |
| Sphinx `-W` gate | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | exit 0, "La compilation a réussi" | PASS (re-run live) |
| uv.lock consistency | `uv lock --check` | "Resolved 48 packages", exit 0 | PASS (re-run live) |
| PyPI artifact live | `curl pypi.org/pypi/pycopg/1.0.0/json` | version 1.0.0, wheel+sdist present | PASS (re-run live, external) |
| GitHub Release state | `gh release view v1.0.0` | published, not draft, not prerelease | PASS (re-run live, external) |
| Publish workflow result | `gh run view 28597685797` | conclusion: success | PASS (re-run live, external) |
| Coverage gate (≥95%) | `PGDATABASE=pycopg_test3 uv run pytest` | not re-run this session (SUMMARY: 96.45%, 1736 passed/2 skipped) | SKIP (accepted per task brief — optional, ~90s, other 3 cheap gates corroborate environment is sound) |
| DeprecationWarning gate | `PGDATABASE=pycopg_test3 uv run pytest -W error::DeprecationWarning` | not re-run this session (SUMMARY: exit 0, no caveat triggered) | SKIP (accepted per task brief) |

### Human Verification Required

None. All must-haves were verifiable programmatically or via external service query (PyPI API, GitHub API), and all returned confirming evidence. No visual/UX/real-time behavior in this phase.

### Gaps Summary

No blocking gaps. One non-blocking documentation drift was found: `REQUIREMENTS.md` still shows REL-11 as unchecked/"Pending" despite the release being complete, verified, and live on PyPI. This is consistent with a previously-logged recurring pattern in this project (REQUIREMENTS.md checkbox-vs-traceability-table drift at milestone close) and does not affect the phase goal, which concerns the release itself being live — confirmed true via independent PyPI/GitHub API checks, tag verification, and gate re-runs.

---

_Verified: 2026-07-02T16:45:00Z_
_Verifier: Claude (gsd-verifier)_
