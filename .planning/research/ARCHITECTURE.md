# Architecture Patterns: v0.8.0 TimescaleDB Advanced Features

**Domain:** TimescaleDB 2.x advanced features integrated into an existing pure-builder + lazy-accessor + sync/async-parity architecture
**Researched:** 2026-06-22
**Confidence:** HIGH — based on direct source-code reading of all required files + live TimescaleDB 2.x API documentation

---

## System Overview

The existing architecture is frozen and must be integrated WITH, not redesigned. Five integration seams are relevant for v0.8.0:

1. **`pycopg/timescale.py`** — the `TimescaleAccessor` / `AsyncTimescaleAccessor` pair that holds all new methods. Today it has 6 methods (hypertable, compression, retention). New methods are ADDED here only.
2. **`pycopg/queries.py`** — `*_SQL` constants for parameterized queries. Management commands that return results go here; DDL-shaped commands too complex for a constant live inline in `timescale.py`.
3. **`tests/test_parity.py` `ACCESSOR_PAIRS`** — already includes `(TimescaleAccessor, AsyncTimescaleAccessor)`. No registry change is needed; all new methods are automatically verified by the existing data-driven `test_accessor_parity` test as long as they appear on both sync and async classes.
4. **`self._db.connect(autocommit=True)`** — the ETL precedent for statements that cannot run inside a transaction block. This seam MUST be used for `create_continuous_aggregate` and `refresh_continuous_aggregate` (and optionally `add_continuous_aggregate_policy`).
5. **`into=` parameter pattern from `spatial.py`** — the standard for query helpers that return rows or DataFrames.

```text
┌──────────────────────────────────────────────────────────────────────┐
│                    Public API (accessor surface)                       │
│  db.timescale.*          async_db.timescale.*                         │
│                                                                        │
│  EXISTING (unchanged):                                                 │
│    create_hypertable     enable_compression    add_compression_policy │
│    add_retention_policy  list_hypertables      hypertable_info         │
│                                                                        │
│  NEW (v0.8.0):                                                         │
│    show_chunks           drop_chunks           add_dimension           │
│    add_reorder_policy                                                  │
│    create_continuous_aggregate ─── requires autocommit seam           │
│    refresh_continuous_aggregate ── requires autocommit seam           │
│    add_continuous_aggregate_policy                                     │
│    time_bucket           time_bucket_gapfill   (query helpers)        │
├──────────────────────────────────────────────────────────────────────┤
│                  pycopg/timescale.py  (MODIFIED)                       │
│  TimescaleAccessor / AsyncTimescaleAccessor                            │
│                                                                        │
│  Extension guard pattern (sync):                                       │
│    if not self._db.schema.has_extension("timescaledb"): raise         │
│  Extension guard pattern (async):                                      │
│    if not await self._db.schema.has_extension("timescaledb"): raise  │
│                                                                        │
│  Autocommit seam (new, mirrors ETL):                                   │
│    with self._db.connect(autocommit=True) as conn: ...                │
│  Async autocommit seam:                                                │
│    async with self._db.connect(autocommit=True) as conn: ...          │
├──────────────────────────────────────────────────────────────────────┤
│                  pycopg/queries.py  (MODIFIED)                         │
│  New constants added to TIMESCALEDB QUERIES section:                   │
│    TSDB_SHOW_CHUNKS  TSDB_DROP_CHUNKS                                  │
│    TSDB_LIST_CONTINUOUS_AGGREGATES                                     │
├──────────────────────────────────────────────────────────────────────┤
│    pycopg/database.py / async_database.py / base.py  (UNCHANGED)      │
│    tests/test_parity.py  ACCESSOR_PAIRS  (UNCHANGED)                  │
│    pycopg/spatial.py / etl.py / admin.py / schema.py  (UNCHANGED)    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Feature Classification by Integration Pattern

### Pattern 1 — Pure-builder-shaped: validate + `%s` + return None or rows

These are standard TimescaleDB management commands that take identifier arguments and return nothing (or return a set of rows from a TimescaleDB system function). They follow the exact same pattern as the existing 6 methods on `TimescaleAccessor`:

1. `_check_timescaledb()` guard first
2. `validate_identifiers(...)` for table/schema/column names
3. `validate_interval(...)` for interval strings
4. `self._db.execute(sql, params)` where all user values travel as `%s`

**Methods in this pattern:**

| Method | Purpose | Returns |
| --- | --- | --- |
| `show_chunks(table, schema, older_than, newer_than)` | List chunks for a hypertable | `list[str]` — chunk names |
| `drop_chunks(table, schema, older_than, newer_than)` | Drop matching chunks | `list[str]` — names of dropped chunks |
| `add_dimension(table, column, schema, number_partitions, chunk_time_interval)` | Add hash or interval partitioning dimension | `None` |
| `add_reorder_policy(table, index_name, schema, if_not_exists)` | Add chunk reorder policy | `None` |
| `add_continuous_aggregate_policy(view_name, start_offset, end_offset, schedule_interval, if_not_exists)` | Add auto-refresh policy for a cagg | `None` |

For `show_chunks` and `drop_chunks`, the `older_than` / `newer_than` parameters are interval strings (validated with `validate_interval`) or `None`. These map to `CALL show_chunks(relation, older_than => INTERVAL %s, ...)` — user values always travel as `%s`.

**Critical note on `add_dimension`:** The TimescaleDB API requires the hypertable to be empty at the time `add_dimension` is called. This is not enforced by pycopg (caller's responsibility); document it in the docstring as a `Raises` entry pointing to the TimescaleDB requirement.

**Critical note on `add_reorder_policy` parameter `index_name`:** This is NOT a schema-qualified identifier — it is the index name as a plain TEXT argument in the TimescaleDB function, but it must still be validated with `validate_identifier` before interpolation into the SQL string, because TimescaleDB's `add_reorder_policy` takes it as a TEXT literal that is internally cast.

### Pattern 2 — Autocommit-seam: cannot run inside a transaction block

These two methods issue TimescaleDB operations that run across multiple internal transactions or manipulate the materialization threshold. They CANNOT run inside a PostgreSQL transaction block — attempting to do so raises a TimescaleDB error.

**Methods requiring the autocommit seam:**

| Method | Why |
| --- | --- |
| `create_continuous_aggregate(view_name, query, schema, with_no_data)` | `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` requires autocommit unless `WITH NO DATA` is specified |
| `refresh_continuous_aggregate(view_name, window_start, window_end)` | `CALL refresh_continuous_aggregate(...)` cannot run inside a transaction block (confirmed by TimescaleDB issue #2876) |

**The transaction-block restriction confirmed:**

- `refresh_continuous_aggregate()` uses two internal transactions: one to update the invalidation threshold, one to materialize. It is not possible to run this inside a caller-supplied transaction block.
- `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` can be run inside a transaction block ONLY when `WITH NO DATA` is specified. The default (with data) materializes immediately and has the same dual-transaction requirement.

**Design decision for `create_continuous_aggregate`:** Always use the autocommit seam, even when `with_no_data=True`. This is simpler and safer than conditional connection routing: the method always opens a fresh autocommit connection, regardless of `with_no_data`. The `with_no_data` parameter defaults to `False` (materialize on creation) to match the TimescaleDB 2.x default behavior.

**Implementation — sync:**

```python
def create_continuous_aggregate(
    self,
    view_name: str,
    query: str,
    schema: str = "public",
    with_no_data: bool = False,
) -> None:
    if not self._db.schema.has_extension("timescaledb"):
        raise ExtensionNotAvailable(...)
    validate_identifiers(view_name, schema)
    # 'query' is a raw SQL fragment supplied by caller — not identifier-validated.
    # Security boundary: same as the spatial 'where=' raw fragment.
    no_data_clause = " WITH NO DATA" if with_no_data else ""
    sql = (
        f"CREATE MATERIALIZED VIEW {schema}.{view_name}"
        f" WITH (timescaledb.continuous) AS {query}{no_data_clause}"
    )
    # Must run outside any transaction block — use dedicated autocommit connection.
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)

async def create_continuous_aggregate(self, ...) -> None:
    if not await self._db.schema.has_extension("timescaledb"):
        raise ExtensionNotAvailable(...)
    validate_identifiers(view_name, schema)
    no_data_clause = " WITH NO DATA" if with_no_data else ""
    sql = (
        f"CREATE MATERIALIZED VIEW {schema}.{view_name}"
        f" WITH (timescaledb.continuous) AS {query}{no_data_clause}"
    )
    async with self._db.connect(autocommit=True) as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql)
```

**Implementation — `refresh_continuous_aggregate`:**

```python
def refresh_continuous_aggregate(
    self,
    view_name: str,
    window_start,          # interval string, timestamp, or None
    window_end,            # interval string, timestamp, or None
    schema: str = "public",
) -> None:
    if not self._db.schema.has_extension("timescaledb"):
        raise ExtensionNotAvailable(...)
    validate_identifiers(view_name, schema)
    # window_start / window_end are user values — always %s params.
    sql = "CALL refresh_continuous_aggregate(%s, %s, %s)"
    params = [f"{schema}.{view_name}", window_start, window_end]
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
```

The async version is identical with `async with` / `await`.

**Critical async gotcha (from Phase 23 MEMORY):** The async extension guard MUST `await` the check:

```python
if not await self._db.schema.has_extension("timescaledb"):
```

Forgetting the `await` causes the guard to always evaluate to `False` (a coroutine object is truthy), silently bypassing the guard. This was a known gotcha when spatial/schema were relocated in v0.6.0.

### Pattern 3 — Query helpers with `into=` return: DataFrame/rows

`time_bucket` and `time_bucket_gapfill` are SQL expression helpers — they produce aggregated time-series rows from a user-specified table. They are NOT management commands; they return data. The spatial accessor's `into="rows"/"df"` pattern is the correct precedent.

**Why they belong in `TimescaleAccessor` and not as raw SQL:** The user would need to know `time_bucket()` and `time_bucket_gapfill()` function signatures, interval formatting, and GROUP BY semantics. pycopg adds value by validating identifiers, building the parameterized query structure, and returning a DataFrame. However, the aggregate expression (e.g., `avg(temperature)`, `max(cpu)`) is user-supplied.

**The query-builder boundary:** pycopg is explicitly NOT a query builder (out of scope). The approach that stays within bounds: accept a user-supplied aggregate expression string as a raw fragment (same as spatial's `where=` parameter — raw fragment, caller's responsibility). The method validates identifiers for table/schema/time_column and bucket_interval, then constructs:

```sql
SELECT time_bucket(%s, {time_column}) AS bucket, {aggregate}
FROM {schema}.{table}
GROUP BY bucket
ORDER BY bucket
```

where `bucket_interval` travels as `%s`, identifiers are validated before interpolation, and `aggregate` is a raw SQL fragment from the caller (documented as "caller's responsibility" in the numpydoc).

**Signature design:**

```python
def time_bucket(
    self,
    table: str,
    time_column: str,
    bucket_interval: str,          # e.g. "1 hour", "15 minutes"
    aggregate: str,                # raw SQL fragment: "avg(temperature)"
    schema: str = "public",
    where: str | None = None,      # raw filter fragment, caller's responsibility
    order_by: str = "bucket",
    limit: int | None = None,
    into: str = "rows",            # "rows" → list[dict], "df" → pd.DataFrame
) -> list[dict] | pd.DataFrame:
```

`time_bucket_gapfill` adds `start` and `finish` parameters (the gap-fill range bounds) and requires TimescaleDB 2.x; these are passed as `%s` params.

```python
def time_bucket_gapfill(
    self,
    table: str,
    time_column: str,
    bucket_interval: str,
    aggregate: str,
    start,           # timestamp or None — %s param for the range start
    finish,          # timestamp or None — %s param for the range end
    schema: str = "public",
    where: str | None = None,
    order_by: str = "bucket",
    limit: int | None = None,
    into: str = "rows",
) -> list[dict] | pd.DataFrame:
```

**`into=` implementation for `time_bucket` / `time_bucket_gapfill`:** These methods return tabular data with no geometry column. Therefore `into="gdf"` is INVALID (no geometry to build a GeoDataFrame from). Only `into="rows"` (→ `list[dict]` via `self._db.execute`) and `into="df"` (→ `pd.DataFrame` via `self._db.to_dataframe`) are valid. Note that spatial uses `into="gdf"` but the timescale query helpers use `into="df"` (pandas DataFrame, not GeoDataFrame).

**New `into=` validator for timescale query helpers:**

```python
_VALID_TSDB_INTO = ("rows", "df")

def _check_tsdb_into(into: str) -> None:
    if into not in _VALID_TSDB_INTO:
        raise ValueError(f"into must be one of {_VALID_TSDB_INTO}, got {into!r}")
```

**`into="df"` path:** calls `self._db.to_dataframe(sql, params)`. This already exists on `Database` and `AsyncDatabase` (flat transactional core — unchanged). The async variant calls `await self._db.to_dataframe(sql, params)`.

---

## `show_chunks` / `drop_chunks` Return Type Decision

**`show_chunks` return type: `list[str]`**

The TimescaleDB `show_chunks()` function returns a set of REGCLASS values (chunk names). Wrap in a `SELECT show_chunks(...)::text` and fetch — each row yields the chunk name as a string. Return `list[str]` (not `list[dict]`) — chunk names are the only useful value and a flat list is more ergonomic.

**SQL constant for `show_chunks`:**

```sql
TSDB_SHOW_CHUNKS = """
    SELECT show_chunks(%s, older_than => %s, newer_than => %s)::text AS chunk_name
"""
```

Note: `older_than` and `newer_than` can be `None` — psycopg sends `None` as SQL `NULL`, which TimescaleDB interprets as "no filter" for these parameters. The REGCLASS is cast to text so it is a plain string in the result.

**`drop_chunks` return type: `list[str]`**

`drop_chunks()` returns the names of dropped chunks (one per row). Same pattern: `list[str]`.

```sql
TSDB_DROP_CHUNKS = """
    SELECT drop_chunks(%s, older_than => %s, newer_than => %s)::text AS chunk_name
"""
```

---

## Data Flow: New Methods

### show_chunks / drop_chunks

```text
db.timescale.show_chunks(table, schema, older_than, newer_than)
    |
    +-- _check_timescaledb guard (self._db.schema.has_extension)
    +-- validate_identifiers(table, schema)
    +-- validate_interval(older_than) if not None
    +-- validate_interval(newer_than) if not None
    |
    +-- sql, params = TSDB_SHOW_CHUNKS, [f"{schema}.{table}", older_than, newer_than]
    +-- rows = self._db.execute(sql, params)
    +-- return [row["chunk_name"] for row in rows]
```

### add_dimension

```text
db.timescale.add_dimension(table, column, schema, number_partitions, chunk_time_interval)
    |
    +-- _check_timescaledb guard
    +-- validate_identifiers(table, column, schema)
    +-- exactly one of number_partitions / chunk_time_interval must be non-None
    +-- validate_interval(chunk_time_interval) if set
    |
    +-- Build inline SQL (too parameterized for a single constant):
    |     if number_partitions:
    |       sql = "SELECT add_dimension(%s, by_hash(%s, %s))"
    |       params = [f"{schema}.{table}", column, number_partitions]
    |     elif chunk_time_interval:
    |       sql = "SELECT add_dimension(%s, by_range(%s, INTERVAL %s))"
    |       params = [f"{schema}.{table}", column, chunk_time_interval]
    +-- self._db.execute(sql, params)
```

Note: `add_dimension` in TimescaleDB 2.x uses the `by_hash()` / `by_range()` sub-function syntax, unlike the older flat-parameter API. The `column` argument is passed as `%s` to `by_hash`/`by_range` (not identifier-interpolated at the SQL level), because these are called as PostgreSQL functions that accept the column name as TEXT.

### create_continuous_aggregate / refresh_continuous_aggregate

See Pattern 2 above — both always use the dedicated autocommit connection seam.

### time_bucket / time_bucket_gapfill

```text
db.timescale.time_bucket(table, time_column, bucket_interval, aggregate, schema, ...)
    |
    +-- _check_timescaledb guard
    +-- _check_tsdb_into(into)
    +-- validate_identifiers(table, time_column, schema)
    +-- validate_interval(bucket_interval)
    |
    +-- Build SQL:
    |     cols_part = f"time_bucket(%s, {time_column}) AS bucket, {aggregate}"
    |     sql = f"SELECT {cols_part} FROM {schema}.{table}"
    |     params = [bucket_interval]
    |     if where: sql += f" WHERE {where}"
    |     sql += f" GROUP BY bucket ORDER BY {order_by}"
    |     if limit: sql += f" LIMIT {int(limit)}"
    |
    +-- if into == "rows": return self._db.execute(sql, params)
    +-- if into == "df":   return self._db.to_dataframe(sql, params)
```

---

## `queries.py` Changes

### New constants to add to the `# TIMESCALEDB QUERIES` section

```python
TSDB_SHOW_CHUNKS = """
    SELECT show_chunks(%s, older_than => %s, newer_than => %s)::text AS chunk_name
"""

TSDB_DROP_CHUNKS = """
    SELECT drop_chunks(%s, older_than => %s, newer_than => %s)::text AS chunk_name
"""

TSDB_LIST_CONTINUOUS_AGGREGATES = """
    SELECT
        view_schema AS schema,
        view_name,
        materialization_hypertable_schema,
        materialization_hypertable_name,
        compression_enabled
    FROM timescaledb_information.continuous_aggregates
    ORDER BY view_schema, view_name
"""
```

`TSDB_LIST_CONTINUOUS_AGGREGATES` is an optional convenience method (`list_continuous_aggregates`) that parallels `list_hypertables` — useful for inspecting what caggs exist. Not strictly required for the main feature set but rounds out the continuous aggregate lifecycle.

### Existing constants UNCHANGED

All 2 existing TimescaleDB constants (`LIST_HYPERTABLES`, `HYPERTABLE_INFO`) stay exactly as-is.

---

## `ACCESSOR_PAIRS` / Parity Test Wiring

**`tests/test_parity.py` — NO CHANGES REQUIRED.**

`ACCESSOR_PAIRS` already contains `(TimescaleAccessor, AsyncTimescaleAccessor)`. The `test_accessor_parity` test iterates all public methods on both classes and asserts they match. Adding new methods to BOTH `TimescaleAccessor` AND `AsyncTimescaleAccessor` is sufficient — the test catches any asymmetry automatically.

**The only parity enforcement needed:** every new method added to `TimescaleAccessor` must have an exact-name, exact-signature mirror on `AsyncTimescaleAccessor` with `async def` and `await` instead of `def` and synchronous calls. The test will fail if any method is missing on either side.

---

## Extension Guard: Sync vs Async Consistency

The existing sync methods use:

```python
if not self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailable(...)
```

The existing async methods correctly use:

```python
if not await self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailable(...)
```

All new methods MUST follow the same pattern. The async guard is the historically problematic one (Phase 23 gotcha documented in MEMORY): forgetting `await` makes the guard always False (a coroutine is truthy). Every new async method must be audited for this before shipping.

---

## Files Modified vs Unchanged

### Modified files

**`pycopg/timescale.py`** — the only file that receives implementation changes:

- `TimescaleAccessor`: add 8 new methods (`show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy`, `create_continuous_aggregate`, `refresh_continuous_aggregate`, `add_continuous_aggregate_policy`, `time_bucket`, `time_bucket_gapfill`)
- `AsyncTimescaleAccessor`: exact async mirror of every new method above
- New module-level helper function `_check_tsdb_into(into)` (analogous to `_check_into` in `spatial.py`)

**`pycopg/queries.py`** — add 3 new SQL constants to the `# TIMESCALEDB QUERIES` section:

- `TSDB_SHOW_CHUNKS`
- `TSDB_DROP_CHUNKS`
- `TSDB_LIST_CONTINUOUS_AGGREGATES` (if `list_continuous_aggregates` is in scope)

### Unchanged files

| File | Why unchanged |
| --- | --- |
| `pycopg/database.py` | No new lazy properties; `_timescale` cache already exists |
| `pycopg/async_database.py` | Same — `_timescale` cache already wired |
| `tests/test_parity.py` | `ACCESSOR_PAIRS` already includes the timescale pair |
| `pycopg/base.py` | No base changes needed |
| `pycopg/spatial.py` | Not touched; `into=` pattern is referenced, not modified |
| `pycopg/etl.py` | Not touched; autocommit seam is referenced, not modified |
| `pycopg/exceptions.py` | `ExtensionNotAvailable` already exported and correct |
| `pycopg/__init__.py` | `TimescaleAccessor` / `AsyncTimescaleAccessor` already exported |
| Any other accessor | `admin`, `maint`, `backup`, `schema`, `spatial` — all untouched |

---

## Suggested Build Order (Phase 30+)

Risk and dependency drive this order. The guiding principle: simplest pure-builder methods first to prove the pattern on the real DB, autocommit seam last because it is the riskiest.

### Phase 30 — Pure-builder methods: show_chunks, drop_chunks, add_dimension, add_reorder_policy

These are the simplest integration: validate identifiers, call `self._db.execute`, return the result. No new connection management, no transaction concern.

**Why first:** Zero new seams. If anything is wrong with the TimescaleDB 2.x API signatures (e.g., `add_dimension`'s `by_hash`/`by_range` sub-function syntax), it surfaces immediately and cheaply without contaminating the harder work.

**Deliverable:** 4 methods × 2 (sync/async) = 8 new methods. `queries.py` gets `TSDB_SHOW_CHUNKS` and `TSDB_DROP_CHUNKS`. Integration tests on live DB confirm correct chunk listing/dropping and dimension addition.

**Risk:** LOW. `add_dimension`'s empty-hypertable requirement is a runtime constraint — document in docstring, test with a fresh hypertable.

### Phase 31 — Continuous aggregates: create, refresh, add_policy

This is the riskiest phase because:

1. `create_continuous_aggregate` and `refresh_continuous_aggregate` require the autocommit seam.
2. The autocommit seam for TimescaleDB is NEW (the ETL precedent uses it, but this is the first timescale method that needs it).
3. The async-guard gotcha (forgetting `await`) is most dangerous here because a silently non-guarded `create_continuous_aggregate` call against a DB without TimescaleDB will fail with a confusing error.
4. `create_continuous_aggregate` accepts a raw SQL query fragment — the security boundary must be clearly documented.

**Why last:** The autocommit seam on `TimescaleAccessor` has no prior precedent (ETL uses it via `ETLAccessor` on a separate accessor with its own `_db.connect` call). Verifying it works correctly on both sync and async `TimescaleAccessor` is the critical proof.

**Deliverable:** 3 methods × 2 (sync/async) = 6 new methods. `queries.py` gets `TSDB_LIST_CONTINUOUS_AGGREGATES`. Integration tests: create a cagg, verify it exists in `timescaledb_information.continuous_aggregates`, refresh it, verify the materialized data, add a policy.

**Risk:** MEDIUM-HIGH. Autocommit seam correctness + async guard. The Phase 31 plan MUST include explicit verification that calling `create_continuous_aggregate` inside a `db.session()` context still works (the autocommit seam bypasses the session connection entirely).

### Phase 32 — Query helpers: time_bucket, time_bucket_gapfill

These return data, not management results. The `into=` pattern is established but the DataFrame path (`into="df"`) requires calling `self._db.to_dataframe` which uses SQLAlchemy under the hood.

**Why after continuous aggregates:** `time_bucket` is most useful when querying against a continuous aggregate. Testing `time_bucket` against a continuous aggregate created in Phase 31 gives more realistic integration coverage.

**Deliverable:** 2 methods × 2 (sync/async) = 4 new methods. The `_check_tsdb_into` helper. Integration tests: `time_bucket` returning `list[dict]` and `pd.DataFrame`, `time_bucket_gapfill` with start/finish bounds, both on real hypertable data.

**Risk:** LOW for `into="rows"`. MEDIUM for `into="df"` — `to_dataframe` uses SQLAlchemy `text()` which needs `%s` → `:p0` conversion (the `_to_named_binds` pattern from `spatial.py`). This must be handled or the `into="df"` path will fail.

### Phase 33 — Release v0.8.0

Version bump, CHANGELOG, docs, Sphinx, PyPI publish. Standard release phase matching Phase 29 / Phase 24 structure.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Running refresh_continuous_aggregate inside db.session()

**What:** `with db.session(): db.timescale.refresh_continuous_aggregate(...)` — if the accessor used `self._db.execute` (the session-aware path), it would run inside the active transaction.

**Why wrong:** `refresh_continuous_aggregate()` cannot run inside a transaction block. TimescaleDB raises an error: "operation not allowed within a transaction block".

**Prevention:** Always route these two methods through `self._db.connect(autocommit=True)`. Confirmed by TimescaleDB GitHub issue #2876. The dedicated autocommit connection bypasses any active `db.session()` entirely.

### Anti-Pattern 2: Forgetting `await` on the async TimescaleDB guard

**What:** `if not self._db.schema.has_extension("timescaledb"):` in an async method (missing `await`).

**Why wrong:** `has_extension` returns a coroutine in async context. A coroutine object is always truthy. The guard evaluates to `not True == False`, so the `raise ExtensionNotAvailable` is NEVER reached. The method proceeds silently without TimescaleDB installed.

**Prevention:** All new `AsyncTimescaleAccessor` methods must use `if not await self._db.schema.has_extension("timescaledb"):`. This was the exact gotcha in Phase 23.

### Anti-Pattern 3: Using a SQL constant for create_continuous_aggregate

**What:** Defining `TSDB_CREATE_CONTINUOUS_AGGREGATE = "CREATE MATERIALIZED VIEW ..."` as a `queries.py` constant.

**Why wrong:** The continuous aggregate view definition includes a user-supplied `query` string (the aggregate SELECT). A `queries.py` constant implies the SQL is a fixed parameterized template. But the query is structural SQL — it cannot be passed as a `%s` parameter (PostgreSQL does not allow DDL bodies as bind parameters). The full CREATE statement must be built as an f-string with validated identifiers and the raw query fragment appended.

**Prevention:** Build the `CREATE MATERIALIZED VIEW` SQL inline in `timescale.py`, not in `queries.py`. Document in the numpydoc that `query` is a raw SQL fragment — caller's responsibility. The security boundary follows the spatial `where=` precedent.

### Anti-Pattern 4: `into="gdf"` for time_bucket

**What:** Accepting `into="gdf"` on `time_bucket` or `time_bucket_gapfill`.

**Why wrong:** These methods return time-series aggregate rows — they have no geometry column. `to_geodataframe` would fail when trying to detect a geometry column.

**Prevention:** Use `_check_tsdb_into` which only accepts `"rows"` and `"df"`. Raise `ValueError` for anything else.

### Anti-Pattern 5: Touching the flat transactional core or other accessors

**What:** Adding any new property or method to `Database`, `AsyncDatabase`, `base.py`, or any other accessor (`SpatialAccessor`, `ETLAccessor`, etc.).

**Why wrong:** v0.8.0 scope is strictly additive to `TimescaleAccessor` / `AsyncTimescaleAccessor`. Cross-contamination creates merge conflicts and violates the single-concern phase principle.

**Prevention:** All new code lives in `pycopg/timescale.py` and `pycopg/queries.py` only.

---

## Scalability Considerations

| Concern | Implication |
| --- | --- |
| `show_chunks` on large hypertables | Returns potentially thousands of chunk names. The method does not add a LIMIT by default — consistent with `list_hypertables`. Document that callers should use `older_than`/`newer_than` to bound the result set for large tables. |
| `create_continuous_aggregate` on huge datasets | Without `WITH NO DATA`, the initial materialization can run for minutes. The `with_no_data=True` parameter exists specifically for this. Document prominently. |
| `refresh_continuous_aggregate` window size | Large windows (months of data) cause proportionally long refresh times. pycopg does not add timeout enforcement — callers use `db.config.statement_timeout` or PostgreSQL `statement_timeout` GUC. |
| `time_bucket` without LIMIT | Materializes all rows in memory. The `limit` parameter mitigates this for exploratory use. |

---

## Sources

- Direct source reading: `pycopg/timescale.py` — existing 6 methods, extension guard pattern (sync + async), `self._db.execute` call site, lazy property wiring via `_timescale` cache
- Direct source reading: `pycopg/spatial.py` — `_check_into`, `into=` routing, `_run()` method, `_to_named_binds` for DataFrame path, PostGIS guard at construction vs per-method
- Direct source reading: `pycopg/etl.py` — `ETLAccessor._start_run`, `_end_run`, `init` — all three use `with self._db.connect(autocommit=True) as conn:` as the autocommit seam precedent
- Direct source reading: `pycopg/queries.py` — existing `LIST_HYPERTABLES`, `HYPERTABLE_INFO` constants; confirmed `%s`-only parameter convention
- Direct source reading: `tests/test_parity.py` — `ACCESSOR_PAIRS` list, `test_accessor_parity` logic; confirmed no change needed for new timescale methods
- Direct source reading: `.planning/PROJECT.md` — v0.8.0 scope lock, zero new deps constraint, TimescaleDB 2.x target, Core Value (sync/async parity), coverage ratchet ≥94
- TimescaleDB 2.x official documentation: `refresh_continuous_aggregate` transaction block restriction confirmed (GitHub issue #2876 "Allow cagg refresh within transaction block" — restriction is intentional by design)
- TimescaleDB API documentation: `show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy`, `add_continuous_aggregate_policy` signatures verified against tigerdata.com/docs (official TimescaleDB docs redirect)
- Memory: Phase 23 async-guard gotcha (`await` omission on `has_extension` in AsyncSchemaAccessor / AsyncSpatialAccessor) — confirmed recurring risk for new async TimescaleDB methods

---

*Architecture research for: pycopg v0.8.0 TimescaleDB advanced features*
*Researched: 2026-06-22*
