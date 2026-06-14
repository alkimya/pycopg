# Feature Research — ETL Pipeline Runner (v0.5.0)

**Domain:** Declarative, code-first, single-process ETL pipeline runner for a PostgreSQL library
**Researched:** 2026-06-14
**Confidence:** HIGH (codebase analysis) / MEDIUM (ecosystem patterns from petl, dlt, Airflow dag\_run schema, community sources)

---

## Context: What This Adds to pycopg

v0.5.0 adds a thin orchestration layer (`db.etl.*` / `async_db.etl.*`) that composes already-shipped
primitives (execute, insert\_many, upsert\_many, to\_dataframe, from\_dataframe, transactions) into a
declarative, re-runnable extract→transform→load flow with a persistent `pipeline_runs` audit table.
The ETL layer is NOT a general-purpose orchestrator. It is scoped to same-DB, Python-callable-transform,
full-load idempotency. All table-stakes items below must become testable ETL-\* requirements.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in a library-grade ETL runner. Missing = the feature is incomplete or untestable.

For each feature: **Depends On** lists the existing pycopg primitive it composes. **Notes** describes the design contract.

---

#### ETL-01 — Declarative pipeline definition

- **Why expected:** Every lightweight ETL tool (petl, dlt, Hamilton) uses an explicit pipeline object/dataclass separating *what* from *when*. A bare `run(source, transform, target)` call is not inspectable or composable.
- **Complexity:** LOW
- **Depends on:** nothing yet — new `Pipeline` dataclass
- **Notes:** `Pipeline` fields: `name`, `source` (SQL string or table name), `target` (table name), `transform` (callable, optional), `load_mode`, `conflict_columns` (for upsert), `schema` (default `public`).

#### ETL-02 — Extract from SQL query or table name

- **Why expected:** Users expect to specify either a raw SQL string or a table name as the extract source. Both are common in petl (`frompgsql`) and dlt (`source(table_name=...)`).
- **Complexity:** LOW
- **Depends on:** `to_dataframe(sql=..., table=...)` — delegates directly
- **Notes:** Source is always same-DB. `source="raw_events"` (table) or `source="SELECT * FROM raw_events WHERE ..."` (SQL).

#### ETL-03 — Python-callable transform (DataFrame → DataFrame)

- **Why expected:** Every code-first ETL tool treats transforms as ordinary Python functions. The canonical signature is `Callable[[pd.DataFrame], pd.DataFrame]`. petl uses row iterators; dlt uses generator functions; Mage uses `@transformer` functions. For pandas-native tools the DataFrame→DataFrame protocol is dominant and maps cleanly to pycopg's `to_dataframe` output.
- **Complexity:** LOW
- **Depends on:** `to_dataframe` output is a DataFrame
- **Notes:** Transform is optional (`None` = no-op). Callable receives the extracted DataFrame; returns a new DataFrame. Errors in transform propagate as `ETLTransformError` and record a failed run.

#### ETL-04 — Load mode: append (insert)

- **Why expected:** Append is the simplest and most expected mode — add rows to the target, never touch existing data. Required for event logs, audit trails, and staging tables.
- **Complexity:** LOW
- **Depends on:** `insert_many`
- **Notes:** Calls `insert_many(target, rows)`. Target table must already exist for append mode; if not, raises `ETLTargetNotFoundError`.

#### ETL-05 — Load mode: replace (truncate-load)

- **Why expected:** Truncate-then-insert is the simplest idempotent full-load strategy. dlt calls this `write_disposition='replace'`. Standard in all ETL tools. Running the same pipeline twice produces the same final state.
- **Complexity:** MEDIUM
- **Depends on:** `execute("TRUNCATE …")` + `insert_many`, wrapped in `transaction()`
- **Notes:** Entire TRUNCATE+INSERT in one DB transaction — all-or-nothing. If target table does not exist, it is created from the DataFrame schema via `from_dataframe(if_exists='replace')`.

#### ETL-06 — Load mode: upsert (merge-by-key)

- **Why expected:** Users want to re-run a pipeline without full-table replacement when the target has data that should be preserved for untouched keys. Requires specifying `conflict_columns`. dlt calls this `write_disposition='merge'` with `primary_key`.
- **Complexity:** MEDIUM
- **Depends on:** `upsert_many(conflict_columns=...)`
- **Notes:** `conflict_columns` required when `load_mode='upsert'`; raise `ValueError` at `Pipeline` construction time if missing. On re-run: existing rows updated, new rows inserted.

#### ETL-07 — Run tracking via `pipeline_runs` table

- **Why expected:** Every production ETL tool captures a run record per execution. Airflow's `dag_run` table, dlt's `_dlt_loads`, and Hevo's audit tables all follow this pattern. Users must be able to query history to diagnose failures or verify success.
- **Complexity:** MEDIUM
- **Depends on:** `execute` / `insert_many` / DDL helpers
- **Notes:** Auto-created table schema: `run_id UUID PK, pipeline_name TEXT, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, status TEXT, rows_extracted INT, rows_loaded INT, error_message TEXT, error_traceback TEXT`. Schema: configurable (default `public`).

#### ETL-08 — Status lifecycle: running → success / failed

- **Why expected:** Users expect a clear lifecycle: a run that started but did not finish is marked `running` (or `failed` on exception). Inspired by Airflow dag\_run states (running/success/failed) and dlt's completion status model.
- **Complexity:** LOW
- **Depends on:** `execute` for INSERT and UPDATE on `pipeline_runs`
- **Notes:** Insert row with `status='running'` at start; UPDATE to `status='success'` or `status='failed'` at end. Failed runs capture `error_message` (exception str) and `error_traceback` (full traceback).

#### ETL-09 — Transactional load (all-or-nothing per run)

- **Why expected:** Replace-mode pipelines must be atomic: truncate + insert must either both succeed or both roll back. A failed mid-load that leaves a half-empty target table is a data corruption scenario.
- **Complexity:** MEDIUM
- **Depends on:** `transaction()` context manager
- **Notes:** Entire load in one DB transaction for `replace` mode. For `upsert` mode, `upsert_many` is a single statement. For `append`, `insert_many` is a single batched operation. Run tracking UPDATE is committed **independently** (separate transaction) so a failed run is still recorded.

#### ETL-10 — `db.etl.run(pipeline)` call shape

- **Why expected:** A single method call that takes a `Pipeline` object and returns a `RunResult`. Consistent with how dlt (`pipeline.run(source)`) and petl (`etl.execute()`) expose execution.
- **Complexity:** LOW
- **Depends on:** all of ETL-01 through ETL-09
- **Notes:** `db.etl.run(pipeline) -> RunResult`. `RunResult` carries: `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, `error` (or None).

#### ETL-11 — `db.etl.history(pipeline_name)` — query run history

- **Why expected:** Users need to look up past runs. dlt exposes `pipeline.last_trace`; Airflow has the `dag_run` table. A library-grade runner must expose a programmatic history query.
- **Complexity:** LOW
- **Depends on:** `execute` / `to_dataframe(sql=...)`
- **Notes:** Returns list of `RunResult` for a named pipeline, ordered newest-first. Caller can filter by status.

#### ETL-12 — Full sync/async parity: `async_db.etl.run(pipeline)`

- **Why expected:** pycopg's core value is sync/async parity. Every method in Database has a tested async equivalent. The ETL surface must be no exception.
- **Complexity:** HIGH
- **Depends on:** `async_db.to_dataframe`, `async_db.upsert_many`, `async_db.insert_many`, async transactions
- **Notes:** Transform callable may be sync; wrap in `asyncio.to_thread()` (same pattern as `run_sync` used in existing async spatial/DataFrame helpers). Async `pipeline_runs` writes use async execute. Covered by existing `test_parity` harness.

#### ETL-13 — `ETLAccessor` lazy accessor on `db.etl`

- **Why expected:** Following the `db.spatial.*` precedent, the ETL surface is exposed as a lazy accessor, not methods added directly to the `Database` class. Keeps the monolith from growing further.
- **Complexity:** LOW
- **Depends on:** `SpatialAccessor` pattern
- **Notes:** `ETLAccessor(db)` initialized on first `.etl` property access. `AsyncETLAccessor(async_db)` for async.

#### ETL-14 — `pipeline_runs` auto-created if missing

- **Why expected:** Users should not have to run a migration manually before using `db.etl.run(...)`. The runner creates the table on first use (CREATE TABLE IF NOT EXISTS).
- **Complexity:** LOW
- **Depends on:** DDL / `execute`
- **Notes:** Idempotent DDL called at `ETLAccessor.__init__` or lazily on first `run()`. No migration file needed for this internal table.

---

### Differentiators (Competitive Advantage)

Features that go beyond baseline expectations, specific to pycopg's domain or core value.

| Feature | Value Proposition | Complexity | Notes |
| --- | --- | --- | --- |
| **Transform chain (list of callables)** | `transform=[clean, normalize, enrich]` applied in sequence. petl is entirely chain-based; users who think in pipeline stages expect this. | LOW | Each callable is `Callable[[pd.DataFrame], pd.DataFrame]`, applied sequentially via reduce. Error in step N records which step failed. |
| **`db.etl.last_run(pipeline_name)`** | One-liner to fetch the most recent run result, useful in notebooks and scripts. Returns `RunResult \| None`. | LOW | Syntactic sugar over `history()[0]` with a None guard. |
| **Row counts surfaced in RunResult** | Extracted row count and loaded row count are distinct. Users want to know "I read 10,000 rows but only loaded 8,500 after transform filtering". | LOW | `rows_extracted` = len(df after extract), `rows_loaded` = rows affected by insert/upsert. |
| **GeoDataFrame transform support** | Transforms that return a GeoDataFrame are loadable via `from_geodataframe`. Natural for spatial ETL users given existing PostGIS support. | MEDIUM | Detect GeoDataFrame in runner post-transform, route to `from_geodataframe`. Not required for MVP. |
| **`pipeline_runs` schema-configurable** | `ETLAccessor(db, schema='etl')` stores run tracking in a dedicated schema, not `public`. Multi-tenant or security-conscious users isolate audit tables. | LOW | Pass schema to all `pipeline_runs` DDL and DML. Default `'public'`. |
| **`dry_run=True` mode** | Execute extract + transform but skip the load and do not write a run record. Lets users validate their transform logic against real data. | LOW | Returns `RunResult(status='dry_run', rows_extracted=N, rows_loaded=0)`. No DB writes. |

---

### Anti-Features (Deferred — Explicitly Out of Scope for v0.5.0)

These are commonly requested in ETL contexts but explicitly deferred. Do NOT propose them as table stakes.

| Anti-Feature | Why Requested | Why Out of Scope for v0.5.0 | What to Do Instead |
| --- | --- | --- | --- |
| **Incremental / watermark-based extract** | "Only load rows since last run" | Requires reliable change detection (updated\_at, CDC). Adds state-management complexity. `pipeline_runs` is designed additively so watermarks slot in cleanly for v0.6.0. | Defer to v0.6.0. Users can pass `source="SELECT * FROM t WHERE updated_at > ..."` manually. |
| **Cross-DB transfer** | Move data from one Database instance to another | Two-connection management, distributed transaction edge cases. Out of scope for v0.5.0. | Same-DB only. Defer. |
| **DataFrame / CSV / Parquet as source or sink** | Read from files or dump to Parquet | Source=files requires I/O abstraction; sink=files is not a DB concern. Scope creep. | Users pre-load DataFrames themselves and pass via transform. |
| **SQL-only transforms** | `transform="UPDATE …"` SQL strings | Bypasses the DataFrame contract, adds injection risk, untestable without a DB. Not aligned with "Python callable" decision. | Users write Python callables that call `db.execute()` for SQL side effects. |
| **Scheduling / DAG / cron / orchestration** | `db.etl.schedule(pipeline, cron='0 * * * *')` | Scheduling is an application-layer concern. pycopg is a library, not a scheduler. Adds persistent-process and failure-recovery concerns. | Document integration with APScheduler or cron calling `db.etl.run(pipeline)`. |
| **Retry-as-orchestration (auto-retry failed runs)** | Automatic re-attempt of a failed pipeline | ETL pipeline re-runs may have business implications (duplicate emails, etc.). Different from transient DB retries (tenacity handles those). | Users re-run manually or via their orchestrator. Single-run semantics keep the library predictable. |
| **Multi-step DAG pipelines** | Fan-out pipelines that depend on each other | DAG dependency resolution is Airflow's job. pycopg's runner is linear: one extract, one transform, one load. | Users call `db.etl.run()` multiple times in their own sequence. |
| **Pipeline versioning / schema evolution** | Auto-manage target schema changes when transform output columns change | Schema migration is already a distinct concern (migrations.py). ETL runner is not a schema migrator. | Use existing `migrations.py` for target schema changes. |
| **Streaming / micro-batch transforms** | Process rows in chunks to avoid OOM on large tables | Adds generator protocol to transforms, complicates error handling and row counting. Appropriate for v0.6.0 alongside incremental. | For large tables use `db.stream()` + `db.insert_many()` directly. |

---

## Feature Dependencies

```text
ETL-13 ETLAccessor (lazy accessor pattern)
    └── requires ETL-07 pipeline_runs DDL (auto-created in __init__)
    └── requires ETL-14 auto-create pipeline_runs

ETL-10 db.etl.run(pipeline)
    ├── requires ETL-01 Pipeline dataclass
    ├── requires ETL-02 Extract
    │       └── composes db.to_dataframe [EXISTING]
    ├── requires ETL-03 Transform callable
    ├── requires ETL-04/05/06 Load mode
    │       ├── ETL-04 composes db.insert_many [EXISTING]
    │       ├── ETL-05 composes db.execute TRUNCATE + db.insert_many [EXISTING]
    │       └── ETL-06 composes db.upsert_many [EXISTING]
    ├── requires ETL-08 Status lifecycle
    │       └── composes db.execute INSERT/UPDATE on pipeline_runs
    └── requires ETL-09 Transactional load
            └── composes db.transaction() [EXISTING]

ETL-11 db.etl.history(name)
    ├── requires ETL-07 pipeline_runs table exists
    └── composes db.execute [EXISTING]

ETL-12 async_db.etl.run(pipeline)
    ├── mirrors ETL-10 sync semantics exactly
    ├── composes async_db.to_dataframe [EXISTING]
    ├── composes async_db.insert_many / upsert_many [EXISTING]
    └── wraps sync transform callables in asyncio.to_thread()

Differentiator: Transform chain
    └── enhances ETL-03 (replace single callable with list)

Differentiator: GeoDataFrame support
    ├── enhances ETL-04/05/06
    └── composes db.from_geodataframe [EXISTING]
```

### Dependency Notes

- **ETL-05 (replace) requires a transaction:** TRUNCATE + INSERT must be atomic. Uses existing `db.transaction()`.
- **ETL-06 (upsert) requires `conflict_columns`:** Validated at `Pipeline` construction, not at run time. Fail fast.
- **ETL-07 (`pipeline_runs`) must exist before ETL-08:** Runner creates the table on accessor init; `run()` can assume it exists.
- **ETL-09 (transaction) and ETL-08 (run tracking) must NOT share a transaction:** Run tracking UPDATE (`status='failed'`) must commit even when the load transaction rolls back. Two separate transactions: (1) load, (2) run record update.
- **ETL-12 (async parity) requires `asyncio.to_thread` for sync transforms:** pandas is not async-safe; this is the confirmed pattern from existing `run_sync` usage in async spatial/DataFrame helpers.

---

## MVP Definition (v0.5.0 Launch Set)

### Must Ship (ETL-\* Table Stakes)

- [x] ETL-01 Pipeline dataclass — defines extract/transform/load declaratively
- [x] ETL-02 Extract from SQL or table name — delegates to `to_dataframe`
- [x] ETL-03 Transform callable (DataFrame→DataFrame), optional/no-op
- [x] ETL-04 Load mode: append
- [x] ETL-05 Load mode: replace (truncate-load, transactional)
- [x] ETL-06 Load mode: upsert (merge-by-key via `conflict_columns`)
- [x] ETL-07 `pipeline_runs` table — auto-created, persistent run audit
- [x] ETL-08 Status lifecycle: running → success / failed with timestamps and row counts
- [x] ETL-09 Transactional load (load tx separate from run tracking tx)
- [x] ETL-10 `db.etl.run(pipeline) -> RunResult` — the primary execution entry point
- [x] ETL-11 `db.etl.history(pipeline_name)` — query past runs
- [x] ETL-12 Async parity — `async_db.etl.run(pipeline)` and `async_db.etl.history(name)`
- [x] ETL-13 `ETLAccessor` lazy accessor on `db.etl` (mirrors `db.spatial`)
- [x] ETL-14 `pipeline_runs` auto-created if missing — no manual migration needed

### Add After MVP Validation

- [ ] Transform chain (list of callables) — ergonomic improvement once single-callable is solid
- [ ] `dry_run=True` mode — useful for testing transforms against production data
- [ ] `db.etl.last_run(pipeline_name)` — convenience wrapper
- [ ] GeoDataFrame-aware load — if spatial ETL use cases emerge

### Future (v0.6.0+)

- [ ] Incremental / watermark extract — `pipeline_runs.finished_at` is the hook point; do not build now
- [ ] Cross-DB transfer — separate Database instances as source/target
- [ ] File source/sink (CSV, Parquet)
- [ ] Streaming transforms for large tables
- [ ] Pipeline dependency DAGs

---

## Requirement Drafts (ETL-\* Testable Statements)

Each table-stakes feature maps to one concrete user-centric requirement:

| Req ID | Testable Requirement |
| --- | --- |
| ETL-01 | User can define a pipeline with `Pipeline(name=..., source=..., target=..., load_mode=...)` and the object is inspectable (`name`, `source`, `target`, `load_mode`, `schema` are readable attributes). |
| ETL-02 | User can set `source="SELECT * FROM raw_events"` (SQL) or `source="raw_events"` (table name) and both successfully extract a DataFrame on `run()`. |
| ETL-03 | User can pass `transform=None` (no-op) or `transform=lambda df: df.dropna()` and the transform is applied before load. An exception in the transform raises `ETLTransformError` and records a failed run. |
| ETL-04 | User can set `load_mode='append'` and running the pipeline twice inserts rows twice into the target. Target must exist; if not, raises `ETLTargetNotFoundError`. |
| ETL-05 | User can set `load_mode='replace'` and running the pipeline twice leaves only the most recent extract's rows in the target. If the target does not exist, it is created. The truncate+insert is atomic: a mid-load error leaves the target unchanged. |
| ETL-06 | User can set `load_mode='upsert'` with `conflict_columns=['id']` and running the pipeline twice updates existing rows and inserts new ones without duplicates. Omitting `conflict_columns` with `load_mode='upsert'` raises `ValueError` at pipeline construction time. |
| ETL-07 | After any `db.etl.run(pipeline)` call, a row exists in `pipeline_runs` with `run_id`, `pipeline_name`, `started_at`, `finished_at`, `status`, `rows_extracted`, `rows_loaded`. |
| ETL-08 | A pipeline run that raises an exception during load records `status='failed'` with a non-null `error_message` and `error_traceback`. The `pipeline_runs` record is committed even when the load transaction rolled back. |
| ETL-09 | In `replace` mode, if an error occurs after TRUNCATE but before INSERT commits, the target table still contains its original rows (the load transaction rolled back). |
| ETL-10 | `db.etl.run(pipeline)` returns a `RunResult` with `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, and `error` fields. |
| ETL-11 | `db.etl.history("my_pipeline")` returns a list of `RunResult` for all past runs of that pipeline, ordered newest-first. |
| ETL-12 | `await async_db.etl.run(pipeline)` and `await async_db.etl.history(name)` exist and produce equivalent results to sync versions. Both are enumerated in the existing `test_parity` harness. |
| ETL-13 | `db.etl` returns an `ETLAccessor` instance. `async_db.etl` returns an `AsyncETLAccessor` instance. Both are lazy (created on first access). |
| ETL-14 | The `pipeline_runs` table is created automatically on the first `db.etl.run()` call if it does not already exist. No user-run DDL is required. |

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
| --- | --- | --- | --- |
| ETL-01 Pipeline dataclass | HIGH | LOW | P1 — foundational |
| ETL-02 Extract from SQL/table | HIGH | LOW | P1 — composes existing |
| ETL-03 Transform callable | HIGH | LOW | P1 — core contract |
| ETL-04 Append load | HIGH | LOW | P1 — simplest load |
| ETL-05 Replace load | HIGH | MEDIUM | P1 — idempotency |
| ETL-06 Upsert load | HIGH | MEDIUM | P1 — idempotency |
| ETL-07 pipeline\_runs table | HIGH | MEDIUM | P1 — observability |
| ETL-08 Status lifecycle | HIGH | LOW | P1 — diagnostic |
| ETL-09 Transactional load | HIGH | MEDIUM | P1 — data safety |
| ETL-10 db.etl.run() | HIGH | MEDIUM | P1 — entry point |
| ETL-11 db.etl.history() | MEDIUM | LOW | P1 — usability |
| ETL-12 Async parity | HIGH | MEDIUM | P1 — core value |
| ETL-13 ETLAccessor | MEDIUM | LOW | P1 — pattern |
| ETL-14 Auto-create table | HIGH | LOW | P1 — zero-config |
| Transform chain | MEDIUM | LOW | P2 — ergonomic |
| dry\_run mode | MEDIUM | LOW | P2 — DX |
| last\_run() | LOW | LOW | P2 — convenience |
| GeoDataFrame load | LOW | MEDIUM | P3 — niche |

---

## Ecosystem Reference: How Lightweight Tools Solve This

| Design Decision | petl | dlt | Airflow dag\_run | This runner |
| --- | --- | --- | --- | --- |
| Pipeline definition | Table-chain composition | `dlt.pipeline(name, destination)` | `@dag` + `@task` decorator | `Pipeline` dataclass — explicit, inspectable |
| Transform signature | `row -> row` iterator | `@dlt.transformer` generator | `@task` callable | `Callable[[pd.DataFrame], pd.DataFrame]` |
| No-op transform | Identity by default | No source = no transform | Empty task | `transform=None` skips step |
| Load mode: replace | `petl.todb(table, create=True)` | `write_disposition='replace'` | DAG re-run clears old | `load_mode='replace'` — TRUNCATE+INSERT in single tx |
| Load mode: upsert | `petl.mergetodb(key=...)` | `write_disposition='merge'` + `primary_key` | Custom task | `load_mode='upsert'` + `conflict_columns=[...]` |
| Run tracking | None built-in | `_dlt_loads` table: load\_id, schema\_name, status, inserted\_at | `dag_run` table: dag\_id, run\_id, start\_date, end\_date, state | `pipeline_runs`: run\_id UUID, pipeline\_name, started\_at, finished\_at, status, rows\_extracted, rows\_loaded, error\_message, error\_traceback |
| Status lifecycle | N/A | 0=complete, other=incomplete | queued / running / success / failed | `running` → `success` / `failed` |
| Transactional load | No (row-by-row) | Destination-dependent | Task-level commit | TRUNCATE+INSERT in single tx (replace mode) |
| Async support | No | No native async | No (Celery workers) | Yes — `async_db.etl.*` via `asyncio.to_thread` for transforms |

---

## Sources

- [petl documentation](https://petl.readthedocs.io/latest/)
- [dlt load dispositions](https://dlthub.com/docs/general-usage/incremental-loading)
- [dlt destination tables](https://dlthub.com/docs/general-usage/destination-tables)
- [dlt architecture explainer](https://dlthub.com/docs/reference/explainers/how-dlt-works)
- [Airflow dag\_run schema](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dag-run.html)
- [Idempotency patterns in ETL](https://medium.com/@iamanjlikaur/ensuring-idempotency-in-data-ingestion-pipelines-33301cf917fb)
- [asyncio.to\_thread with pandas](https://stlplaces.com/blog/how-to-use-asyncio-with-pandas-dataframe)
- pycopg existing API: `pycopg/database.py`, `pycopg/async_database.py`, `pycopg/spatial.py`
- pycopg project context: `.planning/PROJECT.md`

---

*Feature landscape for: pycopg v0.5.0 ETL Pipeline Runner*
*Researched: 2026-06-14*
*Confidence: HIGH on table-stakes scope (clear codebase anchor + consistent ecosystem evidence); MEDIUM on exact ecosystem API shapes (ETL framework docs vary; petl/dlt behave differently; patterns verified across multiple sources)*
