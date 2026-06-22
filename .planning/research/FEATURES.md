# Feature Research — TimescaleDB Advanced API (v0.8.0)

**Domain:** TimescaleDB 2.x time-series feature surface for a high-level Python wrapper (`db.timescale.*`)
**Researched:** 2026-06-22
**Confidence:** HIGH (official TimescaleDB 2.x API docs verified via tigerdata.com; codebase patterns confirmed from `pycopg/timescale.py`)

---

## Context: What v0.8.0 Adds

`db.timescale.*` was created in v0.6.0 with six methods covering hypertable basics:
`create_hypertable`, `enable_compression`, `add_compression_policy`, `add_retention_policy`,
`list_hypertables`, `hypertable_info`.

v0.8.0 adds five new feature areas to the same accessor, all under the same pure-builder
+ validate_identifiers + `%s`-params + lazy-accessor + sync/async parity pattern.

**Pattern contract inherited from the existing accessor:**
- TimescaleDB extension guard: `has_extension("timescaledb")` checked inside each method
- Identifiers always go through `validate_identifier` / `validate_identifiers`
- User-supplied values (intervals, timestamps) always passed as `%s` params — never f-string interpolated
- Pure SQL builders return `(sql: str, params: list)` tuples
- `None` returns for DDL/management; `list[dict]` for queries; `DataFrame` for query-helpers
- `AsyncTimescaleAccessor` mirrors every method exactly with `await`

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features any TimescaleDB Python user assumes exist once they see `db.timescale.*`.
Missing any of these makes the milestone feel incomplete.

---

#### TS-ADV-01 — `create_continuous_aggregate`

**Underlying SQL:**
```sql
CREATE MATERIALIZED VIEW {schema}.{view_name}
  WITH (timescaledb.continuous [, timescaledb.materialized_only = TRUE|FALSE])
  AS {select_sql}
  [WITH [NO] DATA]
```

The `select_sql` body **must** contain a `GROUP BY time_bucket(...)` clause — this is enforced
by TimescaleDB at DDL time, not by the wrapper. The wrapper cannot and should not validate it.

**Parameters (required vs optional, with defaults justified):**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `view_name` | `str` | Yes | — | Target cagg name |
| `select_sql` | `str` | Yes | — | The full SELECT body (must use `time_bucket`) |
| `schema` | `str` | No | `"public"` | Matches existing accessor convention |
| `materialized_only` | `bool` | No | `True` | TimescaleDB 2.x default; `False` enables real-time aggregation at query cost |
| `with_no_data` | `bool` | No | `False` | `False` = `WITH DATA` (immediate refresh on create), `True` defers; default matches PostgreSQL MATERIALIZED VIEW behavior |

**Proposed Python signature:**
```python
def create_continuous_aggregate(
    self,
    view_name: str,
    select_sql: str,
    schema: str = "public",
    materialized_only: bool = True,
    with_no_data: bool = False,
) -> None:
```

**Return shape:** `None` (DDL)

**Security note:** `view_name` and `schema` go through `validate_identifiers`. `select_sql` is
passed verbatim as part of the DDL — it cannot be parameterized (it is structure, not a value).
This is the same pattern as all PostgreSQL DDL. Document that `select_sql` must not be
constructed from untrusted input.

**Classification:** TABLE STAKES — continuous aggregates are the flagship TimescaleDB feature;
the accessor without them is a half-finished time-series API.

**Dependency note:** `select_sql` must contain `time_bucket(...)`. The `time_bucket` query helper
(TS-ADV-03) is a companion but not a code dependency — users write `time_bucket` SQL inline.

---

#### TS-ADV-02 — `refresh_continuous_aggregate`

**Underlying SQL:**
```sql
CALL refresh_continuous_aggregate(
    '{schema}.{view_name}',
    %s,  -- window_start (TIMESTAMPTZ / INTERVAL / INTEGER / NULL)
    %s   -- window_end   (TIMESTAMPTZ / INTERVAL / INTEGER / NULL)
)
```

TimescaleDB 2.x uses `CALL` (not `SELECT`) for this procedure.

`NULL` for `window_start` = lowest changed element; `NULL` for `window_end` = highest changed
element. Both NULL = full refresh.

**Parameters:**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `view_name` | `str` | Yes | — | Target cagg name |
| `window_start` | `datetime \| str \| None` | No | `None` | NULL = from the beginning |
| `window_end` | `datetime \| str \| None` | No | `None` | NULL = to the end; both None = full refresh |
| `schema` | `str` | No | `"public"` | Accessor convention |

Accepting `datetime | str | None` allows callers to pass Python `datetime` objects (psycopg 3
handles the type adaptation) or interval strings like `'1 month'`.

**Proposed Python signature:**
```python
def refresh_continuous_aggregate(
    self,
    view_name: str,
    window_start: "datetime | str | None" = None,
    window_end: "datetime | str | None" = None,
    schema: str = "public",
) -> None:
```

**Return shape:** `None` (procedure call, management)

**Classification:** TABLE STAKES — `create_continuous_aggregate` without `refresh_continuous_aggregate`
leaves the cagg stale; a wrapper that cannot manually refresh is incomplete.

**Dependency:** Requires TS-ADV-01 (a cagg must exist before it can be refreshed).

---

#### TS-ADV-03 — `add_continuous_aggregate_policy`

**Underlying SQL:**
```sql
SELECT add_continuous_aggregate_policy(
    '{schema}.{view_name}',
    start_offset => %s::INTERVAL,
    end_offset   => %s::INTERVAL,
    schedule_interval => %s::INTERVAL
    [, if_not_exists => TRUE]
)
```

`start_offset` must be greater than `end_offset` (both are offsets from `now()`, so `'30 days'`
is further back than `'1 day'`).

**Parameters:**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `view_name` | `str` | Yes | — | Target cagg |
| `start_offset` | `str` | Yes | — | e.g. `'30 days'` — interval string |
| `end_offset` | `str` | Yes | — | e.g. `'1 hour'` — must be < start_offset |
| `schedule_interval` | `str` | No | `'1 hour'` | Matches common time-series batch cadence; TimescaleDB default is 24h but 1h is more useful for active systems |
| `schema` | `str` | No | `"public"` | Accessor convention |
| `if_not_exists` | `bool` | No | `True` | Idempotent by default, consistent with `create_hypertable(if_not_exists=True)` |

All interval strings go through `validate_interval`.

**Proposed Python signature:**
```python
def add_continuous_aggregate_policy(
    self,
    view_name: str,
    start_offset: str,
    end_offset: str,
    schedule_interval: str = "1 hour",
    schema: str = "public",
    if_not_exists: bool = True,
) -> None:
```

**Return shape:** `None` (policy management; underlying function returns job_id INTEGER but
the wrapper discards it — consistent with `add_compression_policy` / `add_retention_policy`)

**Classification:** TABLE STAKES — the continuous aggregate lifecycle is only complete with
auto-refresh. Without this, users must schedule `refresh_continuous_aggregate` calls manually.

**Dependency:** Requires TS-ADV-01 (cagg must exist).

---

#### TS-ADV-04 — `show_chunks`

**Underlying SQL:**
```sql
SELECT show_chunks(
    relation => %s::REGCLASS,
    older_than => %s,   -- optional
    newer_than => %s    -- optional
)::TEXT AS chunk_name
```

Returns set of REGCLASS (chunk names). Cast to TEXT for Python consumption.

`older_than` / `newer_than` accept: INTERVAL string (computed relative to `now()`), or an
explicit TIMESTAMP/TIMESTAMPTZ string, or NULL to omit the filter. psycopg 3 passes these as
typed parameters.

**Parameters:**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `table` | `str` | Yes | — | Hypertable (or cagg) name |
| `older_than` | `str \| None` | No | `None` | Omit = no upper bound filter |
| `newer_than` | `str \| None` | No | `None` | Omit = no lower bound filter |
| `schema` | `str` | No | `"public"` | Accessor convention |

**Proposed Python signature:**
```python
def show_chunks(
    self,
    table: str,
    older_than: "str | None" = None,
    newer_than: "str | None" = None,
    schema: str = "public",
) -> list[str]:
```

**Return shape:** `list[str]` — chunk names in `_timescaledb_internal._hyper_X_Y_chunk` format.
Simple flat list; no need for DataFrame overhead for administrative chunk inspection.

**Classification:** TABLE STAKES — chunk inspection is a baseline operational capability for
any hypertable. Users need it to understand their data distribution and plan retention.

---

#### TS-ADV-05 — `drop_chunks`

**Underlying SQL:**
```sql
SELECT drop_chunks(
    relation => %s::REGCLASS,
    older_than => %s,   -- optional
    newer_than => %s    -- optional
)::TEXT AS chunk_name
```

Same parameter semantics as `show_chunks`. Returns the names of dropped chunks.

**Parameters:**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `table` | `str` | Yes | — | Hypertable or cagg |
| `older_than` | `str \| None` | No | `None` | Omit = no filter |
| `newer_than` | `str \| None` | No | `None` | Omit = no filter |
| `schema` | `str` | No | `"public"` | Accessor convention |

**Proposed Python signature:**
```python
def drop_chunks(
    self,
    table: str,
    older_than: "str | None" = None,
    newer_than: "str | None" = None,
    schema: str = "public",
) -> list[str]:
```

**Return shape:** `list[str]` — names of dropped chunks (empty list if nothing matched).
Returning dropped names lets callers audit what was removed.

**Guard:** Warn if both `older_than` and `newer_than` are None — this drops ALL chunks, which
is almost certainly a mistake. Raise `ValueError` with a clear message requiring at least one
bound. This is the one place where defensive behavior differs from `show_chunks` (inspecting all
chunks is safe; dropping all chunks is destructive).

**Classification:** TABLE STAKES — paired with `show_chunks`; chunk management (especially
manual retention outside policy) is a standard TimescaleDB operational workflow.

**Dependency:** `show_chunks` (TS-ADV-04) and `drop_chunks` (TS-ADV-05) are independent SQL
calls but logically paired — users call `show_chunks` first to preview, then `drop_chunks`.

---

### Differentiators (Valuable but Not Universally Assumed)

---

#### TS-ADV-06 — `time_bucket` query helper

**What it is:** A pure SQL builder that generates a `SELECT time_bucket(...) AS bucket, ...`
query against a hypertable and returns a DataFrame. This is NOT a `db.execute()` escape hatch —
it is a structured query helper in the spatial-helper pattern.

**Underlying SQL generated:**
```sql
SELECT
    time_bucket(%s::INTERVAL, {time_column}) AS bucket,
    {agg_expressions}
FROM {schema}.{table}
{where_clause}
GROUP BY 1
ORDER BY 1
```

All identifiers (`table`, `schema`, `time_column`) go through `validate_identifiers`.
`bucket_width` is a `%s` param. `agg_expressions` are user-provided SQL fragments — like
`select_sql` in `create_continuous_aggregate`, these cannot be parameterized.

**Parameters:**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `table` | `str` | Yes | — | Source hypertable |
| `time_column` | `str` | Yes | — | Timestamp column |
| `bucket_width` | `str` | Yes | — | e.g. `'1 hour'` |
| `aggregates` | `str \| list[str]` | Yes | — | e.g. `["AVG(value)", "COUNT(*)"]` |
| `where` | `str \| None` | No | `None` | Optional WHERE fragment (user-supplied) |
| `schema` | `str` | No | `"public"` | Accessor convention |
| `into` | `str` | No | `"df"` | `"df"` → DataFrame, `"rows"` → list[dict] |

**Proposed Python signature:**
```python
def time_bucket(
    self,
    table: str,
    time_column: str,
    bucket_width: str,
    aggregates: "str | list[str]",
    where: "str | None" = None,
    schema: str = "public",
    into: str = "df",
) -> "DataFrame | list[dict]":
```

**Return shape:** `DataFrame` by default (mirrors `spatial.*` helpers with `into` param);
`list[dict]` when `into="rows"`.

**Classification:** DIFFERENTIATOR — users can always write raw SQL; but having `db.timescale.time_bucket()`
removes boilerplate for the most common time-series query pattern. It is the single most-used
TimescaleDB function in practice. Not strictly required (raw SQL works) but significantly
improves the API's time-series DX.

**Risk flag:** The `aggregates` and `where` parameters accept raw SQL fragments. This is the
same design as `create_continuous_aggregate(select_sql=...)` — necessary because aggregation
expressions are structural SQL, not values. Document clearly that these must not come from
untrusted input.

---

#### TS-ADV-07 — `time_bucket_gapfill` query helper

**What it is:** Same pattern as `time_bucket` but generates `time_bucket_gapfill(...)` and
supports `locf()` / `interpolate()` companion functions in the aggregate expressions.

**Underlying SQL generated:**
```sql
SELECT
    time_bucket_gapfill(%s::INTERVAL, {time_column}, %s, %s) AS bucket,
    {agg_expressions}
FROM {schema}.{table}
{where_clause}
GROUP BY 1
ORDER BY 1
```

`start` and `finish` are required for gapfill (TimescaleDB requires an upper bound to know
how many gap-buckets to generate). They are passed as `%s` params.

The `agg_expressions` list naturally contains `locf(AVG(value))` or `interpolate(SUM(qty))`
as plain SQL strings — the wrapper does not need to know about locf/interpolate specifically.

**Parameters:**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `table` | `str` | Yes | — | Source hypertable |
| `time_column` | `str` | Yes | — | Timestamp column |
| `bucket_width` | `str` | Yes | — | e.g. `'1 hour'` |
| `start` | `str \| datetime` | Yes | — | Start of gapfill range (required by TimescaleDB) |
| `finish` | `str \| datetime` | Yes | — | End of gapfill range (required by TimescaleDB) |
| `aggregates` | `str \| list[str]` | Yes | — | Can contain `locf(...)` / `interpolate(...)` |
| `where` | `str \| None` | No | `None` | Optional WHERE fragment |
| `schema` | `str` | No | `"public"` | Accessor convention |
| `into` | `str` | No | `"df"` | `"df"` → DataFrame, `"rows"` → list[dict] |

**Proposed Python signature:**
```python
def time_bucket_gapfill(
    self,
    table: str,
    time_column: str,
    bucket_width: str,
    start: "str | datetime",
    finish: "str | datetime",
    aggregates: "str | list[str]",
    where: "str | None" = None,
    schema: str = "public",
    into: str = "df",
) -> "DataFrame | list[dict]":
```

**Return shape:** `DataFrame` by default; `list[dict]` when `into="rows"`.

**Classification:** DIFFERENTIATOR — more specialized than `time_bucket`; used when gap rows
(NULL-filled or interpolated) matter. `locf` and `interpolate` are passed inside the
`aggregates` strings — the wrapper does not need dedicated params for them. Users who need
gapfill almost always need the companion functions too, but exposing them as SQL fragments in
`aggregates` keeps the API clean.

**Dependency:** Logically extends TS-ADV-06. Same safety notes on `aggregates` and `where`.

---

#### TS-ADV-08 — `add_dimension`

**Underlying SQL (TimescaleDB 2.x form):**
```sql
-- Hash partitioning (by device, tenant, etc.):
SELECT add_dimension(
    '{schema}.{table}',
    by_hash('{partition_column}', %s)   -- number_partitions as %s
    [, if_not_exists => TRUE]
)

-- Range partitioning (additional time/integer dimension):
SELECT add_dimension(
    '{schema}.{table}',
    by_range('{partition_column}', %s)  -- chunk_time_interval as %s
    [, if_not_exists => TRUE]
)
```

In TimescaleDB 2.x, `by_range()` and `by_hash()` are the current API (replacing the older
positional `number_partitions` / `chunk_time_interval` arguments). The wrapper should use
the 2.x form.

`by_hash` is the common case (space partition by device/tenant to enable parallelism).
`by_range` adds a second time/integer range dimension (less common).

**Design decision — use `partition_type` discriminator:**

Two partition types with mutually exclusive params map cleanly to a type discriminator:
- `partition_type="hash"` requires `number_partitions: int`
- `partition_type="range"` requires `chunk_interval: str`

**Parameters:**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `table` | `str` | Yes | — | Hypertable |
| `column` | `str` | Yes | — | Partitioning column |
| `partition_type` | `str` | No | `"hash"` | Hash is the dominant use case; range is rare |
| `number_partitions` | `int \| None` | No | `None` | Required when `partition_type="hash"` |
| `chunk_interval` | `str \| None` | No | `None` | Required when `partition_type="range"` |
| `schema` | `str` | No | `"public"` | Accessor convention |
| `if_not_exists` | `bool` | No | `True` | Idempotent |

**Proposed Python signature:**
```python
def add_dimension(
    self,
    table: str,
    column: str,
    partition_type: str = "hash",
    number_partitions: "int | None" = None,
    chunk_interval: "str | None" = None,
    schema: str = "public",
    if_not_exists: bool = True,
) -> None:
```

Construction-time validation: if `partition_type="hash"` and `number_partitions` is None →
`ValueError`; if `partition_type="range"` and `chunk_interval` is None → `ValueError`.
Both param on the same call → `ValueError` (mutually exclusive).

**Return shape:** `None` (DDL)

**Classification:** DIFFERENTIATOR — multi-dimensional partitioning is important for
IoT/multi-tenant workloads but is not used in single-stream setups. More advanced than the
table-stakes features above. Users who need it will look for it; users who don't won't be
confused by its absence.

---

#### TS-ADV-09 — `add_reorder_policy`

**Underlying SQL:**
```sql
SELECT add_reorder_policy(
    hypertable => '{schema}.{table}',
    index_name => '{index_name}',
    if_not_exists => TRUE|FALSE
    [, initial_start => %s::TIMESTAMPTZ]
    [, timezone => %s]
)
```

Returns a `job_id` INTEGER (discarded by wrapper, consistent with other policy methods).
The policy reorders all chunks except the two most recent (still receiving writes) and runs
every 24 hours by default.

**Parameters:**

| Param | Type | Required | Default | Justification |
|-------|------|----------|---------|---------------|
| `table` | `str` | Yes | — | Hypertable |
| `index_name` | `str` | Yes | — | Existing index on the hypertable |
| `schema` | `str` | No | `"public"` | Accessor convention |
| `if_not_exists` | `bool` | No | `True` | Idempotent, consistent with other policies |

`table` and `index_name` both go through `validate_identifiers`.

**Proposed Python signature:**
```python
def add_reorder_policy(
    self,
    table: str,
    index_name: str,
    schema: str = "public",
    if_not_exists: bool = True,
) -> None:
```

**Return shape:** `None` (policy management)

**Classification:** DIFFERENTIATOR — reorder policy is a background optimization, not a
data-access feature. Teams with small datasets or SSDs often skip it entirely. Useful for
high-query workloads on HDDs. Worth including for completeness but not a blocker.

---

### Anti-Features (Explicitly Out of Scope)

| Anti-Feature | Why Requested | Why Out of Scope | Alternative |
|--------------|---------------|-----------------|-------------|
| **`remove_continuous_aggregate_policy` / `drop_continuous_aggregate`** | Lifecycle completeness | DROP MATERIALIZED VIEW is a single raw SQL call; a wrapper adds noise. Create/refresh/policy is the usage cycle. | `db.execute("DROP MATERIALIZED VIEW ...")` |
| **`remove_reorder_policy(table)`** | Symmetry with `add_reorder_policy` | Rarely needed; the job_id returned by `add_reorder_policy` is required to call `delete_job(job_id)` which is lower-level than the accessor abstraction. | `db.execute("SELECT delete_job(...)")` |
| **`time_bucket` with `origin` / `offset` params** | Advanced bucketing alignment | The basic form covers 95% of use cases. `origin`/`offset` are edge-case alignment controls; users who need them can write raw SQL. Adding them bloats the signature. | Pass a custom SELECT via raw `db.execute()` |
| **`locf()` / `interpolate()` as first-class Python methods** | Makes gapfill feel more Pythonic | `locf` and `interpolate` are SQL functions used inside GROUP BY aggregates — they cannot be called outside a `time_bucket_gapfill` context. Wrapping them separately would be misleading. | Include them as SQL strings in the `aggregates` list passed to `time_bucket_gapfill()` |
| **cagg waterfall chaining** (cagg on cagg) | Hierarchical aggregation | Supported in TSDB 2.x but requires the user to manage view dependencies; the `select_sql` approach handles it (user writes `FROM schema.lower_cagg`) | Pass the cagg view as the `from` source in `select_sql` |
| **`show_chunks` with `created_before` / `created_after`** | Filtering by physical creation time vs data time | Rarely used (operational metadata filter, not data filter); the data-time filters (`older_than` / `newer_than`) cover all typical use cases | `db.execute("SELECT show_chunks(..., created_before => ...)")` |
| **`compress_chunk` / `decompress_chunk` manual calls** | Fine-grained compression control | Out of scope; compression is managed via `enable_compression` + `add_compression_policy` (existing v0.6.0 surface). Manual per-chunk calls are an advanced operational workflow. | `db.execute("SELECT compress_chunk(...)") ` |

---

## Feature Dependencies

```
TS-ADV-01  create_continuous_aggregate
    └──enables──> TS-ADV-02  refresh_continuous_aggregate
    └──enables──> TS-ADV-03  add_continuous_aggregate_policy
    └──SELECT body must use──> time_bucket() [SQL inline, not TS-ADV-06]

TS-ADV-02  refresh_continuous_aggregate
    └──requires (logically)──> TS-ADV-01 (a cagg must exist)
    └──independent code, no import dependency

TS-ADV-03  add_continuous_aggregate_policy
    └──requires (logically)──> TS-ADV-01 (a cagg must exist)
    └──independent code, no import dependency

TS-ADV-04  show_chunks
    └──logically paired with──> TS-ADV-05 drop_chunks
    └──independent code, no dependency

TS-ADV-05  drop_chunks
    └──requires (logically)──> hypertable exists (created via create_hypertable — existing)

TS-ADV-06  time_bucket helper
    └──logically related to──> TS-ADV-07 time_bucket_gapfill
    └──independent code, no dependency

TS-ADV-07  time_bucket_gapfill helper
    └──conceptually extends──> TS-ADV-06 (same builder pattern)
    └──independent code, no dependency

TS-ADV-08  add_dimension
    └──requires (logically)──> hypertable exists (create_hypertable — existing)
    └──independent code, no dependency

TS-ADV-09  add_reorder_policy
    └──requires (logically)──> hypertable exists + index exists
    └──independent code, no dependency
```

### Dependency Notes

- **Continuous aggregate trio (TS-ADV-01/02/03):** The three methods form a complete lifecycle.
  They must ship together (locked in PROJECT.md). Code-wise each is independent SQL; logically
  TS-ADV-02 and TS-ADV-03 are useless without TS-ADV-01. Phase them together.
- **`time_bucket` select_sql and cagg select_sql share a constraint:** Both require the caller
  to write raw SQL fragments that cannot be parameterized. This is architectural — document it
  consistently in both docstrings.
- **`drop_chunks` guard:** Requiring at least one of `older_than` / `newer_than` prevents
  accidental full table wipe. This is the only place in the new methods that raises on a
  specific None combination.

---

## MVP Definition (v0.8.0 TimescaleDB Advanced Set)

### Must Ship (Table Stakes — block the milestone if absent)

- [ ] TS-ADV-01 — `create_continuous_aggregate` — cagg creation with select_sql body
- [ ] TS-ADV-02 — `refresh_continuous_aggregate` — manual window refresh
- [ ] TS-ADV-03 — `add_continuous_aggregate_policy` — auto-refresh policy
- [ ] TS-ADV-04 — `show_chunks` — chunk inspection with older_than / newer_than
- [ ] TS-ADV-05 — `drop_chunks` — chunk removal with safety guard

### Should Ship (Differentiators — high value, reasonable scope)

- [ ] TS-ADV-06 — `time_bucket` query helper → DataFrame
- [ ] TS-ADV-07 — `time_bucket_gapfill` query helper → DataFrame (with locf/interpolate via aggregates strings)
- [ ] TS-ADV-08 — `add_dimension` — multi-dimensional partitioning
- [ ] TS-ADV-09 — `add_reorder_policy` — chunk reorder background job

### Explicitly Deferred

- cagg remove/drop methods — low value, trivial raw SQL
- `time_bucket` with origin/offset — edge case, raw SQL works
- locf/interpolate as first-class methods — misleading API
- `compress_chunk` / `decompress_chunk` — advanced operational, out of scope

---

## Proposed Method Signatures (Full Reference)

All methods below belong on both `TimescaleAccessor` and `AsyncTimescaleAccessor`
(async version uses `await` and `async def`).

### Continuous Aggregates (must group together in implementation)

```python
# TS-ADV-01
def create_continuous_aggregate(
    self,
    view_name: str,
    select_sql: str,
    schema: str = "public",
    materialized_only: bool = True,
    with_no_data: bool = False,
) -> None: ...

# TS-ADV-02
def refresh_continuous_aggregate(
    self,
    view_name: str,
    window_start: "datetime | str | None" = None,
    window_end: "datetime | str | None" = None,
    schema: str = "public",
) -> None: ...

# TS-ADV-03
def add_continuous_aggregate_policy(
    self,
    view_name: str,
    start_offset: str,
    end_offset: str,
    schedule_interval: str = "1 hour",
    schema: str = "public",
    if_not_exists: bool = True,
) -> None: ...
```

### Chunk Management

```python
# TS-ADV-04
def show_chunks(
    self,
    table: str,
    older_than: "str | None" = None,
    newer_than: "str | None" = None,
    schema: str = "public",
) -> list[str]: ...

# TS-ADV-05
def drop_chunks(
    self,
    table: str,
    older_than: "str | None" = None,
    newer_than: "str | None" = None,
    schema: str = "public",
) -> list[str]: ...
```

### Query Helpers (return DataFrame by default)

```python
# TS-ADV-06
def time_bucket(
    self,
    table: str,
    time_column: str,
    bucket_width: str,
    aggregates: "str | list[str]",
    where: "str | None" = None,
    schema: str = "public",
    into: str = "df",
) -> "DataFrame | list[dict]": ...

# TS-ADV-07
def time_bucket_gapfill(
    self,
    table: str,
    time_column: str,
    bucket_width: str,
    start: "str | datetime",
    finish: "str | datetime",
    aggregates: "str | list[str]",
    where: "str | None" = None,
    schema: str = "public",
    into: str = "df",
) -> "DataFrame | list[dict]": ...
```

### Partitioning and Policies

```python
# TS-ADV-08
def add_dimension(
    self,
    table: str,
    column: str,
    partition_type: str = "hash",
    number_partitions: "int | None" = None,
    chunk_interval: "str | None" = None,
    schema: str = "public",
    if_not_exists: bool = True,
) -> None: ...

# TS-ADV-09
def add_reorder_policy(
    self,
    table: str,
    index_name: str,
    schema: str = "public",
    if_not_exists: bool = True,
) -> None: ...
```

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Classification |
|---------|------------|---------------------|----------|----------------|
| TS-ADV-01 create_continuous_aggregate | HIGH | MEDIUM | P1 | Table stakes |
| TS-ADV-02 refresh_continuous_aggregate | HIGH | LOW | P1 | Table stakes |
| TS-ADV-03 add_continuous_aggregate_policy | HIGH | LOW | P1 | Table stakes |
| TS-ADV-04 show_chunks | HIGH | LOW | P1 | Table stakes |
| TS-ADV-05 drop_chunks | HIGH | LOW | P1 | Table stakes |
| TS-ADV-06 time_bucket helper | HIGH | MEDIUM | P1 | Differentiator |
| TS-ADV-07 time_bucket_gapfill helper | MEDIUM | MEDIUM | P2 | Differentiator |
| TS-ADV-08 add_dimension | MEDIUM | LOW | P2 | Differentiator |
| TS-ADV-09 add_reorder_policy | LOW | LOW | P2 | Differentiator |

**Priority key:**
- P1: Must have for milestone to be coherent
- P2: Strong value-add, ship in same milestone given low additional cost

---

## Implementation Risk Flags

### Risk 1: `CALL` vs `SELECT` for `refresh_continuous_aggregate`

TimescaleDB 2.x uses `CALL refresh_continuous_aggregate(...)` (a stored procedure, not a
function). The existing accessor methods use `SELECT add_*_policy(...)`. psycopg 3 supports
`CALL` via `cursor.execute("CALL ...")` — but if the codebase uses a wrapper that intercepts
`execute()` and doesn't handle `CALL` results cleanly, this may need investigation during
implementation.

**Mitigation:** The existing `db.execute()` passes through to `cursor.execute()` which handles
`CALL` correctly in psycopg 3. Low actual risk; flag for the executor to verify.

### Risk 2: `select_sql` security surface in `create_continuous_aggregate`

`create_continuous_aggregate` takes a raw SQL string as `select_sql`. This cannot be
parameterized. Unlike existing methods that validate identifiers and use `%s` for values, the
cagg SELECT body is structural SQL. The library cannot sanitize it without parsing SQL.

**Mitigation:** Document clearly in the docstring that `select_sql` must not be constructed
from untrusted user input. Consistent with how `db.execute(sql)` accepts raw SQL — pycopg is
not a query builder, it is a wrapper. Same note applies to `aggregates` / `where` in
`time_bucket` / `time_bucket_gapfill`.

### Risk 3: `time_bucket_gapfill` requires `start` and `finish`

TimescaleDB requires an upper bound for `time_bucket_gapfill` to generate gap rows. Without
`finish`, the function does not know how many buckets to generate and will error at the DB
level. The wrapper must enforce that both `start` and `finish` are provided — they are
required parameters in the proposed signature, not optional.

**Mitigation:** Make `start` and `finish` required positional params (no default). DB-level
error message for missing bounds is opaque; surface a Python-level `ValueError` if either
is None when both are provided.

### Risk 4: `add_dimension` by_range vs by_hash SQL form

TimescaleDB 2.x changed `add_dimension` to use `by_range(col, interval)` and
`by_hash(col, n_partitions)` syntax instead of positional arguments. The older form
`add_dimension(table, column, number_partitions => N)` may still work on some 2.x versions
but is deprecated. The wrapper should use the 2.x named forms.

**Mitigation:** Always generate `by_hash('{column}', %s)` or `by_range('{column}', %s)` SQL.
Verify against the local test TimescaleDB version during implementation.

---

## Sources

- [TimescaleDB CREATE MATERIALIZED VIEW (continuous aggregate)](https://www.tigerdata.com/docs/api/latest/continuous-aggregates/create_materialized_view)
- [TimescaleDB add_continuous_aggregate_policy](https://www.tigerdata.com/docs/api/latest/continuous-aggregates/add_continuous_aggregate_policy)
- [TimescaleDB refresh_continuous_aggregate](https://www.tigerdata.com/docs/api/latest/continuous-aggregates/refresh_continuous_aggregate)
- [TimescaleDB time_bucket](https://www.tigerdata.com/docs/api/latest/hyperfunctions/time_bucket)
- [TimescaleDB time_bucket_gapfill](https://www.tigerdata.com/docs/api/latest/hyperfunctions/gapfilling/time_bucket_gapfill)
- [TimescaleDB show_chunks](https://www.tigerdata.com/docs/api/latest/hypertable/show_chunks)
- [TimescaleDB drop_chunks](https://www.tigerdata.com/docs/api/latest/hypertable/drop_chunks)
- [TimescaleDB add_dimension](https://www.tigerdata.com/docs/api/latest/hypertable/add_dimension)
- [TimescaleDB add_reorder_policy](https://www.tigerdata.com/docs/api/latest/hypertable/add_reorder_policy)
- WebSearch: "TimescaleDB 2.x add_reorder_policy parameters index_name hypertable"
- pycopg codebase: `pycopg/timescale.py` (existing accessor — style reference)
- pycopg project context: `.planning/PROJECT.md`

---

*Feature landscape for: pycopg v0.8.0 TimescaleDB Advanced API*
*Researched: 2026-06-22*
*Confidence: HIGH — all 9 features verified against official TimescaleDB 2.x API docs
(via tigerdata.com, the post-acquisition canonical source for timescale docs);
signatures cross-checked against WebSearch; codebase patterns confirmed from timescale.py*
