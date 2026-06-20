# Phase 27: Incremental ETL — Run-Log Integration - Pattern Map

**Mapped:** 2026-06-20
**Files analyzed:** 3 (all modified, no new files)
**Analogs found:** 7 / 7 (every symbol has an in-repo analog; this phase is composition of existing tested parts)

## File Classification

| Modified File | Symbol / change | Role | Data Flow | Closest Analog | Match Quality |
|---------------|-----------------|------|-----------|----------------|---------------|
| `pycopg/queries.py` | `ETL_GET_LAST_WATERMARK` (new const) | query-constant | request-response (read) | `ETL_GET_LAST_RUN` (queries.py:289) | exact |
| `pycopg/queries.py` | `ETL_UPDATE_RUN_WATERMARK` (new const) | query-constant | request-response (write) | `ETL_UPDATE_RUN` (queries.py:270) | exact |
| `pycopg/etl.py` | `from psycopg.types.json import Jsonb` (import) | import | — | existing import block (etl.py:35) | exact |
| `pycopg/etl.py` | `_read_watermark(name)` (new method) | service/accessor-method | CRUD (read) | `last_run` (etl.py:902) + decode via `_decode_watermark` (etl.py:629) | exact |
| `pycopg/etl.py` | `_end_run(..., watermark=None)` (extend) | service/accessor-method | CRUD (write) | `_end_run` current body (etl.py:794-849) | self / exact |
| `pycopg/etl.py` | `max(col)` capture + D-07 coercion + D-06 guard in `run()` | transform / orchestration | transform → request-response | extract→transform boundary (etl.py:1108-1119); `ETLError` raise pattern in `_encode_watermark` (etl.py:613-616) | role-match |
| `tests/test_etl_accessor.py` | 6 live-DB integration tests | test | request-response (assert) | `test_run_writes_full_row` (:231), `test_failed_run_commits_despite_load_rollback` (:259) | exact |

## Pattern Assignments

### `pycopg/queries.py` — `ETL_GET_LAST_WATERMARK` (query-constant, read)

**Analog:** `ETL_GET_LAST_RUN` (queries.py:289-295)

```python
ETL_GET_LAST_RUN = """
    SELECT *
    FROM pipeline_runs
    WHERE pipeline_name = %s
    ORDER BY started_at DESC
    LIMIT 1
"""
```

**New constant (copy shape, narrow SELECT to `watermark`, add the D-03 predicate):**
```python
ETL_GET_LAST_WATERMARK = """
    SELECT watermark
    FROM pipeline_runs
    WHERE pipeline_name = %s
      AND status = 'success'
      AND watermark IS NOT NULL
    ORDER BY started_at DESC
    LIMIT 1
"""
```
Why `SELECT watermark` not `SELECT *`: the read is narrow and feeds one column into `_decode_watermark`. The `status='success' AND watermark IS NOT NULL` predicate is what makes the empty-batch-preserves and no-advance-on-failure invariants fall out of the query (D-03) — failed rows and empty-batch successes (NULL watermark) are auto-skipped.

---

### `pycopg/queries.py` — `ETL_UPDATE_RUN_WATERMARK` (query-constant, write)

**Analog:** `ETL_UPDATE_RUN` (queries.py:270-279)

```python
ETL_UPDATE_RUN = """
    UPDATE pipeline_runs
    SET status = %s,
        finished_at = %s,
        rows_extracted = %s,
        rows_loaded = %s,
        error_message = %s,
        error_traceback = %s
    WHERE run_id = %s
"""
```

**New constant (same columns + trailing `watermark = %s`, param order = existing then watermark then run_id):**
```python
ETL_UPDATE_RUN_WATERMARK = """
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
Per Research Pattern 2 (recommended): a **dedicated** constant makes the failed/empty UPDATE structurally incapable of touching `watermark`, enforcing the no-advance-on-failure invariant in SQL rather than a runtime branch. Match the existing const's whitespace/trailing-`"""` style exactly (no trailing `;` — see WR-03 carry-forward).

---

### `pycopg/etl.py` — import `Jsonb`

**Analog:** existing import block (etl.py:25-43). `from psycopg.rows import dict_row` already present at line 35.

```python
import pandas as pd
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb   # ADD — not present yet (D-05)
```
`ETLError` is already imported (etl.py:38-42, the `noqa: F401` block) — no new exception import needed for the D-06 guard.

---

### `pycopg/etl.py` — `_read_watermark(name)` (NEW method on `ETLAccessor`)

**Analog:** `last_run` (etl.py:902-926) — the verbatim autocommit + `dict_row` template; decode via `_decode_watermark` (etl.py:629-655).

`last_run` body to copy (etl.py:922-926):
```python
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.ETL_GET_LAST_RUN, [name])
        row = cur.fetchone()
return _row_to_result(row) if row is not None else None
```

**New method (swap query, swap mapper for decode, handle NULL):**
```python
def _read_watermark(self, name: str):
    """Return the last successful, non-NULL watermark for a pipeline, or None."""
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_GET_LAST_WATERMARK, [name])
            row = cur.fetchone()
    if row is None or row["watermark"] is None:
        return None
    return _decode_watermark(row["watermark"])
```
`row["watermark"]` is a plain Python `dict` (JSONB read via `dict_row` — verified live in Research §2); fed straight to the frozen `_decode_watermark`. Placement: a method on `ETLAccessor` alongside `_start_run`/`_end_run`/`_fetch_run_result`/`last_run` (Claude's Discretion confirms method placement). numpydoc shallow docstring (`interrogate ≥ 95`).

---

### `pycopg/etl.py` — `_end_run(..., watermark=None)` (extend, write)

**Analog:** the existing `_end_run` body (etl.py:794-849).

Current write-site (etl.py:836-849):
```python
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            queries.ETL_UPDATE_RUN,
            [status, datetime.now(UTC), rows_extracted, rows_loaded,
             error_message, error_traceback, run_id],
        )
```

**Extend (add `watermark: dict | None = None` kwarg after `error_traceback`; branch on None):**
```python
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        if watermark is None:
            cur.execute(queries.ETL_UPDATE_RUN,
                [status, datetime.now(UTC), rows_extracted, rows_loaded,
                 error_message, error_traceback, run_id])
        else:
            cur.execute(queries.ETL_UPDATE_RUN_WATERMARK,
                [status, datetime.now(UTC), rows_extracted, rows_loaded,
                 error_message, error_traceback, Jsonb(watermark), run_id])
```
`watermark` is the **already-encoded envelope dict** (output of `_encode_watermark`); `_end_run` wraps it in `Jsonb(...)` at the binding site (D-05) — never `json.dumps` (would double-encode). Failed (etl.py:1199-1208) and empty-batch (etl.py:1139) callers pass nothing → `watermark is None` → original SQL → column stays NULL. `%s`-only binding, identifiers never interpolated (established pattern).

---

### `pycopg/etl.py` — `max(col)` capture + coercion + guard in `run()`

**Analog for the seam:** extract→transform boundary (etl.py:1108-1119). Capture immediately after `rows_extracted = len(df)` (line 1108), BEFORE the transform loop at line 1121 (D-02 — transforms may rename/drop the column).

**Analog for the D-06 ETLError raise:** the strict-raise style already in `_encode_watermark` (etl.py:613-616):
```python
raise ETLError(
    f"unsupported watermark type {type(value).__name__!r}; "
    f"supported types are {_WATERMARK_SUPPORTED}"
)
```

**New block (insert after etl.py:1108, copy-ready from Research §1):**
```python
raw_watermark = None
col = pipeline.incremental_column
if col is not None:
    if col not in df.columns:
        raise ETLError(
            f"incremental_column {col!r} not found in extracted batch "
            f"columns {list(df.columns)} (ETL-INC-04)"
        )  # D-06 — clear ETLError, not a bare KeyError
    if len(df):                       # max() on empty df is NaN
        m = df[col].max()
        if isinstance(m, pd.Timestamp):
            raw_watermark = m.to_pydatetime()   # plain datetime, offset preserved
        elif isinstance(m, str):
            raw_watermark = str(m)              # normalize numpy.str_ → str
        else:
            raw_watermark = int(m)              # numpy.int64 → plain int
```
**Coercion is at the call-site** (D-07 resolved by Research §1): `numpy.int64` FAILS the `{datetime,int,str}` allowlist (`isinstance(np.int64(5), int)` is False) → `int()` required; `pandas.Timestamp` passes but `.to_pydatetime()` hands the frozen encoder a plain `datetime`; text is plain `str`. Do NOT re-open `_encode_watermark`.

**Success call-site** — currently `self._end_run(run_id, "success", rows_extracted, rows_loaded)` (etl.py:1210). Change to pass the encoded envelope:
```python
wm_env = _encode_watermark(raw_watermark) if raw_watermark is not None else None
self._end_run(run_id, "success", rows_extracted, rows_loaded, watermark=wm_env)
```
Leave the empty-batch path (etl.py:1138-1140) and failed path (etl.py:1199-1208) untouched — they pass no watermark (NULL preserved). `Pipeline` validation (`_validate_incremental`, etl.py:76) already forces `incremental_column` ⇒ `load_mode='upsert'` and a valid identifier, so the guard only fires on a genuinely missing column.

---

### `tests/test_etl_accessor.py` — 6 live-DB integration tests

**Analogs:**
- `test_run_writes_full_row` (:231-257) — the row-assert convention; already asserts `row["watermark"] is None` for non-incremental runs (line 257). Extend this for the incremental first-run / round-trip cases.
- `test_failed_run_commits_despite_load_rollback` (:259+) — the forced-failure harness: `_start_run` + `db.transaction()` + `raise RuntimeError` + `_end_run(run_id, "failed", ...)`. Reuse verbatim for SC-2 (no-advance-on-failure).

**Fixtures to reuse (do not invent new ones):**
- `db` (:20-24), `cleanup_pipeline_runs` (:27-34) — drops `pipeline_runs` on teardown.
- `etl_table` (:422-431) — fresh `(id INTEGER, val TEXT)` target, autocommit create/drop.
- `etl_src` (:434-443) — fresh `(id INTEGER, val TEXT)` source.

**Row-assert pattern (copy from :245-257):**
```python
rows = db.execute("SELECT * FROM pipeline_runs WHERE run_id = %s", [result.run_id])
row = rows[0]
assert row["watermark"] == {"type": "int", "value": <known_max>}   # plain dict from JSONB
assert db.etl._read_watermark("name") == <known_max>
```

**Six tests (extend `TestRunPipelineIntegration` :446):**
| Test (`-k`) | SC / D | Assert |
|-------------|--------|--------|
| `first_run_records_watermark` | SC-1/ETL-INC-02 | `watermark == {"type":"int","value":max}`; `_read_watermark` == max |
| `failed_run_does_not_advance_watermark` | SC-2/ETL-INC-06 | failed row `watermark IS NULL`; `_read_watermark` returns prior W0 (reuse :259 harness) |
| `empty_batch_preserves_watermark` | SC-3/ETL-INC-05 | source `SELECT 1 AS id WHERE false`; `status='success'`, `rows_loaded==0`, `watermark IS NULL`; `_read_watermark` == prior W0 |
| `watermark_jsonb_roundtrip` | SC-4/ETL-INC-10 | parametrize (tz-aware ts, int, text); assert decoded == **coerced** `max()` (Pitfall 4: compare to `m.to_pydatetime()`, NOT a hand literal) |
| `read_watermark_none_first_run` | D-04 | `_read_watermark` == None when no qualifying success row |
| `incremental_column_missing_raises_etlerror` | D-06 | `pytest.raises(ETLError)` when `incremental_column` absent from batch (not `KeyError`) |

Pitfall 4 (timestamptz UTC-normalization on `to_dataframe` read) — assert against the coerced `max()` output, not a `+02:00` literal. `ETLError` import already in test file? It imports `ETLTargetNotFoundError, ETLTransformError` (line 13) — **add `ETLError`** to that import for the D-06 test.

## Shared Patterns

### Dedicated autocommit + `dict_row` run-log connection
**Source:** `_start_run` (etl.py:786-792), `_end_run` (etl.py:836-849), `last_run` (etl.py:922-926)
**Apply to:** `_read_watermark` (new) and the extended `_end_run`
```python
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(<query>, [<params>])
```
Guarantees the watermark commits/reads independently of the load transaction — a failed/rolled-back load still records `status='failed'` with NULL watermark.

### Frozen typed-envelope helpers (no re-open)
**Source:** `_encode_watermark` (etl.py:580-626), `_decode_watermark` (etl.py:629-655)
**Apply to:** `run()` success path (encode the coerced watermark) and `_read_watermark` (decode the read-back dict)
Allowlist is exactly `{datetime, int, str}`; `bool` rejected before the `int` branch. Phase 27 satisfies it via call-site coercion — do NOT modify these.

### `%s`-only binding, `Jsonb()` wrap at write-site
**Source:** every run-log `cur.execute` (etl.py:788, 838); Research §2 verified round-trip
**Apply to:** `_end_run` watermark param
The watermark value is always a `%s` param wrapped in `Jsonb(...)`, never interpolated; read side yields a plain `dict` (no `json.loads`).

### Domain `ETLError` over bare exceptions
**Source:** `_encode_watermark` raise (etl.py:613-616, 623-626); base in `exceptions.py:54`
**Apply to:** the D-06 missing-column guard in `run()`

## No Analog Found

None. Every symbol has a direct in-repo analog (this phase is composition of existing, tested parts — Research "Key insight").

## Metadata

**Analog search scope:** `pycopg/etl.py`, `pycopg/queries.py`, `pycopg/exceptions.py`, `tests/test_etl_accessor.py`
**Files scanned:** 4 (targeted reads at cited line ranges; no full-file loads)
**Pattern extraction date:** 2026-06-20
