---
phase: 31-continuous-aggregate-lifecycle
reviewed: 2026-06-23T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - pycopg/timescale.py
  - tests/test_timescale.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 31: Code Review Report

**Reviewed:** 2026-06-23
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Reviewed the Phase 31 continuous-aggregate lifecycle additions to `pycopg/timescale.py`
(`create_continuous_aggregate`, `refresh_continuous_aggregate`,
`add_continuous_aggregate_policy`, plus the `_check_offset_ordering` / `_OFFSET_RE`
helpers) and their sync/async mirrors, against `tests/test_timescale.py`.

Security posture is solid. Every identifier interpolated into DDL (`view_name`,
`schema`, `index_name`, `column`, `table`) is routed through
`validate_identifiers` / `validate_identifier`, and every interval interpolated
into SQL (`start_offset`, `end_offset`, `schedule_interval`, `chunk_time_interval`)
is gated by `validate_interval`, whose grammar (`^\d+\s+unit s?$`) admits no quotes
or metacharacters. `select_sql` is interpolated raw, but is explicitly documented as
caller-authored structural SQL (not untrusted input) — an accepted contract. No SQL
injection was found in the new surface.

The two recurring-bug classes called out in the brief are both clean:
- **The async `await self._db.schema.has_extension(...)` guard is present and
  correct** in all three new async methods (lines 1603, 1672, 1742). The dedicated
  await-omission regression tests pass (`..._async_no_extension_raises`).
- **The `connect(autocommit=True)` seam is genuinely isolating** — `Database.connect`
  (database.py:392) opens a fresh connection via `_connect_with_retry`, bypassing
  `_session_conn`, so a refresh issued inside `db.session()` cannot inherit the
  enclosing transaction. The D-10b structural-isolation test exercises exactly this.

Parameter binding for `refresh_continuous_aggregate` is correct (window bounds passed
as `[window_start, window_end]` to `%s, %s` rather than interpolated).

Findings below are quality/robustness issues, not blockers.

## Warnings

### WR-01: `time_bucket(` guard is case-sensitive and whitespace-brittle — rejects valid SQL

**File:** `pycopg/timescale.py:792` (sync), `pycopg/timescale.py:1597` (async)
**Issue:** The cagg-select sanity guard does a literal substring test:
```python
if "time_bucket(" not in select_sql:
    raise ValueError("select_sql must contain a time_bucket(...) grouping. ...")
```
PostgreSQL function names are case-insensitive and tolerate whitespace before the
paren, so all of the following are valid `time_bucket` caggs that this guard wrongly
rejects with a misleading "almost certainly a user error" message:
- `SELECT TIME_BUCKET('1 hour', ts) ...` (upper/mixed case)
- `SELECT time_bucket ('1 hour', ts) ...` (space before paren)
- A select that buckets via `time_bucket_gapfill(...)` only — also a legitimate
  continuous-aggregate pattern, also rejected.

This is a false-negative guard: it blocks correct user input. (It is also trivially
false-positive — `time_bucket(` appearing inside a string literal or comment would
satisfy it — but the false-rejection of valid SQL is the more harmful direction.)
**Fix:** Match case-insensitively and allow optional whitespace, e.g.
```python
import re
_TIME_BUCKET_RE = re.compile(r"time_bucket\w*\s*\(", re.IGNORECASE)
...
if not _TIME_BUCKET_RE.search(select_sql):
    raise ValueError(...)
```
or, if the guard is meant only as a soft footgun-catch, document it as a
best-effort heuristic and consider downgrading to a warning rather than a hard
`ValueError`.

### WR-02: `validate_interval` runs before `_check_offset_ordering`, narrowing accepted offsets below what the DB supports

**File:** `pycopg/timescale.py:942-947` (sync), `pycopg/timescale.py:1733-1738` (async)
**Issue:** `add_continuous_aggregate_policy` calls `validate_interval(start_offset)` /
`validate_interval(end_offset)` before deferring ordering to the DB. `validate_interval`
only accepts a single `<number> <unit>` token (`_INTERVAL_PATTERN`), so compound
offsets that TimescaleDB accepts natively — e.g. `"1 day 12 hours"`, `"90 minutes"`
is fine but `"1 month 15 days"` is not — raise `InvalidIdentifier` before reaching the
DB. The docstring and `_check_offset_ordering` notes advertise "calendar units
(`1 month`, `1 year`) … deferred to the DB," implying month/year offsets are
supported, but a *compound* offset mixing units is silently unsupported. The deferral
story is therefore only half-true: single-unit calendar offsets pass, compound
offsets do not.
**Fix:** Either document explicitly that policy offsets must be single
`<number> <unit>` tokens (and that compound intervals are unsupported by this API),
or relax the offset validation to permit psycopg-bound interval values instead of
interpolating them (interval offsets can be passed as `%s::interval` parameters,
removing the need for the restrictive `validate_interval` pre-check entirely).

### WR-03: Policy offsets are interpolated as `INTERVAL '...'` literals rather than bound parameters — inconsistent with the refresh path

**File:** `pycopg/timescale.py:959-969` (sync), `pycopg/timescale.py:1750-1760` (async)
**Issue:** `refresh_continuous_aggregate` correctly binds its window bounds as
parameters (`%s, %s`), but the sibling `add_continuous_aggregate_policy` interpolates
`start_offset` / `end_offset` / `schedule_interval` directly into the statement as
`INTERVAL '{...}'`. This is currently safe only because `validate_interval` strips the
attack surface (no quotes can pass), but it couples correctness to that validator and
is inconsistent with the bound-parameter discipline used three lines of code away in
refresh. Any future relaxation of `validate_interval` (see WR-02) would immediately
turn this into an injection vector. It also forces the WR-02 over-narrow validation to
exist at all.
**Fix:** Bind the intervals as parameters, e.g.
```python
self._db.execute(
    "SELECT add_continuous_aggregate_policy(%s, "
    "start_offset => %s::interval, end_offset => %s::interval, "
    "schedule_interval => %s::interval" + ne + ") AS job_id",
    [f"{schema}.{view_name}", start_offset, end_offset, schedule_interval],
)
```
(handling the `NULL` offset case by passing `None`, which `%s::interval` renders as
`NULL`). This removes the literal interpolation and lets WR-02's validator be relaxed
safely.

## Info

### IN-01: `_OFFSET_RE` is redundant with `validate_interval` for the offsets it sees

**File:** `pycopg/timescale.py:90-93`, used at `pycopg/timescale.py:139-140`
**Issue:** By the time `_check_offset_ordering` runs, both offsets have already passed
`validate_interval`, whose grammar is a strict superset of `_OFFSET_RE` (it adds only
`month`/`year`). The `ms`/`me` match guards can therefore only fail on month/year
inputs. This is not a bug — the logic is correct — but the second regex restates the
unit grammar in a third place (after `_IDENTIFIER_PATTERN` and `_INTERVAL_PATTERN`),
so a future edit to one grammar can silently desync the others.
**Fix:** Consider deriving the fixed-duration unit set from a single shared constant,
or add a comment cross-referencing `_INTERVAL_PATTERN` so the two stay aligned.

### IN-02: Stale module docstring references the removed `pycopg.aliases`

**File:** `pycopg/timescale.py:10`
**Issue:** The module docstring still says aliases "remain as thin deprecated aliases
(see :mod:`pycopg.aliases`) until v0.7.0." `pycopg.aliases` was deleted in Phase 25
and v0.7.0 has shipped; the `:mod:` cross-reference now points at a non-existent
module (this is the same carry-forward doc-drift noted across prior phases).
**Fix:** Remove the `pycopg.aliases` sentence / `:mod:` reference from the docstring.

### IN-03: `add_continuous_aggregate_policy` does not validate `start_offset` < `end_offset` across calendar/mixed units

**File:** `pycopg/timescale.py:142-148`
**Issue:** `_check_offset_ordering` is explicitly best-effort (same-unit only) by
design (D-07), so e.g. `start_offset="6 hours"`, `end_offset="1 day"` (start window
*shorter* than end — almost certainly a user error) passes the Python guard and is
deferred to the DB. This is the documented contract, not a defect, but callers on an
Apache build (where the DB never runs the policy function) get no early feedback for
mixed-unit inversions. Noted for completeness; no change required if D-07 stands.
**Fix:** None required (documented decision). If stricter feedback is later wanted, a
minimal interval-to-seconds normaliser over the five fixed units would cover the
mixed-unit case without new dependencies.

---

_Reviewed: 2026-06-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
