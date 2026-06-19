# Requirements: pycopg v0.7.0 — Alias Removal + Incremental ETL

**Defined:** 2026-06-19
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## v1 Requirements

Requirements for the v0.7.0 release. Each maps to exactly one roadmap phase (numbering continues from Phase 24 → starts at Phase 25).

### Alias Removal

Mechanical, breaking. One deprecation cycle was already served in v0.6.0 (the 56 flat names have emitted `DeprecationWarning` since then). The real logic already lives in the accessors, so removal is a one-block deletion (D-SCOPE-2).

- [ ] **ALIAS-RM-01**: The 56 deprecated flat `@deprecated_alias` stubs are removed from both `Database` and `AsyncDatabase` (112 stubs total); the public surface is accessor-only (`db.timescale/admin/maint/backup/schema.*` + `db.spatial.*`)
- [ ] **ALIAS-RM-02**: Calling any removed flat name raises a plain `AttributeError` (no stub, no warning); the alias-specific warn+delegate tests are removed and `test_parity`/`ACCESSOR_PAIRS` still passes green
- [ ] **ALIAS-RM-03**: A MIGRATION v0.6→v0.7 section documents the removal with a 1:1 flat→accessor replacement table for all 56 names; CHANGELOG `[0.7.0]` has a `Breaking` entry pointing to it
- [ ] **ALIAS-RM-04**: Carried-forward tech debt resolved by removal is closed: WR-01 (deprecated `*args/**kwargs` stubs erasing IDE signatures on this `py.typed` package) and IN-02 (`ExtensionNotAvailable`/error messages still naming flat `db.create_extension(...)`)

### Incremental ETL

Additive watermark-based incremental loading on the v0.5.0 ETL runner. The `pipeline_runs.watermark JSONB` column is already reserved (always NULL since v0.5.0) → no breaking migration. Zero new runtime dependencies.

**Locked scope decisions (cadrage 2026-06-19):**

- Declarative via a single new `Pipeline.incremental_column` field (no callbacks).
- High-water mark = `max(incremental_column)`, computed from the **raw** extracted batch **before** transforms run.
- Comparison operator is `>` (exclusive).
- `incremental_column` + `load_mode="append"` is **forbidden at construction** (`ValueError`) — incremental requires `upsert` (idempotent regardless of watermark-column uniqueness); `replace` also forbidden with incremental.
- First run (no prior watermark) = full load, then record `max(col)`. `initial_watermark` bounding deferred to v0.8.0 (see Future Requirements).
- The new watermark is read from the last **successful** run's row and persisted only on a **successful** load; a failed load must not advance it; an empty batch preserves the prior watermark (never writes NULL).
- Full sync/async parity (Core Value).

- [ ] **ETL-INC-01**: User can declare `Pipeline(incremental_column="updated_at", ...)`; identifier is validated; construction raises `ValueError` for `incremental_column` with `load_mode` ∈ {append, replace} (incremental requires `upsert`)
- [ ] **ETL-INC-02**: On the first run of an incremental pipeline (no prior successful watermark), `db.etl.run()` performs a full load and records `max(incremental_column)` as the new watermark on success
- [ ] **ETL-INC-03**: On subsequent runs, extraction applies `WHERE incremental_column > last_watermark` (exclusive); SQL-string sources are wrapped as `SELECT * FROM (<sql>) <alias> WHERE …`, table sources get the WHERE appended; the watermark value is always passed as a `%s` parameter (never interpolated)
- [ ] **ETL-INC-04**: After a successful load, `max(incremental_column)` is computed from the raw extracted batch (before the transform chain) and recorded; if the watermark column is absent from the extract, a clear `ETL*` error is raised (not a bare `KeyError`)
- [ ] **ETL-INC-05**: An empty incremental batch records a successful run with `rows_loaded=0` and preserves the prior watermark (does not write NULL, does not trigger a full reload next run)
- [ ] **ETL-INC-06**: The watermark is read from the last **successful** run for that pipeline and persisted only on the success path; a failed load records a `failed` run whose watermark does not advance
- [ ] **ETL-INC-07**: `RunResult` exposes `watermark_used` (the filter floor applied this run) and `watermark_recorded` (the new high-water mark persisted); both are `None` for non-incremental pipelines
- [ ] **ETL-INC-08**: `history()` and `last_run()` surface the recorded watermark for past runs
- [ ] **ETL-INC-09**: `dry_run=True` on an incremental pipeline reads the last watermark and computes the would-be filter and new max, writing no `pipeline_runs` row, and returns `watermark_used`/`watermark_recorded` for inspection
- [ ] **ETL-INC-10**: The watermark value round-trips correctly through `pipeline_runs.watermark JSONB` for timestamp, integer, and text watermark columns (typed envelope; no timezone/precision drift), with zero new runtime dependencies
- [ ] **ETL-INC-11**: Full sync/async parity — `AsyncETLAccessor` mirrors the entire incremental surface; `TestEtlParity` is extended to cover it
- [ ] **ETL-INC-12**: Backfill/reset workflow is documented (re-run as full load) and a `docs/etl.md` section + docstrings describe incremental usage, the watermark-column requirements (monotonic, non-decreasing), and the upsert requirement

### Release

- [ ] **REL-07**: v0.7.0 released — version bumped in both sources, CHANGELOG `[0.7.0]` (Breaking/Added) finalized, MIGRATION v0.6→v0.7 complete, Sphinx `-W` clean, coverage ratchet ≥94 held, `-W error::DeprecationWarning` green, tagged + published to PyPI via OIDC (human-gated), clean-venv import smoke confirmed

## Future Requirements

Deferred to a later release. Tracked but not in the v0.7.0 roadmap.

### Incremental ETL (v0.8+)

- **ETL-INC-F01**: `initial_watermark` parameter to bound the first run (avoid a full-table load on huge sources) — additive, non-breaking to add later
- **ETL-INC-F02**: Configurable boundary operator (`>` vs `>=`) for late-arriving-data / lookback strategies
- **ETL-INC-F03**: Multi-column / composite watermarks
- **ETL-INC-F04**: Advisory-lock-based concurrent-run protection for `append` + incremental
- **ETL-INC-F05**: CDC / WAL-based change capture (logical replication) — beyond watermark polling

## Out of Scope

Explicitly excluded for v0.7.0. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| `incremental_column` + `append` | Forbidden — non-unique watermark columns silently drop boundary rows; incremental requires `upsert` for idempotency (locked decision) |
| `incremental_column` + `replace` | Forbidden — `replace` truncates the whole target, incompatible with incremental-by-definition (locked decision) |
| Configurable `>=` boundary / late-data lookback | Deferred to v0.8+ (ETL-INC-F02); `>` exclusive is the v0.7.0 contract |
| Multi-column / composite watermarks | Deferred (ETL-INC-F03); single-column only in v0.7.0 |
| `initial_watermark` first-run bound | Deferred to v0.8.0 (ETL-INC-F01); additive, non-breaking to add later |
| CDC / WAL log decoding | Out of scope — watermark polling only; logical replication is a much larger feature |
| Scheduler / DAG orchestration | Out of scope — `Pipeline` describes one extract→transform→load pass; no `depends_on`/`schedule`/`retry` |
| Cross-DB / file (CSV/parquet) ETL sources/sinks | Out of scope — pycopg ETL is same-DB only (unchanged from v0.5.0) |
| Soft-deprecation cycle for the 56 flat aliases | Not applicable — one cycle already served in v0.6.0; v0.7.0 is the hard removal |

## Traceability

Which phases cover which requirements. Filled during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ALIAS-RM-01 | Phase [N] | Pending |
| ALIAS-RM-02 | Phase [N] | Pending |
| ALIAS-RM-03 | Phase [N] | Pending |
| ALIAS-RM-04 | Phase [N] | Pending |
| ETL-INC-01 | Phase [N] | Pending |
| ETL-INC-02 | Phase [N] | Pending |
| ETL-INC-03 | Phase [N] | Pending |
| ETL-INC-04 | Phase [N] | Pending |
| ETL-INC-05 | Phase [N] | Pending |
| ETL-INC-06 | Phase [N] | Pending |
| ETL-INC-07 | Phase [N] | Pending |
| ETL-INC-08 | Phase [N] | Pending |
| ETL-INC-09 | Phase [N] | Pending |
| ETL-INC-10 | Phase [N] | Pending |
| ETL-INC-11 | Phase [N] | Pending |
| ETL-INC-12 | Phase [N] | Pending |
| REL-07 | Phase [N] | Pending |

**Coverage:**

- v1 requirements: 17 total
- Mapped to phases: 0 (filled by roadmapper)
- Unmapped: 17 ⚠️ (until roadmap created)

---
*Requirements defined: 2026-06-19*
*Last updated: 2026-06-19 after initial definition*
