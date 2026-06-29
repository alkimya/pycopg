---
phase: 43
slug: spatial-v2-spatial-aggregates
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-29
---

# Phase 43 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Full requirement→test map lives in `43-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (verified: `pyproject.toml` `[tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` + `tests/conftest.py` |
| **Quick run command** | `uv run pytest tests/test_spatial.py -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5s quick (SQL-shape + injection + routing) / ~30–60s full |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_spatial.py -x -q`
- **After every plan wave:** Run `uv run pytest` (full suite incl. parity + live integration)
- **Before `/gsd-verify-work`:** Full suite green AND coverage ≥95%
- **Max feedback latency:** ~5 seconds (quick run)

---

## Per-Task Verification Map

> Task IDs (`43-NN-MM`) are assigned when PLAN.md files are written. The authoritative
> requirement→behavior→command map is in `43-RESEARCH.md` § Validation Architecture →
> "Phase Requirements → Test Map" (28 rows across SPAT2-07/08/09 + parity + routing).
> Each plan task's `<automated>` block draws its command from that table.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 43-NN-MM | NN | 1 | SPAT2-07 | T-43-01 | malicious `table`/`geom`/`group_by` → `InvalidIdentifierError` before SQL | injection | `uv run pytest tests/test_spatial.py::TestAggregateBuilders -x` | ❌ W0 | ⬜ pending |
| 43-NN-MM | NN | 1 | SPAT2-08 | T-43-01 | malicious identifiers rejected pre-SQL | injection | `uv run pytest tests/test_spatial.py::TestAggregateBuilders -x` | ❌ W0 | ⬜ pending |
| 43-NN-MM | NN | 1 | SPAT2-09 | T-43-01 | malicious identifiers rejected pre-SQL | injection | `uv run pytest tests/test_spatial.py::TestAggregateBuilders -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_spatial.py` — new `TestAggregateBuilders` class (SQL-shape: aggregate fn, `AS <D-06 col>`, GROUP-BY-after-WHERE placement, `extent` `::text` vs `ST_SetSRID(...::geometry, int(srid))` branch, `filter`/`order_by`/`limit` tail)
- [ ] `tests/test_spatial.py` — injection tests: 3 builders × (malicious `table`, `geom`, `group_by`) = 9 assertions → `InvalidIdentifierError` before any SQL
- [ ] `tests/test_spatial.py` — live integration (`sdb` fixture): whole-table + grouped per aggregate + intentional-NULL fixture asserting D-07 pass-through
- [ ] `tests/test_spatial.py` — `_HELPER_CALLS` + `_GDF_CALLS` extended with the 3 new methods (gdf geom cols `collected`/`dissolved`/`extent`)
- [ ] `tests/test_parity.py` — `test_spatial_aggregates_surface` frozenset test for the 3 methods on both accessors

*Existing infrastructure (`test_accessor_parity`, `test_accessor_parameter_kind_parity`) auto-extends to the new methods — no new harness.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification (SQL-shape unit, injection, live PostGIS integration, parity, routing). None manual-only.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
