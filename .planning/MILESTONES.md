# Milestones

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

