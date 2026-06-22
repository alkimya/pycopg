---
phase: 30-chunk-management-partitioning
reviewed: 2026-06-22T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - pycopg/exceptions.py
  - pycopg/queries.py
  - pycopg/timescale.py
  - tests/test_timescale.py
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 30: Code Review Report

**Reviewed:** 2026-06-22
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 30 adds `TimescaleError`, the `TSDB_SHOW_CHUNKS` / `TSDB_DROP_CHUNKS` SQL
constants, and four accessor methods (`show_chunks`, `drop_chunks`,
`add_dimension`, `add_reorder_policy`) on both sync and async accessors, plus
extensive tests.

The high-risk areas called out for scrutiny are largely **sound**:

- **SQL injection surface is closed.** Every interpolated identifier
  (`{schema}`, `{table}`, `{column}`, `index_name`) is run through
  `validate_identifier(s)` before interpolation, and the `_IDENTIFIER_PATTERN`
  rejects quotes/whitespace/metacharacters. Runtime bound values
  (`older_than`/`newer_than`) are passed as `%s` / `%s::interval` params, never
  interpolated. The `%%I.%%I` escaping in `TSDB_SHOW_CHUNKS` is correct (single
  `%` is consumed by psycopg, yielding literal `format('%I.%I', ...)`).
- **The both-None `ValueError` guard in `drop_chunks` fires first**, before the
  extension check and before any DB round-trip, in both sync and async. Verified
  by `test_drop_chunks_both_none_raises_no_extension_check`.
- **`add_dimension` mutual-exclusivity `ValueError`s are construction-time**,
  before `await`/DB in both variants.
- **Async parity** correctly `await`s both `has_extension` and `execute` in all
  four methods.

No BLOCKER-class defects (injection, data loss, crash) were proven. The findings
below are correctness/robustness concerns (WARNING) and quality items (INFO).
The most material is WR-01: the `add_dimension` exception net is far broader than
its docstring claims, which can mask unrelated failures and mislabel them.

## Warnings

### WR-01: `add_dimension` wraps *all* exceptions as `TimescaleError`, contradicting its own docstring

**File:** `pycopg/timescale.py:584-590` (sync), `pycopg/timescale.py:1142-1148` (async)
**Issue:** The `try/except Exception` net catches **every** exception raised by
`self._db.execute(sql)` and rewraps it as `TimescaleError`. The inline comment
asserts this is "Only reachable when `if_not_exists=False`; when True, TSDB emits
a NOTICE and returns normally." That is incorrect: the wrap is unconditional and
fires regardless of `if_not_exists`. Real failures that have nothing to do with a
duplicate dimension — e.g. table does not exist, table is not a hypertable,
insufficient privilege, connection drop (`OperationalError`), or a
`KeyboardInterrupt`/`asyncio.CancelledError` (both subclasses of `Exception`? —
`CancelledError` is `BaseException` in 3.8+, so that one escapes, but
`TimeoutError` and `OperationalError` do not) — all get flattened into a generic
`TimescaleError("add_dimension failed ...")`. This loses the original SQLSTATE and
error class that callers (and the existing `ExtensionNotAvailable` discipline used
everywhere else in this module) rely on for control flow.

It also diverges from the rest of the module: no other method (`create_hypertable`,
`add_compression_policy`, `add_retention_policy`, `add_reorder_policy`) wraps DB
errors at all — they let the native psycopg error propagate. `add_dimension` is the
lone exception, which is a parity/consistency hazard.

**Fix:** Narrow the catch to the actual DB error base class and let everything else
propagate, so only genuine database failures are rewrapped:
```python
from psycopg import DatabaseError  # module-level import

try:
    self._db.execute(sql)
except DatabaseError as exc:
    raise TimescaleError(
        f"add_dimension failed for column '{column}' on "
        f"'{schema}.{table}': {exc}"
    ) from exc
```
This still satisfies `test_add_dimension_db_error_reraises_as_timescale_error`
(which raises `psycopg.DatabaseError`) and the live duplicate-dimension test, while
no longer swallowing `ValueError`, cancellation, or non-DB programming errors.

### WR-02: `add_dimension` swallows the legitimate `if_not_exists=True` path's NOTICE-but-still-errors case, masking misuse

**File:** `pycopg/timescale.py:577-590` (sync), `pycopg/timescale.py:1138-1148` (async)
**Issue:** Because the wrap is unconditional (see WR-01), when `if_not_exists=True`
and the call legitimately fails for a *non-duplicate* reason (e.g. the table is not
a hypertable, or the column does not exist), the user receives
`TimescaleError("add_dimension failed ...")` with no way to distinguish a benign
duplicate from a genuine schema error. The docstring promises duplicates are
"silently ignored" when `if_not_exists=True`, but any other error is now also
homogenized. A caller who wrote `try: add_dimension(...); except TimescaleError:
pass` to tolerate duplicates would also silently swallow "table does not exist".
**Fix:** Same as WR-01 — narrowing to `DatabaseError` does not fully fix this, but
combined with documenting that *any* DB-level failure (not only duplicates) surfaces
as `TimescaleError`, the contract becomes honest. Update the docstring `Raises`
section to state `TimescaleError` wraps "any database-level failure of
`add_dimension`, including (but not limited to) the duplicate-dimension error when
`if_not_exists=False`," rather than implying it is duplicate-specific.

### WR-03: `int(number_partitions)` accepts `bool` and float-like silently; `number_partitions <= 0` is not guarded

**File:** `pycopg/timescale.py:572` (sync), `pycopg/timescale.py:1133` (async)
**Issue:** `by_hash('{column}', {int(number_partitions)})` coerces with `int()`.
`int(True)` is `1` and `int(3.9)` is `3`, so a caller passing `True` or `3.9` gets a
silently-wrong partition count rather than an error. More importantly, a non-positive
value (`0` or negative) passes the `is None` guard and is interpolated verbatim into
`by_hash('col', 0)`, which the DB will reject with a TimescaleError far from the call
site — there is no early, clear validation. The type hint is `int | None`, but nothing
enforces a positive integer.
**Fix:** Validate explicitly before building SQL:
```python
if partition_type == "hash":
    if number_partitions is None:
        raise ValueError("partition_type='hash' requires number_partitions to be set.")
    if isinstance(number_partitions, bool) or not isinstance(number_partitions, int):
        raise ValueError("number_partitions must be a positive int.")
    if number_partitions < 1:
        raise ValueError("number_partitions must be >= 1.")
```

### WR-04: `older_than` / `newer_than` typed as `str | datetime` but `date`, `int`, and other non-str types fall through to the bare-`%s` branch unchecked

**File:** `pycopg/timescale.py:51-68` (`_build_chunk_bound_fragments`)
**Issue:** The builder branches on `isinstance(x, str)` and treats *everything else*
(the `else`) as a datetime to bind as bare `%s`. A caller who passes an `int`,
`date`, `Decimal`, or any other object reaches the `else` branch and is bound as a
plain value; psycopg may coerce it in surprising ways or the DB may reject it with an
opaque error. The contract is "str = interval literal, datetime = timestamptz", but
nothing rejects a third type. This is a latent footgun given `drop_chunks` is
DESTRUCTIVE — e.g. passing a naive `int` epoch could match an unexpected chunk set.
**Fix:** Make the non-str branch explicit and reject unsupported types:
```python
elif isinstance(older_than, datetime):
    older_frag = ", older_than => %s"
    params.append(older_than)
else:
    raise TypeError(
        f"older_than must be str (interval) or datetime, got {type(older_than).__name__}"
    )
```
Apply symmetrically to `newer_than`. (Note: `datetime` is a subclass of `date`, so an
`isinstance(x, datetime)` check correctly excludes bare `date`.)

## Info

### IN-01: Module docstring references the removed alias layer

**File:** `pycopg/timescale.py:9-10`
**Issue:** The module docstring still says the flat `db.*` names "remain as thin
deprecated aliases (see :mod:`pycopg.aliases`) until v0.7.0." Per project memory the
alias layer was deleted in Phase 25 and `pycopg/aliases` no longer exists; the
`:mod:` cross-reference is now dangling and will break a `sphinx -W` doc build if that
file is ever included. This is the carry-forward "accessor docstring `:mod:` drift"
noted across phases.
**Fix:** Remove or rewrite the second paragraph of the module docstring to drop the
`pycopg.aliases` reference.

### IN-02: `TSDB_DROP_CHUNKS` discards the `drop_chunks()` SRF result

**File:** `pycopg/queries.py:271-273`, used at `pycopg/timescale.py:472-478`
**Issue:** `SELECT drop_chunks(...)` returns the set of dropped chunk names, but the
code ignores the result and instead returns the pre-captured list. This is the
documented capture-before-drop design (the regclass JOIN cannot run post-drop), so it
is intentional — but worth noting that the returned list is the *predicted* set, not a
*confirmed* set. If the DB drops a different set than predicted (e.g. a concurrent
insert created a new chunk between capture and drop), the returned list silently
diverges from reality. Acceptable for v1; flag for awareness.
**Fix:** None required. Optionally document in the `Returns` section that the list is
the captured preview, not a post-drop confirmation.

### IN-03: `chunk_seq` test helper is fragile to schema/name changes

**File:** `tests/test_timescale.py:452-456, 573-577`
**Issue:** `int(parts[-2])` assumes the chunk name always ends `..._N_chunk`. If
TimescaleDB ever changes internal chunk naming, the ordering tests fail with an opaque
`ValueError` rather than a clear assertion message. Duplicated in two places.
**Fix:** Extract to a single module-level helper with a guard/clear error, or use a
regex `re.search(r"_(\d+)_chunk$", name)` and assert the match exists.

### IN-04: Stale/aspirational comment in `add_dimension` about reachability

**File:** `pycopg/timescale.py:580-583`
**Issue:** The comment "Only reachable when `if_not_exists=False`" is factually wrong
(see WR-01) and will mislead future maintainers into thinking the wrap is duplicate-
specific.
**Fix:** Correct the comment to describe the actual behavior once WR-01 is addressed
(wraps any `DatabaseError` from the call).

---

_Reviewed: 2026-06-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
