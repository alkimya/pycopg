---
phase: 14
slug: spatial-helpers-phase-8-r-alis-e
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-12
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio_mode = "auto") |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~60 seconds (full suite with coverage gate) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -o addopts=""` (scoped to touched test files for speed)
- **After every plan wave:** Run `uv run pytest` (full suite with coverage gate)
- **Before `/gsd-verify-work`:** Full suite must be green (modulo 3 known pre-existing flaky DB tests — not regressions)
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | SPA-02, SPA-03, SPA-04 | T-14-01 | identifiers via validate_identifiers (≥11 calls); values via %s only, no f-string coords | unit (import) | `uv run python -c "import pycopg.spatial as s; ..."` (builder presence assert) | ❌ W0 | ⬜ pending |
| 14-01-02 | 01 | 1 | SPA-06 | — | exact (sql, params) assertions per builder branch | unit (DB-free) | `uv run pytest tests/test_spatial.py::TestGeometryResolver tests/test_spatial.py::TestBuilders -x -q -o addopts=""` | ❌ W0 | ⬜ pending |
| 14-02-01 | 02 | 2 | SPA-02, SPA-04 | T-14-02 | PostGIS guard → ExtensionNotAvailable; into="gdf" on scalar → ValueError | unit (import) | `uv run python -c "from pycopg.spatial import SpatialAccessor, AsyncSpatialAccessor; ..."` | ❌ W0 | ⬜ pending |
| 14-02-02 | 02 | 2 | SPA-05 | — | lazy property, deferred import | unit (import) | `uv run python -c "from pycopg import Database, AsyncDatabase, SpatialAccessor, AsyncSpatialAccessor; ..."` | ❌ W0 | ⬜ pending |
| 14-02-03 | 02 | 2 | SPA-05, SPA-06 | T-14-04 / T-14-08 | guard tested via mock; where= raw-fragment convention documented | integration + parity | `uv run pytest tests/test_spatial.py::TestGuard tests/test_spatial.py::TestIntegration tests/test_parity.py -x -q -o addopts=""` | ❌ W0 | ⬜ pending |
| 14-03-01 | 03 | 1 | SPA-01 | — | N/A (documentation) | grep gate | `grep -Eq "D-01" .planning/phases/08-spatial-helpers/08-DESIGN.md && ! grep -qi "Points à TRANCHER" ...` | ✅ | ⬜ pending |
| 14-04-01 | 04 | 3 | SPA-06 | — | coverage cliquet capped, never lowered | full suite | `uv run pytest -o addopts="" -q && uv run pytest -q && uv run interrogate pycopg` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_spatial.py` — DB-free pure-builder tests (exact SQL string + params assertions) for SPA-02, SPA-03, SPA-04
- [ ] PostGIS integration tests (local pycopg_test db, postgis installed) for SPA-03, SPA-06
- [ ] `tests/test_parity.py` — auto-detects `spatial` property on both Database and AsyncDatabase (SPA-05); sync + async accessors must land in the same wave

*Existing infrastructure (pytest, conftest fixtures, pycopg_test db with PostGIS 3.6.3) covers framework needs — no install required.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification — pure builders assert exact SQL without DB; accessors covered by PostGIS integration tests; parity by test_parity.py.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
