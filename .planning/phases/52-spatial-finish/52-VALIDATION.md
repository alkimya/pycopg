---
phase: 52
slug: spatial-finish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-04
---

# Phase 52 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from 52-RESEARCH.md "## Validation Architecture". Per-task rows are finalized once PLAN.md files exist.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (+ pytest-asyncio for the async accessor mirror; already configured) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `addopts` enforces `--cov=pycopg --cov-fail-under=95` |
| **Quick run command** | `PGDATABASE=pycopg_test3 uv run pytest tests/test_spatial.py -x -q` |
| **Full suite command** | `PGDATABASE=pycopg_test3 uv run pytest` |
| **Estimated runtime** | ~20–60 s (spatial file quick; full suite longer) |

---

## Sampling Rate

- **After every task commit:** Run `PGDATABASE=pycopg_test3 uv run pytest tests/test_spatial.py -x -q`
- **After every plan wave:** Run `PGDATABASE=pycopg_test3 uv run pytest` (full suite, coverage gate enforced)
- **Before `/gsd-verify-work`:** Full suite green + `uv run mypy pycopg` (--strict, 0 errors) + interrogate 100% + Sphinx `-W` clean
- **Max feedback latency:** ~60 s

---

## Per-Task Verification Map

Requirement → test-type map (RESEARCH §Validation Architecture). Exact `{N}-PP-TT` task IDs are filled in after planning; every SPAT-F requirement below already has an automated command.

| Requirement | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|------------|-----------------|-----------|-------------------|-------------|
| SPAT-F01 | `gridSize=None` keeps overlay SQL byte-identical (D-03) | T-52-01 | `validate_identifiers` first; `gridSize` `%s`-bound | unit (pure SQL string) | `pytest tests/test_spatial.py -k "test_union_emits_st_union or test_difference_emits_st_difference or test_intersection_emits_st_intersection" -x` | ✅ regression guard |
| SPAT-F01 | `gridSize=<float>` emits 3rd `%s` arg | T-52-01 | float bound as `%s`, no client guard (D-02) | unit + DB integration | `PGDATABASE=pycopg_test3 pytest tests/test_spatial.py -k "grid_size" -x` | ❌ W0 |
| SPAT-F02 | `length` ST_Length scalar, `unit=m/srid`; 0 for non-linear (D-10) | T-52-01 | identifiers validated; unit whitelisted via `_validate_unit` | unit + DB integration | `PGDATABASE=pycopg_test3 pytest tests/test_spatial.py -k "length" -x` | ❌ W0 |
| SPAT-F03 | `envelope` ST_Envelope geometry column, into=rows/gdf (D-11) | T-52-01 | identifiers validated | unit + gdf routing | `pytest tests/test_spatial.py -k "envelope" -x` | ❌ W0 |
| SPAT-F04 | `point_on_surface` geometry (NOT scalar x/y) (D-05) | T-52-01 | identifiers validated | unit + gdf routing | `pytest tests/test_spatial.py -k "point_on_surface" -x` | ❌ W0 |
| SPAT-F05 | `is_valid`/`is_valid_reason` scalar rows-only; `_SCALAR_HELPERS` gdf-rejection (D-12) | T-52-01 | identifiers validated; `_check_into` rejects gdf | unit + guard | `pytest tests/test_spatial.py -k "is_valid" -x` | ❌ W0 |
| SPAT-F06 | `overlaps`/`touches`/`crosses`/`disjoint` — 4 input forms + EXISTS `ref=` + into=rows/gdf (D-06/D-07) | T-52-01 | `_resolve_geometry` `%s`-binds all values | unit (SQL string) + gdf routing | `pytest tests/test_spatial.py -k "overlaps or touches or crosses or disjoint" -x` | ❌ W0 |
| SPAT-F01..F06 | injection test per new builder (standing bar) | T-52-01 | `InvalidIdentifierError` on malicious `table`/`schema`/`geom`/`columns` | unit | `pytest tests/test_spatial.py -k "invalid_table or invalid_column" -x` | ❌ W0 (extend parametrized pattern) |
| Standing bar | sync/async parity for all 9 new methods | — | — | parity (name-generic, auto-extends) | `pytest tests/test_parity.py -x` | ✅ exists |
| Standing bar | mypy --strict clean incl. new `@overload` stubs | — | — | static | `uv run mypy pycopg` | ✅ exists |
| Standing bar | coverage ≥95% | — | — | coverage | `uv run pytest` | ✅ exists |
| Standing bar | interrogate 100% (numpydoc) | — | — | static | `uv run interrogate pycopg` | ✅ exists |
| Standing bar | Sphinx `-W` clean | — | — | doc build | `uv run sphinx-build -W docs docs/_build` | ✅ exists |

*Status legend: ✅ green · ❌ red · ⚠️ flaky · ⬜ pending*

---

## Wave 0 Requirements

New tests to add in `tests/test_spatial.py` (all extend existing conventions — no new framework/fixture files needed):

- [ ] `tests/test_spatial.py::TestBuilders` — SQL-string tests for all 9 new/changed methods (mirror `contains`/`intersects`/`union`/`area`/`perimeter`/`make_valid` exact-string-assertion style)
- [ ] Extend `_HELPER_CALLS` (~line 1667) and `_GDF_CALLS` (~line 1692) fixtures with the 9 new method entries (predicates go in `_GDF_CALLS` per the amended D-06 into= decision) → auto-covers `TestAccessorRouting` sync/async rows+gdf
- [ ] Extend `TestGuard` scalar-gdf-rejection parametrize (~line 862) with `length`, `is_valid`, `is_valid_reason`
- [ ] `tests/test_spatial.py::TestIntegration` live-DB tests: gridSize positive-path (server 3.6.4/GEOS 3.13.1 supports it), `length` polygon=0 proof, `disjoint` EXISTS-quantifier footgun proof
- [ ] Injection test per new builder — extend existing `test_*_invalid_table`/`test_*_invalid_column` pattern for each of the 9 new/changed builders

*Infrastructure otherwise complete: pytest + PostGIS 3.6.4 + GEOS 3.13.1 on `pycopg_test3` fully sufficient (RESEARCH §Environment Availability).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | All phase behaviors have automated verification (unit + live-DB integration). |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter (set at Wave 0 completion during execution)

**Approval:** pending
