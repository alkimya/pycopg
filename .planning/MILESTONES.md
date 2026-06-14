# Milestones

## v0.4.0 Quality & Spatial Helpers (Shipped: 2026-06-14)

**Phases completed:** 7 phases (9–15), 36 plans, 62 tasks

**Delivered:** Full sync/async parity, PostGIS spatial helpers (`db.spatial.*`), numpydoc docs with an interrogate gate, residual security fixes, and a uv-based toolchain — shipped to PyPI + ReadTheDocs under a 94% coverage ratchet.

**Key accomplishments:**

- **uv toolchain (Phase 9):** PEP 735 dev groups + committed `uv.lock`/`.python-version`; CI test matrix (3.11/3.12/3.13) and publish both run under uv (`uv build`), hatchling backend + OIDC trusted publishing preserved.
- **Residual security & robustness (Phase 10):** closed B1 (pool commit-before-return), B2 (session close-on-commit-failure), B3 (atomic migration apply/rollback), B5 (os.environ), each with a red→green regression test; coverage ratchet → 80.
- **Full sync/async parity (Phase 11):** AsyncDatabase gained 9 missing methods (DDL constraints, admin, create/create_from_env); Database gained insert_many/upsert_many/stream/notify; C1/C2/C3 fixed; `test_parity` extended to real-DB behavior; ratchet → 90.
- **Refactoring — wired abstractions (Phase 12):** `Database`/`AsyncDatabase` now inherit `DatabaseBase`+`QueryMixin`; ~25 inline SQL strings replaced by `queries.py` constants; pure DB-free builders extracted; ratchet honestly flipped 90→92 (95 stretch deferred).
- **Documentation quality (Phase 13):** all public docstrings migrated to numpydoc; interrogate gate (≥95) + mypy in CI; real exception types (ExtensionNotAvailable/DatabaseExists); `__version__` via importlib.metadata.
- **Spatial helpers (Phase 14):** `pycopg/spatial.py` with geometry resolver + 11 pure PostGIS SQL builders + `SpatialAccessor`/`AsyncSpatialAccessor` at parity; PostGIS guard + `%s` parameterization; ratchet → 94.
- **Release (Phase 15):** Sphinx spatial docs + RTD green; CHANGELOG/MIGRATION/version bump 0.4.0; Node 24 CI action bumps; tag `v0.4.0` + PyPI publish via OIDC.

**Stats:**

- Codebase: 10,528 LOC Python (lib) + 11,228 LOC tests
- Coverage ratchet: 70 → 80 → 90 → 92 → 94 (measured 94.09%)
- Timeline: 9 days (2026-06-06 → 2026-06-14)
- Commits: ~163 in window; Git range: chore(09-01) → docs(audit) v0.4.0
- Audit: PASSED (46/46 requirements, 7/7 phases, 14/14 integration, 4/4 E2E flows)

---

## v0.3.0 Consolidation Release (Shipped: 2026-02-11)

**Phases completed:** 7 phases, 14 plans, 20 tasks

**Delivered:** Full AsyncDatabase/Database feature parity, critical bug fixes, production resilience, 72.76% test coverage, and complete documentation for pycopg v0.3.0.

**Key accomplishments:**

- Fixed 5 critical bugs: session cleanup leaks, transaction detection, migration logging, TimescaleDB validation, SRID inference
- Full AsyncDatabase parity: 30+ async methods (DataFrame, Admin, Backup, Roles, PostGIS, TimescaleDB)
- Production resilience: retry/backoff with tenacity, statement_timeout, configurable batch sizes, pool reconnection
- Test coverage from 23% to 72.76%: 60+ new tests including edge cases, pool stress, and automated parity verification
- Complete documentation: CHANGELOG, MIGRATION guide, updated README, rebuilt Sphinx API reference
- Version bumped to 0.3.0 across pyproject.toml and Sphinx configuration

**Stats:**

- Lines changed: 17,706 insertions, 38 deletions across 71 files
- Codebase: 13,648 LOC Python
- Timeline: 42 days (2026-01-01 → 2026-02-11)
- Commits: 77
- Git range: feat(01-01) → docs(phase-07)

---
