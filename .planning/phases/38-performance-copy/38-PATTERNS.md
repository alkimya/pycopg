# Phase 38: Performance COPY - Pattern Map

**Mapped:** 2026-06-26
**Files analyzed:** 8 (3 source files × methods + 5 test files)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/database.py` — `_stream_df_copy` (new helper) | utility | streaming / file-I/O | `copy_insert` (same file, L1037–1043) | exact |
| `pycopg/database.py` — `from_dataframe` (modify) | service | CRUD + streaming | `copy_insert` (same file) + ETL `head(0).to_sql` (`etl.py` L1381) | exact |
| `pycopg/database.py` — `insert_batch` (micro-opt) | service | CRUD | `insert_batch` itself (L982–985) — hoist only | exact |
| `pycopg/async_database.py` — `_async_stream_df_copy` (new helper) | utility | streaming / file-I/O | `copy_insert` async (same file, L678–686) | exact |
| `pycopg/async_database.py` — `from_dataframe` (modify) | service | CRUD + streaming | `copy_insert` async (same file) | exact |
| `pycopg/async_database.py` — `insert_batch` (micro-opt) | service | CRUD | `insert_batch` async (same file, L622–626) | exact |
| `pycopg/etl.py` — sync load seam (modify steps 3–6) | service | streaming / CRUD | `copy_insert` (database.py L1037) + seam comment (etl.py L1410–1421) | role-match |
| `pycopg/etl.py` — async load seam (modify steps 3–6) | service | streaming / CRUD | `copy_insert` async (async_database.py L678) + async seam (etl.py L2083–2089) | role-match |
| `tests/test_database_integration.py` — `TestFromDataframeCopy` (new class) | test | request-response | `test_from_dataframe` (same file, L317–334) + `test_copy_insert` (L781–) | exact |
| `tests/test_async_database.py` — async from_dataframe COPY spy (new) | test | request-response | `test_from_dataframe_basic` (same file, L644–662) | exact |
| `tests/test_database.py` — `insert_batch` non-regression (extend) | test | CRUD | `test_insert_batch_and_select` (test_database_integration.py L82) | role-match |
| `tests/test_etl_accessor.py` — ETL COPY path (extend) | test | streaming | `test_run_writes_full_row` (same file, L231–257) | exact |
| `tests/test_parity.py` — parity green check | test | request-response | `test_from_dataframe_primary_key_parity` (same file, L476) | exact |

---

## Pattern Assignments

### `pycopg/database.py` — `_stream_df_copy` (new module-level helper, sync)

**Analog:** `copy_insert` in the same file (L1037–1043)

**Current `copy_insert` core pattern** (database.py L1037–1043):
```python
with self.connect() as conn:
    with conn.cursor() as cur:
        with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row([row.get(col) for col in columns])
    conn.commit()
    return len(rows)
```

**New helper — copy the `cur.copy` shape, add df.isna mask, drop connection management:**
```python
def _stream_df_copy(
    cur,           # psycopg.Cursor — provided by caller; no connection opened here
    df: pd.DataFrame,
    table: str,
    schema: str,
    columns: list[str],
) -> int:
    if df.empty:
        return 0
    cols_str = ", ".join(columns)
    null_mask = df.isna().values   # shape (n_rows, n_cols), pre-computed once
    row_values = df.values         # object array, preserves Timestamp / np.int64
    with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
        for i, row in enumerate(row_values):
            null_row = null_mask[i]
            copy.write_row(
                [None if null_row[j] else row[j] for j in range(len(row))]
            )
    return cur.rowcount
```

**Key constraints:**
- No `self.connect()`, no `conn.commit()` — caller owns the connection boundary.
- `validate_identifiers` already called by the caller before invoking this helper.
- `cur.rowcount` is read **after** the `with cur.copy(...)` block closes (RESEARCH Pitfall 4).

---

### `pycopg/database.py` — `from_dataframe` (modify, L1204–1244)

**Analog (DDL side):** `etl.py` L1379–1386 — `df.head(0).to_sql` for table creation before load.
**Analog (COPY side):** `copy_insert` (same file, L1037–1043) — `self.connect()` + `conn.cursor()` + `conn.commit()`.

**Current state** (database.py L1233–1244):
```python
validate_identifiers(table, schema)
df.to_sql(
    name=table,
    con=self.engine,
    schema=schema,
    if_exists=if_exists,
    index=index,
    dtype=dtype,
)
if primary_key and if_exists != "append":
    self.schema.add_primary_key(table, primary_key, schema)
```

**Target pattern (Hybrid DDL + COPY, D-01/D-03/D-04):**
```python
validate_identifiers(table, schema)

# Step 1 — DDL: create/replace empty typed schema (preserves dtype, if_exists, index)
df_ddl = df.reset_index() if index else df          # D-01a: include index cols for DDL+COPY
df_ddl.head(0).to_sql(
    name=table, con=self.engine, schema=schema,
    if_exists=if_exists, index=False, dtype=dtype,
)
# DDL commits on engine (D-04: two-phase accepted for replace)

# Step 2 — COPY data on a separate psycopg connection (D-03)
columns = list(df_ddl.columns)   # derived from df_ddl (not df) to match DDL columns
with self.connect() as conn:
    with conn.cursor() as cur:
        _stream_df_copy(cur, df_ddl, table, schema, columns)
    conn.commit()

# Step 3 — PK (unchanged)
if primary_key and if_exists != "append":
    self.schema.add_primary_key(table, primary_key, schema)
```

**Validation pattern** (copy from `copy_insert` L1028):
```python
validate_identifiers(table, schema)  # first, before any SQL interpolation
```

---

### `pycopg/database.py` — `insert_batch` micro-opt (L982–985, D-05)

**Current state** (database.py L982–985):
```python
for row in batch:
    row_placeholders = ", ".join(["%s"] * len(columns))  # invariant — recomputed each row
    placeholders.append(f"({row_placeholders})")
    params.extend(row.get(col) for col in columns)
```

**Target pattern (hoist before loop):**
```python
row_placeholders = ", ".join(["%s"] * len(columns))  # computed once per batch
for row in batch:
    placeholders.append(f"({row_placeholders})")
    params.extend(row.get(col) for col in columns)
```

Byte-exact: only the computation site moves, the produced SQL string is identical.

---

### `pycopg/async_database.py` — `_async_stream_df_copy` (new module-level helper, async)

**Analog:** `copy_insert` async (same file, L678–686)

**Current `copy_insert` async core pattern** (async_database.py L678–686):
```python
async with self.connect() as conn:
    async with conn.cursor() as cur:
        async with cur.copy(
            f"COPY {schema}.{table} ({cols_str}) FROM STDIN"
        ) as copy:
            for row in rows:
                await copy.write_row([row.get(col) for col in columns])
    await conn.commit()
    return len(rows)
```

**New async helper — mirror of sync, with `async with` + `await copy.write_row`:**
```python
async def _async_stream_df_copy(
    cur,           # psycopg.AsyncCursor — provided by caller
    df: pd.DataFrame,
    table: str,
    schema: str,
    columns: list[str],
) -> int:
    if df.empty:
        return 0
    cols_str = ", ".join(columns)
    null_mask = df.isna().values
    row_values = df.values
    async with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
        for i, row in enumerate(row_values):
            null_row = null_mask[i]
            await copy.write_row(
                [None if null_row[j] else row[j] for j in range(len(row))]
            )
    return cur.rowcount
```

**Key difference from sync:** `async with cur.copy(...)` + `await copy.write_row(...)`.
Do NOT use the sync helper in an async context (RESEARCH Pitfall 6).

---

### `pycopg/async_database.py` — `from_dataframe` (modify, L967–1010)

**Current state** (async_database.py L996–1010):
```python
validate_identifiers(table, schema)
async with self.async_engine.connect() as conn:
    await conn.run_sync(
        lambda sync_conn: df.to_sql(
            name=table,
            con=sync_conn,
            schema=schema,
            if_exists=if_exists,
            index=index,
            dtype=dtype,
        )
    )
if primary_key and if_exists != "append":
    await self.schema.add_primary_key(table, primary_key, schema)
```

**Target pattern (Hybrid DDL + async COPY):**
```python
validate_identifiers(table, schema)

# Step 1 — DDL via sync engine (run_sync pattern preserved from async_engine)
df_ddl = df.reset_index() if index else df
await self.async_engine.connect().__aenter__().run_sync(
    # mirror: use existing run_sync pattern for DDL head(0) only
    lambda sync_conn: df_ddl.head(0).to_sql(
        name=table, con=sync_conn, schema=schema,
        if_exists=if_exists, index=False, dtype=dtype,
    )
)
# (exact run_sync call shape already present at L997–1007)

# Step 2 — COPY data on async psycopg connection (D-03)
columns = list(df_ddl.columns)
async with self.connect() as conn:
    async with conn.cursor() as cur:
        await _async_stream_df_copy(cur, df_ddl, table, schema, columns)
    await conn.commit()

# Step 3 — PK (unchanged)
if primary_key and if_exists != "append":
    await self.schema.add_primary_key(table, primary_key, schema)
```

Note: the `async with self.async_engine.connect()` pattern for the DDL step is already established at L997 — reuse exactly that shape, just wrapping `df_ddl.head(0)` instead of full `df`.

---

### `pycopg/async_database.py` — `insert_batch` micro-opt (L622–626, D-05)

**Current state** (async_database.py L622–626):
```python
for row in batch:
    row_placeholders = ", ".join(["%s"] * len(columns))  # same invariant as sync
    placeholders.append(f"({row_placeholders})")
    params.extend(row.get(col) for col in columns)
```

**Target pattern** (hoist before loop — mirror of sync change):
```python
row_placeholders = ", ".join(["%s"] * len(columns))  # once per batch
for row in batch:
    placeholders.append(f"({row_placeholders})")
    params.extend(row.get(col) for col in columns)
```

---

### `pycopg/etl.py` — sync load seam (modify steps 3–6, L1350–1421)

**Analog (COPY pattern):** `copy_insert` (database.py L1037–1043) — but inlined on the seam cursor, not via method call (D-02a).
**Analog (seam shape):** existing seam at L1415–1421 (keep `session`/`transaction`/`cursor` nesting intact).

**Current step 3 — materialization** (etl.py L1350–1366, to be replaced for append/replace):
```python
# Step 3 — current (to replace for append/replace):
rows = (
    df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
)
if not rows:
    self._end_run(run_id, "success", rows_extracted, 0)
    return self._fetch_run_result(run_id)
columns = list(rows[0].keys())
```

**Target step 3** (D-02, D-02b):
```python
# Step 3 — COPY path (append/replace); upsert still needs rows list below
if df.empty:
    self._end_run(run_id, "success", rows_extracted, 0)
    return self._fetch_run_result(run_id)
columns = list(df.columns)
# For upsert only: materialize rows list (INSERT ON CONFLICT needs dict list)
if pipeline.load_mode == "upsert":
    rows = df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
```

**Current step 5 — builders** (etl.py L1391–1406, to preserve for upsert; remove append/replace insert builders):
```python
if pipeline.load_mode == "append":
    insert_sql, insert_params = _build_insert_sql(
        pipeline.target, columns, rows, pipeline.schema
    )
elif pipeline.load_mode == "upsert":
    insert_sql, insert_params = _build_upsert_sql(...)
else:  # replace
    truncate_sql, _ = build_truncate_sql(pipeline.target, pipeline.schema)
    insert_sql, insert_params = _build_insert_sql(...)
```

**Target step 5** (append/replace via COPY; upsert unchanged):
```python
if pipeline.load_mode == "upsert":
    insert_sql, insert_params = _build_upsert_sql(
        pipeline.target, rows, list(pipeline.conflict_columns), schema=pipeline.schema
    )
elif pipeline.load_mode == "replace":
    truncate_sql, _ = build_truncate_sql(pipeline.target, pipeline.schema)
# append: no SQL to build — COPY inline below
```

**Current step 6 — atomic seam** (etl.py L1415–1421, to modify inline):
```python
with self._db.session():
    with self._db.transaction() as conn:
        with conn.cursor() as cur:
            if pipeline.load_mode == "replace":
                cur.execute(truncate_sql)
            cur.execute(insert_sql, insert_params)
            rows_loaded += cur.rowcount
```

**Target step 6** (COPY inline on seam cursor for append/replace; D-02a — never call `copy_insert` public):
```python
with self._db.session():
    with self._db.transaction() as conn:
        with conn.cursor() as cur:
            if pipeline.load_mode == "replace":
                cur.execute(truncate_sql)
            if pipeline.load_mode in ("append", "replace"):
                # COPY inline — cur is the transaction cursor (seam preserved)
                _stream_df_copy(cur, df, pipeline.target, pipeline.schema, columns)
                rows_loaded += cur.rowcount   # read AFTER with cur.copy() closes
            else:  # upsert
                cur.execute(insert_sql, insert_params)
                rows_loaded += cur.rowcount
```

---

### `pycopg/etl.py` — async load seam (modify steps 3–6, L2019–2089)

**Analog:** sync seam above (mirror pattern). Async seam shape (etl.py L2083–2089):
```python
async with self._db.session():
    async with self._db.transaction() as conn:
        async with conn.cursor() as cur:
            if pipeline.load_mode == "replace":
                await cur.execute(truncate_sql)
            await cur.execute(insert_sql, insert_params)
            rows_loaded += cur.rowcount
```

**Target step 6 (async mirror):**
```python
async with self._db.session():
    async with self._db.transaction() as conn:
        async with conn.cursor() as cur:
            if pipeline.load_mode == "replace":
                await cur.execute(truncate_sql)
            if pipeline.load_mode in ("append", "replace"):
                await _async_stream_df_copy(
                    cur, df, pipeline.target, pipeline.schema, columns
                )
                rows_loaded += cur.rowcount
            else:  # upsert
                await cur.execute(insert_sql, insert_params)
                rows_loaded += cur.rowcount
```

Steps 3 and 5 are mirrored from the sync version (same logic, only `await` added where needed).

---

## Test Pattern Assignments

### `tests/test_database_integration.py` — `TestFromDataframeCopy` (new class)

**Analog:** `test_from_dataframe` (same file, L317–334) for real-DB data verification.
**Analog:** `test_copy_insert` (same file, L781+) for COPY-specific verification structure.

**Existing test to extend/copy fixture pattern from** (L317–334):
```python
def test_from_dataframe(self, db, temp_table_name, cleanup_table):
    pd = pytest.importorskip("pandas")
    cleanup_table(temp_table_name)
    df = pd.DataFrame({"name": ["x", "y", "z"], "value": [10, 20, 30]})
    db.from_dataframe(df, temp_table_name)
    results = db.execute(f'SELECT * FROM "{temp_table_name}" ORDER BY name')
    assert len(results) == 3
```

**New test structure (D-06 spy pattern from RESEARCH Q3):**
```python
class TestFromDataframeCopy:
    """PERF-01: from_dataframe routes data via COPY, not via df.to_sql data path."""

    def test_from_dataframe_copy_path(self, db, cleanup_table):
        """to_sql called exactly once (head(0) DDL); data loaded via COPY."""
        import pandas as pd
        from unittest.mock import patch

        t = f"test_copy_{uuid.uuid4().hex[:8]}"
        cleanup_table(t)
        df = pd.DataFrame({"id": [1, 2, 3], "val": ["a", "b", "c"]})
        original_to_sql = pd.DataFrame.to_sql
        to_sql_calls = []

        def spy_to_sql(self, *args, **kwargs):
            to_sql_calls.append(len(self))
            return original_to_sql(self, *args, **kwargs)

        with patch.object(pd.DataFrame, "to_sql", spy_to_sql):
            db.from_dataframe(df, t)

        rows = db.execute(f'SELECT COUNT(*) AS n FROM public."{t}"')
        assert rows[0]["n"] == 3
        assert len(to_sql_calls) == 1, "to_sql must be called once (DDL only)"
        assert to_sql_calls[0] == 0, "to_sql called on head(0), not full df"
```

Additional tests in this class: `test_from_dataframe_replace`, `test_from_dataframe_append`, `test_from_dataframe_index_true`, `test_from_dataframe_nan_null`.

---

### `tests/test_async_database.py` — async from_dataframe COPY spy (new test, PERF-05)

**Analog:** `test_from_dataframe_basic` (same file, L644–662) — mock engine + `patch.object(df, "to_sql")`.

**Existing async test pattern** (L644–662):
```python
async def test_from_dataframe_basic(self, config):
    import pandas as pd
    mock_engine, mock_sync_conn = create_async_engine_mock()
    df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
    db = AsyncDatabase(config)
    db._async_engine = mock_engine
    with patch.object(df, "to_sql") as mock_to_sql:
        await db.from_dataframe(df, "users")
        mock_to_sql.assert_called_once()
```

**New test** — update the assertion: `to_sql` still called once (for DDL) but now also verify `connect` was called (for COPY). For real-DB, mirror `test_from_dataframe_real_db_applies_pk` pattern at L2852.

---

### `tests/test_database.py` / `tests/test_database_integration.py` — `insert_batch` non-regression (PERF-03)

**Analog:** `test_insert_batch_and_select` (test_database_integration.py L82–113).

No new behavior, just verify that `insert_batch` produces identical results before/after hoist. Extend the existing test or add a targeted non-regression assertion verifying row count and content match on a small dataset.

---

### `tests/test_etl_accessor.py` — ETL COPY path verification (extend existing, PERF-02)

**Analog:** `test_run_writes_full_row` (same file, L231–257) — real DB, pipeline with `load_mode="replace"`, verifies `rows_loaded` is not None.

**Extension pattern:**
```python
def test_etl_run_copy_path_rows_loaded(self, db, cleanup_pipeline_runs):
    """PERF-02: ETL run with append/replace uses COPY; rows_loaded matches DataFrame size."""
    tbl = f"etl_copy_{uuid.uuid4().hex[:8]}"
    p = Pipeline(name="perf02", source="SELECT 1 AS id, 'a' AS val", target=tbl, load_mode="replace")
    try:
        result = db.etl.run(p)
    finally:
        db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

    assert result.status == "success"
    assert result.rows_loaded == 1   # exact count, not just non-None
```

---

## Shared Patterns

### validate_identifiers — applied before every COPY SQL interpolation
**Source:** `pycopg/database.py` L1028 (in `copy_insert`) and L1233 (in `from_dataframe`)
**Apply to:** `_stream_df_copy` callers (caller validates before passing to helper), ETL seam step 3/5.
```python
validate_identifiers(table, schema)   # always first, before any f-string with table/schema
```

### Connection management — sync
**Source:** `copy_insert` (database.py L1037–1043)
```python
with self.connect() as conn:
    with conn.cursor() as cur:
        # ... COPY ...
    conn.commit()
```

### Connection management — async
**Source:** `copy_insert` async (async_database.py L678–686)
```python
async with self.connect() as conn:
    async with conn.cursor() as cur:
        # ... async COPY ...
    await conn.commit()
```

### ETL seam constraint (D-02a)
**Source:** `etl.py` L1410–1414 comment + seam at L1415
Never call `copy_insert` (public) or any method that opens its own connection from inside `with self._db.session(): with self._db.transaction() as conn:`. COPY must run inline on the `cur` yielded by the transaction context manager.

### NaN/NaT normalisation
**Source:** RESEARCH Q1 (verified live), `df.isna().values` mask pattern
```python
null_mask = df.isna().values   # pre-computed boolean matrix (n_rows x n_cols)
row_values = df.values         # object array — preserves Timestamp, np.int64
# per-row: [None if null_mask[i][j] else row_values[i][j] for j in ...]
```
Apply to: `_stream_df_copy`, `_async_stream_df_copy`. Do NOT pass `pd.NaT` raw to `write_row`.

### Test real-DB env
**Source:** `.planning/STATE.md` + RESEARCH Environment
All real-DB tests must use `PGDATABASE=pycopg_test2`. The default `pycopg_test` DB is broken since 2026-06-24. Coverage gate stays at `--cov-fail-under=94` (unchanged in Phase 38).

---

## No Analog Found

None — all modification targets have close in-repo analogs.

---

## Metadata

**Analog search scope:** `pycopg/database.py`, `pycopg/async_database.py`, `pycopg/etl.py`, `tests/test_database_integration.py`, `tests/test_async_database.py`, `tests/test_etl_accessor.py`, `tests/test_parity.py`
**Files scanned:** 7 source + test files read directly
**Pattern extraction date:** 2026-06-26
