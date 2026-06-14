# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- ✅ **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 (shipped 2026-06-14)

## Phases

<details>
<summary>✅ v0.4.0 Quality & Spatial Helpers (Phases 9-15) — SHIPPED 2026-06-14</summary>

- [x] Phase 9: Migration uv (outillage : dev + CI + build + lockfile) — completed 2026-06-06
- [x] Phase 10: Sécurité résiduelle & robustesse (bugs B1/B2/B3/B5) — coverage cliquet → 80 — completed 2026-06-08
- [x] Phase 11: Parité sync/async complète — coverage cliquet → 90 — completed 2026-06-09
- [x] Phase 12: Refactoring (brancher base.py + queries.py) — coverage cliquet → 92 (95 stretch deferred) — completed 2026-06-09
- [x] Phase 13: Qualité documentaire (docstrings numpydoc + interrogate ≥ 95) — completed 2026-06-10
- [x] Phase 14: Spatial helpers (`db.spatial.*`, ex-Phase 8) — coverage cliquet → 94 — completed 2026-06-12
- [x] Phase 15: Release v0.4.0 (PyPI + ReadTheDocs) — completed 2026-06-14

Full details: [milestones/v0.4.0-ROADMAP.md](milestones/v0.4.0-ROADMAP.md) · Requirements: [milestones/v0.4.0-REQUIREMENTS.md](milestones/v0.4.0-REQUIREMENTS.md) · Audit: [milestones/v0.4.0-MILESTONE-AUDIT.md](milestones/v0.4.0-MILESTONE-AUDIT.md)

</details>

<details>
<summary>✅ v0.3.0 Consolidation Release (Phases 1-7) — SHIPPED 2026-02-11</summary>

- [x] Phase 1: Bug Fixes & Foundation (2/2 plans) — completed 2026-02-11
- [x] Phase 2: AsyncDatabase DataFrame Parity (2/2 plans) — completed 2026-02-11
- [x] Phase 3: AsyncDatabase Admin/Backup Parity (2/2 plans) — completed 2026-02-11
- [x] Phase 4: AsyncDatabase Extensions Parity (2/2 plans) — completed 2026-02-11
- [x] Phase 5: Resilience & Configuration (2/2 plans) — completed 2026-02-11
- [x] Phase 6: Test Coverage (2/2 plans) — completed 2026-02-11
- [x] Phase 7: Documentation & Release (2/2 plans) — completed 2026-02-11

Full details: [milestones/v0.3.0-ROADMAP.md](milestones/v0.3.0-ROADMAP.md)

</details>

## Next Milestone

No active milestone. Start the next one with `/gsd-new-milestone` (questioning → research → requirements → roadmap). Candidate work lives in v2 requirements of the archived v0.4.0 requirements (API enhancements, ETL layer on top of the spatial helpers).

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Bug Fixes & Foundation | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 2. AsyncDatabase DataFrame Parity | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 3. AsyncDatabase Admin/Backup Parity | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 4. AsyncDatabase Extensions Parity | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 5. Resilience & Configuration | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 6. Test Coverage | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 7. Documentation & Release | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| — Security Hotfix v0.3.1 | v0.3.1 | — | Shipped | 2026-06-06 |
| 9. Migration uv (outillage) | v0.4.0 | 4/4 | Complete | 2026-06-06 |
| 10. Sécurité résiduelle & robustesse | v0.4.0 | 5/5 | Complete | 2026-06-08 |
| 11. Parité sync/async complète | v0.4.0 | 7/7 | Complete | 2026-06-09 |
| 12. Refactoring (base.py + queries.py) | v0.4.0 | 4/4 | Complete | 2026-06-09 |
| 13. Qualité documentaire (numpydoc + interrogate) | v0.4.0 | 6/6 | Complete | 2026-06-10 |
| 14. Spatial helpers (db.spatial.*) | v0.4.0 | 4/4 | Complete | 2026-06-12 |
| 15. Release v0.4.0 (PyPI + RTD) | v0.4.0 | 6/6 | Complete | 2026-06-14 |
