---
phase: 32-query-helpers-parity-verification
reviewed: 2026-06-23T11:46:11Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - pycopg/timescale.py
  - tests/test_timescale.py
  - tests/test_parity.py
findings:
  critical: 0
  warning: 1
  info: 4
  total: 5
status: issues_found
---

# Phase 32: Code Review Report

**Reviewed:** 2026-06-23T11:46:11Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the Phase-32 additions only: the two module-level pure builders
(`_build_time_bucket_sql`, `_build_time_bucket_gapfill_sql`), the local routing
helpers (`_to_named_binds`, `_check_into`, `_VALID_INTO`), the `_run`/`time_bucket`/
`time_bucket_gapfill` methods on both `TimescaleAccessor` and
`AsyncTimescaleAccessor`, plus the new mock + live tests and the
`test_timescale_v080_surface` parity assertion.

The phase's headline contracts are all met and were independently verified:

- **SQL injection surface is clean.** Both builders call
  `validate_identifiers(table, schema, time_column)` *before* any identifier
  interpolation; `bucket_width`, `start`, and `finish` are bound as `%s` and never
  string-interpolated. `aggregates`/`where` are caller-supplied structural SQL — the
  documented, accepted trust posture (same as spatial). Not flagged as injection.
- **Gapfill double-bind is exactly right.** Params are
  `[bucket_width, start, finish, start, finish]` (5 entries) and the SQL has exactly
  5 `%s` (verified by the mock test `sql.count("%s") == 5` and by reading the
  builder). WHERE uses `>= %s` (inclusive lower) / `< %s` (exclusive upper).
- **Async `await`s are correct** — the recurring Phase-23/30/31 missing-`await`
  regression did NOT recur. Both async methods use
  `await self._db.schema.has_extension("timescaledb")`, and async `_run` awaits both
  `to_dataframe` and `execute` (`to_dataframe`/`execute` confirmed to be coroutines
  in `async_database.py`).
- **`into="gdf"` raises `ValueError` before any DB call** — `_check_into` runs
  before the extension guard and before any builder/SQL; mock tests assert
  `db.execute.assert_not_called()` and `db.to_dataframe.assert_not_called()`.
- **Sync/async signatures are byte-identical** for `time_bucket`,
  `time_bucket_gapfill`, and `_run` (verified via `inspect.signature`).
- **No new dependencies, no new autocommit branches** (D-12 honored); numpydoc
  docstrings present and complete; `ruff check` passes; the 16 new mock/parity tests
  pass.

One Warning (a real correctness footgun shared with the spatial precedent) and four
Info items follow.

## Warnings

### WR-01: Literal `%` in `aggregates`/`where` breaks both the `rows` and `df` paths

**File:** `pycopg/timescale.py:262-271` (`_to_named_binds`), `pycopg/timescale.py` (`_build_time_bucket_sql` / `_build_time_bucket_gapfill_sql` body); manifests in `TimescaleAccessor._run` / `AsyncTimescaleAccessor._run`

**Issue:** `aggregates` and `where` are interpolated verbatim into the SQL string
that still carries `%s` placeholders. A caller using a perfectly legitimate
structural SQL fragment that contains a literal percent sign will corrupt parameter
binding on *both* output paths:

- **`into="rows"` path:** `self._db.execute(sql, params)` calls
  `cur.execute(sql, params)` with a non-empty `params` list. psycopg treats `%` as a
  format marker when params are present, so e.g.
  `aggregates="to_char(bucket, 'YYYY-MM-DD%')"` or `where="name LIKE 'a%'"` raises a
  psycopg formatting error (`IndexError: tuple index out of range` /
  `unsupported format character`) instead of running. A bare `%` is the documented
  psycopg footgun (must be `%%`).
- **`into="df"` path:** `_to_named_binds` does `sql.split("%s")`. If a structural
  fragment contains the literal substring `%s` (e.g. `where="fmt = '%s'"`), `parts`
  gains an extra element and the loop indexes `params[i]` past the end of the
  positional list, raising `IndexError` — or, worse, silently mis-maps a later real
  placeholder to the wrong value if counts happen to line up.

This is the same latent issue present in `spatial._to_named_binds`/`_run`, so it is
consistent with the accepted "structural SQL" trust posture and is NOT an injection
bug. But it is a *correctness* footgun distinct from the injection question the trust
posture covers: a well-intentioned caller passing valid SQL gets a confusing low-level
error. Worth documenting and ideally guarding.

**Fix:** At minimum, document the `%` constraint in the `aggregates`/`where`
docstrings (callers must write `%%` for a literal percent). A more robust fix is to
reject or escape literal `%s` in the structural fragments before binding, or to
detect a placeholder-count mismatch in `_to_named_binds` and raise a clear error:

```python
def _to_named_binds(sql: str, params: list) -> tuple[str, dict]:
    parts = sql.split("%s")
    if len(parts) - 1 != len(params):
        raise ValueError(
            f"placeholder/param count mismatch: {len(parts) - 1} %s vs "
            f"{len(params)} params — does a structural fragment contain a "
            "literal '%s'? Escape it as '%%s'."
        )
    out = parts[0]
    binds: dict = {}
    for i, part in enumerate(parts[1:]):
        out += f":p{i}{part}"
        binds[f"p{i}"] = params[i]
    return out, binds
```

## Info

### IN-01: Stale `# noqa: F401` on `FeatureNotSupported` import

**File:** `tests/test_timescale.py:26`

**Issue:** `from psycopg.errors import FeatureNotSupported  # noqa: F401` — the
`noqa: F401` (and the explanatory comment at line 18 about "the live reorder-policy
integration test") is now stale: the Phase-32 live gapfill tests
(`TestTimeBucketGapfillLive`) genuinely *use* `FeatureNotSupported` in their
`except` clauses, so the import is no longer unused. The suppression is harmless but
misleading.

**Fix:** Drop the `# noqa: F401` (and update/remove the now-inaccurate comment at
line 18) so the import documents its real, current usage.

### IN-02: Live gapfill tests pass trivially on Apache builds (no production-path assertion)

**File:** `tests/test_timescale.py` (`TestTimeBucketGapfillLive.test_time_bucket_gapfill_live` and `test_time_bucket_gapfill_async_live`)

**Issue:** On the local/CI Apache build, `time_bucket_gapfill` raises
`FeatureNotSupported`, which the test swallows with `except FeatureNotSupported: pass`.
On Apache builds these tests therefore assert nothing about the real gap-filled
output — they only confirm the function is license-gated. This is the documented,
accepted Phase-31 "license-tolerant" pattern (D-08), with the mock test held
authoritative for SQL shape, so it is acceptable — but the real NULL-pad behavior is
never exercised in this environment. Noted so the limitation is visible, not as a
defect.

**Fix:** None required (matches D-08). If a TSL/Community runner is ever available in
CI, consider gating these as `xfail(reason=...)` on Apache rather than silently
passing, so the real-output branch is tracked.

### IN-03: `_to_named_binds` duplicated verbatim from `spatial.py` (deliberate per D-06)

**File:** `pycopg/timescale.py:262-285` vs `pycopg/spatial.py:995-1021`

**Issue:** `_to_named_binds` is a byte-for-byte copy of `spatial._to_named_binds`.
This is an explicit, recorded decision (D-06: avoid a `timescale → spatial`
private-helper dependency; promotion to `utils.py` deferred because it would touch
`spatial.py`, outside this phase's file scope). Flagged only as a tracked
duplication so the future cleanup (a 3rd accessor needing it → promote to `utils.py`)
is not forgotten; the WR-01 placeholder-count fix, if applied, should land in both
copies.

**Fix:** No action this phase. Track the `utils.py` promotion for when a third
accessor needs the helper.

### IN-04: `time_bucket` / `time_bucket_gapfill` accept `into` positionally without a keyword-only guard

**File:** `pycopg/timescale.py` (`TimescaleAccessor.time_bucket` signature and async/gapfill mirrors)

**Issue:** `into` is an ordinary positional-or-keyword parameter at the end of a long
signature (`table, time_column, bucket_width, aggregates, where, schema, into`). A
caller who passes `where`/`schema` positionally and then `into` positionally is fine,
but the long flat positional list makes accidental misalignment (e.g. passing a
schema string into `where`) easy and silent. The spatial accessor uses `*,` to force
several of its routing args keyword-only; these helpers do not. This matches the
REQ-verbatim signatures (TS-ADV-06/07 list `into` as positional-capable), so it is
not a contract violation — noted as an ergonomics/robustness observation.

**Fix:** Optional, and only if the REQ signature permits: make `into` (and possibly
`schema`/`where`) keyword-only with a bare `*` separator to prevent silent positional
misalignment. Defer if it would break the REQ-verbatim signature contract.

---

_Reviewed: 2026-06-23T11:46:11Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
