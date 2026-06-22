# Technology Stack — v0.8.0 TimescaleDB Advanced Features

**Project:** pycopg v0.8.0 — Advanced TimescaleDB features under `db.timescale.*`
**Researched:** 2026-06-22
**Scope:** Stack additions needed for continuous aggregates, `time_bucket`/`time_bucket_gapfill`, `show_chunks`/`drop_chunks`, `add_dimension`, `reorder_policy`.
**Confidence:** HIGH

---

## Verdict: Zero New Runtime Dependencies Confirmed

All v0.8.0 features are buildable with the existing runtime stack. No additions to
`pyproject.toml` are required.

**Confidence:** HIGH — verified against official TimescaleDB API docs (tigerdata.com)
and the existing psycopg 3 accessor pattern in `pycopg/timescale.py`.

---

## Existing Stack (Do Not Change)

| Technology | Version Constraint | Role in v0.8.0 |
|---|---|---|
| Python | 3.11+ | Language |
| psycopg | >=3.1.0 (installed: 3.3.4) | PostgreSQL driver; `conn.autocommit = True` for CAGG DDL |
| psycopg_pool | >=3.2.0 | Connection pooling (no change) |
| pandas | >=2.0.0 | DataFrame return path for `time_bucket`/`time_bucket_gapfill` helpers |
| geopandas | >=0.14.0 | Not involved in TimescaleDB features |
| tenacity | any | Retry/backoff; no role in this milestone |

No new entry needed. All required functionality is already present.

---

## TimescaleDB Server Version Floor

**Minimum: TimescaleDB 2.0** — with feature-specific floors noted below.

The v0.8.0 target is "TimescaleDB 2.x only" (locked scope decision, PROJECT.md).
The rationale for the version floor by feature group:

| Feature Group | Effective Floor | Why |
|---|---|---|
| `CREATE MATERIALIZED VIEW … WITH (timescaledb.continuous)` | 2.0 | Continuous aggregates (modern materialized-view form) shipped in 1.3.0; by 2.0 the API was stable and the old `continuous_agg_policy` interface was replaced |
| `refresh_continuous_aggregate()` | 2.0 | Available since 1.3.0; `CALL` syntax stable in 2.0 |
| `add_continuous_aggregate_policy()` | 2.0 | Available since 1.7.0; current named-parameter form stable in 2.0 |
| `time_bucket()` | 2.0 | Available since 0.0.10-beta; timezone parameter available in 2.x |
| `time_bucket_gapfill()` | 2.0 | Available since 1.2.0; `timezone` parameter requires 2.9+ |
| `show_chunks()` / `drop_chunks()` | 2.0 | `drop_chunks` 2.x form (requires explicit hypertable arg) available in 2.0 |
| `add_dimension()` modern API | **2.13** | The `by_range()`/`by_hash()` builders were introduced in 2.13; the deprecated positional signature is available since 0.1.0 |
| `add_reorder_policy()` | 2.0 | Available since 1.2.0 |

**Practical recommendation:** document the floor as **TimescaleDB >= 2.0** for all features
except `add_dimension()` with the modern API, which requires **>= 2.13** (document explicitly
in the method's docstring Raises section or Notes). The existing `_check_timescaledb` guard
verifies extension presence but not the version — implement the 2.13 note as a documentation
warning only (version introspection would require a new query, not worth the complexity at
this scope).

---

## PostgreSQL Version Requirements

| TimescaleDB Series | Minimum PostgreSQL |
|---|---|
| 2.0 | 12 |
| 2.1–2.3 | 11 |
| 2.4–2.9 | 12 |
| 2.10–2.12 | 12 |
| 2.13–2.15 | 13 |
| 2.16–2.22 | 14–15 |
| 2.23–2.28 | 15 |
| 2.29+ | 16 |

The project's existing test environment targets local PostgreSQL 15/16 with TimescaleDB 2.x,
which satisfies the floor for all features including `add_dimension` modern API (2.13 → PG 13+).
No special PostgreSQL minimum is required beyond what TimescaleDB 2.x already imposes.

---

## Critical: Transaction-Block Restrictions

This is the most important integration concern for the v0.8.0 implementation.
**Two operations cannot run inside a transaction block and require a dedicated autocommit
connection or session.** This mirrors the ETL run-log isolation pattern already used in
`pycopg/etl.py`.

### Operations That CANNOT Run Inside a Transaction Block

#### 1. `CREATE MATERIALIZED VIEW … WITH (timescaledb.continuous) … WITH DATA`

**Exact error:** `ERROR: CREATE MATERIALIZED VIEW ... WITH DATA cannot run inside a transaction block`

**Why:** TimescaleDB's continuous aggregate creation with data materialization runs an
internal two-phase process that opens its own transactions. PostgreSQL does not allow
`CREATE MATERIALIZED VIEW … WITH DATA` inside an explicit transaction block.

**Workaround A — autocommit connection (RECOMMENDED):**
Open a dedicated `psycopg.connect(autocommit=True)` connection (or `conn.autocommit = True`),
issue the DDL, then close/return it. The existing `Database._connect_autocommit()` helper
(used by ETL run-logging) provides exactly this pattern. Use the same helper for CAGG DDL.

**Workaround B — `WITH NO DATA`:**
`CREATE MATERIALIZED VIEW … WITH NO DATA` CAN run inside a transaction block because it
defers materialization. The caller must then issue `CALL refresh_continuous_aggregate(…)`
separately (which itself also needs autocommit — see below).

**pycopg integration point:** `TimescaleAccessor.create_continuous_aggregate()` must NOT
use `self._db.execute()` (which runs under the normal psycopg connection, which psycopg 3
wraps in implicit transactions). Instead it must obtain an autocommit connection via the same
mechanism as `ETLAccessor._autocommit_conn()`.

#### 2. `CALL refresh_continuous_aggregate(…)`

**Why:** The refresh runs internally across two transactions (first to advance the
invalidation threshold, second to materialize). This multi-transaction behavior is
incompatible with PostgreSQL transaction blocks. (GitHub issue #2876, confirmed in
TimescaleDB docs and community.)

Since TimescaleDB 2.28, refresh is batched by default (each batch = its own transaction),
which reinforces this requirement.

**Autocommit is mandatory** for `refresh_continuous_aggregate`. Same pattern as
`create_continuous_aggregate`: use a dedicated autocommit connection.

**pycopg integration point:** `TimescaleAccessor.refresh_continuous_aggregate()` must also
use the autocommit connection helper.

### Operations That CAN Run Inside a Normal Transaction Block

The following operations are standard SQL/PL/pgSQL functions — they execute within the
caller's transaction and do not open their own internal transactions:

| Operation | Transaction Safe | Notes |
|---|---|---|
| `add_continuous_aggregate_policy()` | YES | Returns job_id; standard function call |
| `show_chunks()` | YES | Read-only SELECT-returning function |
| `drop_chunks()` | YES | Standard function; commits chunk drops atomically with the caller |
| `add_dimension()` | YES | Standard function; empty-hypertable constraint is a logical (not transactional) restriction |
| `add_reorder_policy()` | YES | Returns job_id; standard function call |
| `time_bucket()` / `time_bucket_gapfill()` | YES | Pure SQL functions embedded in SELECT queries |

These can all use `self._db.execute()` / `self._db.to_dataframe()` via the normal connection.

---

## Autocommit Pattern — Integration with Existing psycopg Model

psycopg 3 wraps every connection in an implicit transaction by default. DDL/commands that
require autocommit must use `conn.autocommit = True` or `psycopg.connect(autocommit=True)`.

The ETL accessor already solves this: `_autocommit_conn()` opens a dedicated connection
(bypassing the pool) with `autocommit=True`, uses it for run-log inserts/updates, and
closes it when done. The CAGG methods must use the same helper. Do NOT set
`conn.autocommit = True` on the pool connection — that would mutate shared pool state.

**Confirmed psycopg 3 API** (MEDIUM confidence — official docs, not live-tested here):
```python
# Option A: connect() parameter
conn = psycopg.connect(conninfo, autocommit=True)

# Option B: attribute (must be set before first statement)
conn.autocommit = True
```

The existing `Database._autocommit_conn()` (introduced for ETL run-logging) already
implements Option A. Reuse it for CAGG DDL and refresh — no new infrastructure.

For `AsyncTimescaleAccessor`, use the async equivalent:
```python
conn = await psycopg.AsyncConnection.connect(conninfo, autocommit=True)
```
The `AsyncDatabase._autocommit_conn()` async equivalent should already exist (ETL parity);
verify before Phase implementation.

---

## Function Signatures (Verified Against Official Docs)

### Continuous Aggregates

**`CREATE MATERIALIZED VIEW` DDL** (via `create_continuous_aggregate()`):
```sql
CREATE MATERIALIZED VIEW <view_name>
WITH (timescaledb.continuous [, timescaledb.materialized_only = TRUE|FALSE])
AS SELECT time_bucket(<interval>, <time_col>) AS bucket, <agg_exprs>
   FROM <hypertable>
   GROUP BY bucket [, <other_cols>]
[WITH [NO] DATA]
```
Requires autocommit. `WITH NO DATA` avoids the transaction restriction but then
`refresh_continuous_aggregate` is needed afterward (also autocommit).

**`refresh_continuous_aggregate()`** — `CALL`, not `SELECT`:
```sql
CALL refresh_continuous_aggregate(
    continuous_aggregate => '<view_name>',   -- REGCLASS
    window_start => <interval_or_timestamptz>,
    window_end   => <interval_or_timestamptz>
    [, force => FALSE]
)
```
Requires autocommit. Available since TimescaleDB 1.3.0; parameters stable in 2.x.

**`add_continuous_aggregate_policy()`**:
```sql
SELECT add_continuous_aggregate_policy(
    continuous_aggregate => '<view_name>',  -- REGCLASS
    start_offset         => INTERVAL,        -- NULL = MIN(timestamp)
    end_offset           => INTERVAL,        -- NULL = MAX(timestamp)
    schedule_interval    => INTERVAL,        -- required
    if_not_exists        => FALSE,
    initial_start        => NULL,            -- TIMESTAMPTZ
    timezone             => NULL             -- TEXT
)
```
Returns INTEGER `job_id`. Transaction-safe. Available since 1.7.0; stable in 2.x.

### Chunk Management

**`show_chunks()`**:
```sql
SELECT show_chunks(
    relation     => '<hypertable_or_cagg>',  -- REGCLASS, required
    older_than   => <interval_or_timestamp>,  -- optional
    newer_than   => <interval_or_timestamp>,  -- optional
    created_before => <interval_or_timestamp>, -- optional (cannot combine with older_than)
    created_after  => <interval_or_timestamp>  -- optional (cannot combine with newer_than)
)
```
Returns REGCLASS set (chunk names). Transaction-safe. Available since 0.9.0.

**`drop_chunks()`**:
```sql
SELECT drop_chunks(
    relation     => '<hypertable_or_cagg>',  -- REGCLASS, required (2.x: no cross-table drops)
    older_than   => <interval_or_timestamp>,
    newer_than   => <interval_or_timestamp>,
    verbose      => FALSE,
    created_before => <interval_or_timestamp>,
    created_after  => <interval_or_timestamp>
)
```
Transaction-safe. The 2.x form requires an explicit `relation` arg (cannot drop across all
hypertables). Available since 0.1.0; 2.x form is breaking vs 1.x.

### Hypertable Management

**`add_dimension()`** — modern API (TimescaleDB >= 2.13):
```sql
SELECT add_dimension(
    hypertable   => '<table_name>',          -- REGCLASS
    dimension    => by_range('<col>', <interval>) | by_hash('<col>', <num_partitions>),
    if_not_exists => FALSE
)
```
Transaction-safe. **Only works on EMPTY hypertables** (no chunks). Available since 2.13.0
for this `by_range`/`by_hash` form; deprecated positional form since 0.1.0.

**`add_reorder_policy()`**:
```sql
SELECT add_reorder_policy(
    hypertable   => '<table_name>',  -- REGCLASS
    index_name   => '<index_name>',  -- TEXT
    if_not_exists => FALSE,
    initial_start => NULL,           -- TIMESTAMPTZ
    timezone      => NULL            -- TEXT
)
```
Returns INTEGER `job_id`. Transaction-safe. Available since 1.2.0.

### Query Helpers

**`time_bucket()`** — pure SQL function, embedded in SELECT:
```sql
time_bucket(
    bucket_width => INTERVAL | SMALLINT | INT | BIGINT,
    ts           => TIMESTAMP | TIMESTAMPTZ | DATE | SMALLINT | INT | BIGINT,
    offset       => INTERVAL | INTEGER,  -- optional
    origin       => TIMESTAMP | TIMESTAMPTZ | DATE,  -- optional
    timezone     => TEXT  -- optional, TIMESTAMPTZ only
)
```
Available since 0.0.10-beta. `timezone` param available in 2.x.

**`time_bucket_gapfill()`** — pure SQL function, embedded in SELECT with GROUP BY:
```sql
time_bucket_gapfill(
    bucket_width => INTERVAL,
    ts           => TIMESTAMP | TIMESTAMPTZ,
    start        => TIMESTAMP | TIMESTAMPTZ,  -- optional but recommended (lower bound)
    finish       => TIMESTAMP | TIMESTAMPTZ,  -- REQUIRED for gapfill to work correctly
    timezone     => TEXT                       -- optional, requires TimescaleDB >= 2.9
)
```
Available since 1.2.0. `timezone` param requires 2.9+.

**Key restriction for `time_bucket_gapfill`:** must appear as a top-level expression
directly in the GROUP BY clause — cannot be wrapped in another function. The SQL builder
for this function must produce queries where `time_bucket_gapfill(...)` is the GROUP BY
expression directly. An upper bound (`finish`) is required for correct gapfill behavior;
the builder should require it as a non-optional parameter.

---

## What NOT to Add

| Rejected approach | Reason |
|---|---|
| Any new runtime dep | Hard project constraint: zero new runtime deps |
| `timescaledb-python` or similar SDK | Does not exist as a stable lib; SQL is the interface |
| Setting `autocommit=True` on the pool connection | Would corrupt pool state; always use a dedicated `_autocommit_conn()` |
| Version-introspection guard for `add_dimension` 2.13 API | Over-engineering; document the 2.13 floor in the docstring, let psycopg surface the SQL error if the server is older |
| `DROP MATERIALIZED VIEW` method for CAGG teardown | Out of scope for v0.8.0; schema-level DDL belongs in `db.schema.*`, not `db.timescale.*` |
| `locf()` / `interpolate()` gapfill helpers | Advanced gapfill; defer to v0.9.0+ if requested |
| `reorder_chunk()` (manual single-chunk reorder) | Out of scope; `add_reorder_policy()` (automated) is the target |

---

## Version Compatibility Summary

| Component | Minimum | Notes |
|---|---|---|
| TimescaleDB | 2.0 | All features except `add_dimension` modern API |
| TimescaleDB | 2.9 | `time_bucket_gapfill` timezone parameter |
| TimescaleDB | 2.13 | `add_dimension` with `by_range`/`by_hash` builders |
| PostgreSQL | 13 | Implied by TimescaleDB 2.13 minimum (for `add_dimension` modern API) |
| psycopg | >=3.1.0 (project floor) | `autocommit=True` on `connect()` available since psycopg 3.0 |
| Python | 3.11+ (project floor) | No new Python requirements |

---

## Sources

- TimescaleDB API — `create_materialized_view`:
  https://www.tigerdata.com/docs/api/latest/continuous-aggregates/create_materialized_view
- TimescaleDB API — `refresh_continuous_aggregate`:
  https://www.tigerdata.com/docs/reference/timescaledb/continuous-aggregates/refresh_continuous_aggregate
- TimescaleDB API — `add_continuous_aggregate_policy`:
  https://www.tigerdata.com/docs/reference/timescaledb/continuous-aggregates/add_continuous_aggregate_policy
- TimescaleDB API — `show_chunks`:
  https://www.tigerdata.com/docs/reference/timescaledb/hypertables/show_chunks
- TimescaleDB API — `drop_chunks`:
  https://www.tigerdata.com/docs/reference/timescaledb/hypertables/drop_chunks
- TimescaleDB API — `add_dimension` (modern):
  https://www.tigerdata.com/docs/reference/timescaledb/hypertables/add_dimension
- TimescaleDB API — `add_reorder_policy`:
  https://www.tigerdata.com/docs/reference/timescaledb/hypertables/add_reorder_policy
- TimescaleDB API — `time_bucket`:
  https://www.tigerdata.com/docs/api/latest/hyperfunctions/time_bucket
- TimescaleDB API — `time_bucket_gapfill`:
  https://www.tigerdata.com/docs/api/latest/hyperfunctions/gapfilling/time_bucket_gapfill
- TimescaleDB docs — create a continuous aggregate (transaction restriction):
  https://www.tigerdata.com/docs/use-timescale/latest/continuous-aggregates/create-a-continuous-aggregate
- TimescaleDB GitHub issue #2876 — `refresh_continuous_aggregate` cannot run in transaction:
  https://github.com/timescale/timescaledb/issues/2876
- TimescaleDB PostgreSQL version compatibility matrix:
  https://www.tigerdata.com/docs/deploy/self-hosted/upgrades/upgrade-pg
- psycopg 3 transaction management / autocommit:
  https://www.psycopg.org/psycopg3/docs/basic/transactions.html
- Existing pycopg codebase — `pycopg/timescale.py`, `pycopg/etl.py` (ETL autocommit pattern)

---
*Stack research for: pycopg v0.8.0 — TimescaleDB advanced features*
*Researched: 2026-06-22*
