# Architecture Research

**Domain:** Watermark-based incremental ETL integrated into existing pycopg v0.5.0 ETL runner
**Researched:** 2026-06-19
**Confidence:** HIGH — based on direct source-code reading of `pycopg/etl.py`, `pycopg/queries.py`, and `.planning/PROJECT.md`

---

## System Overview

The existing architecture is frozen and must be integrated WITH, not redesigned. The incremental feature slots into three seams already present in the v0.5.0 design:

1. `pipeline_runs.watermark JSONB` — reserved column, always NULL today, designed for this exact purpose.
2. `ETL_UPDATE_RUN` — the existing autocommit UPDATE path; watermark persists via this same path on success only.
3. `ETL_GET_LAST_RUN` — the existing last-run query; watermark is read from the most-recent **successful** row using a filtered variant.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                          Public API (UNCHANGED)                           │
│   db.etl.run(pipeline)   async_db.etl.run(pipeline)                     │
│   Pipeline(incremental_column="ts")   ← new optional field              │
├──────────────────────────────────────────────────────────────────────────┤
│                     pycopg/etl.py  (MODIFIED)                            │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────┐   │
│  │  Pipeline (frozen dataclass) │  │  ETLAccessor / AsyncETLAccessor │   │
│  │  + incremental_column: str  │  │  run():                          │   │
│  │  + __post_init__:           │  │   NEW: _read_watermark()         │   │
│  │    replace+incremental=err  │  │   MODIFIED: extract with WHERE   │   │
│  │                             │  │   NEW: _compute_new_watermark()  │   │
│  │  NEW pure builders:         │  │   MODIFIED: _end_run watermark   │   │
│  │  build_incremental_where()  │  └─────────────────────────────────┘   │
│  │  build_wrapped_source_sql() │                                         │
│  └─────────────────────────────┘                                         │
├──────────────────────────────────────────────────────────────────────────┤
│                  pycopg/queries.py  (MODIFIED)                           │
│   ETL_GET_LAST_SUCCESS_WATERMARK  ← NEW constant                        │
│   ETL_UPDATE_RUN_WITH_WATERMARK   ← NEW constant (or extended UPDATE)   │
├──────────────────────────────────────────────────────────────────────────┤
│              pycopg/database.py / async_database.py (UNCHANGED)          │
├──────────────────────────────────────────────────────────────────────────┤
│                    Existing infrastructure (UNCHANGED)                    │
│  Database / AsyncDatabase   pipeline_runs table (watermark col exists)  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Integration Point Map

The five questions from the research prompt, answered against exact file/function locations:

### Q1: WHERE to read the prior watermark

**Read from:** `pipeline_runs.watermark` of the most recent **successful** row for `pipeline.name`.

**Why last successful:** A failed run does not advance the watermark (invariant). Reading from the last row regardless of status would skip rows if the previous run failed mid-load. Only `status = 'success'` rows carry a valid watermark.

**New SQL constant in `pycopg/queries.py`:**

```sql
ETL_GET_LAST_SUCCESS_WATERMARK = """
    SELECT watermark
    FROM pipeline_runs
    WHERE pipeline_name = %s
      AND status = 'success'
      AND watermark IS NOT NULL
    ORDER BY started_at DESC
    LIMIT 1
"""
```

**Which connection:** The autocommit run-log reader connection — identical to `_fetch_run_result`, `last_run`, and `history`. This is a plain `SELECT`; it must NOT run on the load-transaction connection (which could be inside a `db.session()` and subject to snapshot isolation). Open a dedicated `db.connect(autocommit=True)` for this read, just as every other run-log access does.

**New private helper in `ETLAccessor` and `AsyncETLAccessor`:**

```python
def _read_watermark(self, name: str) -> object | None:
    """Return the last successful watermark for pipeline *name*, or None."""
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_GET_LAST_SUCCESS_WATERMARK, [name])
            row = cur.fetchone()
    return row["watermark"] if row is not None else None
```

`None` return means: first run (no prior success) — perform full load and record `max(col)` as the first watermark.

### Q2: WHERE the new max(col) is computed and the consistency hazard

**Compute from:** the extracted DataFrame, using `df[pipeline.incremental_column].max()`.

**Why DataFrame-side, not a separate MAX query:** The extract already returns the rows that will be loaded. Computing `max(col)` from the extracted batch is strictly consistent — the watermark reflects exactly what was loaded. A separate `SELECT MAX(col)` query would read a snapshot that may include rows arriving after the extract (race window), advancing the watermark past rows not yet loaded.

**The consistency hazard:** rows arriving between the extract snapshot and the load are NOT in the extracted DataFrame. If the watermark were set to "current DB max" rather than "batch max", those rows would be skipped on the next run. Using `df[col].max()` avoids this: the next run will pick them up because `WHERE col > last_watermark` is `> batch_max`, which is strictly less than the current DB max at next-run time.

**For first run (watermark is None):** no WHERE clause is applied; full extract proceeds. The watermark written is `df[col].max()` from that full-load batch.

**For empty batches:** if the extracted DataFrame is empty (no new rows since last run), `df[col].max()` returns `NaN`/`NaT`/`None`. The watermark must NOT advance in this case — keep the existing watermark. The `_end_run` call records `status='success'` with watermark unchanged (i.e., do not overwrite the existing column — use the same new-watermark-only path).

**New private helper in `ETLAccessor` (pure, no I/O):**

```python
def _compute_new_watermark(
    self, df: pd.DataFrame, incremental_column: str
) -> object | None:
    """Return max(incremental_column) from df, or None if df is empty."""
    if df.empty:
        return None
    val = df[incremental_column].max()
    # pandas max() returns NaN/NaT on all-null columns; treat as None
    if pd.isna(val):
        return None
    # Convert pandas Timestamp → Python datetime (psycopg serializes natively)
    if hasattr(val, 'to_pydatetime'):
        return val.to_pydatetime()
    return val
```

### Q3: WHEN/HOW the new watermark is persisted — the invariant

**Core invariant:** The watermark only advances on a successful run. On failure, the existing watermark in `pipeline_runs` is not modified.

**Implementation:** The existing `_end_run()` call on the success path is extended to also write the watermark. The failure-path `_end_run()` call (inside `except`) does NOT pass a watermark — it writes `NULL` for the watermark column, leaving prior successful rows' watermarks intact.

Two options for SQL:

**Option A (preferred): new constant `ETL_UPDATE_RUN_WITH_WATERMARK` for success path**

Keep `ETL_UPDATE_RUN` exactly as-is for the failure path (no watermark written into any row). Add a new constant that includes the watermark for the success path:

```sql
ETL_UPDATE_RUN_WITH_WATERMARK = """
    UPDATE pipeline_runs
    SET status = %s,
        finished_at = %s,
        rows_extracted = %s,
        rows_loaded = %s,
        error_message = %s,
        error_traceback = %s,
        watermark = %s
    WHERE run_id = %s
"""
```

`_end_run()` signature becomes:

```python
def _end_run(
    self,
    run_id: int,
    status: str,
    rows_extracted: int,
    rows_loaded: int,
    error_message: str | None = None,
    error_traceback: str | None = None,
    watermark: object | None = None,   # NEW optional field
) -> None:
```

When `watermark is not None`, use `ETL_UPDATE_RUN_WITH_WATERMARK` and pass `json.dumps({"value": watermark_serialized})` as the JSONB parameter. When `watermark is None`, use the existing `ETL_UPDATE_RUN` — the `watermark` column for this row stays `NULL`.

**Why not a single `_end_run` with conditional SQL:** two constants with explicit dispatch is cleaner than building the SQL string conditionally. It also keeps `ETL_UPDATE_RUN` unchanged and the failure path unmodified, reducing the diff on a security-sensitive path.

**Watermark JSONB format:** store as `{"value": <scalar>}`. This reserves namespace for future multi-column watermarks without breaking the existing `watermark IS NOT NULL` filter. The read helper unwraps `row["watermark"]["value"]`.

**What happens on a failed load:** the `except` block calls `self._end_run(run_id, "failed", ...)` without the watermark argument. The `pipeline_runs` row for this failed run gets `watermark = NULL`. The next run reads `ETL_GET_LAST_SUCCESS_WATERMARK` which filters `status = 'success'` — it skips the failed row entirely and returns the same prior watermark. The re-run starts from the same point.

### Q4: New pure builders needed

Two new pure builders (no I/O, no `self`) in `pycopg/etl.py`, placed alongside the existing builders:

**Builder 1: `build_incremental_where_clause(incremental_column)`**

Validates the identifier, returns the raw WHERE fragment for embedding:

```python
def build_incremental_where_clause(incremental_column: str) -> str:
    """Return a WHERE fragment for incremental filtering.

    Parameters
    ----------
    incremental_column : str
        Column name to filter on. Must be a valid SQL identifier.

    Returns
    -------
    str
        ``'WHERE <col> > %s'`` with the validated column name interpolated.

    Raises
    ------
    InvalidIdentifier
        If ``incremental_column`` is not a valid SQL identifier.
    """
    validate_identifiers(incremental_column)
    return f"WHERE {incremental_column} > %s"
```

**Builder 2: `build_wrapped_source_sql(source_sql, incremental_column)`**

Wraps a SQL-string source with the incremental WHERE, following the locked scope decision ("sources SQL enveloppées en `SELECT * FROM (<sql>) sub WHERE col > %s`"):

```python
def build_wrapped_source_sql(
    source_sql: str,
    incremental_column: str,
) -> str:
    """Wrap a SQL source with an incremental WHERE clause.

    Parameters
    ----------
    source_sql : str
        The original source SQL (SELECT/WITH statement).
    incremental_column : str
        Column name for the watermark filter. Must be a valid SQL identifier.

    Returns
    -------
    str
        Wrapped SQL of the form
        ``'SELECT * FROM (<source_sql>) AS _etl_inc_sub WHERE <col> > %s'``.

    Raises
    ------
    InvalidIdentifier
        If ``incremental_column`` is not a valid SQL identifier.
    """
    validate_identifiers(incremental_column)
    return (
        f"SELECT * FROM ({source_sql}) AS _etl_inc_sub"
        f" WHERE {incremental_column} > %s"
    )
```

**Builder 3 (for table sources): `build_incremental_table_sql(table, schema, incremental_column)`**

For table-name sources (not SQL strings), the existing extract path builds `SELECT * FROM schema.table`. The incremental variant appends the WHERE:

```python
def build_incremental_table_sql(
    table: str,
    schema: str,
    incremental_column: str,
) -> str:
    """Build a SELECT with incremental WHERE for a table-name source.

    Parameters
    ----------
    table : str
        Source table name. Must be a valid SQL identifier.
    schema : str
        Schema name. Must be a valid SQL identifier.
    incremental_column : str
        Column name for the watermark filter. Must be a valid SQL identifier.

    Returns
    -------
    str
        SQL of the form
        ``'SELECT * FROM schema.table WHERE col > %s'``.

    Raises
    ------
    InvalidIdentifier
        If any identifier is not valid.
    """
    validate_identifiers(table, schema, incremental_column)
    return f"SELECT * FROM {schema}.{table} WHERE {incremental_column} > %s"
```

**How they slot beside existing builders:** placed after `build_truncate_sql` and before `_build_insert_sql` in `etl.py`. They are module-level functions, no class dependency. No changes to `_build_insert_sql` or `_build_upsert_sql`.

### Q5: Concurrency — two runs of the same pipeline

For v0.7.0: **last-writer-wins is acceptable; no locking needed.**

Rationale:

- `pipeline_runs` is append-only; two concurrent runs each get their own `run_id`.
- Both runs read the same prior watermark (the same last-success row).
- Both extract overlapping windows (both satisfy `col > prior_watermark`).
- With `load_mode="append"`: duplicate rows are inserted. This is a caller concern — `append` never claims idempotency.
- With `load_mode="upsert"`: duplicate upserts are idempotent by design (ON CONFLICT DO UPDATE sets the same values). The second run overwrites the first run's identical rows — correct.
- The watermark written by whichever run finishes last reflects the later batch's max. Since both batches overlap from the same prior watermark, the later finish is a superset — the watermark is still correct or slightly further ahead (also correct).
- Advisory locks (`pg_try_advisory_lock`) would prevent true duplication for `append` mode but add complexity. Defer to v0.8.0 if needed; document the limitation.

**Document explicitly** in the `Pipeline` docstring: concurrent runs of the same pipeline are safe only with `load_mode="upsert"`. For `append` + incremental, the caller is responsible for ensuring non-overlapping runs.

---

## Modified Data Flow: `ETLAccessor.run()` with `incremental_column`

The changes to `run()` are additive — two new steps are injected into the existing 6-step flow:

```text
db.etl.run(pipeline)   where pipeline.incremental_column is set
    |
    +-- self.init()                              [UNCHANGED — autocommit conn]
    +-- run_id = self._start_run(name)           [UNCHANGED — autocommit conn]
    |
    +-- NEW STEP 0: _read_watermark(name)        [autocommit conn]
    |       SELECT watermark FROM pipeline_runs
    |       WHERE pipeline_name=%s AND status='success' AND watermark IS NOT NULL
    |       ORDER BY started_at DESC LIMIT 1
    |       → prior_watermark (Python scalar or None)
    |
    +-- STEP 1: EXTRACT  (MODIFIED)
    |       if incremental_column and prior_watermark is not None:
    |           if SQL source: wrap with build_wrapped_source_sql() + pass [prior_watermark] as param
    |           if table source: use build_incremental_table_sql() + pass [prior_watermark] as param
    |       else (first run or non-incremental):
    |           existing extract logic unchanged
    |
    +-- STEP 2: TRANSFORM CHAIN                  [UNCHANGED]
    |
    +-- STEP 3: NaN/NaT → None                  [UNCHANGED]
    |
    +-- NEW STEP 3b: _compute_new_watermark(df, incremental_column)
    |       → new_watermark (Python scalar or None if empty batch)
    |
    +-- STEP 4: EXISTENCE CHECK                  [UNCHANGED]
    |
    +-- STEP 5: BUILD LOAD SQL                   [UNCHANGED]
    |
    +-- STEP 6: ATOMIC LOAD                      [UNCHANGED]
    |       with self._db.session():
    |           with self._db.transaction() as conn:
    |               cur.execute(insert_sql, insert_params)
    |               rows_loaded += cur.rowcount
    |
    +-- SUCCESS PATH:
    |       if new_watermark is not None:
    |           self._end_run(run_id, "success", ..., watermark=new_watermark)
    |           → uses ETL_UPDATE_RUN_WITH_WATERMARK, passes json-serialized watermark
    |       else:  (empty batch — watermark unchanged)
    |           self._end_run(run_id, "success", ...)
    |           → uses existing ETL_UPDATE_RUN, watermark column stays NULL for this row
    |
    +-- EXCEPT PATH (UNCHANGED in effect):
            self._end_run(run_id, "failed", ...) — no watermark arg
            → uses existing ETL_UPDATE_RUN, watermark stays NULL for this row
```

**Key invariant:** `new_watermark` is computed from the extracted DataFrame BEFORE the load step. The load step is atomic. The watermark UPDATE happens AFTER the load commits. If the load transaction raises, execution jumps to the `except` block, which calls `_end_run` WITHOUT the watermark. The watermark therefore only advances when the load successfully commits.

There is a narrow failure window: the load commits but `_end_run` raises before the watermark UPDATE. In this case the run row stays `status='running'` (its final UPDATE was lost), and the next run reads the prior success watermark (re-processes the same window). With `upsert`, this is idempotent. With `append`, rows are duplicated. This window exists in the current non-incremental design too (failed `_end_run` leaves a `running` row) — it is a known accepted limitation, not a regression.

---

## `Pipeline` Dataclass Changes

### New field

```python
@dataclass(frozen=True)
class Pipeline:
    # ... existing fields unchanged ...
    incremental_column: str | None = None   # NEW — default None = non-incremental
```

### `__post_init__` additions

```python
# In Pipeline.__post_init__, after existing validations:

# Incremental + replace is forbidden (locked scope decision)
if self.incremental_column is not None and self.load_mode == "replace":
    raise ValueError(
        "incremental_column is not compatible with load_mode='replace'; "
        "use 'append' or 'upsert' (locked scope ETL-INC-01)"
    )

# Validate incremental_column as a SQL identifier at construction time
if self.incremental_column is not None:
    validate_identifiers(self.incremental_column)
```

Construction-time validation keeps the "frozen + validated at birth" contract consistent with every other field.

---

## `RunResult` — No Changes Required

`RunResult` does not expose the watermark field to callers. The watermark is an internal run-log implementation detail readable via `history()` if the caller directly inspects `pipeline_runs`. Adding `watermark` to `RunResult` is deferred — it would require either a new field (source compatibility break on positional construction) or a `@dataclass` kwarg-only pattern. Not needed for v0.7.0.

---

## `queries.py` Changes

### New constants to add (in the `# ETL QUERIES` section)

```python
ETL_GET_LAST_SUCCESS_WATERMARK = """
    SELECT watermark
    FROM pipeline_runs
    WHERE pipeline_name = %s
      AND status = 'success'
      AND watermark IS NOT NULL
    ORDER BY started_at DESC
    LIMIT 1
"""

ETL_UPDATE_RUN_WITH_WATERMARK = """
    UPDATE pipeline_runs
    SET status = %s,
        finished_at = %s,
        rows_extracted = %s,
        rows_loaded = %s,
        error_message = %s,
        error_traceback = %s,
        watermark = %s
    WHERE run_id = %s
"""
```

### Existing constants UNCHANGED

- `ETL_INIT_PIPELINE_RUNS` — no DDL change needed; `watermark JSONB` column already exists.
- `ETL_INSERT_RUN` — unchanged; new runs insert with `watermark` defaulting to `NULL`.
- `ETL_UPDATE_RUN` — unchanged; used for the failure path and empty-batch success path.
- `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`, `ETL_GET_RUN` — unchanged; they return `watermark` as part of `SELECT *`, already available.

---

## Sync/Async Parity Path

Every new private method and every SQL constant is used identically in both `ETLAccessor` and `AsyncETLAccessor`. The pattern is byte-for-byte the same as the v0.5.0 run-log helpers:

| Method | Sync | Async |
| --- | --- | --- |
| `_read_watermark(name)` | `with self._db.connect(autocommit=True)` | `async with self._db.connect(autocommit=True)` |
| `_compute_new_watermark(df, col)` | shared pure function (no `self`) | same pure function |
| `build_wrapped_source_sql(...)` | pure function, no class | same pure function |
| `build_incremental_table_sql(...)` | pure function, no class | same pure function |
| `build_incremental_where_clause(...)` | pure function, no class | same pure function |
| `_end_run(..., watermark=...)` | `with self._db.connect(autocommit=True)` | `async with self._db.connect(autocommit=True)` |

`TestEtlParity` covers `ETLAccessor` vs `AsyncETLAccessor` method surface. The new `_read_watermark` and modified `_end_run` are private — no parity-test changes needed for them. The `incremental_column` field on `Pipeline` is tested via `test_pipeline_incremental_validation.py` (new, no DB required).

---

## Recommended Project Structure — Files Touched

### Modified files (incremental feature only)

**`pycopg/etl.py`** — main changes:

- `Pipeline`: add `incremental_column: str | None = None` field; `__post_init__` guard for `replace` + incremental.
- New pure builders: `build_wrapped_source_sql`, `build_incremental_table_sql`, `build_incremental_where_clause`, `_compute_new_watermark`.
- `ETLAccessor` and `AsyncETLAccessor`: add `_read_watermark` method; modify `run()` to call it, apply watermark filter in extract, compute new watermark after extract; modify `_end_run` signature to add `watermark=None` kwarg and dispatch to `ETL_UPDATE_RUN_WITH_WATERMARK` when non-None.

**`pycopg/queries.py`** — add two SQL constants to the `# ETL QUERIES` section:

- `ETL_GET_LAST_SUCCESS_WATERMARK`
- `ETL_UPDATE_RUN_WITH_WATERMARK`

### New test files

| File | Purpose |
| --- | --- |
| `tests/test_etl_incremental.py` | Pure-builder unit tests (no DB) and integration tests for first-run, incremental, empty-batch, failure no-advance, replace+incremental guard |
| `tests/test_etl_incremental_async.py` | Async mirror of the integration tests |

### Untouched files

| File | Why |
| --- | --- |
| `pycopg/database.py` | No new properties, no new lazy fields |
| `pycopg/async_database.py` | No new properties, no new lazy fields |
| `pycopg/__init__.py` | No new exports needed; `Pipeline` already exported; new builders are internal |
| `pycopg/queries.py` DDL | `ETL_INIT_PIPELINE_RUNS` stays identical; `watermark` column already present |
| `tests/test_parity.py` | No new public accessor methods; `_read_watermark` is private |
| `pycopg/exceptions.py` | No new exception types; existing `ETLTransformError`/`ETLTargetNotFoundError` cover failure modes |

---

## Watermark Serialization

Watermarks are stored as JSONB in the format `{"value": <scalar>}`. This wrapper:

- Reserves namespace for future multi-column watermarks (`{"ts": ..., "id": ...}`) without a schema migration.
- Avoids ambiguity when the scalar is `0`, `""`, or `false` (all falsy in Python but valid watermarks).
- Makes `watermark IS NOT NULL` the only filter needed — an empty dict `{}` is also non-null, but the `"value"` key check guards against malformed rows.

**Python → JSONB serialization:** psycopg 3 serializes `dict` to JSONB natively when the column type is `JSONB`. Pass `{"value": watermark_value}` directly. For `datetime` values (the most common watermark type), convert pandas `Timestamp` to Python `datetime` first via `.to_pydatetime()` — psycopg 3 serializes `datetime` inside a dict as an ISO 8601 string; this round-trips correctly on read.

**JSONB → Python deserialization:** psycopg 3 deserializes JSONB into Python `dict`. The `_read_watermark` helper returns `row["watermark"]["value"]` — a plain Python scalar (str, int, float, or datetime-string). The caller (in `run()`) passes this directly as `%s` to the incremental SQL; psycopg handles type matching with the DB column.

**For datetime columns (most common):** the watermark round-trips as an ISO 8601 string. When passed back as a `%s` parameter in `WHERE ts > %s`, psycopg coerces the string to a `timestamptz` for comparison. If strict typing is needed, cast explicitly in the WHERE: `WHERE ts > %s::timestamptz`. The builders should not add this cast by default — keep them type-agnostic. Document the cast option in the numpydoc.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Watermark from `MAX(col)` DB Query Instead of Batch Max

**What:** Run `SELECT MAX(incremental_column) FROM source` after extract to get the "true" current max.

**Why wrong:** Rows arriving between the extract snapshot and this MAX query produce a watermark that is ahead of what was loaded. Next run skips those rows permanently.

**Do instead:** `df[incremental_column].max()` — the batch max is the correct, consistent watermark.

### Anti-Pattern 2: Writing Watermark on the Load Transaction Connection

**What:** Update `pipeline_runs.watermark` inside the `db.session()` / `db.transaction()` block alongside the load.

**Why wrong:** If the load transaction rolls back, the watermark UPDATE rolls back too — no problem. But then the separate `_end_run` (on the autocommit connection) writes `status='failed'` without a watermark, which is correct. The real risk is complexity: the load transaction is intentionally isolated from run-log writes (ETL-08/09 invariant). Mixing them breaks the dual-connection architecture.

**Do instead:** Write the watermark in `_end_run` via the autocommit connection, after the load transaction has committed — the existing success path.

### Anti-Pattern 3: Watermark Advances on Empty Batch

**What:** When `df.empty`, still write `new_watermark = datetime.now()` to avoid re-scanning old data.

**Why wrong:** The watermark must reflect `max(incremental_column)` of rows actually processed — not wall-clock time. An empty batch means no new rows were found; the prior watermark is still valid.

**Do instead:** When the batch is empty, call `_end_run(run_id, "success", 0, 0)` without a watermark argument. The watermark column for this row stays `NULL`. The next run reads the last non-null success watermark and gets the same value — correct re-scan boundary.

### Anti-Pattern 4: `replace` + `incremental_column`

**What:** Allow `Pipeline(incremental_column="ts", load_mode="replace")`.

**Why wrong:** `replace` truncates the target before loading. If the load only inserts the incremental window (new rows since last watermark), the TRUNCATE destroys all prior loaded data. Semantically incoherent.

**Do instead:** Raise `ValueError` at `Pipeline.__post_init__` time (construction-time guard, consistent with existing validations). The locked scope decision (ETL-INC-01) mandates `load_mode ∈ {append, upsert}` for incremental.

### Anti-Pattern 5: Mutating `ETL_UPDATE_RUN` to Always Include Watermark

**What:** Add `watermark = %s` to the existing `ETL_UPDATE_RUN` constant and always pass `None` or the watermark.

**Why wrong:** Passing `None` for `watermark` would overwrite a previously-set watermark on a re-used run_id — impossible with BIGSERIAL, but fragile. More importantly, NULL-overwriting makes it impossible to distinguish "run with no incremental" from "incremental run with empty batch". Using two distinct SQL constants (`ETL_UPDATE_RUN` and `ETL_UPDATE_RUN_WITH_WATERMARK`) keeps the failure path completely unchanged and the intent explicit.

---

## Suggested Build Order (Phase 25+)

Dependencies drive this order. The ALIAS-RM-01 work (removing 56 deprecated aliases) is independent of ETL-INC-01 and can run in parallel or sequentially; it is pure deletion work with no dependency on the incremental feature.

#### Phase 25 — Alias removal (ALIAS-RM-01)

Files: `pycopg/database.py`, `pycopg/async_database.py`, alias test files, MIGRATION v0.6→v0.7, CHANGELOG `[0.7.0]` Breaking section. Deliverable: hard-remove 56 deprecated stubs; update parity tests. Tests: alias tests now assert `AttributeError`; parity tests updated.

#### Phase 26 — Incremental ETL: pure layer

Files: `pycopg/etl.py` (`Pipeline.incremental_column` + `__post_init__`), new pure builders (`build_wrapped_source_sql`, `build_incremental_table_sql`, `build_incremental_where_clause`, `_compute_new_watermark`). Deliverable: construction-time validation; pure builders with identifier guards. Tests: unit tests, no DB — `replace`+`incremental_column` raises; identifier validation; SQL shape assertions.

#### Phase 27 — Incremental ETL: run-log integration

Files: `pycopg/queries.py` (2 new constants), `ETLAccessor._read_watermark` + modified `_end_run`, `AsyncETLAccessor._read_watermark` + modified `_end_run`. Deliverable: watermark read/write on dedicated autocommit connections. Tests: integration — first-run writes watermark, failure does NOT advance watermark, empty batch does NOT advance watermark.

#### Phase 28 — Incremental ETL: extract integration + async parity

Files: `ETLAccessor.run()` + `AsyncETLAccessor.run()` modified extract step; `TestEtlParity` confirms `run` signature unchanged. Deliverable: end-to-end incremental — first full load, second load fetches only new rows, correct watermark stored. Tests: integration + async parity — `rows_extracted` reflects only new rows on second run; watermark matches `df[col].max()`.

#### Phase 29 — Release v0.7.0

Files: CHANGELOG `[0.7.0]` finalized, MIGRATION v0.6→v0.7 with full alias table, version bump, Sphinx docs updated, PyPI publish. Gates: coverage ratchet ≥94, `interrogate ≥ 95`, Sphinx `-W` clean.

#### Phase ordering rationale

- Phase 25 (alias removal) first: it is the mechanical debt work with zero ETL coupling. Getting it out of the way keeps the git diff for Phases 26–28 clean and isolated to incremental ETL. It also immediately resolves WR-01 (IDE signature degradation) after one phase.
- Phase 26 before 27: pure builder layer must exist before the accessor can call them. Unit-testable without DB, so the test suite runs fast and gives confidence before touching live connections.
- Phase 27 before 28: run-log integration (`_read_watermark`, modified `_end_run`) must be proven correct in isolation (the invariant tests) before wiring into the full `run()` body. Otherwise a subtle bug in watermark-advance logic is buried inside a complex end-to-end flow.
- Phase 28 last for incremental: the extract modification is the riskiest change (SQL injection surface — subquery wrapping). It builds on proven builders (Phase 26) and proven run-log integration (Phase 27). Async parity is enforced within this phase, not as a separate phase.
- Phase 29 (release) is gated on all integration tests passing, coverage ratchet, and `interrogate`.

---

## Sources

- Direct source reading: `pycopg/etl.py` (full file, 1477 lines) — `ETLAccessor.run()`, `AsyncETLAccessor.run()`, `_start_run`, `_end_run`, `_fetch_run_result`, `Pipeline.__post_init__`, all existing builders
- Direct source reading: `pycopg/queries.py` — `ETL_INIT_PIPELINE_RUNS` (watermark column confirmed present), `ETL_UPDATE_RUN` (parameter order), `ETL_GET_LAST_RUN` (no status filter — gap identified), `ETL_INSERT_RUN`
- Direct source reading: `.planning/PROJECT.md` — v0.7.0 locked scope decisions (ETL-INC-01, ALIAS-RM-01), dual-connection atomicity seam documented in History section, `watermark JSONB` reservation rationale, phase numbering continues from Phase 25
- Direct source reading: `.planning/research/ARCHITECTURE.md` v0.5.0 — prior architecture decisions, dual-connection invariant explanation, `_row_to_result` drops `watermark` (confirmed — watermark not in RunResult)

---

*Architecture research for: pycopg v0.7.0 incremental ETL (watermark/CDC) integration*
*Researched: 2026-06-19*
