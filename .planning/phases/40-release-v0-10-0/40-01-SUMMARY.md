---
phase: 40-release-v0-10-0
plan: "01"
subsystem: release
tags: [release, changelog, version, coverage, sphinx, interrogate, pytest]

requires:
  - phase: 39-couverture-benchmarks
    provides: "coverage ratchet at 95%, benchmark suite, 96.32% measured coverage"
  - phase: 38-performance-copy
    provides: "COPY-routed from_dataframe/ETL/insert_batch, validate_identifiers regression fix"
  - phase: 37-dette-audit
    provides: "5 BLOCKER fixes, ruff clean, TableNotFound raise site, fixture isolation"

provides:
  - "Version bumped to 0.10.0 in all three canonical sources (pyproject.toml, uv.lock, docs/conf.py)"
  - "CHANGELOG [0.10.0] entry — Changed + Fixed only, Keep a Changelog, qualitative COPY perf with benchmarks/ pointer"
  - "All 4 release gates verified green (coverage 96.32%, interrogate 100%, Sphinx -W clean, -W error::DeprecationWarning clean)"
  - "Tree is committed and gates-green, ready for Plan 40-02 tag + OIDC publish"

affects: [40-02-PLAN, pypi-publish]

tech-stack:
  added: []
  patterns:
    - "Keep a Changelog: Changed + Fixed only (no Added) for a hardening release with no new public API"
    - "4-gate green-before-ship: coverage ≥95, interrogate ≥95, Sphinx -W, -W error::DeprecationWarning"

key-files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock
    - docs/conf.py
    - CHANGELOG.md
    - pycopg/pool.py

key-decisions:
  - "D-01 applied: CHANGELOG [0.10.0] uses Changed + Fixed only (no Added) — first release with no new public API"
  - "D-02 applied: COPY gains documented qualitatively with pointer to benchmarks/ (no hardcoded speedup numbers)"
  - "D-03 applied: minimal docs touch — version strings + CHANGELOG only, no README/RTD content changes"
  - "D-04 applied: no v1.0.0 / freeze / deprecation signaling in [0.10.0] entry"
  - "Deviation fix: ConnectionPool open=True added (df2f94f) to silence psycopg_pool DeprecationWarning before Gate 4"

patterns-established:
  - "Three-source version bump: pyproject.toml (manual edit) + docs/conf.py (manual edit) + uv.lock (uv lock regeneration)"
  - "uv lock --check as lockfile drift guard in release prep"

requirements-completed: [REL-10]

duration: 9min
completed: "2026-06-26"
---

# Phase 40 Plan 01: Release v0.10.0 Prep Summary

**v0.10.0 "Durcissement & Performance" tree prepared — version bumped in all 3 sources, Keep-a-Changelog [0.10.0] entry authored (Changed + Fixed, no Added), and all 4 release gates verified green (96.32% coverage, 100% interrogate, Sphinx -W clean, DeprecationWarning-error suite clean)**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-26T22:32:59Z
- **Completed:** 2026-06-26T22:41:40Z
- **Tasks:** 3 (Tasks 1 and 2 committed in prior run; Task 3 verified now)
- **Files modified:** 5 (pyproject.toml, uv.lock, docs/conf.py, CHANGELOG.md, pycopg/pool.py)

## Accomplishments

- Version bumped to 0.10.0 in all three canonical sources: `pyproject.toml` line 7, `docs/conf.py` line 17, and `uv.lock` pycopg entry (regenerated via `uv lock`); `uv lock --check` exits 0
- CHANGELOG `[0.10.0] - 2026-06-26` entry authored with strict Keep a Changelog structure (`### Changed` + `### Fixed` only, no `### Added`), qualitative COPY performance description pointing to `benchmarks/`, and all Phase 37–39 debt/fix highlights
- All 4 release gates verified green; tree is ready for Plan 40-02 to tag and publish
- Deviation fix applied (Rule 2): `ConnectionPool(open=True)` in `pycopg/pool.py` to silence `psycopg_pool` DeprecationWarning before Gate 4 could pass cleanly

## Task Commits

Each task was committed atomically:

1. **Task 1: Bump version in all three canonical sources** - `d921e6d` (chore)
2. **Task 2: Author the [0.10.0] CHANGELOG entry** - `3cb7afe` (docs)
3. **Deviation fix: ConnectionPool open=True** - `df2f94f` (fix) — applied between Tasks 2 and 3 to clear DeprecationWarning gate
4. **Task 3: Verify all 4 release gates** — verification only, no new commit (gates confirmed green)

**Plan metadata commit:** see Final Commit section below.

## Gate Verification Results (Task 3)

Each gate is recorded with its exact command and result.

### Gate 1: Coverage ≥95%

**Command:** `PGDATABASE=pycopg_test2 uv run pytest`

**Result:** PASSED — 1426 passed, 2 skipped, 1 failed, 1 warning in 84.62s

**Coverage:** Total 96.32% (`Required test coverage of 95% reached`)

**Known failure:** `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — pre-existing PostGIS-env limitation (PostGIS not installed in pycopg_test2). This is the only failure. Per plan notes and MEMORY, this is a documented environment constraint, not a regression. Gate treated as GREEN.

---

### Gate 2: interrogate ≥95% (docstring coverage)

**Command:** `uv run interrogate pycopg --fail-under 95 --quiet`

**Result:** PASSED — `RESULT: PASSED (minimum: 95.0%, actual: 100.0%)` — exit code 0

---

### Gate 3: Sphinx -W clean

**Command:** `uv run sphinx-build -W --keep-going -b html docs docs/_build/html`

**Result:** PASSED — `La compilation a réussi.` — exit code 0, no warnings escalated to errors

All 13 modules autodoc'd without warning. HTML written to `docs/_build/html/`.

---

### Gate 4: -W error::DeprecationWarning green

**Command:** `PGDATABASE=pycopg_test2 uv run pytest -W error::DeprecationWarning`

**Result:** PASSED — 1426 passed, 2 skipped, 1 failed, 1 warning in 80.56s

**Coverage:** 96.32%

**Known failure:** Same as Gate 1 — `test_create_spatial_index_name_parameter` (PostGIS-env limitation). No DeprecationWarning failures. Gate treated as GREEN.

The `open=True` fix (df2f94f) applied before this gate ensures `psycopg_pool.ConnectionPool` does not emit `DeprecationWarning` when called without `open=`.

---

### Gate Summary

| Gate | Command | Result | Status |
| ---- | ------- | ------ | ------ |
| 1. Coverage ≥95% | `PGDATABASE=pycopg_test2 uv run pytest` | 96.32%, 1 known PostGIS-env failure | GREEN |
| 2. interrogate 100% | `uv run interrogate pycopg --fail-under 95 --quiet` | 100.0% | GREEN |
| 3. Sphinx -W clean | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | 0 warnings, build success | GREEN |
| 4. -W error::DeprecationWarning | `PGDATABASE=pycopg_test2 uv run pytest -W error::DeprecationWarning` | 96.32%, 1 known PostGIS-env failure | GREEN |

## Files Created/Modified

- `pyproject.toml` — version bumped from `0.9.0` to `0.10.0` (line 7)
- `uv.lock` — pycopg editable entry version bumped to `0.10.0` via `uv lock` regeneration
- `docs/conf.py` — Sphinx `release` string bumped from `'0.9.0'` to `'0.10.0'` (line 17)
- `CHANGELOG.md` — new `## [0.10.0] - 2026-06-26` section inserted between `[Unreleased]` and `[0.9.0]`
- `pycopg/pool.py` — `ConnectionPool(open=True)` added to silence `psycopg_pool` DeprecationWarning (deviation fix)

## Decisions Made

- **D-01 applied:** CHANGELOG `[0.10.0]` uses `### Changed` + `### Fixed` only — no `### Added`. The absence of an Added section is intentional and correct for the first release with no new public API.
- **D-02 applied:** COPY performance gains described qualitatively ("higher-throughput bulk insertion for large DataFrames") with pointer to `benchmarks/` and `benchmarks/README.md`. No hardcoded speedup figures.
- **D-03 applied:** Minimal docs touch — only version strings and CHANGELOG modified. No README or RTD content changes.
- **D-04 applied:** No mention of v1.0.0, "freeze", or "deprecation" in the `[0.10.0]` CHANGELOG section.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] ConnectionPool open=True to clear DeprecationWarning**

- **Found during:** Task 3 (Gate 4 preparation)
- **Issue:** `psycopg_pool.ConnectionPool` emits `DeprecationWarning` when called without `open=` argument (psycopg-pool 3.2.x behavior change). Gate 4 (`-W error::DeprecationWarning`) would fail.
- **Fix:** Added `open=True` to `ConnectionPool(...)` call in `pycopg/pool.py` to explicitly opt in to the new default, silencing the warning.
- **Files modified:** `pycopg/pool.py`
- **Verification:** Gate 4 run passes cleanly with no DeprecationWarning failures.
- **Committed in:** `df2f94f` (fix(40-01): add open=True to ConnectionPool to silence psycopg_pool DeprecationWarning)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing explicit opt-in for psycopg_pool API change)
**Impact on plan:** Fix was required for Gate 4 to pass. No scope creep. The fix was committed as `fix(40-01)` and is already in the tree.

## Issues Encountered

- The prior executor run (which generated commits `d921e6d`, `3cb7afe`, `df2f94f`) had already completed Tasks 1 and 2 plus the deviation fix. This run completed Task 3 (gate verification) and created the SUMMARY.
- The `pycopg_test` database remains unusable (TimescaleDB catalog mismatch since 2026-06-24); all DB-touching commands used `PGDATABASE=pycopg_test2`.
- PostGIS-env limitation in `pycopg_test2` causes 1 test failure (`test_create_spatial_index_name_parameter`). Pre-existing, documented in MEMORY. Not a regression.

## Known Stubs

None — this is a release-prep plan with no new UI components or placeholder data.

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced. The `ConnectionPool` fix (pool.py) is internal-only and closes the DeprecationWarning surface.

## Next Phase Readiness

- v0.10.0 tree is committed, gates-green, and ready for Plan 40-02
- Plan 40-02: tag `v0.10.0` (annotated), OIDC-publish wheel + sdist to PyPI (human-gated), then clean-venv smoke confirming `__version__ == "0.10.0"`
- No blockers for Plan 40-02

---
*Phase: 40-release-v0-10-0*
*Completed: 2026-06-26*

## Self-Check: PASSED

- FOUND: `.planning/phases/40-release-v0-10-0/40-01-SUMMARY.md`
- FOUND: `pyproject.toml`, `CHANGELOG.md`, `docs/conf.py`
- FOUND commit: `d921e6d` (version bump)
- FOUND commit: `3cb7afe` (CHANGELOG entry)
- FOUND commit: `df2f94f` (ConnectionPool fix)
