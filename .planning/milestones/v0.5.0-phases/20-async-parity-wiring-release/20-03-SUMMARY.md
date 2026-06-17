---
phase: 20-async-parity-wiring-release
plan: "03"
subsystem: release
tags: [release, version-bump, changelog, migration, coverage, sphinx, interrogate, pypi]
dependency_graph:
  requires: [phases/20-async-parity-wiring-release/20-01, phases/20-async-parity-wiring-release/20-02]
  provides: [v0.5.0 release artifacts, CHANGELOG [0.5.0], MIGRATION v0.5.0, all gates green]
  affects: [pyproject.toml, docs/conf.py, uv.lock, CHANGELOG.md, MIGRATION.md, tests/test_etl_accessor.py]
tech_stack:
  added: []
  patterns: [keep-a-changelog, uv-release-playbook, coverage-ratchet]
key_files:
  created: []
  modified:
    - pyproject.toml
    - docs/conf.py
    - uv.lock
    - CHANGELOG.md
    - MIGRATION.md
    - tests/test_etl_accessor.py
decisions:
  - "Version bumped to 0.5.0 in pyproject.toml + docs/conf.py; uv.lock refreshed via uv lock"
  - "pycopg.__version__ resolves to 0.5.0 via importlib.metadata after uv sync (no __init__.py edit needed)"
  - "Coverage shortfall addressed by adding 9 async + 4 sync ETL branch tests (93.25% initial → 94.26% final)"
  - "Gate B (interrogate) and Gate C (Sphinx -W) passed on first attempt — no docstring or doc fixes needed"
  - "uv build dist/pycopg-0.5.0* produced locally for pre-publish verification"
  - "STOP BEFORE publish: no git tag, no push, no GitHub Release — orchestrator handles with human sign-off"
metrics:
  duration: "~25 minutes"
  completed: "2026-06-16"
  tasks_completed: 2
  tasks_total: 3
  files_changed: 6
---

# Phase 20 Plan 03: v0.5.0 Release Prep Summary

Version bumped `0.4.0 → 0.5.0` across all locations, lockfile refreshed, CHANGELOG `[0.5.0]`
and MIGRATION `v0.4.x → v0.5.0` written, all three release gates green (coverage 94.26%,
interrogate >=95, Sphinx -W clean). Distribution artifacts built locally. STOP before publish.

**RELEASE PREP COMPLETE — AWAITING PUBLISH SIGN-OFF**

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Bump version 0.4.0→0.5.0, refresh lockfile, write CHANGELOG + MIGRATION | 5405b99 | pyproject.toml, docs/conf.py, uv.lock, CHANGELOG.md, MIGRATION.md |
| 2 | Add ETL branch coverage tests to clear 94% gate | 6f1eaaa | tests/test_etl_accessor.py |

Task 3 (tag + push + publish) is intentionally NOT executed — blocked by `<publish_boundary>` /
`gate="blocking-human"`. The orchestrator will handle tagging, pushing, and creating the GitHub
Release with explicit human sign-off.

## What Was Built

### Task 1: Version Bump + CHANGELOG + MIGRATION

**`pyproject.toml`:** `version = "0.5.0"` (was `"0.4.0"`)

**`docs/conf.py`:** `release = '0.5.0'` (was `'0.4.0'`)

**`uv.lock`:** Re-pinned `pycopg v0.4.0 -> v0.5.0` via `uv lock`; `uv lock --check` exits 0.

**`pycopg.__version__`:** Resolves to `"0.5.0"` via `importlib.metadata` after `uv sync --all-extras --dev`.
No edit to `pycopg/__init__.py` was needed (auto-resolves from installed package metadata per RESEARCH §16).

**`CHANGELOG.md`:** Added `## [0.5.0] - 2026-06-15` section directly under `## [Unreleased]`
(per Keep-a-Changelog format). Under `### Added` documents the full ETL milestone scope
(Phases 16-20): `db.etl.*` / `async_db.etl.*` namespace, `Pipeline` dataclass, `pipeline_runs`
auto-creation, `RunResult`, `ETLAccessor`/`AsyncETLAccessor` lazy accessors, exception hierarchy,
top-level exports, `asyncio.to_thread` dispatch, zero new runtime deps. Compare-link footer
updated: `[Unreleased]` → `compare/v0.5.0...HEAD`; new `[0.5.0]: compare/v0.4.0...v0.5.0`.

**`MIGRATION.md`:** Added `# Migration Guide: v0.4.x to v0.5.0` section at the end. No breaking
changes. Additive-only: describes the ETL namespace, `Pipeline`, `RunResult`, `db.etl.init()`,
sync/async usage examples, transform callables, new top-level exports. Upgrade checklist included.

### Task 2: Coverage Gate — ETL Branch Tests

Initial full-suite run: 93.25% (below 94% gate). The shortfall was in uncovered ETL branches:
- Async dry-run + `extract_limit` + table source
- Async dry-run + transform list
- Async transform list in normal run
- Async empty DataFrame early-return
- Async exception path (`status='failed'` recording)
- Async `upsert` / `append` load modes
- Async `ETLTargetNotFoundError`
- Sync dry-run + `extract_limit` (SQL source)
- Sync dry-run + transform list
- Sync normal run + `extract_limit`
- Sync empty DataFrame early-return

Added **9 async tests** to `TestAsyncRunResultSurface` and **4 sync tests** to `TestRunResultSurface`
in `tests/test_etl_accessor.py`. These exercise the ETL branch paths listed above. Final coverage:
**94.26%** (gate: >=94%). All new tests pass.

## Release Gate Results

### Gate A — Coverage (SC-5)

**Command:** `uv run pytest` (bare full suite, NOT `-o addopts=""`)

**Result: PASSED — 94.26% >= 94%**

```
Name                       Stmts   Miss  Cover   Missing
--------------------------------------------------------
pycopg/__init__.py            15      2    87%   38-39
pycopg/async_database.py     695     62    91%   ...
pycopg/base.py               144      0   100%
pycopg/config.py              92      5    95%   ...
pycopg/database.py           668     63    91%   ...
pycopg/etl.py                319     15    95%   820, 840, 847-848, 1280, 1300, ...
pycopg/exceptions.py          22      0   100%
pycopg/migrations.py         121      0   100%
pycopg/pool.py               114      0   100%
pycopg/queries.py             31      0   100%
pycopg/spatial.py            288      0   100%
pycopg/utils.py               54      0   100%
--------------------------------------------------------
TOTAL                       2563    147    94%
Required test coverage of 94% reached. Total coverage: 94.26%
```

**Test outcomes:** 981 passed, 2 failed (known-flaky), 2 skipped

**Known-flaky failures (2) — NOT regressions:**
- `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — pre-existing
  `UndefinedTable`/bad connection state failure (environment-specific; confirmed in project memory)
- `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter`
  — pre-existing `UndefinedTable` failure (environment-specific; confirmed in project memory)

**Real failures (0 expected):** Zero. No ETL/parity/behavioral tests failed.

Third pre-existing known-flaky test (`TestBehavioralParity::test_create_constructor_parity` —
ObjectInUse race) did not trigger in this run.

### Gate B — Docstrings (SC-5)

**Command:** `uv run interrogate pycopg --fail-under 95 --quiet`

**Result: PASSED — exit 0 (no output, gate passed on first attempt)**

No docstring gaps: `AsyncETLAccessor` and all its methods were already documented with full
numpydoc docstrings in Plan 01.

### Gate C — Sphinx -W Build (SC-5)

**Command:** `uv run sphinx-build -W --keep-going -b html docs docs/_build/html`

**Result: PASSED — "La compilation a réussi." (build succeeded, 0 warnings)**

`docs/etl.md` added to toctree in Plan 02 — no orphan-document warning. All cross-references
resolve cleanly.

### Pre-publish Verification

**`uv build`:** Succeeded — produced `dist/pycopg-0.5.0-py3-none-any.whl` and
`dist/pycopg-0.5.0.tar.gz`.

**`uv lock --check`:** Exits 0 — lockfile is current (required by CI publish gate).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing coverage] Added ETL branch tests to clear 94% gate**
- **Found during:** Task 2 (Gate A)
- **Issue:** Initial full-suite coverage was 93.25% — 0.75% below the 94% ratchet. The shortfall
  was entirely in uncovered ETL branches (sync + async dry-run/extract_limit/transform-list/empty-DF
  / exception paths), not in any regression. The existing `TestAsyncRunResultSurface` (7 tests)
  covered the main happy-paths only.
- **Fix:** Added 9 async tests + 4 sync tests in `tests/test_etl_accessor.py` targeting the specific
  uncovered branches. Coverage: 93.25% → 93.95% (first attempt, still below) → 94.26% (final,
  PASSED).
- **Files modified:** `tests/test_etl_accessor.py`
- **Commit:** 6f1eaaa

### Worktree Base Recovery (infrastructure)

Worktree had forked from commit `333e070` (stale `origin/HEAD` — Phase 18 era) instead of the
dispatch base `104bce4` (Wave 2 completion). Since zero commits were ahead of the stale base,
`git reset --hard 104bce4816880175c7f07076c53db79b6bfc600d` was applied before any changes.
This is the documented recurring worktree-base-mismatch recovery pattern for this repository.
After reset, `docs/etl.md` was confirmed present (Wave 1/2 indicator).

## What Is NOT Done (Blocked — Human Sign-off Required)

Per `<publish_boundary>` directive in the task prompt, the following are intentionally NOT
performed by this executor:

- `git tag v0.5.0`
- `git push` (any push — tags or branch commits)
- `gh release create v0.5.0`
- Any invocation of `.github/workflows/publish.yml`

The orchestrator will merge this worktree branch to `main`, then handle tag + push + GitHub
Release with explicit human approval.

## Known Stubs

None — this plan modifies release metadata and test files only. No production code stubs.

## Threat Surface Scan

No new security surface introduced. This plan touches only release metadata (pyproject.toml,
docs/conf.py, uv.lock, CHANGELOG.md, MIGRATION.md) and test files. No new network endpoints,
auth paths, SQL, or identifier-interpolation paths. T-20-04 (supply-chain / PyPI publish) is
fully mitigated by the blocking human checkpoint on Task 3 — no publish occurred.

The built artifacts (`dist/pycopg-0.5.0-py3-none-any.whl` and `dist/pycopg-0.5.0.tar.gz`)
are local-only and have not been uploaded to PyPI.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| pyproject.toml version = "0.5.0" | FOUND (grep -q confirmed) |
| docs/conf.py release = '0.5.0' | FOUND (grep -q confirmed) |
| CHANGELOG.md [0.5.0] section | FOUND (grep -q confirmed) |
| CHANGELOG.md compare/v0.4.0...v0.5.0 link | FOUND (grep -q confirmed) |
| uv.lock pins pycopg 0.5.0 | FOUND (uv lock --check exits 0) |
| pycopg.__version__ == "0.5.0" | FOUND (python -c assert confirmed) |
| MIGRATION.md v0.5.0 section | FOUND |
| commit 5405b99 (Task 1) exists | FOUND |
| commit 6f1eaaa (Task 2 coverage) exists | FOUND |
| Gate A: coverage 94.26% >= 94% | PASSED |
| Gate B: interrogate exit 0 | PASSED |
| Gate C: sphinx-build -W exit 0 | PASSED |
| dist/pycopg-0.5.0-py3-none-any.whl | FOUND (uv build) |
| dist/pycopg-0.5.0.tar.gz | FOUND (uv build) |
| NO git tag / push / publish performed | CONFIRMED |
