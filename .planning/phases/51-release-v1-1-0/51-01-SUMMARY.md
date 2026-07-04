---
phase: 51-release-v1-1-0
plan: 01
subsystem: testing
tags: [release, timescaledb, docs, metadata, deprecation-warning, kind-parity]

requires:
  - phase: 48-timescaledb-follow-ups
    provides: time_bucket origin/offset params (WR-01 carry-forward target)
  - phase: 50-crud-introspection-follow-ups
    provides: shipped v1.1.0 public surface documented by DOC-13 edits
provides:
  - pyproject Development Status classifier 5 - Production/Stable (D-02)
  - api-reference Exceptions block canonical *Error names only (D-03, gate-critical)
  - CLAUDE.md Version line pycopg v1.1.0 on disk (D-04, file is gitignored)
  - time_bucket origin/offset ValueError hoisted before has_extension() on sync+async (D-05/WR-01)
  - sync+async WR-01 regression tests asserting has_extension not called
affects: [51-02, release-gates, changelog-fixed-entry]

tech-stack:
  added: []
  patterns:
    - "Pre-round-trip pure-Python guard hoisted before has_extension(); original _build_time_bucket_sql guard kept as defense-in-depth (3 guards total)"
    - "KIND-parity: identical guard edited in BOTH TimescaleAccessor and AsyncTimescaleAccessor"

key-files:
  created: []
  modified:
    - pyproject.toml
    - docs/api-reference.md
    - CLAUDE.md
    - pycopg/timescale.py
    - tests/test_timescale.py

key-decisions:
  - "CLAUDE.md is gitignored (.gitignore:67) — D-04 edit applied on disk (grep gate = 1) but intentionally NOT committed; it is a local dev-instructions file, never tracked, never shipped."
  - "WR-01 committed as a single atomic commit (fix + tests). TDD_MODE is off; RED was verified live (3 failing) before the GREEN hoist."

patterns-established:
  - "Guard hoist changes only WHEN the identical ValueError fires (earlier) — non-breaking under the frozen SemVer-1.0 API; classified as ### Fixed, not ### Changed."

requirements-completed: [DOC-13]

duration: 12min
completed: 2026-07-04
---

# Phase 51 Plan 01: Pre-release corrections (DOC-13 + WR-01) Summary

**DOC-13 metadata/docs corrections (stable-1.x classifier, canonical `*Error` import example, CLAUDE.md v1.1.0) plus the WR-01 fix hoisting the `time_bucket` origin/offset `ValueError` before `has_extension()` on both sync and async, with sync+async regression tests.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-04T10:08Z
- **Completed:** 2026-07-04T10:20Z
- **Tasks:** 2
- **Files modified:** 5 (4 tracked + 1 gitignored on-disk)

## Accomplishments
- **D-02** — `pyproject.toml` classifier `Development Status :: 4 - Beta` → `5 - Production/Stable`.
- **D-03 (gate-critical)** — `docs/api-reference.md` "## Exceptions" import example now uses only canonical `*Error` names (`ExtensionNotAvailableError`, `TableNotFoundError`, `InvalidIdentifierError`), comment column re-aligned; no deprecated alias remains to trip gate #4 (`-W error::DeprecationWarning`).
- **D-04** — `CLAUDE.md` Version line `pycopg v0.9.0` → `pycopg v1.1.0` (applied on disk).
- **D-05 / WR-01** — hoisted `if origin is not None and offset is not None: raise ValueError(...)` before the `has_extension()` call in `TimescaleAccessor.time_bucket` (sync) and `AsyncTimescaleAccessor.time_bucket` (async); `_build_time_bucket_sql` guard retained as defense-in-depth (3 guards total).
- New tests `test_time_bucket_origin_offset_no_extension_check` (sync) + `test_time_bucket_origin_offset_async_no_extension_check` (async) assert `has_extension.assert_not_called()`; strengthened `test_time_bucket_origin_offset_mutual_exclusion` likewise. RED verified (3 failing) before the GREEN hoist.

## Task Commits

1. **Task 1: DOC-13 metadata/docs corrections (D-02/03/04)** - `c1eb423` (docs) — pyproject + api-reference tracked; CLAUDE.md edited on disk (gitignored, not in commit).
2. **Task 2: WR-01 guard hoist (D-05, sync+async) + regression tests** - `8e82136` (fix)

## Files Created/Modified
- `pyproject.toml` - stable-1.x Development Status classifier (D-02)
- `docs/api-reference.md` - Exceptions block canonical `*Error` names (D-03)
- `CLAUDE.md` - Version line v1.1.0 (D-04; on disk, gitignored)
- `pycopg/timescale.py` - hoisted origin/offset guard on sync + async time_bucket (D-05)
- `tests/test_timescale.py` - 2 new WR-01 regression tests + strengthened mutual-exclusion test

## Decisions Made
- **CLAUDE.md gitignored:** The D-04 requirement is satisfied by the on-disk edit (the grep acceptance checks disk content). `.gitignore:67` excludes `CLAUDE.md` — it has never been tracked and is a local developer-instructions file, so the change is correctly NOT in version control and NOT in the published wheel.
- WR-01 committed atomically (fix + tests together); TDD_MODE off, so no separate RED commit — RED was proven live before hoisting.

## Deviations from Plan
None - plan executed exactly as written. (The CLAUDE.md gitignore behavior was anticipated by D-04's disk-content grep gate, not a deviation.)

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required in this plan.

## Next Phase Readiness
- Gate #4 (`-W error::DeprecationWarning`) is now unblocked — the docs import example imports no deprecated alias.
- The single `### Fixed` CHANGELOG entry (WR-01) that 51-02 must record is landed and behavior-verified.
- Guard counts: `grep -c 'origin is not None and offset is not None' pycopg/timescale.py` → 3. Parity green (40 passed). Full `tests/test_timescale.py` → 135 passed.
- 51-02 can proceed: version bump + CHANGELOG + 5 release gates.

---
*Phase: 51-release-v1-1-0*
*Completed: 2026-07-04*
