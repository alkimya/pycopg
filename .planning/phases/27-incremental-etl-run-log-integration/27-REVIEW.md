---
phase: 27-incremental-etl-run-log-integration
reviewed: 2026-06-20T15:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - pycopg/queries.py
  - pycopg/etl.py
  - tests/test_etl_accessor.py
findings:
  critical: 0
  warning: 3
  info: 1
  total: 4
status: issues_found
---

# Phase 27: Code Review Report

**Reviewed:** 2026-06-20
**Depth:** standard (Phase 27 additive diff only — commits cfe8f1e, 7e96a4a, 682de82)
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 27 is small and structurally sound. The SQL constants are correct and safe (parameterized, no trailing `;`, parameter order verified). The `_read_watermark` autocommit pattern mirrors `last_run` correctly. The `_end_run` branching properly keeps `ETL_UPDATE_RUN` on the failed/empty path and `ETL_UPDATE_RUN_WATERMARK` only on the success path — the no-advance-on-failure and empty-batch-preserves invariants are correctly enforced by SQL design.

The `Jsonb(watermark)` write-site wrapping is correct (T-27-01 mitigated). Pipeline name binding in `_read_watermark` is a `%s` parameter (T-27-02 mitigated). No new dependencies. The six integration tests are structurally correct and prove SC-1..SC-4, D-04, and D-06.

Three warnings and one info item remain, all in the `run()` watermark capture block introduced in this phase.

---

## Warnings

### WR-01: `else: int(m)` silently truncates float watermark columns

**File:** `pycopg/etl.py:1208`

**Issue:** The coercion fallthrough is:

```python
if isinstance(m, pd.Timestamp):
    raw_watermark = m.to_pydatetime()
elif isinstance(m, str):
    raw_watermark = str(m)
else:
    raw_watermark = int(m)  # numpy.int64 → plain int
```

The `else` branch is designed for `numpy.int64` integer columns, which is the common case. However, it also handles `numpy.float64` — and `int(numpy.float64(99.99))` = `99`. If a user sets `incremental_column` on a `NUMERIC`, `FLOAT`, or `DOUBLE PRECISION` PostgreSQL column, the watermark is **silently truncated**. The stored watermark of `99` instead of `99.99` means any rows with values between `99` and `99.99` would be missed on the next incremental extract (Phase 28). There is no warning, no error — the run succeeds with a subtly wrong watermark.

`_encode_watermark` accepts `int` and `str` but not `float` — the call-site coercion converts float to int before the strict encoder sees it, bypassing the type guard that would otherwise surface this as an ETLError.

**Fix:** Add an explicit float/Decimal guard before the `else` branch that either raises `ETLError` (float is not a supported watermark type — user should cast their column to INTEGER or use a TIMESTAMP instead) or adds `float` to `_WATERMARK_SUPPORTED`. The cleanest fix without reopening `_encode_watermark` is to raise at the call site:

```python
elif isinstance(m, (float, np.floating)):
    raise ETLError(
        f"incremental_column {col!r} has float dtype; float watermarks are not "
        f"supported (use INTEGER or TIMESTAMP). Supported types: {_WATERMARK_SUPPORTED}"
    )
else:
    raw_watermark = int(m)  # numpy.int64 → plain int (D-07)
```

Note: `numpy` is not currently imported in `etl.py`; alternatively use `not isinstance(m, (int, np.integer))` before the `int()` call — but `np.integer` would require the import. The simplest form: check `isinstance(m, float)` (covers `np.float64` which is not a subclass of `float` in all numpy versions — use `pd.api.types.is_float(m)` for safety):

```python
elif pd.api.types.is_float(m) and not m.is_integer():
    raise ETLError(...)
else:
    raw_watermark = int(m)
```

Or simply reject all floats unconditionally since float watermarks have no defined semantics in this library.

---

### WR-02: `int(m)` on all-NULL numeric column crashes with `ValueError` inside the try block

**File:** `pycopg/etl.py:1199-1208`

**Issue:** The guard `if len(df):` protects against `max()` on an empty DataFrame. But for a **non-empty DataFrame whose `incremental_column` contains only NULL values**, `df[col].max()` returns `float('nan')` (for object/float dtype) or `pd.NaT` (for datetime dtype), and both fall through to `else: int(m)`:

- `int(float('nan'))` → `ValueError: cannot convert float NaN to integer`
- `int(pd.NaT)` → `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NaTType'`

These unhandled exceptions propagate to the outer `except Exception` block, which marks the run as `'failed'` and re-raises — so the run fails with a cryptic `ValueError`/`TypeError` instead of a meaningful `ETLError`. This is most likely to occur when a newly-backfilled table has NULLs in the watermark column.

**Fix:** After `m = df[col].max()`, add a null check before the type dispatch:

```python
if len(df):
    m = df[col].max()
    if pd.isna(m):
        # All values in incremental_column are NULL — treat as no watermark
        pass  # raw_watermark stays None
    elif isinstance(m, pd.Timestamp):
        raw_watermark = m.to_pydatetime()
    elif isinstance(m, str):
        raw_watermark = str(m)
    else:
        raw_watermark = int(m)
```

This degrades gracefully (no watermark recorded for that run, same as the empty-batch path) instead of crashing.

---

### WR-03: Empty-batch early-return discards a non-None `raw_watermark` captured before transforms

**File:** `pycopg/etl.py:1237-1240`

**Issue:** The sequence is:

1. Raw batch extracted → `rows_extracted = len(df)` (non-zero)
2. Watermark captured → `raw_watermark` set from `df[col].max()`
3. Transform chain applied → may filter rows out entirely
4. `rows = df.astype(object)...to_dict(...)` → empty list
5. `if not rows: self._end_run(run_id, "success", rows_extracted, 0)` — no watermark passed

If a transform eliminates all rows from a non-empty extract, the run records `status='success'`, `rows_loaded=0`, **and no watermark** — even though a valid watermark was captured from the raw batch. This means the prior successful watermark is preserved (correct from the query's perspective), but the pipeline does not advance the watermark even though it processed rows.

This is an edge case with ambiguous desired semantics (should a transform-eliminated batch advance the watermark?), but the current behavior is not consistent with the comment at line 1237: "Empty DataFrame: no load needed" — the DataFrame is not necessarily empty; the derived `rows` dict list is empty after NaN-to-None conversion. More importantly, the captured `raw_watermark` is silently discarded without documentation, which may be surprising in Phase 28 when users observe no watermark advance after transform-filtered runs.

**Fix (minimal):** Add a comment at line 1239 to document the deliberate discard:

```python
# Empty rows after transforms — do not persist watermark (treat as empty batch,
# prior watermark is preserved by ETL_GET_LAST_WATERMARK's NOT NULL predicate).
self._end_run(run_id, "success", rows_extracted, 0)
```

Or, if the intent is that the watermark SHOULD advance when rows were extracted (even if transforms dropped them all), pass `watermark=wm_env` here too — but that would be a scope decision. The warning is that the current behavior is undocumented and may surprise Phase 28 implementors.

---

## Info

### IN-01: `_read_watermark` return type annotation missing

**File:** `pycopg/etl.py:960`

**Issue:** The method signature is `def _read_watermark(self, name: str):` with no return type annotation. The docstring states it returns `datetime or int or str or None`, but the type hint is absent. The frozen `_decode_watermark` also lacks a return annotation, but that is out-of-scope for Phase 27.

**Fix:**

```python
def _read_watermark(self, name: str) -> datetime | int | str | None:
```

This also requires `datetime` to be in scope at the method level — it is already imported at the top of `etl.py`. This is purely a type-hint quality issue; no runtime behavior is affected.

---

_Reviewed: 2026-06-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
