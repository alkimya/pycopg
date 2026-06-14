# Project Research Summary

**Project:** pycopg v0.5.0 — ETL Pipeline Runner
**Domain:** Declarative same-DB ETL layer on top of an existing sync/async PostgreSQL library
**Researched:** 2026-06-14
**Confidence:** HIGH

## Executive Summary

pycopg v0.5.0 adds a thin, declarative ETL layer (`db.etl.*` / `async_db.etl.*`) on top of the
primitives already shipped in v0.4.0 — no new runtime dependencies. The entire feature surface
(Pipeline dataclass, EtlAccessor, AsyncEtlAccessor, `pipeline_runs` run-tracking table) is built
from stdlib `dataclasses` + `typing.Protocol`, the existing `to_dataframe` / `upsert_many` /
`from_dataframe` / `transaction()` methods, and SQL constants added to `queries.py`. The
implementation mirrors `spatial.py` exactly: pure, DB-free builder functions at module level; a
single `etl.py` file containing both sync and async accessors; lazy `db.etl` / `async_db.etl`
properties in `database.py` / `async_database.py`.

The recommended build order flows from the hard dependency graph: the pure layer (Pipeline
dataclass + SQL builders) must precede any I/O code; the `pipeline_runs` schema must be finalised
before load modes are wired (the two-independent-connection pattern for run-log writes is a
transaction-boundary architectural decision that the load step depends on); load modes (truncate /
upsert) must be solid before the full `run()` orchestrator is assembled; async parity is built in
parallel at each step — not bolted on at the end, per the PAR-* lesson from v0.4.0.

Three open design decisions surface across the research files and must be resolved at requirements
or early roadmap planning before any code is written: (1) how `pipeline_runs.watermark` is
represented (JSONB single column vs. two TEXT columns); (2) whether a load failure re-raises the
original exception or wraps it in a new `PipelineError`; and (3) whether `pipeline_runs` is
auto-created lazily on first `run()` or requires an explicit `db.etl.init()` call. The researchers
are not unanimous on (3): ARCHITECTURE.md favours explicit `init()`, FEATURES.md lists auto-create
as table stakes (ETL-14). This must be decided before Phase B starts.

## Key Findings

### Recommended Stack

**Verdict: zero new runtime dependencies.** Every ETL capability required by v0.5.0 is already
present in the installed stack (psycopg 3.3.4, psycopg_pool 3.3.1, pandas 3.0.3, SQLAlchemy 2.0.50,
tenacity 9.1.4) or in Python 3.11+ stdlib (`dataclasses`, `typing.Protocol`, `asyncio.to_thread`,
`datetime`, `uuid`). No new `pyproject.toml` entry is needed.

**Core technologies (roles in ETL layer):**
- **stdlib `dataclasses` + `typing.Protocol`:** `Pipeline`, `ExtractSpec`, `LoadSpec` frozen
  dataclasses; `TransformFn` Protocol. Zero-dep, introspectable, validated via `__post_init__`.
- **psycopg 3.3.4:** extract (raw SQL SELECT), load (INSERT / COPY), DDL for `pipeline_runs`,
  independent autocommit connections for run-log writes.
- **pandas 3.0.3:** extract result is a DataFrame; transform callable receives and returns one;
  load delegates to existing `from_dataframe` / `upsert_many`.
- **SQLAlchemy 2.0.50:** already wired via `to_dataframe` / `from_dataframe`; ETL load reuses the
  same path.
- **`asyncio.to_thread` (stdlib):** wraps sync transform callables in `AsyncEtlAccessor` — the
  same delegation pattern as `conn.run_sync` throughout `async_database.py`.
- **tenacity 9.1.4:** inherited transparently; ETL runner benefits from existing
  `OperationalError` retry without any new wiring.

Do NOT add: dlt, Airflow, Prefect, Pydantic, attrs, alembic, apache-beam, asyncpg, pyarrow, or any
scheduler. All are overkill for same-DB, single-process, Python-callable-transform ETL.

### Expected Features

**Must have (table stakes — all 14 ETL-* items):**
- ETL-01: `Pipeline` dataclass — declarative, inspectable descriptor
- ETL-02: Extract from SQL string or table name — delegates to `to_dataframe`
- ETL-03: Python callable transform (`DataFrame -> DataFrame`), optional / no-op
- ETL-04: Load mode `append` — `insert_many`, target must exist
- ETL-05: Load mode `replace` (truncate-load) — atomic TRUNCATE + INSERT in one transaction
- ETL-06: Load mode `upsert` — `upsert_many` with `conflict_columns`, validated at construction
- ETL-07: `pipeline_runs` table — persistent run audit, auto-created, forward-compat schema
- ETL-08: Status lifecycle `running` -> `success` / `failed` with timestamps + row counts + error
- ETL-09: Transactional load — load transaction separate from run-tracking transaction
- ETL-10: `db.etl.run(pipeline) -> RunResult` — primary execution entry point
- ETL-11: `db.etl.history(pipeline_name)` — query past runs, newest-first
- ETL-12: Full async parity — `async_db.etl.run(pipeline)` and `async_db.etl.history(name)`
- ETL-13: `EtlAccessor` / `AsyncEtlAccessor` lazy accessor on `db.etl` / `async_db.etl`
- ETL-14: `pipeline_runs` auto-created on first use — no manual DDL required

**Should have (differentiators — add after MVP validation):**
- Transform chain: `transform=[clean, normalize, enrich]` — replace single callable with list
- `dry_run=True` mode — extract + transform, skip load, return `RunResult(status='dry_run')`
- `db.etl.last_run(pipeline_name)` — convenience wrapper over `history()[0]`
- GeoDataFrame-aware load — detect GeoDataFrame post-transform, route to `from_geodataframe`
- `pipeline_runs` schema-configurable — `ETLAccessor(db, schema='etl')` for multi-tenant isolation

**Defer to v0.6.0+ (anti-features for v0.5.0):**
- Incremental / watermark-based extract (`pipeline_runs` schema includes nullable watermark now so
  v0.6.0 requires no ALTER TABLE)
- Cross-DB transfer
- File source / sink (CSV, Parquet)
- SQL-only transforms
- Scheduling / cron / DAG / orchestration
- Streaming / micro-batch transforms

### Architecture Approach

The ETL layer adds one new file (`pycopg/etl.py`) and modifies four existing files (`queries.py`,
`database.py`, `async_database.py`, `__init__.py`). The pattern is a direct mirror of `spatial.py`:
pure, DB-free builder functions and frozen dataclasses at module level; both `EtlAccessor` (sync)
and `AsyncEtlAccessor` (async) in the same file; shared SQL builders called by both accessors
without duplication; lazy `db.etl` / `async_db.etl` properties using the identical shape as
`db.spatial` / `async_db.spatial`.

**Major components:**

1. **`Pipeline` / `ExtractSpec` / `LoadSpec` frozen dataclasses** (`etl.py`) — immutable, DB-free,
   validated in `__post_init__`; `conflict_columns` validated at construction time, not run time;
   `validate_identifiers` called on all identifier fields.
2. **Pure SQL builders** (`etl.py` module level) — `build_init_sql()`, `build_truncate_sql()`,
   shared between sync and async accessors; fully unit-testable without a DB.
3. **ETL SQL constants** (`queries.py` new `# ETL QUERIES` section) — `ETL_INIT_PIPELINE_RUNS`,
   `ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`.
4. **`EtlAccessor` (sync)** (`etl.py`) — public: `init()`, `run(pipeline)`, `list_runs(name,
   limit)`, `get_last_run(name)`; private: `_start_run()`, `_end_run()`, `_extract()`, `_load()`.
5. **`AsyncEtlAccessor` (async)** (`etl.py`) — identical public signature; all methods `async def`;
   transform dispatch via `asyncio.to_thread(transform_fn, df)` instead of direct call.
6. **Lazy `db.etl` / `async_db.etl` properties** (`database.py` / `async_database.py`) — two lines
   each: `_etl` field in `__init__`, lazy property following `db.spatial` shape exactly.
7. **`pipeline_runs` table** — forward-compat schema: TEXT status with CHECK constraint, BIGSERIAL PK,
   nullable `watermark` JSONB column (present and NULL in v0.5.0), independent autocommit connections
   for run-log writes.

**Critical transaction boundary:**
Run-log writes (`_start_run`, `_end_run`) use a dedicated raw connection opened via
`psycopg.connect(**db.config.connect_params(), autocommit=True)`, never the pool. The load step
runs inside `db.transaction()`. This ensures a failed load still records `status='failed'` in
`pipeline_runs` — the failure record is never rolled back.

### Critical Pitfalls

1. **Run-log in same transaction as load** — if `pipeline_runs` INSERT/UPDATE shares the load
   transaction, a failed run leaves no trace. Prevention: always use a dedicated autocommit
   connection for run-log writes, opened independently of the pool. Test: deliberately fail the
   load; assert `pipeline_runs` has `status='failed'` row.

2. **Truncate-then-fail data loss** — TRUNCATE without a wrapping transaction leaves the target
   empty if load fails after TRUNCATE. Prevention: always wrap TRUNCATE + INSERT in a single
   `db.transaction()`. Do NOT use `copy_insert` for truncate-load (COPY manages its own commit and
   is incompatible with an outer transaction without a staging table). Test: exception mid-insert;
   assert target row count equals pre-run count.

3. **Identifier injection in load SQL builders** — f-string interpolation of `pipeline.load_table`
   or `conflict_columns` without `validate_identifiers` is a SQL injection regression against the
   hardening shipped in v0.3.1. Prevention: every ETL load builder must call
   `validate_identifiers(table, schema)` and `validate_identifiers(*conflict_columns)` before any
   string interpolation. Extend `test_sql_injection.py` to cover ETL cases.

4. **Sync transform blocks the async event loop** — calling `transform_fn(df)` directly in
   `AsyncEtlAccessor.run()` blocks the event loop. Prevention: `await asyncio.to_thread(transform_fn, df)`
   — the same pattern as `conn.run_sync` in `async_database.py`. Test: slow transform + concurrent
   coroutine; assert the concurrent coroutine is not blocked.

5. **ETL accessor parity gap invisible to `test_parity`** — `test_parity.py` inspects top-level
   `Database` vs `AsyncDatabase` members; it sees `db.etl` on both but does not recurse into
   accessor classes. Prevention: add `TestEtlParity` class that inspects `EtlAccessor` vs
   `AsyncEtlAccessor` method surfaces using `inspect.getmembers`.

6. **`pipeline_runs` schema blocks v0.6.0** — using a PostgreSQL ENUM for `status` requires
   `ALTER TYPE` to add future values. Prevention: `status TEXT NOT NULL CHECK (status IN
   ('running', 'success', 'failed'))` with a nullable `watermark JSONB` column present from
   creation (always NULL in v0.5.0, written by v0.6.0 without ALTER TABLE).

7. **Coverage gate drops below 94%** — ETL adds I/O-heavy paths that need real-PG integration
   tests to cover. Prevention: write integration tests against `pycopg_test` for all ETL paths;
   measure `uv run pytest --cov` on real PG before raising the gate; per D-08, never raise the
   ratchet without measuring.

8. **Scope creep toward DAG / orchestrator** — `Pipeline` must not grow `depends_on`, `schedule`,
   `retry_on_failure`, or `parent_run_id` fields. `run()` executes exactly one pipeline,
   unconditionally. Document this boundary in the `Pipeline` docstring.

## Implications for Roadmap

The four researcher agents converged on a five-phase build order. Slight ordering differences
(ARCHITECTURE.md listed 11 steps; FEATURES.md grouped by feature cluster; PITFALLS.md mapped
pitfalls to phases) are reconciled here into one recommended sequence.

### Phase A: Pure Layer + Dataclasses (no DB)

**Rationale:** All downstream phases depend on the `Pipeline` / `ExtractSpec` / `LoadSpec`
dataclasses and the shared SQL builders. Building these first produces a stable, fully unit-testable
artifact before any I/O code is written.

**Delivers:** Frozen dataclasses with `__post_init__` validation; `TransformFn` Protocol;
`_validate_pipeline()`; pure builder functions; `queries.py` ETL constants section. All
unit-tested without a DB connection.

**Addresses:** ETL-01 (Pipeline dataclass), ETL-13 partial (accessor stubs)

**Avoids:** Scope creep (no DAG/scheduler fields in Pipeline); identifier injection
(`validate_identifiers` called in `__post_init__` from day one); wrong-schema trap
(`pipeline_runs` schema decided here, before DDL is written — resolve OD-1 and OD-3 in this phase).

**Research flag:** No deeper research needed. Pattern is fully established by `spatial.py`.

---

### Phase B: Run-Tracking Foundation (schema + lifecycle)

**Rationale:** The `pipeline_runs` schema and the two-connection run-log pattern are architectural
decisions that load wiring depends on. If the transaction boundary is designed wrong here, all
subsequent load phases inherit the bug. This phase must be complete and tests green before any
load code is written.

**Delivers:** `ETL_INIT_PIPELINE_RUNS` DDL; `EtlAccessor.init()` + `AsyncEtlAccessor.init()`;
`_start_run()` / `_end_run()` on dedicated autocommit connection (sync + async); `pipeline_runs`
row lifecycle (running -> success / failed); advisory lock (`pg_try_advisory_lock`) for
concurrent-run guard.

**Addresses:** ETL-07, ETL-08, ETL-14, ETL-09 partial (transaction boundary design)

**Avoids:** Run-log-in-same-transaction trap; pool exhaustion (raw `psycopg.connect`, not pool);
`pipeline_runs` schema blocking v0.6.0 (JSONB watermark column present, TEXT status with CHECK).

**Key dependency:** OD-3 (`init()` explicit vs. lazy auto-create) must be resolved before this
phase starts.

**Research flag:** No deeper research needed. Two-connection pattern confirmed by Airflow/dbt/Prefect
precedent and directly described in PITFALLS.md.

---

### Phase C: Load Modes (extract + truncate + upsert)

**Rationale:** Extract and load compose existing primitives (`to_dataframe`, `upsert_many`,
`from_dataframe`, `transaction()`). Building them after run-tracking means load errors are
immediately recorded by `_end_run()` during development.

**Delivers:** `_extract()` (sync + async); `_load(mode='replace')` — TRUNCATE +
`from_dataframe(if_exists='append')` inside `db.transaction()` (sync + async);
`_load(mode='upsert')` — `upsert_many` with `conflict_columns` (sync + async);
`_load(mode='append')` — `insert_many` (sync + async). All load builders call
`validate_identifiers` before any f-string.

**Addresses:** ETL-02, ETL-04, ETL-05, ETL-06, ETL-09

**Avoids:** Truncate-then-fail data loss (TRUNCATE inside transaction, not autocommit); identifier
injection (validate_identifiers in every builder); `copy_insert` incompatibility (do NOT use for
truncate-load — COPY and outer transactions conflict; document COPY-based path as deferred).

**Research flag:** No deeper research needed. Load primitives are existing, tested code.

---

### Phase D: Full Runner + Query Surface

**Rationale:** `EtlAccessor.run()` is the integration point that wires Phases A-C together. It
must come after all building blocks are independently tested. `list_runs` / `get_last_run` are
trivial once `pipeline_runs` rows exist.

**Delivers:** `EtlAccessor.run(pipeline) -> RunResult` (sync + async); `list_runs(name, limit)`
(sync + async); `get_last_run(name)` (sync + async); `RunResult` dataclass with all required fields;
end-to-end integration tests covering success, failure, re-run idempotency; `TestEtlParity` class
inspecting accessor method surfaces.

**Addresses:** ETL-10, ETL-11, ETL-12, ETL-03 (transform dispatch)

**Avoids:** Async event-loop blockage (`asyncio.to_thread` in async `run()`); ETL accessor parity
gap (`TestEtlParity` written test-first before async implementation); coverage gate drop (all
failure branches are integration-tested against `pycopg_test`, no mock-DB shortcuts).

**OD-2 must be resolved here:** does `run()` re-raise the original exception or wrap in
`PipelineError`? Recommendation: re-raise the original; document that the run is recorded before
re-raise.

**Research flag:** No deeper research needed. Orchestration pattern fully described in ARCHITECTURE.md.

---

### Phase E: Wiring, Exports, Docs, Coverage Gate

**Rationale:** Lazy properties and public exports add no logic — they are the integration seam.
Wiring last avoids exposing an incomplete API surface during development.

**Delivers:** `db.etl` / `async_db.etl` lazy properties; `from pycopg import Pipeline,
EtlAccessor, AsyncEtlAccessor` exports; `docs/etl.md` Sphinx page; CHANGELOG v0.5.0 entry;
MIGRATION.md bootstrap note; coverage gate measured and held at >= 94%; `interrogate >= 95` on
ETL docstrings.

**Addresses:** ETL-13 (lazy accessor), public API completeness, docs/release readiness

**Avoids:** Coverage gate drop (measure before declaring done, per D-08); `test_parity` regression
(the `etl` property must appear on both `Database` and `AsyncDatabase`; `SYNC_ONLY_METHODS` /
`ASYNC_ONLY_METHODS` must not gain ETL exceptions).

**Research flag:** No deeper research needed. Follows established release checklist from Phase 15.

---

### Phase Ordering Rationale

- **Pure layer first (A):** zero dependencies; forces open design decisions before any I/O code.
- **Run-tracking before load (B before C):** the two-connection transaction pattern is an
  architectural constraint the load step's error handling depends on.
- **Load before full runner (C before D):** `run()` is a thin orchestrator of extract + transform
  + load + run tracking; all four must exist independently before wiring.
- **Sync and async together at each phase:** PAR-* lesson from v0.4.0 Phase 11 — sync-only then
  async-catch-up produces parity drift.
- **Wiring last (E):** lazy properties and exports have no logic; wiring last keeps the public API
  complete at first exposure.

### Research Flags

All phases have standard, well-established patterns. No phase requires
`/gsd-plan-phase --research-phase` deep-dive:
- **Phase A:** direct mirror of `spatial.py` frozen dataclasses + Protocol
- **Phase B:** two-connection run-log and `pg_try_advisory_lock` are stable, documented PG APIs
- **Phase C:** load primitives are existing tested methods; transaction pattern is established
- **Phase D:** orchestration wiring; all patterns known; `asyncio.to_thread` is stdlib since 3.9
- **Phase E:** release checklist identical to Phase 15 (v0.4.0)

## Open Design Decisions

These three items must be decided at requirements or roadmap review time, before Phase B starts.

### OD-1: `pipeline_runs` Watermark Column Shape

ARCHITECTURE.md recommends a single `watermark JSONB` column. PITFALLS.md (Pitfall 10) recommends
two TEXT columns `watermark_column TEXT` + `watermark_value TEXT`. Both are forward-compat for v0.6.0.
**Recommendation: JSONB single column** — leaner schema, flexible for any watermark type, avoids
manual column-name-to-value mapping at v0.6.0 read time.

### OD-2: Exception Strategy on Load Failure

FEATURES.md: "Re-raises the original exception after recording failure." ARCHITECTURE.md mentions
optional `PipelineError` in `exceptions.py`. **Recommendation: re-raise the original exception** —
stack trace is preserved; callers do not need a new exception type to catch ETL failures.

### OD-3: `pipeline_runs` Initialisation

ARCHITECTURE.md strongly recommends explicit `db.etl.init()`. FEATURES.md ETL-14 requires
auto-create. **Recommendation: both** — lazy `CREATE TABLE IF NOT EXISTS` inside `run()` as the
zero-config default, with `init()` also exposed as an explicit bootstrap convenience for callers
who want separation of setup from execution. The idempotent DDL makes both safe to call.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against live venv; zero-new-deps conclusion is certain |
| Features | HIGH | 14 table-stakes items have clear codebase anchors; differentiators confirmed against petl/dlt/Airflow precedent |
| Architecture | HIGH | Pattern read directly from `spatial.py`; all signatures and file paths verified in source |
| Pitfalls | HIGH | Derived from actual codebase code paths (`database.py`, `async_database.py`, `test_parity.py`), not generic ETL theory |

**Overall confidence:** HIGH

### Gaps to Address

- **OD-1 / OD-2 / OD-3:** one-sentence decisions each; no additional research required.
- **Advisory lock scope:** PITFALLS.md recommends `pg_try_advisory_lock` for concurrent-run
  protection. If deemed too complex for MVP, it can be deferred with documented risk. The data
  integrity risk for concurrent truncate-load is HIGH; deferral is not recommended.
- **`extract_limit` / `extract_batch_size`:** PITFALLS.md Pitfall 7 recommends these to prevent OOM
  on large tables; FEATURES.md does not include them in table stakes. Recommendation: add
  `extract_limit: int | None = None` as a zero-cost optional `Pipeline` field with a clear memory
  contract in the docstring; full `extract_batch_size` streaming deferred to v0.6.0.

## Sources

### Primary (HIGH confidence — direct source reading)

- `/home/loc/workspace/pycopg/pycopg/spatial.py` — canonical accessor pattern mirrored by ETL layer
- `/home/loc/workspace/pycopg/pycopg/database.py` — `upsert_many`, `from_dataframe`, `transaction()`, `spatial` lazy property
- `/home/loc/workspace/pycopg/pycopg/async_database.py` — `run_sync` pattern, async `to_dataframe`, async `transaction()`
- `/home/loc/workspace/pycopg/pycopg/queries.py` — SQL constant conventions and section style
- `/home/loc/workspace/pycopg/pycopg/base.py` — `DatabaseBase`, `QueryMixin`, pure builder functions
- `/home/loc/workspace/pycopg/pycopg/migrations.py` — tracking-table bootstrap pattern for `Migrator`
- `/home/loc/workspace/pycopg/tests/test_parity.py` — parity harness mechanics and exception sets
- `/home/loc/workspace/pycopg/.planning/PROJECT.md` — v0.5.0 scope, deferred items, D-08 coverage rule
- Live venv introspection — psycopg 3.3.4, pandas 3.0.3, psycopg_pool 3.3.1, tenacity 9.1.4, SQLAlchemy 2.0.50

### Secondary (MEDIUM confidence — ecosystem documentation)

- petl documentation — load mode naming, chain transform pattern
- dlt load dispositions — `write_disposition='replace'/'merge'`, `_dlt_loads` table schema
- Airflow dag_run schema — status lifecycle, separate state connection precedent
- asyncio.to_thread with pandas — event-loop-safe sync callable dispatch
- PostgreSQL docs — `pg_try_advisory_lock`, `TEXT + CHECK` vs `ENUM`, COPY within transaction

---
*Research completed: 2026-06-14*
*Ready for roadmap: yes*
