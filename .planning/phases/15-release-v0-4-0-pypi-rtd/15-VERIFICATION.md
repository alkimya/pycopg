---
status: passed
phase: 15-release-v0-4-0-pypi-rtd
goal: "Livrer v0.4.0 sur PyPI + ReadTheDocs."
requirements: [REL-01, REL-02, REL-03, REL-04, REL-05, REL-06]
verified: 2026-06-14
score: 6/6
method: direct re-check + SUMMARY/audit cross-reference (verifier agent died on a socket error after producing no file; orchestrator completed verification directly)
---

# Phase 15 Verification — Release v0.4.0 (PyPI + RTD)

**Goal:** Livrer v0.4.0 sur PyPI + ReadTheDocs.
**Verdict:** ✅ PASSED — 6/6 must-haves satisfied. v0.4.0 is live on PyPI and RTD.

## Requirements coverage (6/6)

| REQ | Criterion | Evidence | Status |
|-----|-----------|----------|--------|
| REL-01 | Sphinx docs updated: PostGIS `execute()` → helpers; api-reference regenerated | `docs/postgis.md` has 16 `db.spatial.*` calls; `docs/spatial.md` (296 lines) exists & in index toctree; `.. automodule:: pycopg.spatial` in api-autodoc.md; "Spatial Helpers (db.spatial.*)" section in api-reference.md; `sphinx-build -W` exit 0; `interrogate --fail-under 95` exit 0 | ✅ |
| REL-02 | ReadTheDocs build green (`.readthedocs.yaml` validated, RTD live) | `.readthedocs.yaml` validated & unchanged; `pycopg.spatial` imports without geopandas; **maintainer confirmed the live RTD build green** (15-05-SUMMARY.md, resume-signal "approved") | ✅ |
| REL-03 | CHANGELOG v0.4.0; version bumped everywhere; MIGRATION notes | `pyproject.toml` version "0.4.0" (0 leftover 0.3.1); `docs/conf.py` `release = '0.4.0'` (line 17); `## [0.4.0]` in CHANGELOG; `Migration Guide: v0.3.x to v0.4.0` in MIGRATION.md; `import pycopg → 0.4.0`; `uv lock --check` clean | ✅ |
| REL-04 | Wheel published to PyPI via uv build + GitHub release; tag created | git tag `v0.4.0` on origin (`30ff8ee`); GitHub Release published → `publish.yml` OIDC publish; **clean-venv `pip install pycopg==0.4.0` verified, `__version__` == 0.4.0**; maintainer confirmed "published" | ✅ |
| REL-05 | GitHub Actions Node 20 → Node 24 | No `@v4` checkout/upload/download-artifact remain; `actions/checkout@v6`, `upload-artifact@v7`, `download-artifact@v8` (live-verified node24 majors); OIDC `id-token: write` intact | ✅ |
| REL-06 | Milestone audit passes before archiving | `.planning/v0.4.0-MILESTONE-AUDIT.md` status: passed (46/46 requirements, 7/7 phases, 4/4 integration flows, 0 broken links) | ✅ |

## Plan completion

All 6 plans have SUMMARY.md (15-01 … 15-06) and are marked `[x]` in ROADMAP.

## Known non-blocking items (not phase-15 gaps)

- **Pre-existing flaky DB tests** (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`, `test_create_constructor_parity`) fail in the local Postgres env — documented pre-existing/environment failures. Phase 15 changed **no library source** (`pycopg/` is byte-identical to the pre-phase base), so these cannot be phase-15 regressions. The pre-publish gate (15-04) measured 94.09% coverage at the ≥94% gate with only these flakes failing.
- **TableNotFound** is exported but has no internal raise site (user-`except` only). Benign.
- **Phase 12 coverage-95 stretch** unmet (actual 90→92/94) — tracked as milestone tech debt; REF-01..05 requirements are satisfied.

## Security note

Each plan carried its own threat model (T-15-01..06): docs-only threats `accept`; supply-chain
threats `mitigate` (OIDC present, no hardcoded PyPI token, wheel inspected — performed in
15-04/15-06). No 15-SECURITY.md was generated; `/gsd-secure-phase 15` can formalize this if
required by the security-enforcement gate.
