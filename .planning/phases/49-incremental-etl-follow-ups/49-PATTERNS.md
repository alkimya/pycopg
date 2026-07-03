# Phase 49: Incremental ETL Follow-ups - Pattern Map

**Mapped:** 2026-07-03
**Files analyzed:** 3 existing files modified (no new files/modules)
**Analogs found:** 5 / 5 extension points (all analogs are shipped siblings in the same file)

This phase is a pure **extend-in-place** phase: `pycopg/etl.py`, `pycopg/queries.py`, and
`tests/test_etl.py`/`tests/test_parity.py` are the entire surface. There is no "new file vs
existing file" analog search to do — the closest analog for every new piece of logic is the
adjacent, already-shipped pattern in the same function/class. This document maps each of the
four features (F01-F04) to its concrete in-repo precedent with line numbers and excerpts, as
directed by CONTEXT.md/RESEARCH.md.

## File Classification

| File (extended, not created) | Role | Data Flow | Extension Points | Closest Analog (same file) |
|---|---|---|---|---|
| `pycopg/etl.py` — `Pipeline` dataclass + `__post_init__` | model / config | CRUD (config validation) | add `initial_watermark`, `incremental_inclusive`, `incremental_lookback`, `concurrency` fields; widen `incremental_column` | `extract_limit` guard (:258-269) + `conflict_columns` str-reject/list→tuple normalization (:230-244) |
| `pycopg/etl.py` — `RunResult` dataclass | model | request-response (return value) | new `'skipped'` transient status value (no new field required per Claude's Discretion) | existing `'dry_run'` transient status (:285, and the dry-run RunResult construction at :1276-1283 / :1972-1979) |
| `pycopg/etl.py` — `_build_incremental_extract_sql` (:539) | service (pure SQL builder) | transform (build SQL string + params) | extend for `>=`/lookback operator choice and composite tuple compare | itself — the existing scalar `>` builder body (:587-600) is the base to extend in place |
| `pycopg/etl.py` — `_encode_watermark`/`_decode_watermark` (:607/:656) | service (pure codec) | transform (serialize/deserialize) | add `"composite"` tag | itself — the existing 3-branch `if tag == ...` dispatch chain |
| `pycopg/etl.py` — `_read_watermark` sync (:1007) / async (:1722) | service (pure-ish DB read) | request-response | seed fallback (F01) applied at call site, not inside the function (see Open Question resolution below) | itself — the `if row is None or row["watermark"] is None: return None` early-return (:1039-1045 equivalent) |
| `pycopg/etl.py` — max-watermark capture block, sync (:1315-1347) + dry-run mirror (:1227-1250) + async (:2011-2043) + async dry-run mirror (:1923-1946) | service (pure type dispatch) | transform | extend for lookback floor arithmetic (F02) and composite sorted-last-row capture (F03) | itself — the existing `pd.isna` → `pd.Timestamp` → `str` → `is_float`-reject → `int` dispatch chain, duplicated 4x already (2 statuses x sync/async) |
| `pycopg/etl.py` — `run()` sync (:1132) / async (:1843) | controller (orchestrates read→extract→transform→load→record) | request-response, CRUD | wrap whole body in advisory-lock acquire/release (F04); add `'skipped'` early-return fork | the existing `dry_run` early fork inside `run()` (:1211 sync / :1907 async) — same "early return before the real load, no `pipeline_runs` row written" shape |
| `pycopg/etl.py` — `_end_run` sync (:840) / async (:1565) | service (DB write, autocommit) | CRUD (UPDATE) | persist composite envelope (already opaque `dict`, no change needed — `_encode_watermark` output is passed through unchanged) | itself; no structural change expected, only the *value* passed in changes shape |
| `pycopg/queries.py` — new `ETL_ADVISORY_LOCK`/`ETL_ADVISORY_TRY_LOCK`/`ETL_ADVISORY_UNLOCK` constants | config (SQL constant) | request-response | 3 new triple-quoted `ETL_*` string constants | `ETL_GET_LAST_WATERMARK` (:383-391) / `ETL_UPDATE_RUN_WATERMARK` (:393-403) — naming convention `ETL_<VERB>_<NOUN>`, single bound `%s` param style |
| `tests/test_etl.py` | test | — | new `TestInitialWatermark`, `TestCompositeWatermark`, `TestAdvisoryLock` classes + extend `TestBuildIncrementalExtractSql`/`TestPipeline` | existing `TestPipeline` (conflict_columns/extract_limit guard tests) and existing watermark envelope round-trip tests in the same file |
| `tests/test_parity.py` | test | — | **no new registration needed** — no new accessor method is added (all 4 features are `Pipeline` fields); existing `ACCESSOR_PAIRS` already covers `(ETLAccessor, AsyncETLAccessor)` | `ACCESSOR_PAIRS` registry (already wired) |

## Pattern Assignments

### F01 — `initial_watermark` field + seed-floor fallback

**Analog for the field + construction guard:** `extract_limit` guard, `pycopg/etl.py:258-269`
(bool-before-int / positive-int shape), combined with the `_validate_incremental` requires-column
precedent.

```python
# Source: pycopg/etl.py:258-269 — the exact shape to replicate for initial_watermark's guard
if self.extract_limit is not None:
    if isinstance(self.extract_limit, bool) or not isinstance(
        self.extract_limit, int
    ):
        raise ValueError(
            "extract_limit must be a positive integer or None, got "
            f"{self.extract_limit!r}"
        )
    if self.extract_limit <= 0:
        raise ValueError(
            f"extract_limit must be a positive integer, got {self.extract_limit!r}"
        )
```
D-02's guard ("requires `incremental_column` set, else `ValueError`") mirrors the existing
`load_mode="upsert" requires conflict_columns` guard at `pycopg/etl.py:250-254`:
```python
# Source: pycopg/etl.py:250-254
if self.load_mode == "upsert" and not self.conflict_columns:
    raise ValueError(
        "load_mode='upsert' requires conflict_columns to be non-empty (D-07)"
    )
```

**Analog for the seed-floor read fallback:** the existing null-watermark early return in
`_read_watermark`, `pycopg/etl.py:1007` (sync) / `:1722` (async):
```python
# Current shape (paraphrased from etl.py _read_watermark, sync :1007 / async :1722):
# ... SELECT watermark FROM pipeline_runs WHERE pipeline_name=%s AND status='success' ...
if row is None or row["watermark"] is None:
    return None
return _decode_watermark(row["watermark"])
```
**Resolution of RESEARCH.md's Open Question 1:** apply the fallback at the **call site** in
`run()` (both sync :1132 and async :1843), not inside `_read_watermark` itself — smaller diff,
`_read_watermark` stays a pure "what does the DB say" query, existing unit tests for it stay
valid unchanged. Pattern: `wm = self._read_watermark(name); if wm is None: wm = pipeline.initial_watermark`
(explicit `is None`, never falsy-check, since `0` is a valid watermark).

### F02 — `incremental_inclusive` / `incremental_lookback` + boundary SQL

**Analog:** the fields are two more entries alongside `extract_limit`/`conflict_columns` in the
`Pipeline` dataclass, guarded the same way (D-05: keyword-only, default preserves old SQL).

**Core builder pattern to extend** — `_build_incremental_extract_sql`, `pycopg/etl.py:587-600`
(read the full function body already captured above at offset 539-600 in this session):
```python
# Source: pycopg/etl.py:587-600 (current, exclusive-only) — extend the two return lines
validate_identifiers(column)
if watermark is None:
    if _is_sql_source(source):
        return source, []
    validate_identifiers(source, schema)
    return f"SELECT * FROM {schema}.{source}", []
if _is_sql_source(source):
    clean = source.rstrip().rstrip(";").rstrip()
    sql = f"SELECT * FROM ({clean}) {_PYCOPG_INC_ALIAS} WHERE {column} > %s"
    return sql, [watermark]
validate_identifiers(source, schema)
return f"SELECT * FROM {schema}.{source} WHERE {column} > %s", [watermark]
```
Extension: parametrize the literal `>` as `op = ">=" if inclusive else ">"` and substitute
`{column} {op} %s` in both the subquery-wrap and table-append branches. `validate_identifiers`
stays line-1 (already there).

**Analog for lookback arithmetic (Python-side subtraction before binding):** the existing
type-dispatch chain that already distinguishes `datetime`/`int`/`str` when *capturing* the
watermark — `pycopg/etl.py:1315-1347` (sync) and the mirrored `:2011-2043` (async):
```python
# Source: pycopg/etl.py (sync max-capture dispatch, ~1330-1347) — the 3-way type check to reuse
elif isinstance(m, pd.Timestamp):
    raw_watermark = m.to_pydatetime()
elif isinstance(m, str):
    raw_watermark = str(m)
elif pd.api.types.is_float(m):
    raise ETLError(...)  # analogous shape for the lookback-on-str runtime guard
else:
    raw_watermark = int(m)
```
Apply the same `isinstance(floor, datetime)` / `isinstance(floor, int)` / `else: raise ETLError`
three-way dispatch to compute `read_floor = floor - pipeline.incremental_lookback` before it is
passed into `_build_incremental_extract_sql`. D-07: the RECORDED watermark keeps using the
existing unmodified max-capture block — do not thread the lookback-adjusted floor back into the
recorded value.

### F03 — composite watermark (tuple key)

**Analog for widening + normalizing `incremental_column`:** `conflict_columns` str-reject +
list→tuple normalization, `pycopg/etl.py:230-244` (already read in full above):
```python
# Source: pycopg/etl.py:230-244 — the exact precedent for D-09's incremental_column widening
if isinstance(self.conflict_columns, str):  # type: ignore[unreachable]
    raise ValueError(
        "conflict_columns must be a sequence of column names, not a "
        f"single string; got {self.conflict_columns!r} (did you mean "
        f"[{self.conflict_columns!r}]?)"
    )
if not isinstance(self.conflict_columns, tuple):
    object.__setattr__(  # type: ignore[unreachable]
        self, "conflict_columns", tuple(self.conflict_columns)
    )
```
Caveat (per RESEARCH.md Pattern 2): `incremental_column` differs from `conflict_columns` in that
a bare `str` for `incremental_column` must be KEPT as a scalar (single-column, back-compat) —
it is a sequence like `["day","seq"]` that becomes the composite tuple. So the widening guard is
"if it's a `str`, leave as-is (scalar path); if it's a non-str `Sequence`, normalize to
`tuple(...)`" — the inverse polarity of the `conflict_columns` str-reject, not a literal copy.

**Analog for the tuple-compare SQL:** extend `_build_incremental_extract_sql` (:539-600) — same
function as F02, composed together:
```python
# Extension sketch grounded in the exact current builder shape (etl.py:587-600):
is_composite = isinstance(column, tuple)
if is_composite:
    validate_identifiers(*column)
else:
    validate_identifiers(column)
op = ">=" if inclusive else ">"
...
if is_composite:
    cols_sql = "(" + ", ".join(column) + ")"
    placeholders = "(" + ", ".join(["%s"] * len(column)) + ")"
    clause = f"WHERE {cols_sql} {op} {placeholders}"
    params = list(watermark)  # ordered tuple of scalars
else:
    clause = f"WHERE {column} {op} %s"
    params = [watermark]
```

**Analog for the envelope codec's new tag:** `_decode_watermark`'s existing tag-dispatch chain,
`pycopg/etl.py:676-688`:
```python
# Source: pycopg/etl.py:676-688 (current) — add one more `if tag == ...` branch
tag = envelope["type"]
value = envelope["value"]
if tag == "datetime":
    return datetime.fromisoformat(value)
if tag == "int":
    return int(value)
if tag == "str":
    return str(value)
# NEW (D-11): if tag == "composite": return tuple(_decode_watermark(v) for v in envelope["values"])
raise ETLError(f"Unknown watermark type tag {tag!r} ...")
```
And `_encode_watermark`'s existing bool-before-int guard (`pycopg/etl.py:638-653`) must be reused
**per-element** for composite values — never a bulk `all(isinstance(...))` check (Pitfall 2):
```python
# Source: pycopg/etl.py:638-653 — reuse THIS exact function per composite element, don't
# reimplement a parallel bulk-type check
if isinstance(value, bool):
    raise ETLError(...)
if isinstance(value, datetime):
    return {"type": "datetime", "value": value.isoformat()}
if isinstance(value, int):
    return {"type": "int", "value": value}
if isinstance(value, str):
    return {"type": "str", "value": value}
raise ETLError(...)
```

**Analog for the composite max-ROW capture (not per-column max):** the existing scalar max-capture
block, `pycopg/etl.py:1315-1347` (sync), `:2011-2043` (async) — same block as F02's lookback
analog, extended with a `pd.isna()`-per-element guard (Pitfall 4) then
`df.sort_values(list(cols)).iloc[-1][list(cols)]` instead of `df[col].max()`.

### F04 — advisory-lock concurrency (`concurrency` field)

**Analog for the field:** same `Pipeline` dataclass, keyword-only Literal field — pattern already
used for `load_mode: Literal[...]` (see `_validate_load_mode` reference at :246 and the
`_VALID_LOAD_MODES`-style validation mentioned in RESEARCH.md Standard Stack).

**Analog for the `'skipped'` transient RunResult (writes no `pipeline_runs` row):** the existing
`dry_run` early fork inside `run()`, `pycopg/etl.py:1211` (sync) / `:1907` (async):
```python
# Source: pycopg/etl.py run(), dry_run fork (~:1211-1284 sync / :1907-1980 async) — the exact
# "transient status, no DB row written" precedent for 'skipped' (D-13)
if dry_run:
    ...  # extract + transform only, no load, no pipeline_runs INSERT/UPDATE
    return RunResult(
        run_id=None,
        pipeline_name=pipeline.name,
        status="dry_run",
        ...
        watermark_recorded=dry_raw_watermark,
    )
```
D-13's `'skipped'` result follows the identical shape: `RunResult(run_id=None, status="skipped",
rows_extracted=0, rows_loaded=0, ...)`, returned BEFORE any DB round-trip beyond the lock attempt
itself, no `pipeline_runs` row.

**Analog for the dedicated-connection lifecycle:** RESEARCH.md/CONTEXT.md both point to the
existing "dedicated autocommit run-log connection" seam from v0.5.0 ETL-09 (the connection used
by `_end_run`/`_insert_run` for run-log writes, independent of the load transaction) as the
precedent for opening a *third* dedicated connection for the advisory lock — same
`self._db.connect(autocommit=True)` idiom already used elsewhere in `etl.py` for run-log I/O
(see `_read_watermark`'s `with self._db.connect(autocommit=True) as conn:` shape).

**New `queries.py` constants** — follow the `ETL_<VERB>_<NOUN>` naming convention of
`ETL_GET_LAST_WATERMARK` (:383-391) / `ETL_UPDATE_RUN_WATERMARK` (:393-403):
```python
# Analog naming/shape source: pycopg/queries.py:383-403
ETL_GET_LAST_WATERMARK = """
    SELECT watermark
    FROM pipeline_runs
    WHERE pipeline_name = %s
      AND status = 'success'
      AND watermark IS NOT NULL
    ORDER BY started_at DESC
    LIMIT 1
"""
# New (D-15), same file, same style, single bound %s param:
ETL_ADVISORY_LOCK = "SELECT pg_advisory_lock(hashtextextended(%s, 0))"
ETL_ADVISORY_TRY_LOCK = "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))"
ETL_ADVISORY_UNLOCK = "SELECT pg_advisory_unlock(hashtextextended(%s, 0))"
```
No change needed to `ETL_INIT_PIPELINE_RUNS`'s `status` CHECK constraint
(`pycopg/queries.py:335`, `CHECK (status IN ('running','success','failed'))`) — `'skipped'` is
never persisted, exactly like `'dry_run'` is never persisted today.

## Shared Patterns

### Sync/async full duplication (CRITICAL — no shared helper exists)
**Source:** `ETLAccessor` (`pycopg/etl.py:758`) / `AsyncETLAccessor` (`pycopg/etl.py:1484`)
**Apply to:** every one of the 5 extended functions/methods (`_read_watermark`, `_do_extract`,
`run`, `_end_run`) — each exists twice, ~280 lines apart, with **zero shared code**. `run()` sync
is :1132-~1480; `run()` async is :1843-~2170. Grep for `def run(` after any edit to confirm both
occurrences were touched identically (RESEARCH.md Pitfall 6 — `test_accessor_parity` will NOT
catch a missed async edit since both methods already exist).
```python
# Confirm both occurrences edited:
# grep -n "def run(" pycopg/etl.py   ->  must show 2 hits, both changed
```

### Builder-pur / injection safety
**Source:** `_build_incremental_extract_sql` (`pycopg/etl.py:587`, `validate_identifiers(column)`
as line 1 of logic) and `_build_upsert_sql`-style helper (`pycopg/etl.py:524`,
`validate_identifiers(*conflict_columns)`)
**Apply to:** the composite tuple-compare builder (`validate_identifiers(*column)` for the tuple
case) and the advisory-lock SQL (pipeline name is bound `%s`, never interpolated — matches every
existing `ETL_*` constant's parameter style).

### Frozen-dataclass field + `__post_init__` guard
**Source:** `extract_limit` (`pycopg/etl.py:258-269`), `conflict_columns` (`:230-244`),
`load_mode`/`conflict_columns` cross-guard (`:250-254`)
**Apply to:** all 4 new/widened `Pipeline` fields (`initial_watermark`, `incremental_inclusive`,
`incremental_lookback`, `concurrency`, widened `incremental_column`) — same frozen-dataclass
`object.__setattr__` mutation idiom when normalization is needed.

### Transient RunResult status (no `pipeline_runs` row)
**Source:** `dry_run` fork in `run()` (`pycopg/etl.py:1211` sync / `:1907` async), `'dry_run'`
documented at `:285`
**Apply to:** the new `'skipped'` status (D-13) — same early-return-before-any-DB-write shape.

## No Analog Found

None — every new surface in this phase has a direct, already-shipped sibling pattern in the same
file (`pycopg/etl.py`) or the same constants file (`pycopg/queries.py`). This is expected: Phase
49 is declared out-of-scope for new modules/files (CONTEXT.md "NOT in scope: any new load mode
... any breaking change") and RESEARCH.md's Recommended Project Structure confirms zero new
files.

## Metadata

**Analog search scope:** `pycopg/etl.py` (2179 lines, read via targeted offset/limit reads at
the cited line ranges), `pycopg/queries.py` (lines 300-403 read), confirmed via `grep -n` for
all relevant `class`/`def` anchors (`Pipeline`, `RunResult`, `_build_incremental_extract_sql`,
`_encode_watermark`, `_decode_watermark`, `_read_watermark`, `_do_extract`, `run`, `_end_run`,
`ETLAccessor`, `AsyncETLAccessor`) to re-verify line numbers against the live file (confirmed to
match RESEARCH.md's citations within a few lines, consistent with RESEARCH.md's Assumption A1).
**Files scanned:** 2 source files (`etl.py`, `queries.py`) + prior reads of `tests/test_etl.py`,
`tests/test_parity.py` reported in RESEARCH.md (not re-read here to avoid duplicate context cost
— RESEARCH.md already confirmed their structure this same session).
**Pattern extraction date:** 2026-07-03
