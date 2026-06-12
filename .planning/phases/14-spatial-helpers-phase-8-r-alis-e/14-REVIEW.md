---
phase: 14-spatial-helpers-phase-8-r-alis-e
reviewed: 2026-06-12T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - pycopg/spatial.py
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/__init__.py
  - tests/test_spatial.py
  - pyproject.toml
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 14: Code Review Report

**Reviewed:** 2026-06-12
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the new spatial module (resolver + 11 pure builders + sync/async accessors), the lazy `spatial` properties on both database classes, the package exports, the test suite (169 spatial tests), and the coverage gate change. Security posture is solid: every identifier passes `validate_identifiers` before interpolation, every user value is a `%s` parameter, SRID goes through `int()` coercion, and the PostGIS guard covers both sync (construction) and async (first call) paths. No critical issues. One warning about literal `%` handling in the raw `where=` fragment interacting with the gdf named-binds conversion, plus two minor informational notes.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: Literal `%s` inside a `where=` fragment breaks parameter handling

**File:** `pycopg/spatial.py` (`_append_tail` / `_to_named_binds`)
**Issue:** `where=` is a raw SQL fragment (accepted limitation T-14-04). But if a caller writes a LIKE pattern containing the byte sequence `%s` — e.g. `where="name LIKE 'foo%suffix'"` is fine, while `where="name LIKE '%s_x'"` is not — the rows path makes psycopg see an extra placeholder (placeholder/param count mismatch error), and the gdf path's `_to_named_binds` splits on it and raises `IndexError` (more `%s` occurrences than params). The failure is confusing rather than dangerous (no injection — the value never gets interpolated), and `Database.execute` has the same psycopg `%%`-escaping requirement, so this is convention-consistent.
**Fix:** Document the `%%` escaping requirement in the `where=` parameter docs (one line in the module docstring or each `where` param description). Optionally add a defensive check in `_to_named_binds`: `if len(parts) - 1 != len(params): raise ValueError("where= fragments must escape literal % as %% ...")` to convert the IndexError into an actionable message.

## Info

### IN-01: `within` with `into="gdf"` and default `SELECT *` can yield duplicate column names

**File:** `pycopg/spatial.py` (`build_within_sql` / `SpatialAccessor.within`)
**Issue:** The two-table JOIN with default `columns=None` produces `SELECT *`, returning columns from both tables. If both tables have identically named columns (e.g. both named `geometry`), pandas/geopandas receives duplicate column labels and `geom_col=left_geom` becomes ambiguous.
**Fix:** No code change needed for phase scope — mention in the `within` docstring that `columns=` should be used with `into="gdf"` when column names collide across the joined tables.

### IN-02: Async PostGIS guard is not concurrency-deduplicated

**File:** `pycopg/spatial.py` (`AsyncSpatialAccessor._check_postgis`)
**Issue:** Two concurrent first calls on the same accessor can both run the `has_extension` query before `_postgis_ok` flips to True. Harmless (idempotent read, both succeed), just a duplicate round-trip in a rare race.
**Fix:** Acceptable as-is; an `asyncio.Lock` would be over-engineering for an idempotent boolean check.

---

_Reviewed: 2026-06-12_
_Reviewer: Claude (inline, gsd-code-reviewer contract; subagent spawn skipped per project infra constraint — see MEMORY pycopg-execute-phase-infra)_
