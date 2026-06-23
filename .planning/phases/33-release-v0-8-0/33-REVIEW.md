---
phase: 33-release-v0-8-0
reviewed: 2026-06-23T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - docs/timescaledb.md
  - docs/api-reference.md
  - docs/conf.py
  - README.md
  - CHANGELOG.md
  - pyproject.toml
findings:
  critical: 0
  warning: 4
  info: 1
  total: 5
status: issues_found
---

# Phase 33: Code Review Report

**Reviewed:** 2026-06-23
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Release-only phase: version metadata, changelog, and TimescaleDB documentation.
No production Python was changed (by design). I cross-checked every documented
method signature against the source of truth (`pycopg/timescale.py`).

Verdict: **the user-facing docs are accurate, but `CHANGELOG.md` is not.** The
`[0.8.0]` changelog narrative documents several method signatures with parameter
names and defaults that do not exist in the shipped code. Crucially, the changelog
contradicts both `docs/api-reference.md` and `docs/timescaledb.md` (which are
correct) on the same methods — so this is provably wrong, not merely a stylistic
choice. The two query-helper signatures in the changelog are wrong enough that a
user copying them would write code that raises `TypeError` (missing the required
`aggregates` argument, plus invented `extra_columns`/`params` kwargs).

Good news verified:
- Version `0.8.0` is consistent across `pyproject.toml:7` and `docs/conf.py:17`.
- `docs/api-reference.md` TimescaleDB table (lines 188-202) matches the real
  signatures exactly, including defaults and the required `aggregates` arg.
- README "15 methods" claim and the api-reference 15-row table both match the 15
  public methods in `timescale.py`.
- `docs/timescaledb.md` example calls all use valid parameter names
  (`materialized_only`, `window_start`/`window_end`, `aggregates`, `into`, etc.).
- The Community/TSL license note (timescaledb.md:293-298) correctly scopes the
  gated methods (gapfill + the three cagg methods + add_reorder_policy).
- drop_chunks both-`None`-raises-`ValueError` and dry_run docs match the code.

## Warnings

### WR-01: CHANGELOG documents wrong signatures for the two query-helper methods (contradicts api-reference, would TypeError if copied)

**File:** `CHANGELOG.md:47-53`
**Issue:** The changelog narrative for `time_bucket` and `time_bucket_gapfill`
invents parameters that do not exist and omits the required positional argument:

Changelog claims:
```
time_bucket(table, time_column, bucket_width, into="rows", extra_columns=None, where=None, params=None)
time_bucket_gapfill(table, time_column, bucket_width, start, finish, into="rows", extra_columns=None, where=None, params=None)
```

Actual (`pycopg/timescale.py:1172` and `:1235`):
```python
time_bucket(table, time_column, bucket_width, aggregates, where=None, schema="public", into="df")
time_bucket_gapfill(table, time_column, bucket_width, start, finish, aggregates, where=None, schema="public", into="df")
```

Defects: (a) `aggregates` is a **required** positional arg — omitted entirely;
(b) `extra_columns` and `params` kwargs do not exist; (c) default is `into="df"`,
not `into="rows"`. `docs/api-reference.md:201-202` and the examples in
`docs/timescaledb.md:168-192,241-249` document these correctly, so the changelog
is internally contradicted. A user copying the changelog form would hit
`TypeError: time_bucket() missing 1 required positional argument: 'aggregates'`
and `TypeError: unexpected keyword argument 'extra_columns'`.
**Fix:** Align the changelog entries with the real signatures:
```
- `db.timescale.time_bucket(table, time_column, bucket_width, aggregates,
  where=None, into="df")` — time-bucket aggregation helper; returns a
  `pandas.DataFrame` (default `into="df"`) or `list[dict]` (`into="rows"`).
- `db.timescale.time_bucket_gapfill(table, time_column, bucket_width, start,
  finish, aggregates, where=None, into="df")` — gap-filling time-bucket query;
  `start`/`finish` are required absolute bounds. Requires Community/TSL build.
```

### WR-02: CHANGELOG uses wrong parameter names for two continuous-aggregate methods

**File:** `CHANGELOG.md:32, 37`
**Issue:** Two cagg method signatures in the changelog use parameter names that
do not exist:
- Line 32: `create_continuous_aggregate(view_name, select_sql, materialized=True, with_no_data=False)` — the real kwarg is `materialized_only` (`timescale.py:917`), not `materialized`. `docs/timescaledb.md:268` correctly uses `materialized_only=True`.
- Line 37: `refresh_continuous_aggregate(view_name, start=None, finish=None)` — the real kwargs are `window_start`/`window_end` (`timescale.py:995-996`). `docs/api-reference.md:199` and `docs/timescaledb.md:276-280` correctly use `window_start`/`window_end`.

Both would raise `TypeError: unexpected keyword argument` if copied.
**Fix:**
```
- `db.timescale.create_continuous_aggregate(view_name, select_sql,
  materialized_only=True, with_no_data=False)` ...
- `db.timescale.refresh_continuous_aggregate(view_name, window_start=None,
  window_end=None)` ...
```

### WR-03: CHANGELOG shows `if_not_exists=False` as the default for three methods whose real default is `True`

**File:** `CHANGELOG.md:24, 26, 42`
**Issue:** The changelog signatures show `if_not_exists=False` for:
- `add_dimension` (line 22-24) — real default is `if_not_exists=True` (`timescale.py:744`)
- `add_reorder_policy` (line 26) — real default is `True` (`timescale.py:870`)
- `add_continuous_aggregate_policy` (line 41-42) — real default is `True` (`timescale.py:1069`)

The behavioral prose ("Raises `TimescaleError` ... when `if_not_exists=False`")
is correct, but presenting `False` as the *default* misstates the shipped API:
the default is the silently-idempotent `True`. `docs/api-reference.md:196,197,200`
correctly document `if_not_exists=True`.
**Fix:** Change the three changelog signatures to `if_not_exists=True` (the actual
default), or drop the `if_not_exists` arg from the changelog one-liners entirely
and keep only the behavioral sentence.

### WR-04: CHANGELOG omits the `partition_type` discriminator from `add_dimension`

**File:** `CHANGELOG.md:22-25`
**Issue:** The changelog signature `add_dimension(table, column,
number_partitions=None, chunk_interval=None, if_not_exists=False)` drops
`partition_type="hash"` (`timescale.py:740`), which is the parameter that selects
`by_hash` vs `by_range`. The prose mentions "space partition (`by_hash`) or time
partition (`by_range`)" but gives no way to choose between them, and a reader
cannot tell that `partition_type` is how you do it. `docs/api-reference.md:196`
and `docs/timescaledb.md:341-355` show `partition_type` correctly.
**Fix:** Include `partition_type="hash"` in the changelog signature:
`add_dimension(table, column, partition_type="hash", number_partitions=None, chunk_interval=None, if_not_exists=True)`.

## Info

### IN-01: `datetime.utcnow()` in doc examples is deprecated in Python 3.12+

**File:** `docs/timescaledb.md:234, 275, 312` (also README is clean here)
**Issue:** Example code uses `datetime.utcnow()`, which emits a
`DeprecationWarning` on Python 3.12+ (the project targets Python 3.11+). It still
runs and the surrounding API usage is correct, so this is cosmetic, but copy-paste
users on 3.12 will see a warning. Not a Sphinx-build concern (it is inside a code
fence, not executed).
**Fix:** Prefer `datetime.now(timezone.utc)` in the examples for forward
compatibility, e.g. `from datetime import datetime, timedelta, timezone` then
`now = datetime.now(timezone.utc)`.

---

_Reviewed: 2026-06-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
