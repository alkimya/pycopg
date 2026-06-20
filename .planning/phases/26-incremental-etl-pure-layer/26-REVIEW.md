---
phase: 26-incremental-etl-pure-layer
reviewed: 2026-06-20T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - pycopg/etl.py
  - tests/test_etl.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 26: Code Review Report

**Reviewed:** 2026-06-20
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 26 adds the pure (DB-free) incremental-ETL foundation to `pycopg/etl.py`:
the `Pipeline.incremental_column` field, `_validate_incremental`,
`_build_incremental_extract_sql`, and the `_encode_watermark` /
`_decode_watermark` envelope pair, with a co-located test suite. The full ETL
test suite passes (92 passed).

The headline security invariants for this layer hold:

- **SQL injection surface is clean.** In `_build_incremental_extract_sql` the
  watermark is *always* emitted as a single `%s` placeholder and appended to the
  params list — never f-string interpolated (verified on every branch). The
  `column` identifier is validated via `validate_identifiers` on every code path
  (it is the first statement, before any branch). `source`/`schema` are validated
  before interpolation on the table-source paths. The raw SQL-string `source`
  interpolation is pre-existing, user-supplied SQL behaviour identical to the
  Phase 18 `run()` extract path — not a new injection surface.
- **The bool-before-int guard in `_encode_watermark` is correct** and matches the
  existing `extract_limit` guard. `bool` is rejected before the `int` branch.
- **Validation ordering is correct.** `__post_init__` runs `_validate_load_mode`
  before `_validate_incremental`, and the forbidden-combo (intent) error is
  reported before the identifier syntax check — both are covered by tests.

No Critical issues found. The defects below are an asymmetry between
`_encode_watermark` (strict allowlist) and `_decode_watermark` (no validation),
plus two test-coverage gaps. They are correctness/robustness Warnings, not
blockers, because the decode side is fed only by its own encode side in normal
operation.

## Warnings

### WR-01: `_decode_watermark` silently mis-types any non-`datetime`/`int` envelope

**File:** `pycopg/etl.py:649-655`
**Issue:** `_decode_watermark` reads the `type` tag but only special-cases
`"datetime"` and `"int"`; *everything else* falls through to `return str(value)`.
The encode side enforces a strict `{datetime, int, str}` allowlist and rejects
`float`/`Decimal`/`bool` with `ETLError`, but the decode side has no matching
guard. A corrupted, hand-edited, or future-version JSONB envelope such as
`{"type": "float", "value": 3.14}` is silently coerced to the string `"3.14"`
rather than raising — a round-trip asymmetry that can produce a watermark of the
wrong Python type and break the monotonic-comparison contract downstream
(Phase 27 write-site). Verified:

```python
_decode_watermark({"type": "float", "value": 3.14})  # -> "3.14" (str), no error
```

**Fix:** Make decode explicit and reject unknown tags symmetrically with encode:

```python
tag = envelope["type"]
value = envelope["value"]
if tag == "datetime":
    return datetime.fromisoformat(value)
if tag == "int":
    return int(value)
if tag == "str":
    return str(value)
raise ETLError(
    f"unsupported watermark envelope type {tag!r}; "
    f"supported types are {_WATERMARK_SUPPORTED}"
)
```

### WR-02: `_decode_watermark` raises bare `KeyError` on a malformed envelope

**File:** `pycopg/etl.py:649-650`
**Issue:** `envelope["type"]` and `envelope["value"]` use bare subscripting, so a
malformed envelope (missing `type` or `value` key — e.g. a `NULL`/`{}` JSONB read,
or a schema-version mismatch) raises an opaque `KeyError('type')` instead of a
domain `ETLError`. This leaks an implementation detail and is inconsistent with
the encode side, which raises `ETLError` for every bad input. Verified:

```python
_decode_watermark({})  # -> KeyError: 'type'
```

**Fix:** Validate envelope shape and raise `ETLError` (folds naturally into the
WR-01 fix):

```python
if not isinstance(envelope, dict) or "type" not in envelope or "value" not in envelope:
    raise ETLError(f"malformed watermark envelope: {envelope!r}")
```

### WR-03: SQL-string source with content after a trailing `;` produces invalid subquery SQL

**File:** `pycopg/etl.py:569-570`
**Issue:** The `clean = source.rstrip().rstrip(";").rstrip()` hygiene only strips a
trailing semicolon at the *very end* of the string. A SQL-string source whose
semicolon is followed by anything — most realistically a trailing line comment —
leaves an embedded `;` inside the wrapped subquery, producing a guaranteed
PostgreSQL syntax error at extract time. Verified:

```python
_build_incremental_extract_sql("SELECT 1; -- x", "id", "public", 5)
# -> 'SELECT * FROM (SELECT 1; -- x) _pycopg_inc WHERE id > %s'  (invalid)
```

The docstring (D-08) explicitly disclaims a SQL parser, so a heuristic is
accepted; however the current heuristic silently emits broken SQL rather than
failing loudly. This is not a security issue (the watermark is still
parameterized) but it is a correctness footgun for a documented-supported input
shape (SQL-string sources). **Fix:** Either document that trailing-comment /
multi-statement sources are unsupported and reject a `source` containing an
interior `;` (raise `ETLError`), or strip only a single trailing `;` and
explicitly reject the rest:

```python
clean = source.rstrip()
if clean.endswith(";"):
    clean = clean[:-1].rstrip()
if ";" in clean:
    raise ETLError(
        "incremental SQL-string source must be a single statement with no "
        f"interior ';' (got {source!r})"
    )
```

## Info

### IN-01: No test for naive-`datetime` watermark round-trip

**File:** `tests/test_etl.py:584-650` (TestEncodeDecodeWatermark)
**Issue:** Every datetime test uses a tz-*aware* datetime. `_encode_watermark`
uses `isoformat()` with no UTC normalization (D-02), so a naive datetime
round-trips as naive — verified manually to work — but this is the exact
boundary the "no normalization" decision protects, and it is untested. A future
refactor that adds normalization would silently break naive watermarks with no
failing test.
**Fix:** Add a round-trip assertion for a naive datetime, asserting
`decoded.tzinfo is None` and equality.

### IN-02: No test for the `_decode_watermark` unknown-tag / malformed-envelope paths

**File:** `tests/test_etl.py:584-650`
**Issue:** Decode is only exercised through encode-produced envelopes and two
hand-built valid dicts. The unknown-tag fall-through (WR-01) and the
missing-key path (WR-02) are completely uncovered, which is why the silent
mis-typing went unnoticed. Once WR-01/WR-02 are fixed, add tests asserting
`ETLError` for `{"type": "float", ...}` and for `{}`.
**Fix:** Add `pytest.raises(ETLError)` cases for an unknown tag and an empty
envelope.

### IN-03: Duplicated `ETLError` raise body in `_encode_watermark`

**File:** `pycopg/etl.py:612-626`
**Issue:** The unsupported-type `ETLError(...)` message is constructed
identically in the `bool` early-reject branch and in the final fall-through
branch (same f-string, same `_WATERMARK_SUPPORTED`). Minor duplication; a small
local helper or restructuring (check `bool` then fall through to a single raise)
would remove the copy. Not a correctness issue — the two messages are byte
-identical today, but they can drift independently.
**Fix:** Extract a single `raise ETLError(...)` reached by both the `bool` branch
and the final fall-through, e.g. by replacing the early `bool` raise with `pass`
into the shared tail, or factoring a `_unsupported_watermark(value)` helper.

---

## Narrative Findings (AI reviewer)

All findings above are narrative (direct adversarial code review). No
`<structural_findings>` block was provided for this phase.

Items explicitly checked and found **clean** (no finding):

- Watermark never interpolated — `%s` param on every branch of
  `_build_incremental_extract_sql`. (BLOCKER-class check: passed.)
- `column` validated on every path (first statement). `source`/`schema`
  validated before interpolation on both table-source paths (None and
  watermarked). (passed)
- `bool`-before-`int` guard in `_encode_watermark`. (passed)
- `__post_init__` ordering: `_validate_load_mode` → `_validate_incremental` →
  upsert/`conflict_columns` check; forbidden-combo before identifier check.
  Tested by `test_garbage_load_mode_reported_before_incremental` and
  `test_combo_checked_before_identifier`. (passed)
- Exclusive `>` boundary on all filtered paths; `watermark is None` returns
  unfiltered SELECT with `[]` params. (passed)
- aware-datetime / int / str round-trips are lossless (offset + microseconds
  preserved). (passed)

---

_Reviewed: 2026-06-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
