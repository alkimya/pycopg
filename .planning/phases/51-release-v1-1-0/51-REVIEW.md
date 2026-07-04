---
phase: 51-release-v1-1-0
reviewed: 2026-07-04T10:35:14Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - pycopg/timescale.py
  - tests/test_timescale.py
  - docs/api-reference.md
  - pyproject.toml
  - docs/conf.py
  - CHANGELOG.md
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 51: Code Review Report

**Reviewed:** 2026-07-04T10:35:14Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the Phase 51 (v1.1.0 release) diff since `c1eb423^`. The material code
change is WR-01: the `origin`/`offset` mutual-exclusion `ValueError` was hoisted
before the `has_extension()` DB round-trip in both `TimescaleAccessor.time_bucket`
(sync) and `AsyncTimescaleAccessor.time_bucket` (async), with the existing guard
inside `_build_time_bucket_sql` retained as defense-in-depth. The remaining files
are docs/metadata edits (classifier bump, version bumps, exception-name example
fix, CHANGELOG).

The material code change is **correct and verified**:

- **Message parity:** AST-level `literal_eval` of all three `ValueError` sites
  (lines 272, 1553, 2889) confirms the runtime string is **byte-identical** across
  sync, async, and the builder — no drift.
- **KIND-parity:** The hoisted guard is placed identically in both accessors
  (after `_check_into`, immediately before `has_extension()`); sync/async parity
  holds.
- **Ordering:** The guard precedes the only DB round-trip in the method
  (`has_extension()`); no behavior change beyond "fires earlier."
- **Test correctness:** The new tests set `has_extension` to a mock returning
  `True`, then assert `has_extension.assert_not_called()`. This genuinely proves
  the ordering — a regression that un-hoisted the guard would still raise
  `ValueError` (from the builder's guard) but would leave `has_extension` called,
  failing the assertion. The async test correctly uses `AsyncMock`.

No BLOCKER-severity issues found. One WARNING (stale/missing CHANGELOG compare
link references for the 1.1.0 release) and three INFO items follow.

## Warnings

### WR-01: CHANGELOG 1.1.0 section has no compare-link reference; `[Unreleased]` link is stale

**File:** `CHANGELOG.md:542-543` (and new `## [1.1.0]` heading at line 10)
**Issue:** The diff adds a `## [1.1.0] - 2026-07-04` section whose bracketed
version is, per the "Keep a Changelog" convention this file follows, a reference
link — but no `[1.1.0]:` link definition was added to the footer. Additionally,
the `[Unreleased]` link definition still points at `v1.0.0...HEAD`. After a 1.1.0
release, `[Unreleased]` should compare against `v1.1.0`, and a `[1.1.0]:`
definition should exist. As written, the `[1.1.0]` heading renders as a broken
reference link and the "Unreleased" diff range is wrong. This is a release
artifact, so the broken link is user-visible on the published changelog.
**Fix:**
```markdown
[Unreleased]: https://github.com/alkimya/pycopg/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/alkimya/pycopg/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/alkimya/pycopg/compare/v0.10.1...v1.0.0
```

## Info

### IN-01: New sync test fully duplicates the strengthened existing test

**File:** `tests/test_timescale.py:2579-2601`
**Issue:** `test_time_bucket_origin_offset_no_extension_check` (sync) is a strict
subset of the just-strengthened `test_time_bucket_origin_offset_mutual_exclusion`
(lines 2552-2577): same `Database`, same `has_extension`-returns-`True` mock,
same `origin`+`offset` call, same `pytest.raises(match="mutually exclusive")`, and
the same `mock_schema.has_extension.assert_not_called()` assertion (line 2577 vs
2601). It adds no coverage the strengthened test does not already provide. The
**async** variant (2603-2625) is the genuinely valuable addition (async parity was
not previously covered).
**Fix:** Remove the redundant sync `test_time_bucket_origin_offset_no_extension_check`
and keep the strengthened `..._mutual_exclusion` sync test plus the new async test;
or merge to make intent explicit.

### IN-02: Mutual-exclusion message triplicated as a raw literal with no single source of truth

**File:** `pycopg/timescale.py:273-275`, `1554-1556`, `2890-2892`
**Issue:** The identical message string is hand-duplicated across three raise
sites. This diff correctly kept them byte-identical, but the arrangement means a
future edit to one site (e.g., wording tweak) silently drifts the other two — and
byte-identical parity is exactly the property tests do not assert. The current
`match="mutually exclusive"` assertions would not catch a drift in the trailing
clause.
**Fix:** Extract a module-level constant, e.g.
`_TIME_BUCKET_ORIGIN_OFFSET_MSG = "time_bucket: 'origin' and 'offset' are mutually exclusive (TimescaleDB has no time_bucket overload accepting both); pass one or neither."`
and reference it from all three `raise ValueError(...)` sites.

### IN-03: CHANGELOG introspection bullets omit the `db.schema.*` access path

**File:** `CHANGELOG.md` (Added → "CRUD + introspection" block, ~lines 36-42)
**Issue:** The `materialized_views(...)`, `materialized_view_columns(...)`, and
`describe(...)` entries live on `db.schema.*` (verified: defined in
`pycopg/schema.py`, not on `Database`), whereas the sibling CRUD entries
(`delete_where`, `count`, `paginate`, `Page`) live on `db.*` directly. The heading
lists both files `(pycopg/database.py, pycopg/schema.py)` but gives no per-method
access path (unlike the TimescaleDB block, which uses `db.timescale.*`). A reader
could reasonably expect `db.describe(...)` rather than `db.schema.describe(...)`.
**Fix:** Prefix the introspection bullets with `db.schema.` (or split the block so
the access path is unambiguous), matching the `db.timescale.*` convention used
above.

---

_Reviewed: 2026-07-04T10:35:14Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
