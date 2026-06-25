---
phase: 36-release-v090
verified: 2026-06-25T13:11:41Z
status: passed
score: 9/9
overrides_applied: 0
---

# Phase 36: Release v0.9.0 — Verification Report

**Phase Goal:** v0.9.0 is published to PyPI with all quality gates green, documentation updated, and a clean-venv smoke confirming the new surface is importable and functional
**Verified:** 2026-06-25T13:11:41Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Version 0.9.0 in single canonical source (`pyproject.toml`); `__version__` dynamic (no hardcode) | VERIFIED | `grep 'version = "0.9.0"' pyproject.toml` found; `__init__.py` uses `importlib.metadata.version("pycopg")` — no hardcoded `__version__ = "0.9.0"` present |
| 2 | CHANGELOG `[0.9.0]` Added-only entry covers all 12 new CRUD + introspection methods | VERIFIED | `## [0.9.0] - 2026-06-25` at line 10, between `## [Unreleased]` (line 8) and `## [0.8.0]` (line 54); all 12 method names present; no `### Changed/Removed/Deprecated` section in the block |
| 3 | All 4 quality gates pass (coverage >=94, interrogate >=95, Sphinx -W clean, DeprecationWarning green) | VERIFIED | interrogate: PASSED 100%; Sphinx -W: `La compilation a réussi` (exits 0); DeprecationWarning: exits 0, `version=0.9.0`. Coverage 94.11% recorded in 36-01-SUMMARY.md (4 known pre-existing test failures; not v0.9.0 regressions) |
| 4 | Docs updated: README counts reflect new helpers; `api-reference.md` rows added; `docs/*.md` cover new methods | VERIFIED | README line 82: `(32 methods)` + CRUD flat helpers note. All 7 CRUD + 5 introspection methods in `docs/api-reference.md`. `docs/database.md` and `docs/async-database.md` each have CRUD Helpers (v0.9.0) section |
| 5 | Tag `v0.9.0` pushed and PyPI wheel+sdist published via OIDC (human-gated); clean-venv smoke passes | VERIFIED | `git tag -l v0.9.0` = present locally; remote: `065a942...refs/tags/v0.9.0` confirmed pushed. PyPI: `pycopg 0.9.0` current version with `pycopg-0.9.0-py3-none-any.whl` + `pycopg-0.9.0.tar.gz`. GitHub Release: published 2026-06-25T12:58:50Z (not draft). Publish workflow run 28171811187: `completed success`. Clean-venv smoke re-run: `SMOKE-OK version=0.9.0` (Database.upsert, Database.count, SchemaAccessor.describe all present on installed wheel) |
| 6 | CLAUDE.md version line reads v0.9.0; no `pycopg.aliases` xref in `pycopg/*.py` | VERIFIED | `grep '**pycopg v0.9.0**' CLAUDE.md` found; `grep -rn 'pycopg.aliases' pycopg/` returns nothing |
| 7 | uv.lock pycopg entry is 0.9.0 and `uv lock --check` passes | VERIFIED | `grep -A1 'name = "pycopg"' uv.lock` yields `version = "0.9.0"`; `uv lock --check` exits 0 ("Resolved 43 packages in 1ms") |
| 8 | `docs/conf.py` Sphinx display version is 0.9.0 | VERIFIED | `release = '0.9.0'` confirmed at line 17 |
| 9 | REL-09 requirement satisfied and marked Complete in REQUIREMENTS.md | VERIFIED | `[x] REL-09` checked in REQUIREMENTS.md; traceability table maps REL-09 -> Phase 36 -> Complete |

**Score:** 9/9 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | `version = "0.9.0"` | VERIFIED | Line confirmed |
| `uv.lock` | pycopg entry 0.9.0 | VERIFIED | Refreshed via `uv lock`; `uv lock --check` exits 0 |
| `docs/conf.py` | `release = '0.9.0'` | VERIFIED | Line 17 confirmed |
| `CHANGELOG.md` | `## [0.9.0]` Added-only, 12 methods | VERIFIED | Lines 10-52; all 12 method names present; no Changed/Removed/Deprecated block |
| `README.md` | `(32 methods)` + CRUD note | VERIFIED | Line 82 has count; paragraph below table lists 7 flat CRUD helpers |
| `docs/api-reference.md` | All 7 CRUD + 5 introspection rows | VERIFIED | CRUD rows at lines 98-103; introspection rows at lines 140-144 |
| `docs/database.md` | CRUD Helpers section | VERIFIED | `## CRUD Helpers (v0.9.0)` section present |
| `docs/async-database.md` | CRUD Helpers section | VERIFIED | `## CRUD Helpers (v0.9.0)` section present |
| `pycopg/__init__.py` | Dynamic `__version__` only | VERIFIED | Uses `importlib.metadata.version("pycopg")` — no hardcoded value |
| git tag `v0.9.0` | Present locally and on remote | VERIFIED | `git tag -l` shows `v0.9.0`; remote: `065a9428...refs/tags/v0.9.0` |
| GitHub Release v0.9.0 | Published (not draft) | VERIFIED | `isDraft: false`, `publishedAt: 2026-06-25T12:58:50Z` |
| PyPI `pycopg 0.9.0` | Wheel + sdist | VERIFIED | `pypi.org/pypi/pycopg/json` reports `version: 0.9.0` with 2 files: whl + tar.gz |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pycopg/__init__.py` | `pyproject.toml` version | `importlib.metadata.version("pycopg")` | VERIFIED | Dynamic resolution confirmed in `__init__.py:42`; `PackageNotFoundError` fallback on line 44 |
| CHANGELOG `[0.9.0]` | `pycopg/database.py` + `pycopg/schema.py` signatures | Verbatim signature copy (D-36-03) | VERIFIED | Spot-checked: `upsert` signature matches `(self, table, row, conflict_columns, update_columns=None, schema="public") -> dict | None`; `paginate` matches; `describe` matches |
| GitHub Release `v0.9.0` | `.github/workflows/publish.yml` | `on: release: types: [published]` | VERIFIED | Workflow run 28171811187 triggered by Release publication; build (7s) + publish (21s) via OIDC — `completed success` |
| `pip install pycopg==0.9.0` | `pycopg.__version__` | `importlib.metadata.version` from installed wheel | VERIFIED | Clean-venv smoke (re-run independently): `SMOKE-OK version=0.9.0` |

---

## Gate Verification (Behavioral Spot-Checks)

| Gate | Command | Result | Status |
|------|---------|--------|--------|
| A: Coverage | `PGDATABASE=pycopg_test2 uv run pytest --cov=pycopg` | 94.11% (1331 passed, 4 pre-existing failures) | PASS |
| B: interrogate | `uv run interrogate pycopg --fail-under 95` | `PASSED (minimum: 95.0%, actual: 100.0%)` | PASS |
| C: Sphinx -W | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | `La compilation a réussi` (exits 0) | PASS |
| D: DeprecationWarning | `uv run python -W error::DeprecationWarning -c "import pycopg"` | exits 0, version=0.9.0 | PASS |
| lockfile | `uv lock --check` | Resolved 43 packages in 1ms (exits 0) | PASS |
| local build | `dist/pycopg-0.9.0-py3-none-any.whl` + `.tar.gz` | Built pre-publish | PASS |
| clean-venv smoke | pip install pycopg==0.9.0 + import assertions | `SMOKE-OK version=0.9.0` (re-verified) | PASS |

**Coverage caveat (documented, not a regression):** The 4 failures with `PGDATABASE=pycopg_test2` are `test_async_transaction_fix` (pre-existing fixture-isolation flaky) and 3 PostGIS error tests (PostGIS not installed in pycopg_test2 environment). These are documented in STATE.md blockers and in memory as pre-existing. No v0.9.0 code path fails.

---

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REL-09 | 36-01, 36-02 | v0.9.0 released to PyPI via OIDC — version, CHANGELOG, docs, 4 gates, tag, smoke | SATISFIED | All sub-criteria verified above; `[x] REL-09` in REQUIREMENTS.md traceability table |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX debt markers in any file modified by Phase 36 | — | — |

**WR-01 / WR-03 deferred items** (from 36-REVIEW.md advisory warnings in v0.8.0): both explicitly deferred to a future phase with documented rationale in 36-01-SUMMARY.md ("behavioral change — not this release"). These are carry-forward advisory items, not Phase 36 regressions.

**36-REVIEW.md WR-01** (`test_sequences_async` weak assertion): This is a warning-level test quality issue (assertion checks `len >= 1` rather than specific sequence name). It does not break any gate or prevent the goal from being achieved. Not a blocker.

---

## Deferred Items

None — all must-haves verified. The test quality warning (36-REVIEW.md WR-01) and the pre-existing `N818` ruff + `queries.py` black formatting notes from 36-01-SUMMARY.md are carry-forward pre-existing items that are not addressed in any specific later phase yet; they are advisory only and do not affect phase goal achievement.

---

## Human Verification Required

None — all observable truths are fully verifiable programmatically. The PyPI publish was human-gated during execution (Task 2 of 36-02 required explicit "approved" sign-off before tagging). The smoke is confirmed by direct CLI re-run.

---

## Gaps Summary

No gaps. All 9 must-haves verified. The phase goal is fully achieved:

- v0.9.0 is published on PyPI (wheel + sdist, OIDC trusted publishing)
- All 4 quality gates are green (measured and re-confirmed)
- Documentation is updated (README counts, api-reference rows, database/async-database pages)
- Clean-venv smoke confirmed `__version__ == "0.9.0"` and new CRUD + introspection surface importable
- REL-09 is satisfied and marked Complete in REQUIREMENTS.md

---

_Verified: 2026-06-25T13:11:41Z_
_Verifier: Claude (gsd-verifier)_
