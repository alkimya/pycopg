---
phase: 47-release-v1-0-0
plan: 01
subsystem: docs
tags: [docstrings, sphinx, interrogate, spatial, api-reference, postgis]

# Dependency graph
requires:
  - phase: 44-spatial-v2-serialization-mvt
    provides: as_geojson/as_text/as_mvt serialization helpers whose docstrings/docs carried the D-47-03 debt (IN-02 typos, WR-01 PostGIS floor)
  - phase: 41-api-homogenization
    provides: filter= rename (FREEZE-01) and the InvalidIdentifier -> InvalidIdentifierError rename (FREEZE-02) whose artifacts this plan corrects
provides:
  - "22x InvalidIdentifierErrorError docstring typos in pycopg/spatial.py corrected to the real InvalidIdentifierError class"
  - "docs/api-reference.md spatial v1 (11 rows) + timescale (2 rows) where= corrected to filter=; CRUD where= rows (count/paginate) left intact"
  - "as_text(max_decimal_digits=) two-arg PostGIS floor corrected to >= 3.1 across pycopg/spatial.py, docs/spatial.md, docs/stability.md"
  - "Re-verified Sphinx -W --keep-going clean and interrogate 100% after the docs/docstring edits"
affects: [47-02-release-v1-0-0, 47-03-release-v1-0-0]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - pycopg/spatial.py
    - docs/api-reference.md
    - docs/spatial.md
    - docs/stability.md

key-decisions:
  - "Blind find/replace was avoided for where=->filter=; only the 11 spatial v1 rows + 2 timescale rows were touched via line-range sed (199-209, 240-241), verified count(where=)==2 afterward"
  - "The as_text PostGIS >= 3.1 note (WR-01 from Phase 44 review) had no prior text anywhere to literally correct 3.0->3.1 -- it was undocumented. Added the note fresh in pycopg/spatial.py (build_text_sql + both as_text docstrings, sync/async parity) and docs/spatial.md + docs/stability.md, following the existing make_valid version-note style"

patterns-established: []

requirements-completed: [REL-11]

# Metrics
duration: 5min
completed: 2026-07-02
---

# Phase 47 Plan 01: Debt Triage (D-47-03 Docs/Docstring Correctness) Summary

**Corrected 22 non-existent `InvalidIdentifierErrorError` docstring typos, renamed 13 stale `where=` doc rows to `filter=` (spatial v1 + timescale, CRUD rows untouched), and documented the real PostGIS >= 3.1 floor for `as_text`'s two-arg form — zero executable lines touched, both docs gates re-verified green.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-02T13:59:15Z
- **Completed:** 2026-07-02T14:04:03Z
- **Tasks:** 3 completed
- **Files modified:** 4 (pycopg/spatial.py, docs/api-reference.md, docs/spatial.md, docs/stability.md)

## Accomplishments

- Closed T-47-01: all 22 `InvalidIdentifierErrorError` (Phase 41 FREEZE-02 double-rename artifact) corrected to the real, importable `InvalidIdentifierError` class in `pycopg/spatial.py` docstring `Raises:` sections.
- Closed T-47-02: `docs/api-reference.md` spatial v1 helper rows (`contains`, `within`, `intersects`, `dwithin`, `distance`, `nearest`, `area`, `perimeter`, `centroid`, `buffer`, `transform`) and timescale rows (`time_bucket`, `time_bucket_gapfill`) now show `filter=`, matching the live post-FREEZE-01/D3 keyword. The 2 CRUD dict-equality rows (`count`, `paginate`) were left untouched — their `where=` is correct.
- Documented the real PostGIS `>= 3.1` requirement for `as_text(max_decimal_digits=)`'s two-arg `ST_AsText(geom, ndigits)` form (Phase 44 WR-01), in `pycopg/spatial.py` (`build_text_sql` + both sync/async `as_text` docstrings), `docs/spatial.md`, and `docs/stability.md`.
- Re-verified `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` exits 0 and `uv run interrogate -c pyproject.toml pycopg` reports 100.0% after all edits.

## Task Commits

Each task was committed atomically:

1. **Task 1: Correct the 22 InvalidIdentifierErrorError double-suffix docstring typos in spatial.py** - `6e6f5a3` (docs)
2. **Task 2: Audit api-reference.md where= to filter= for spatial/timescale rows and correct the as_text PostGIS 3.1 note** - `ddd0398` (docs)
3. **Task 3: Re-verify Sphinx -W clean + interrogate 100% after the docs/docstring edits** - verification only, no commit (gates confirmed green: Sphinx exit 0, interrogate 100.0%)

**Plan metadata:** (this commit)

## Files Created/Modified

- `pycopg/spatial.py` - 22 docstring `Raises:` typo fixes (`InvalidIdentifierErrorError` -> `InvalidIdentifierError`); `build_text_sql` + both `as_text` method docstrings (sync/async) now note the two-arg form requires PostGIS >= 3.1
- `docs/api-reference.md` - 11 spatial v1 rows + 2 timescale rows `where=` -> `filter=` (13 rows total); 2 CRUD rows (`count`, `paginate`) unchanged
- `docs/spatial.md` - `as_text` usage section gains the PostGIS >= 3.1 two-arg form note
- `docs/stability.md` - new note block next to the `as_geojson`/`as_text` precision note documenting the PostGIS >= 3.1 requirement for `as_text(max_decimal_digits=)`

## Decisions Made

- Used targeted line-range `sed` (lines 199-209 and 240-241 in `docs/api-reference.md`) instead of a global find/replace to guarantee the 2 CRUD `where=` rows at lines 102-103 were never touched — verified by post-edit `grep -c "where=" docs/api-reference.md` returning exactly `2`.
- The as_text PostGIS-3.1 note did not previously exist anywhere verbatim as a "3.0" claim to literally correct — Phase 44's WR-01 finding described the *absence* of a version note (undocumented gap), not a wrong existing number. Added the note fresh in all 4 files following the plan's intent and the existing `make_valid` version-note style, rather than searching for non-existent text to replace.

## Deviations from Plan

None - plan executed exactly as written. The as_text PostGIS note required composing new text (no literal "3.0" to swap for "3.1" existed at the exact `as_text` docstring locations), which is consistent with the plan's own acceptance criteria (grep for the corrected `3.1` note, not a diff of an existing `3.0` string).

## Issues Encountered

- Sphinx/interrogate initially failed because `uv run sphinx-build` resolved to a global (non-project) install missing `pygments`/`sphinx` entirely. Resolved by running `uv pip install -r docs/requirements.txt` (the exact step CI's `tests.yml` "Build Sphinx docs" job performs) before re-running the gate — not a plan deviation, just following the documented CI prerequisite.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- D-47-03 docs/correctness debt fully closed: no non-existent class name, no stale spatial/timescale `where=`, correct PostGIS floor for `as_text` two-arg form, both docs gates green.
- Ready for Plan 47-02 (version bump + CHANGELOG `[1.0.0]` + MIGRATION final review) and Plan 47-03 (5 gates + tag + human-gated OIDC publish + smoke).
- No blockers.

---
*Phase: 47-release-v1-0-0*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: pycopg/spatial.py, docs/api-reference.md, docs/spatial.md, docs/stability.md
- FOUND: commit 6e6f5a3 (Task 1)
- FOUND: commit ddd0398 (Task 2)
- FOUND: commit e079a8d (SUMMARY.md)
