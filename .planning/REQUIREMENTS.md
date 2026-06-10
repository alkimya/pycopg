# Requirements: pycopg v0.4.0 — Quality & Spatial Helpers

**Defined:** 2026-06-06
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

Scoped from the 2026-06-06 audit (`.planning/AUDIT-2026-06-06.md`) and the Phase 8 spatial design. Full milestone rationale, locked conventions, and phase dependencies: `.planning/milestones/v0.4.0-MILESTONE.md`.

## v1 Requirements

Requirements for the v0.4.0 release. Each maps to exactly one roadmap phase (9–15).

### Tooling — uv (Phase 9)

- [x] **TOOL-01**: Contributor can set up the dev environment with `uv sync --all-extras --dev` (pyproject configured for uv)
- [x] **TOOL-02**: Repository ships a committed `uv.lock` and a `.python-version` for reproducible environments
- [x] **TOOL-03**: CI test workflow runs under uv and passes (replaces the classic `venv`/`pip` flow)
- [x] **TOOL-04**: CI publish workflow builds via `uv build` (wheel + sdist) while keeping hatchling backend and PyPI trusted publishing
- [x] **TOOL-05**: Contributor docs (CLAUDE.md, Makefile, Development/CONTRIBUTING) use uv commands; end-user docs keep `pip install pycopg`

### Security — Residual & Robustness (Phase 10)

- [x] **SEC-01**: `PooledDatabase.execute` commits before returning so `INSERT ... RETURNING` results are not rolled back on pool return (B1)
- [x] **SEC-02**: Sync `session()` no longer masks the original exception when commit/close fails in `finally` (B2)
- [x] **SEC-03**: Migration `_apply`/`rollback` run inside an explicit atomic transaction (B3)
- [x] **SEC-04**: Subprocess helpers use `os.environ` correctly instead of `subprocess.os.environ` (B5)
- [x] **SEC-05**: Async `create_role` validates identifiers up-front (residual gap noted during the v0.3.1 hotfix)
- [x] **SEC-06**: Each residual fix has a dedicated red→green regression test

### Parity — Sync/Async (Phase 11)

- [x] **PAR-01**: AsyncDatabase implements `add_primary_key`, `add_foreign_key`, `add_unique_constraint`, `truncate_table`
- [x] **PAR-02**: AsyncDatabase implements `drop_extension`, `database_exists`, `list_databases`, `create`/`create_from_env`
- [x] **PAR-03**: Database implements `insert_many`, `upsert_many`, `stream`, `notify`
- [x] **PAR-04**: Async `from_dataframe`/`from_geodataframe` actually apply `primary_key` instead of silently ignoring it (C1)
- [x] **PAR-05**: `AsyncDatabase.close()` disposes the SQLAlchemy async engine instead of being a no-op (C2)
- [x] **PAR-06**: Async engine uses the `postgresql+psycopg_async://` driver URL (C3)
- [x] **PAR-07**: `create_extension(schema)` and `create_schema(owner)` signatures and `table_info`/`list_roles` semantics aligned sync/async
- [x] **PAR-08**: `test_parity` verifies return fields and mocked behavior, not just method/param names
- [x] **PAR-09**: Coverage ratchet raised to 90% (`--cov-fail-under=90`) and passing

### Refactoring — Wire Existing Abstractions (Phase 12)

- [x] **REF-01**: ~25 inline SQL strings replaced by the `queries.py` constants (single source of truth) (R1)
- [x] **REF-02**: `Database` and `AsyncDatabase` inherit the shared `base.py` layer (`DatabaseBase`, `QueryMixin`); `from_env`/`from_url`/`__repr__` and batch-insert builder lifted up (R3)
- [x] **REF-03**: Pure stateless builders extracted and unit-tested without a DB: `_build_role_options`, `_build_pg_dump_cmd`, `_build_pg_restore_cmd` (R4)
- [x] **REF-04**: Residual dead code removed (unused `import re`, unread `stdout`, no-op `try/except: raise`, unused `*_SIMPLE` constants, stale "Phase 3" comments)
- [x] **REF-05**: Coverage ratchet raised and passing — landed at 92% (`--cov-fail-under=92`, measured 92.55%); the 95% target was deferred (remaining ~3 pts are DB/IO paths out of this phase's scope, D-07 "never freeze an unmet gate"). See 12-04-SUMMARY.md.

### Documentation Quality (Phase 13)

- [ ] **DOC-06**: All public docstrings migrated to numpydoc format (Summary/Parameters/Returns/Raises), shallow, no Examples section
- [x] **DOC-07**: `interrogate` added as a dev dependency with `fail-under=95` and enforced in a CI job
- [x] **DOC-08**: `napoleon_numpy_docstring` enabled in Sphinx conf
- [ ] **DOC-09**: Public methods raise the real exception types (`ExtensionNotAvailable`, `TableNotFound`, etc.) instead of `RuntimeError`/`ValueError` (V2)
- [x] **DOC-10**: `__version__` resolved via `importlib.metadata.version()` so all version sources agree (V1)
- [x] **DOC-11**: mypy added as a dev dependency with config (TY1)
- [ ] **DOC-12**: `async_engine` property annotated with its return type (TY2)

### Spatial Helpers (Phase 14)

- [ ] **SPAT-01**: The 4 open Phase 8 design points (`into=`, geometry input, `unit=`, `where=`) are resolved at phase start and 08-DESIGN.md updated
- [ ] **SPAT-02**: `pycopg/spatial.py` provides pure SQL builders plus `SpatialAccessor` and `AsyncSpatialAccessor`
- [ ] **SPAT-03**: `db.spatial.*` exposes ~10 helpers (contains, within, intersects, dwithin, distance, nearest, area, perimeter, centroid, buffer, transform)
- [ ] **SPAT-04**: Spatial helpers guard on PostGIS (`has_extension`) and validate identifiers + parameterize values as `%s`
- [ ] **SPAT-05**: `async_db.spatial.*` is at parity with `db.spatial.*`, covered by `test_parity`
- [ ] **SPAT-06**: Pure builder unit tests (no DB) plus PostGIS integration tests for the spatial helpers

### Release v0.4.0 (Phase 15)

- [ ] **REL-01**: Sphinx docs updated — PostGIS `execute(...)` examples replaced by the new helpers; api-reference regenerated
- [ ] **REL-02**: ReadTheDocs build is green (`.readthedocs.yaml` validated, RTD live)
- [ ] **REL-03**: CHANGELOG v0.4.0 written; version bumped consistently everywhere; MIGRATION notes for any breaking changes
- [ ] **REL-04**: Wheel published to PyPI via `uv build` + GitHub release → auto-publish; tag created
- [ ] **REL-05**: GitHub Actions bumped from Node 20 to Node 24 (deprecation noted during the 0.3.1 release)
- [ ] **REL-06**: Milestone audit (`gsd-audit-milestone`) passes before archiving

## v2 Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### API Enhancements

- **API-01**: Named parameter support (:name syntax converts to %s internally)
- **API-02**: Connection health checks (validate pool connections before checkout)
- **API-03**: Comprehensive structured logging (connection lifecycle, query execution)
- **API-04**: Transaction isolation level control (SERIALIZABLE, READ COMMITTED)
- **API-05**: Savepoint support (nested transactions)
- **API-06**: Sync result streaming (async already has it)

### Architecture

- **ARCH-02**: Dynamic connection pool sizing based on queue depth

### ETL

- **ETL-01**: Full ETL layer built on top of the spatial helpers (the helpers are its building blocks; the layer itself is a later milestone)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| ORM/model layer | Duplicates SQLAlchemy, maintenance nightmare |
| Query builder/fluent API | Never as good as SQLAlchemy Core |
| Schema diff/auto-migration | Complex, error-prone, out of scope |
| Multi-database support | pycopg is PostgreSQL-specific by design |
| Query result caching | Premature optimization, defer to post-ETL |
| `uv_build` backend | Too intrusive; hatchling stays (uv-compatible, wired to trusted publishing) |
| 100% hard coverage gate | Caps at 95 to avoid blocking on hard-to-mock I/O (subprocess, network) |
| Docstring Examples sections | numpydoc kept shallow by decision; examples live in Sphinx narrative docs |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TOOL-01 | Phase 9 | Complete |
| TOOL-02 | Phase 9 | Complete |
| TOOL-03 | Phase 9 | Complete |
| TOOL-04 | Phase 9 | Complete |
| TOOL-05 | Phase 9 | Complete |
| SEC-01 | Phase 10 | Complete |
| SEC-02 | Phase 10 | Complete |
| SEC-03 | Phase 10 | Complete |
| SEC-04 | Phase 10 | Complete |
| SEC-05 | Phase 10 | Complete |
| SEC-06 | Phase 10 | Complete |
| PAR-01 | Phase 11 | Complete |
| PAR-02 | Phase 11 | Complete |
| PAR-03 | Phase 11 | Complete |
| PAR-04 | Phase 11 | Complete |
| PAR-05 | Phase 11 | Complete |
| PAR-06 | Phase 11 | Complete |
| PAR-07 | Phase 11 | Complete |
| PAR-08 | Phase 11 | Complete |
| PAR-09 | Phase 11 | Complete |
| REF-01 | Phase 12 | Complete |
| REF-02 | Phase 12 | Complete |
| REF-03 | Phase 12 | Complete |
| REF-04 | Phase 12 | Complete |
| REF-05 | Phase 12 | Complete |
| DOC-06 | Phase 13 | Pending |
| DOC-07 | Phase 13 | Complete |
| DOC-08 | Phase 13 | Complete |
| DOC-09 | Phase 13 | Pending |
| DOC-10 | Phase 13 | Complete |
| DOC-11 | Phase 13 | Complete |
| DOC-12 | Phase 13 | Pending |
| SPAT-01 | Phase 14 | Pending |
| SPAT-02 | Phase 14 | Pending |
| SPAT-03 | Phase 14 | Pending |
| SPAT-04 | Phase 14 | Pending |
| SPAT-05 | Phase 14 | Pending |
| SPAT-06 | Phase 14 | Pending |
| REL-01 | Phase 15 | Pending |
| REL-02 | Phase 15 | Pending |
| REL-03 | Phase 15 | Pending |
| REL-04 | Phase 15 | Pending |
| REL-05 | Phase 15 | Pending |
| REL-06 | Phase 15 | Pending |

**Coverage:**

- v1 requirements: 46 total
- Mapped to phases: 46
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-06*
*Last updated: 2026-06-06 after milestone v0.4.0 definition*
