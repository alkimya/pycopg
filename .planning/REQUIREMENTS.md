# Requirements: pycopg v1.1.0 — Follow-ups additifs (TimescaleDB · ETL incrémental · CRUD/introspection)

**Defined:** 2026-07-02
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

> First additive **1.x** point release under the frozen SemVer 1.0 API. All requirements below are the deferred family follow-ups recorded in the archived `milestones/v1.0.0-REQUIREMENTS.md` Future section (REQ-IDs kept verbatim for traceability), plus the pending doc/metadata patch (DOC-13) and the release (REL-12). **Additive / non-breaking** under the frozen API — no `DeprecationWarning`/MIGRATION churn expected.

## Cross-cutting acceptance criteria (apply to every feature requirement)

Not separate requirements — the standing bar each feature REQ must meet at verification:

- **Sync/async parity** — every new public method/param exists and is tested on both `Database`/`AsyncDatabase` (or their accessors), enforced by `test_accessor_parity` + `test_accessor_parameter_kind_parity`.
- **Builder-pur + injection safety** — `validate_identifiers` is line 1 of every new SQL builder, user values bound as `%s`/`%(name)s`, with a dedicated injection test per new builder.
- **Additive/non-breaking** — no changes to existing signatures' behavior; keyword-only new params; no new `DeprecationWarning`.
- **Zero new runtime dependencies.**
- **Coverage ratchet ≥95%** (baseline 96.45%); `mypy --strict` stays a blocking gate at 0 errors; `interrogate` 100%; Sphinx `-W` clean.

## v1.1.0 Requirements

### TimescaleDB Follow-ups (`db.timescale.*`)

- [x] **TSDB-F01**: User can drop a continuous aggregate and remove its refresh policy — `db.timescale.drop_continuous_aggregate(name)` and `remove_continuous_aggregate_policy(name)`, completing the cagg lifecycle opened in v0.8.0.
- [x] **TSDB-F02**: User can align `time_bucket` boundaries to a custom origin/offset — keyword-only `origin=`/`offset=` params on `db.timescale.time_bucket`.
- [x] **TSDB-F03**: User can compress and decompress an individual chunk — `db.timescale.compress_chunk(chunk)` / `decompress_chunk(chunk)` per-chunk control.
- [x] **TSDB-F04**: User can filter `show_chunks` by physical time range — keyword-only `newer_than=`/`older_than=` bounds on `db.timescale.show_chunks`.

### Incremental ETL Follow-ups (`db.etl.*` / `Pipeline`)

- [ ] **ETL-INC-F01**: User can set an `initial_watermark` on a `Pipeline` to bound (or seed) the first incremental run instead of a full initial load.
- [ ] **ETL-INC-F02**: User can configure the incremental boundary — inclusive `>=` and/or a lookback overlap — instead of the fixed exclusive `>`.
- [ ] **ETL-INC-F03**: User can define multi-column watermarks (composite incremental keys) on a `Pipeline`.
- [ ] **ETL-INC-F04**: User can serialize concurrent runs of the same pipeline via PostgreSQL advisory locks (no overlapping incremental loads).

### CRUD + Introspection Follow-ups (flat transactional core + `db.schema.*`)

- [x] **CRUD-F01**: User can pass a raw-SQL WHERE fragment (with bound params) as an escape hatch on the predicate helpers (`delete_where`/`update_where`/`count`/`exists`/`paginate`) for conditions the dict form can't express.
- [x] **CRUD-F02**: User can paginate by keyset/cursor (seek method) for stable, index-friendly deep pagination.
- [x] **CRUD-F03**: User can retrieve a page envelope carrying `total` count and `has_next` alongside the rows.
- [ ] **INTRO-F01**: User can get `db.schema.describe()` output as a structured dataclass and/or DataFrame, not only a plain dict.
- [x] **INTRO-F02**: User can introspect materialized views — `db.schema.materialized_views()` plus per-view column introspection.

### Docs / Metadata + Release

- [ ] **DOC-13**: Published package metadata and docs are correct for a stable 1.x — `pyproject.toml` classifier `Development Status :: 5 - Production/Stable`; `docs/api-reference.md` uses the `*Error` exception names (no deprecated-name imports that trip `-W error::DeprecationWarning`); `CLAUDE.md` Version line reflects the shipped version.
- [ ] **REL-12**: pycopg v1.1.0 released to PyPI — version bumped across all sources, Added-only CHANGELOG `[1.1.0]`, all 5 gates green (coverage ≥95%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`, `mypy --strict` 0 errors), annotated tag `v1.1.0`, human-gated OIDC publish, clean-venv smoke.

## Future Requirements (deferred to a later additive 1.x — non-breaking under the frozen API)

### ETL incremental (deferred 2026-07-02)

- **ETL-INC-F05**: CDC / WAL change capture — a large distinct subsystem (logical replication slots + output-plugin decoding), comparable in weight to raster; scoped out of v1.1.0 to keep it a coherent set of additive follow-ups.

### Spatial

- **SPAT-F01**: `gridSize` precision parameter on overlay functions (union/difference/intersection) — GEOS ≥ 3.9 edge case.

### Raster (post-1.0)

- **RASTER-F01**: PostGIS raster I/O and processing surface — large distinct subsystem.

## Out of Scope

Explicitly excluded from v1.1.0. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| CDC / WAL change capture (ETL-INC-F05) | Large distinct subsystem (replication slots + pgoutput/wal2json decoding); deferred to keep v1.1.0 a coherent set of additive follow-ups (2026-07-02 scope call) |
| Raster support (RASTER-F01) | Large distinct PostGIS subsystem, its own future milestone |
| `gridSize` overlay precision (SPAT-F01) | GEOS ≥ 3.9 edge case; pairs naturally with future spatial work, not this cycle |
| Any breaking change to a public signature | API is frozen under SemVer 1.0; new params are keyword-only and additive only |
| `:name` parameter translator | Resolved in v1.0.0 (PARAM-01): native `%(name)s`; a hand-rolled parser is too fragile to freeze |
| New runtime dependencies | Library rule held since v0.4.0; follow-ups reuse existing psycopg/pandas surface |

## Traceability

Which phases cover which requirements.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TSDB-F01 | Phase 48 | Complete |
| TSDB-F02 | Phase 48 | Complete |
| TSDB-F03 | Phase 48 | Complete |
| TSDB-F04 | Phase 48 | Complete |
| ETL-INC-F01 | Phase 49 | Pending |
| ETL-INC-F02 | Phase 49 | Pending |
| ETL-INC-F03 | Phase 49 | Pending |
| ETL-INC-F04 | Phase 49 | Pending |
| CRUD-F01 | Phase 50 | Complete |
| CRUD-F02 | Phase 50 | Complete |
| CRUD-F03 | Phase 50 | Complete |
| INTRO-F01 | Phase 50 | Pending |
| INTRO-F02 | Phase 50 | Complete |
| DOC-13 | Phase 51 | Pending |
| REL-12 | Phase 51 | Pending |

**Coverage:**

- v1.1.0 requirements: 15 total
- Mapped to phases: 15/15 ✓
- Unmapped: 0

---
*Requirements defined: 2026-07-02*
*Last updated: 2026-07-02 after roadmap creation (Phases 48-51 mapped, 100% coverage)*
