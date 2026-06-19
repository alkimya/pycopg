# Technology Stack — v0.7.0 Incremental ETL (Watermark/CDC)

**Project:** pycopg v0.7.0 — Incremental ETL on top of existing ETL runner
**Researched:** 2026-06-19
**Scope:** Watermark serialization into `pipeline_runs.watermark JSONB` only.
The alias-removal half of v0.7.0 is mechanical and needs no stack research.

---

## Verdict: Zero New Runtime Dependencies Confirmed

The incremental ETL feature is fully buildable with the existing runtime stack.
No additions to `pyproject.toml` dependencies are required.

**Confidence:** HIGH — verified against psycopg 3.3.4 (installed), Context7
official psycopg docs, and live Python interpreter tests.

---

## Existing Stack (Do Not Change)

| Technology | Version Constraint | Role |
| --- | --- | --- |
| Python | 3.11+ | Language (fromisoformat ISO 8601 full support) |
| psycopg | >=3.1.0 (installed: 3.3.4) | PostgreSQL driver; provides `Jsonb` wrapper |
| psycopg_pool | >=3.2.0 | Connection pooling |
| pandas | >=2.0.0 | DataFrame; `Series.max()` returns `pd.Timestamp` / `np.int64` |
| geopandas | >=0.14.0 | GeoDataFrame; no role in watermark feature |
| tenacity | any | Retry/backoff; no role in watermark feature |
| numpy | transitive via pandas | `np.integer` isinstance check needed in `_encode_watermark` |

No new entry needed. All required functionality is already present in these deps.

---

## The JSONB Watermark Mechanism

### Why JSONB for a Scalar Value

The `incremental_column` value could be a `TIMESTAMPTZ`, `BIGINT`, or `TEXT`
column in PostgreSQL. Using `JSONB` (already reserved as `pipeline_runs.watermark
JSONB`) lets us store any scalar type in one column without schema branching. The
envelope stores a type tag alongside the value so the read path can reconstruct
the correct Python type.

### Write Path

`psycopg.types.json.Jsonb` — HIGH confidence (Context7 + live test)

```python
from psycopg.types.json import Jsonb

# Wrap the envelope dict as JSONB before passing to cur.execute()
cur.execute(
    "UPDATE pipeline_runs SET watermark = %s WHERE run_id = %s",
    [Jsonb({"value": "2024-06-15T12:00:00+00:00", "type": "timestamptz"}), run_id],
)
```

- `Jsonb(obj)` signals psycopg 3 to serialize `obj` to a JSONB PostgreSQL value.
- Uses `json.dumps` by default (stdlib, no extra dep).
- A per-call `dumps=` kwarg on `Jsonb(obj, dumps=fn)` can be used for non-serializable
  types, but the tagged-envelope approach makes this unnecessary: values are already
  converted to stdlib-serializable Python types before being placed in the envelope dict.
- Available since psycopg 3.x; confirmed stable in 3.1+ (project minimum).

### Read Path

Automatic dict return — HIGH confidence (live test)

When psycopg 3 reads a `JSONB` column it automatically calls `json.loads` via
`JsonbLoader.load()`. No custom loader is needed. With `dict_row`, the returned
row gives:

```python
row["watermark"]   # None when NULL (first run), or dict when set
```

The existing `_row_to_result` in `etl.py` already drops `watermark` (D-10). The
new `_get_last_watermark` helper reads the column directly before calling
`_row_to_result`, so `RunResult` stays unchanged.

No `set_json_dumps` / `set_json_loads` global side effects. The watermark
helpers encode/decode locally without touching the global psycopg JSON adapter.

---

## Watermark Envelope Format

Store a tagged two-key dict: `{"value": <scalar>, "type": <tag>}`.

| Python source type | Stored as | Type tag |
| --- | --- | --- |
| `pd.Timestamp` (tz-aware or naive) | ISO 8601 string via `.to_pydatetime().isoformat()` | `"timestamptz"` |
| `numpy.integer` (int64, int32, …) | `int(v)` | `"bigint"` |
| `str` | as-is | `"text"` |
| `datetime.datetime` | `.isoformat()` | `"timestamptz"` |
| `int` / `float` (plain Python) | as-is | `"bigint"` / `"float"` |

**Why tagged envelope, not raw scalar:** `json.loads` returns `str` for
everything serialized as a string. Without a type tag, a timestamp stored as
`"2024-06-15T12:00:00+00:00"` and a pipeline-name string like
`"2024-06-15T12:00:00+00:00"` are indistinguishable on read-back. The tag
makes `_decode_watermark` unambiguous and keeps the implementation in stdlib.

**Edge case — empty batch (pd.NaT from `.max()`):** If the batch DataFrame is
empty after filtering, `df[col].max()` returns `pd.NaT`. The write path must
check `pd.isna(max_val)` and skip the watermark update (keep the prior value).
This is correct semantics: an empty incremental batch means no new high-water
mark.

**Edge case — naive timestamps:** `pd.Timestamp` without timezone info is
allowed. `.to_pydatetime()` preserves the naive state; `isoformat()` omits the
`+00:00` suffix. The WHERE filter still works because PostgreSQL `timestamp`
(without tz) columns accept a naive Python datetime via psycopg 3's standard
datetime adapter. Document this: "tz-aware columns produce tz-aware watermarks;
naive columns produce naive watermarks."

---

## Two New Pure Functions in `etl.py`

These are the only new code units required at the stdlib/psycopg layer.

### `_encode_watermark(val) -> dict`

Converts a pandas/numpy `max()` result to the tagged envelope ready for
`Jsonb(...)`. Called after a successful incremental load, before `_end_run`.

```python
import datetime
import numpy as np
import pandas as pd

def _encode_watermark(val) -> dict:
    """Convert a pandas/numpy max() result to a JSONB-serializable envelope."""
    if isinstance(val, pd.Timestamp):
        return {"value": val.to_pydatetime().isoformat(), "type": "timestamptz"}
    if isinstance(val, np.integer):
        return {"value": int(val), "type": "bigint"}
    if isinstance(val, np.floating):
        return {"value": float(val), "type": "float"}
    if isinstance(val, datetime.datetime):
        return {"value": val.isoformat(), "type": "timestamptz"}
    if isinstance(val, int):
        return {"value": val, "type": "bigint"}
    if isinstance(val, float):
        return {"value": val, "type": "float"}
    return {"value": str(val), "type": "text"}
```

### `_decode_watermark(raw) -> Any`

Converts the Python dict returned by psycopg's `json.loads` back to the
correct Python scalar for use in the WHERE filter parameter.

```python
def _decode_watermark(raw: dict | None):
    """Reconstruct a Python scalar from a stored watermark envelope."""
    if raw is None:
        return None
    tag = raw.get("type")
    val = raw.get("value")
    if tag == "timestamptz":
        return datetime.datetime.fromisoformat(val)   # stdlib, Python 3.11+
    if tag == "bigint":
        return int(val)
    if tag == "float":
        return float(val)
    return val  # text or unknown — return as str
```

`datetime.datetime.fromisoformat` handles both tz-aware
(`"2024-06-15T12:00:00+00:00"`) and naive (`"2024-06-15T12:00:00"`) ISO
strings in Python 3.11+. The project already requires Python 3.11+ so no
backport is needed.

---

## Changes to Existing Files

### `pycopg/etl.py`

**`Pipeline` dataclass** — add one field after `extract_limit`:

```python
incremental_column: str | None = None
```

Add to `__post_init__` validation:

```python
if self.incremental_column is not None and self.load_mode == "replace":
    raise ValueError(
        "incremental_column is not compatible with load_mode='replace' "
        "(replace truncates the target, making watermarks meaningless)"
    )
```

**`ETLAccessor._end_run` / `AsyncETLAccessor._end_run`** — add optional
`watermark: dict | None = None` parameter. When not `None`, wrap with `Jsonb`
and dispatch to `ETL_UPDATE_RUN_WITH_WATERMARK`; otherwise keep `ETL_UPDATE_RUN`
unchanged.

```python
from psycopg.types.json import Jsonb

wm_param = Jsonb(watermark) if watermark is not None else None
```

This avoids any overhead on non-incremental pipelines and preserves backward
compatibility: non-incremental runs continue to write `NULL` to the watermark
column via the original `ETL_UPDATE_RUN` query.

**`ETLAccessor._get_last_watermark(name)` / `AsyncETLAccessor._get_last_watermark(name)`**
— new private method. Queries `ETL_GET_LAST_WATERMARK` and returns
`_decode_watermark(row["watermark"])`. Returns `None` when no prior successful
run exists (triggers first-run full load path).

**`ETLAccessor.run()` / `AsyncETLAccessor.run()`** — two insertion points:

1. Before extract: if `pipeline.incremental_column` is set, call
   `_get_last_watermark(name)`. If the result is not `None`, inject the WHERE
   clause into the source query.
2. After successful load: if `pipeline.incremental_column` is set, compute
   `batch_max = df[pipeline.incremental_column].max()`. If not `pd.isna(batch_max)`,
   call `_end_run(..., watermark=_encode_watermark(batch_max))`.

**SQL injection safety:** `incremental_column` is a column identifier. It must
pass `validate_identifiers()` before interpolation into any SQL string, using
the same pattern as `pipeline.source` and `pipeline.target` today.

**Subquery wrap for SQL sources:**

```python
# incremental_column validated via validate_identifiers() before f-string use
filtered_sql = (
    f"SELECT * FROM ({pipeline.source}) AS _etl_sub"
    f" WHERE {pipeline.incremental_column} > %s"
)
df = db.to_dataframe(sql=filtered_sql, params={"p": last_wm})
```

For table sources, the same WHERE clause is appended to the generated
`SELECT * FROM {schema}.{table}` string.

### `pycopg/queries.py`

Two new SQL constants (additive — no existing constant is changed):

```python
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

ETL_GET_LAST_WATERMARK = """
    SELECT watermark
    FROM pipeline_runs
    WHERE pipeline_name = %s
      AND status = 'success'
    ORDER BY started_at DESC
    LIMIT 1
"""
```

`ETL_UPDATE_RUN` is left exactly as-is. The only query that changes behavior is
the new `ETL_UPDATE_RUN_WITH_WATERMARK` variant dispatched by `_end_run` when a
watermark dict is provided.

**No schema migration:** the `watermark JSONB` column already exists in every
`pipeline_runs` table created by `ETL_INIT_PIPELINE_RUNS` since v0.5.0. All
those columns are currently `NULL`. The feature slots on additively.

---

## What NOT to Add

| Rejected approach | Reason |
| --- | --- |
| Any new runtime dep (orjson, python-dateutil, etc.) | Zero-new-dep is a hard project constraint; stdlib + existing psycopg/pandas are sufficient |
| `set_json_dumps` global override | Mutates a global adapter state; the tagged-envelope approach avoids non-serializable types entirely |
| Expose `watermark` on `RunResult` | Internal tracking detail; widening the public API adds serialization complexity with no user-facing value |
| Separate `WatermarkPipeline` subclass | Widens the public API; `Pipeline.incremental_column: str \| None = None` (locked scope decision) is sufficient and backward-compatible |
| Storing raw scalar in JSONB (not tagged envelope) | Makes type reconstruction ambiguous on read: `json.loads` returns `str` for all JSON strings, including datetime ISO strings |
| `Jsonb(obj, dumps=custom_fn)` per-call custom encoder | Unnecessary: pre-converting pandas/numpy types to stdlib scalars before constructing the envelope avoids non-serializable objects |
| Schema migration for `pipeline_runs` | The `watermark JSONB` column was reserved in v0.5.0 DDL; it exists in all installed schemas already |
| Modifying `ETL_UPDATE_RUN` to add `watermark=%s` | Would add a mandatory watermark param to every `_end_run` call; a separate `ETL_UPDATE_RUN_WITH_WATERMARK` keeps the non-incremental path zero-overhead |

---

## Sources

- psycopg 3 JSON adaptation — Context7 `/psycopg/psycopg` (`basic/adapt.rst`, `api/types.rst`):
  `Jsonb` wrapper, `set_json_dumps`, `JsonbLoader`, per-call `dumps=` kwarg — HIGH confidence
- psycopg version in use — live: `psycopg.__version__` = `3.3.4`
- `JsonbLoader.load()` source — live inspect: confirmed `self.loads(data)` = `json.loads`
- `Jsonb` import from `psycopg.types.json` — live import test, psycopg >= 3.1.0
- `pd.Timestamp.to_pydatetime().isoformat()` round-trip — live pandas test
- `np.integer` isinstance check for numpy int types — live test (`np.int64`, `np.int32`)
- `pd.NaT` from empty-batch `Series.max()` — live pandas test
- `datetime.datetime.fromisoformat` ISO 8601 full support in Python 3.11+ — stdlib docs
- `pyproject.toml` dep constraints — `/home/loc/workspace/pycopg/pyproject.toml`
- Existing ETL patterns — `/home/loc/workspace/pycopg/pycopg/etl.py` (Pipeline, ETLAccessor, AsyncETLAccessor)
- Existing SQL constants — `/home/loc/workspace/pycopg/pycopg/queries.py` (ETL_UPDATE_RUN, ETL_GET_LAST_RUN, watermark JSONB DDL)
