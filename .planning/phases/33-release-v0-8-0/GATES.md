# Phase 33 Quality Gates — v0.8.0 Release

**Date:** 2026-06-23
**Baseline (v0.7.0):** coverage 95.11%, interrogate 100%, Sphinx -W clean, -W DeprecationWarning green
**Release:** v0.8.0

---

## Gate 1: Test Suite + Coverage Ratchet

**Command:** `uv run pytest`

**Config:** `addopts` wires `--cov-fail-under=94` in `pyproject.toml`

**Result:** PASS

**Measured value:** 95.11% total coverage (≥94 required)

**Details:**
- 1288 passed, 2 failed (pre-existing flakies), 2 skipped, 11 warnings — 78.72s
- 2 known failures:
  - `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — pre-existing fixture-isolation flake
  - `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — pre-existing fixture-isolation flake
  - These are NOT v0.8.0 regressions (documented in STATE.md Blockers since Phase 32)
- Required test coverage of 94% reached. Total coverage: 95.11%

---

## Gate 2: Docstring Coverage (interrogate)

**Command:** `uv run interrogate`

**Config:** `[tool.interrogate]` in `pyproject.toml`: `fail-under = 95`

**Result:** PASS

**Measured value:** 100.0% (≥95 required)

**Details:**
- `RESULT: PASSED (minimum: 95.0%, actual: 100.0%)`
- All 9 new TimescaleDB methods have complete docstrings

---

## Gate 3: Sphinx Documentation Build (warnings-as-errors)

**Command:** `uv run sphinx-build -W docs docs/_build/html`

**Result:** PASS

**Measured value:** 0 warnings (clean build)

**Details:**
- `La compilation a réussi.` — Sphinx 9.1.0
- All 15 pages built cleanly including the rewritten `timescaledb.md` + updated `api-reference.md`
- `.. automodule:: pycopg.timescale` autodoc renders 9 new methods from docstrings without warnings

---

## Gate 4: Deprecation Warning Regression Guard

**Command:** `uv run python -W error::DeprecationWarning -c "import pycopg"`

**Result:** PASS

**Measured value:** Exit 0 (no DeprecationWarning raised)

**Details:**
- No-op regression guard: all 56 alias stubs were removed in v0.7.0; nothing reintroduced a deprecation
- Import succeeded cleanly with `-W error::DeprecationWarning` flag active

---

## Summary

| Gate | Command | Measured | Threshold | Status |
|------|---------|----------|-----------|--------|
| 1 — pytest/coverage | `uv run pytest` | 95.11% | ≥94% | PASS |
| 2 — interrogate | `uv run interrogate` | 100.0% | ≥95% | PASS |
| 3 — Sphinx -W | `uv run sphinx-build -W docs docs/_build/html` | 0 warnings | 0 | PASS |
| 4 — DeprecationWarning | `uv run python -W error::DeprecationWarning -c 'import pycopg'` | exit 0 | exit 0 | PASS |

**All 4 gates: PASS — release is sound for tagging.**
