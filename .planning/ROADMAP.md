# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- 🔵 **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 — *validé 2026-06-06, prêt à exécuter*

## Phases

### 🔵 v0.4.0 Quality & Spatial Helpers (Phases 9-15) — EN COURS

Détails : [milestones/v0.4.0-MILESTONE.md](milestones/v0.4.0-MILESTONE.md) · Exigences : [REQUIREMENTS.md](REQUIREMENTS.md) (46 mappées, 0 non couverte) · Audit source : [AUDIT-2026-06-06.md](AUDIT-2026-06-06.md)

- [ ] Phase 9: Migration uv (outillage : dev + CI + build + lockfile)
- [ ] Phase 10: Sécurité résiduelle & robustesse (bugs B1/B2/B3/B5) — coverage cliquet → 80
- [ ] Phase 11: Parité sync/async complète — coverage cliquet → 90
- [ ] Phase 12: Refactoring (brancher base.py + queries.py) — coverage cliquet → 95
- [ ] Phase 13: Qualité documentaire (docstrings numpydoc + interrogate ≥ 95)
- [ ] Phase 14: Spatial helpers (`db.spatial.*`, ex-Phase 8) — trancher 4 points ouverts en début de phase
- [ ] Phase 15: Release v0.4.0 (PyPI + ReadTheDocs)

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
| 9. Migration uv (outillage) | v0.4.0 | 0/? | Pending (5 req) | — |
| 10. Sécurité résiduelle & robustesse | v0.4.0 | 0/? | Pending (6 req) | — |
| 11. Parité sync/async complète | v0.4.0 | 0/? | Pending (9 req) | — |
| 12. Refactoring (base.py + queries.py) | v0.4.0 | 0/? | Pending (5 req) | — |
| 13. Qualité documentaire (numpydoc + interrogate) | v0.4.0 | 0/? | Pending (7 req) | — |
| 14. Spatial helpers (db.spatial.*) | v0.4.0 | 0/? | Pending (6 req) | — |
| 15. Release v0.4.0 (PyPI + RTD) | v0.4.0 | 0/? | Pending (6 req) | — |
