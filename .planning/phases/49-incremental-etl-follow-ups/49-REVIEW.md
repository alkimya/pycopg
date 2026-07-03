---
phase: 49-incremental-etl-follow-ups
reviewed: 2026-07-03T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - pycopg/etl.py
  - pycopg/queries.py
  - tests/test_etl.py
  - tests/test_etl_accessor.py
  - docs/etl.md
findings:
  critical: 0
  warning: 3
  info: 1
  total: 4
status: issues_found
---

# Phase 49: Code Review Report

**Reviewed:** 2026-07-03
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the ETL incremental follow-ups (ETL-INC-F01..F04): `initial_watermark`
seed-floor, `incremental_inclusive`/`incremental_lookback` boundary config,
composite multi-column watermark (row-value compare + `"composite"` envelope +
greatest-ROW capture), and `concurrency="wait"/"skip"` advisory-lock.

Overall the implementation is strong. The **SQL-injection surface is clean**:
every new/changed builder (`_build_incremental_extract_sql` composite branch,
`_encode_composite_watermark`, the advisory-lock constants) validates
identifiers via `validate_identifiers` and binds all values as `%s`/named
params. The advisory-lock key is correctly derived server-side via
`hashtextextended(%s, 0)` with the pipeline name **bound** (never Python
`hash()`, never interpolated) — see `queries.py:405-412`.
**Sync/async parity is intact** across all four forks: seed fallback, lookback
guard, composite capture, and the lock wrap are byte-identical between
`ETLAccessor` (etl.py:1593-2011) and `AsyncETLAccessor` (etl.py:2372-2767).
**Composite correctness is right and well-tested**: `_capture_watermark`
(etl.py:1084-1130) takes the sorted greatest ROW (not per-column maxes), reads
each element from its own native-dtype column to avoid cross-column dtype
promotion, and voids the whole tuple on any NaN element
(`tests/test_etl.py:595-619` prove the (2,1)-not-(2,99) pitfall). The advisory
lock is session-scoped on a dedicated connection, released in `finally` with
connection-close auto-release, and `"skip"`-when-held writes no `pipeline_runs`
row (verified before `init()`/`_start_run()` at etl.py:1636-1647).

Findings are one edge-case correctness fragility in the positional→named bind
reconciliation and two stale-documentation defects that contradict the shipped
behavior. No blockers.

## Warnings

### WR-01: `%s` literal in a SQL source collides with watermark placeholder substitution

**File:** `pycopg/etl.py:1133-1150` (`_reconcile_watermark_binds`)
**Issue:** The helper maps the builder's positional `%s` placeholders to named
binds via `sql.replace("%s", ":wm", 1)` (single) / a per-index
`sql.replace("%s", f":wm{i}", 1)` loop (composite). The replace targets the
*first* `%s` in the whole string — but for a SQL-string source,
`_build_incremental_extract_sql` embeds the user's raw source verbatim
(`SELECT * FROM ({clean}) _pycopg_inc WHERE {lhs} {op} {placeholders}`,
etl.py:836). If the source SQL contains a literal `%s` (e.g. a `LIKE '%s%'`
predicate), the substitution mis-targets that literal instead of the watermark
placeholder, corrupting the query: the `:wm` bind lands inside the string
literal and a stray unbound `%s` remains → SQLAlchemy raises (or, worst case,
filters on the wrong column). The single-column path had this latent since
Phase 27; the composite loop (new in 49-04) amplifies it to N placeholders.
Because incremental requires `upsert`, a mis-filtered read is not silently
duplicated, but the run either errors or reads the wrong window.
**Fix:** Do not string-search the whole SQL. Have the builder emit a
distinctive sentinel token (or return the placeholder positions/count directly)
and substitute only those, e.g. build with `:wm{i}` named binds in the builder
itself rather than emitting `%s` and re-scanning. Minimal mitigation: substitute
from the right / anchor on the `WHERE {lhs} {op} (...)` tail the builder appended
rather than a bare `"%s"` search over embedded user SQL:
```python
# builder emits named binds directly for the incremental path:
placeholders = "(" + ", ".join(f":wm{i}" for i in range(len(cols))) + ")"
# ... and returns params as {f"wm{i}": v}, dropping _reconcile_watermark_binds
```

### WR-02: `Pipeline.initial_watermark` docstring contradicts the shipped composite validation

**File:** `pycopg/etl.py:200-206`
**Issue:** The docstring states the composite (`Sequence`) `initial_watermark`
form "is accepted by the type but its per-element/length-match validation is
NOT implemented here; it lands in a later plan (D-04) once `incremental_column`
is widened to a tuple." That is stale from the 49-01 plan: `__post_init__`
(etl.py:388-409) now fully implements composite `initial_watermark` — length
match against `incremental_column`, per-element `_encode_watermark` allowlist,
and tuple normalization (and `tests/test_etl.py:437-449` assert it). The
docstring misleads maintainers about the actual validation contract.
**Fix:** Replace the "NOT implemented here" paragraph with the shipped
behavior: composite seeds must be a same-length sequence of allowlisted scalars,
validated per element and normalized to a tuple at construction.

### WR-03: `docs/etl.md` note claims `initial_watermark` is unimplemented ("planned for v0.8.0")

**File:** `docs/etl.md:412-416`
**Issue:** The trailing `.. note::` block reads: "An `initial_watermark` option
to bound the first full-load scan is planned for v0.8.0 (ETL-INC-F01). Until
then, the first incremental run always reads the entire source table." This
directly contradicts the shipped feature — which the *same document* fully
documents 130 lines earlier (docs/etl.md:268-272, 295) — and misinforms users
that seeding is unavailable. Left in place it will read as a correctness bug
report against working code.
**Fix:** Delete the stale note block (lines 412-416); the "Boundary
configuration and composite keys (v1.1.0)" section already documents
`initial_watermark` correctly.

## Info

### IN-01: Integer watermark column containing NULLs fails the run via float-dtype rejection

**File:** `pycopg/etl.py:1060-1081` (`_coerce_watermark_scalar`)
**Issue:** pandas promotes an integer column with any NULL to `float64` on
extract. `_coerce_watermark_scalar` then hits `pd.api.types.is_float(m)` and
raises `ETLError("... has float dtype; float watermarks are not supported")`,
failing the entire run even though the values are integral. The composite path
(etl.py:1123-1129) inherits this per element. This is pre-existing (Phase 27),
documented as "Float columns are rejected at runtime" (docs/etl.md:255-256), and
a NULL watermark violates the monotonic-column contract — so it is a footgun,
not a defect. Flagged only because the composite widening increases the number
of columns that can trip it.
**Fix (optional):** If a nullable-int watermark is a supported use case,
narrow the guard to reject only non-integral floats (e.g. accept
`float.is_integer()` values, coercing to `int`) instead of blanket float
rejection; otherwise document the NULL-promotion pitfall explicitly.

---

_Reviewed: 2026-07-03_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
