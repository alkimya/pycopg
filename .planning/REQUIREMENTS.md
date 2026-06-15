# Requirements: pycopg v0.5.0 — ETL Pipeline Runner

**Defined:** 2026-06-14
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with a consistent, clean API.

## v0.5.0 Requirements

A declarative ETL pipeline-runner layer (`db.etl.*` / `async_db.etl.*`) that runs extract → transform → load flows with run tracking and safe, idempotent re-runs — same-DB only, Python-callable transforms, at full sync/async parity. Built entirely on existing pycopg primitives (no new runtime dependencies). Each requirement maps to a roadmap phase.

### Pipeline & Transform

- [x] **ETL-01**: User can define a pipeline with `Pipeline(name=..., source=..., target=..., load_mode=...)`; the object is inspectable (`name`, `source`, `target`, `load_mode`, `conflict_columns`, `schema` are readable attributes).
- [ ] **ETL-02**: User can set `source="SELECT ..."` (SQL) or `source="table_name"` (table) and both extract a DataFrame on `run()` (same-DB, delegates to `to_dataframe`).
- [ ] **ETL-03**: User can pass `transform=None` (no-op) or a `Callable[[DataFrame], DataFrame]`; the transform is applied before load. An exception in the transform raises `ETLTransformError` and records a failed run.

### Load Modes & Idempotency

- [ ] **ETL-04**: User can set `load_mode='append'`; running the pipeline twice inserts rows twice. Target must exist; if not, raises `ETLTargetNotFoundError`.
- [ ] **ETL-05**: User can set `load_mode='replace'` (truncate-load); running twice leaves only the latest extract's rows. If the target does not exist, it is created. TRUNCATE+INSERT is atomic — a mid-load error leaves the target unchanged.
- [ ] **ETL-06**: User can set `load_mode='upsert'` with `conflict_columns=['id']`; running twice updates existing rows and inserts new ones with no duplicates. Omitting `conflict_columns` with `load_mode='upsert'` raises `ValueError` at pipeline construction time.
- [x] **ETL-09**: The load runs in its own DB transaction; in `replace` mode an error after TRUNCATE but before INSERT commits leaves the target with its original rows (load transaction rolled back). The run-tracking write is committed independently of the load transaction.

### Run Tracking & Results

- [x] **ETL-07**: After any `run()`, a row exists in `pipeline_runs` with `run_id`, `pipeline_name`, `started_at`, `finished_at`, `status`, `rows_extracted`, `rows_loaded`. The table reserves a nullable `watermark` column (always NULL in v0.5.0) for forward-compat with v0.6.0 incremental support — no breaking migration required later.
- [x] **ETL-08**: A run that raises during load records `status='failed'` with non-null `error_message` and `error_traceback`; the `pipeline_runs` record is committed even when the load transaction rolled back.
- [ ] **ETL-10**: `db.etl.run(pipeline)` returns a `RunResult` carrying `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, and `error`.
- [ ] **ETL-11**: `db.etl.history("my_pipeline")` returns a list of `RunResult` for that pipeline, newest-first.
- [x] **ETL-14**: The `pipeline_runs` table is auto-created on first `run()` if missing (CREATE TABLE IF NOT EXISTS); an explicit `db.etl.init()` is also available. No user-run migration is required.

### Accessor & Parity

- [ ] **ETL-13**: `db.etl` returns a lazily-created `ETLAccessor`; `async_db.etl` returns a lazily-created `AsyncETLAccessor` — mirroring the `db.spatial` precedent, keeping the monolithic Database class from growing.
- [ ] **ETL-12**: `await async_db.etl.run(pipeline)` / `await async_db.etl.history(name)` exist and produce results equivalent to the sync versions; sync transform callables are dispatched via `asyncio.to_thread`. A dedicated `TestEtlParity` extension to the existing `test_parity` harness enumerates the ETL surface.

### Developer Experience

- [ ] **ETL-15**: User can call `run(pipeline, dry_run=True)` to execute extract + transform but skip the load and write no run record; returns a `RunResult` with `status='dry_run'`, `rows_loaded=0`.
- [ ] **ETL-16**: User can set `transform=[clean, normalize, enrich]` (a list of callables) applied in sequence; an error reports which step failed. A single callable and `None` remain valid.
- [ ] **ETL-17**: User can call `db.etl.last_run("my_pipeline")` to fetch the most recent `RunResult` (or `None`) — sugar over `history()`.

## Future Requirements

Deferred to a later milestone (likely v0.6.0). Tracked, not in this roadmap. The `pipeline_runs` schema is designed so these slot in additively.

### Incremental (v0.6.0)

- **ETL-INC-01**: Watermark/incremental extract — load only rows newer than the last successful run (by timestamp or id). Hook point: `pipeline_runs.finished_at` + the reserved `watermark` column.

### Endpoints (v0.6.0+)

- **ETL-XDB-01**: Cross-DB transfer — source and target on different `Database`/`AsyncDatabase` instances.
- **ETL-FILE-01**: File source/sink — CSV / Parquet / DataFrame as a pipeline source or sink.

### Scale (v0.6.0+)

- **ETL-STREAM-01**: Streaming / micro-batch transforms for tables too large to materialize in one DataFrame.

### Spatial (opportunistic)

- **ETL-GEO-01**: GeoDataFrame-aware load — route post-transform GeoDataFrames to `from_geodataframe`. Deferred unless spatial ETL demand emerges.

## Out of Scope

Explicitly excluded for v0.5.0 and beyond. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| SQL-only transforms (`transform="UPDATE ..."`) | Bypasses the DataFrame contract, adds injection risk, untestable without a DB; conflicts with the locked "Python callable" decision. Users write Python that calls `db.execute()` for SQL side effects. |
| Scheduling / DAG / cron / orchestration | Application-layer concern; pycopg is a library, not a scheduler. Document integration with cron/APScheduler calling `db.etl.run()`. |
| Retry-as-orchestration (auto-retry failed runs) | Re-runs can have business side effects; different from transient DB retries (tenacity already handles those). Keep single-run semantics predictable. |
| Multi-step DAG pipelines (fan-out, inter-pipeline deps) | DAG resolution is an orchestrator's job; pycopg's runner is linear (one extract, one transform, one load). |
| Pipeline versioning / target schema evolution | Schema migration is a distinct concern handled by `migrations.py`; the ETL runner is not a schema migrator. |
| New runtime dependencies (dlt, Airflow/Prefect/Dagster, SQLAlchemy ORM, alembic, pyarrow) | The layer is built entirely on existing psycopg / pandas / stdlib. A thin, dependency-light layer is pycopg's core value. |

## Open Design Decisions (resolved at definition; confirm at phase-discuss)

| ID | Decision | Resolution |
|----|----------|-----------|
| OD-1 | `pipeline_runs` watermark column type | Single nullable `JSONB watermark` column, always NULL in v0.5.0 (ETL-07). Flexible for any watermark shape in v0.6.0. |
| OD-2 | Failure exception strategy | Domain exceptions for known cases (`ETLTransformError`, `ETLTargetNotFoundError`); otherwise re-raise the original exception after recording the failed run (don't wrap user exceptions). |
| OD-3 | `pipeline_runs` creation | Both: lazy auto-create on first `run()` (ETL-14) AND explicit `db.etl.init()` convenience. |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ETL-01 | Phase 16 | Complete |
| ETL-02 | Phase 18 | Pending |
| ETL-03 | Phase 18 | Pending |
| ETL-04 | Phase 18 | Pending |
| ETL-05 | Phase 18 | Pending |
| ETL-06 | Phase 18 | Pending |
| ETL-07 | Phase 17 | Complete |
| ETL-08 | Phase 17 | Complete |
| ETL-09 | Phase 17 | Complete |
| ETL-10 | Phase 19 | Pending |
| ETL-11 | Phase 19 | Pending |
| ETL-12 | Phase 20 | Pending |
| ETL-13 | Phase 20 | Pending |
| ETL-14 | Phase 17 | Complete |
| ETL-15 | Phase 19 | Pending |
| ETL-16 | Phase 18 | Pending |
| ETL-17 | Phase 19 | Pending |

**Coverage:**

- v0.5.0 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-14*
*Last updated: 2026-06-14 — traceability table populated after roadmap creation (Phases 16–20)*
