---
phase: 48-timescaledb-follow-ups
plan: 03
subsystem: database
tags: [timescaledb, postgres, sync-async-parity, sql-builder]

# Dependency graph
requires:
  - phase: 48-01 (cagg teardown pair)
    provides: test_timescale_v110_surface frozenset seed (2 names) + established plain-execute pattern
  - phase: 48-02 (time_bucket origin/offset)
    provides: no direct coupling — F02 was param-only, frozenset unchanged by 48-02
provides:
  - "db.timescale.compress_chunk(chunk, *, if_not_compressed=True) -> None (sync + async)"
  - "db.timescale.decompress_chunk(chunk, *, if_compressed=True) -> None (sync + async)"
  - "test_timescale_v110_surface frozenset now complete at 4 names (F01 + F03)"
  - "TSDB-F04 (show_chunks physical-time filter) verified already-shipped + documented + newer_than symmetry test added"
affects: [49, 50]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bound-value %s::regclass params for chunk names (NOT validate_identifiers) — the reconciliation carve-out for a value that isn't a schema/table identifier"
    - "None-return + has_extension-guard-first convention (mirrors enable_compression/add_compression_policy)"

key-files:
  created: []
  modified:
    - pycopg/timescale.py
    - tests/test_timescale.py
    - tests/test_parity.py
    - docs/timescaledb.md

key-decisions:
  - "compress_chunk/decompress_chunk do NOT call validate_identifiers — chunk is a bound %s::regclass VALUE returned by show_chunks(), not a caller-supplied identifier; injection safety is met entirely by parameter binding (RESEARCH D-10/D-11 explicit carve-out, honored per the plan's RECONCILIATION note)"
  - "if_not_compressed/if_compressed ARE bound as %s (unlike the cagg family's literal-boolean idiom) — because compress_chunk/decompress_chunk are plain PostgreSQL function calls, not TimescaleDB policy-registration calls with the =>-literal convention; confirmed by live TSDB 2.28.2 introspection"
  - "recompress param deliberately NOT added (out of scope per D-09/RESEARCH Anti-Patterns)"
  - "TSDB-F04 required zero production code change — _build_chunk_bound_fragments already dispatches newer_than symmetrically to older_than; only a mirror test + doc example were added"
  - "License note in docs/timescaledb.md now accurately distinguishes: compress_chunk/decompress_chunk ARE TSL-gated, but drop_continuous_aggregate/remove_continuous_aggregate_policy are NOT (per RESEARCH D-05) even though cagg *creation* is"

patterns-established:
  - "Injection-by-binding test convention (test_*_binds_not_interpolates) for methods with bound-value-only args and no identifier arguments — a new test shape alongside the existing InvalidIdentifierError-raise convention used by F01/F02"

requirements-completed: [TSDB-F03, TSDB-F04]

# Metrics
duration: 25min
completed: 2026-07-03
---

# Phase 48 Plan 03: Per-Chunk Compression + F04 Verification/Docs Summary

**Added `compress_chunk`/`decompress_chunk` (bound `%s::regclass`, no `validate_identifiers` — the plan's explicit reconciliation carve-out) to both accessor classes, completing Phase 48's TimescaleDB follow-up surface; verified and documented the already-shipped `show_chunks` physical-time filter (TSDB-F04) with a `newer_than`-datetime symmetry test and doc examples.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-03T11:40:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- `TimescaleAccessor.compress_chunk` / `decompress_chunk` and their `AsyncTimescaleAccessor` twins — emit the exact confirmed SQL (`SELECT compress_chunk(%s::regclass, if_not_compressed => %s)` / decompress mirror), `has_extension` guard first, return `None`, keyword-only flags, no `validate_identifiers` (no identifier argument exists — `chunk` is a bound value per RESEARCH D-10/D-11).
- Full mock coverage: `TestCompressChunkMock` / `TestDecompressChunkMock` — SQL-shape, flag-toggle, no-extension guard (`db.execute.assert_not_called()`), a dedicated "binds-not-interpolates" injection-by-binding test proving a malicious chunk string lands only in `params[0]` and never in the raw SQL template, plus async mirrors (10 new tests total).
- `test_timescale_v110_surface` (tests/test_parity.py) extended to the full 4-name Phase 48 set: `drop_continuous_aggregate`, `remove_continuous_aggregate_policy`, `compress_chunk`, `decompress_chunk` — asserted on both accessor classes.
- TSDB-F04 verified: `test_show_chunks_sql_shape_datetime_newer_than` added inside `TestShowChunksMock` (mirrors the existing `_datetime_older_than` test), confirming `_build_chunk_bound_fragments` already symmetrically dispatches `newer_than` — zero production code change needed.
- `docs/timescaledb.md`: new "Per-Chunk Compression" subsection (sync + async examples), cagg teardown prose (`drop_continuous_aggregate`/`remove_continuous_aggregate_policy`) completing the create→refresh→policy→teardown narrative, `newer_than` interval-str/datetime examples alongside the existing `older_than` ones, and an accurately-extended Community/TSL license note (compress/decompress ARE gated; cagg teardown is NOT, even though creation is).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add compress_chunk + decompress_chunk to both accessor classes** - `fe94be6` (feat)
2. **Task 2: Add F03 mock tests + F04 newer_than symmetry test + extend v110 parity frozenset** - `6773569` (test)
3. **Task 3: Document per-chunk compress/decompress + surface show_chunks physical-time filter** - `42389f4` (docs)

## Files Created/Modified

- `pycopg/timescale.py` - `compress_chunk`/`decompress_chunk` × 2 classes (168 new lines); both bound-value execute, `has_extension`-guard-first, `None`-return, full numpydoc `Raises` block (ExtensionNotAvailableError + FeatureNotSupported)
- `tests/test_timescale.py` - `TestCompressChunkMock` (5 tests) + `TestDecompressChunkMock` (5 tests) + `test_show_chunks_sql_shape_datetime_newer_than` (1 test, inside `TestShowChunksMock`)
- `tests/test_parity.py` - `test_timescale_v110_surface` frozenset extended 2→4 names
- `docs/timescaledb.md` - Per-Chunk Compression subsection, cagg teardown prose, `newer_than` examples, extended license note

## Decisions Made

- `compress_chunk`/`decompress_chunk` deliberately skip `validate_identifiers` — the plan's RECONCILIATION note is explicit that CONTEXT D-10's "standing bar" assumed an identifier exists, but these two methods have none (`chunk` is a bound `%s::regclass` value returned by `show_chunks()`); calling `validate_identifiers` on a non-identifier would be a spurious, incorrect call. Injection safety is proven instead by a dedicated `test_*_binds_not_interpolates` test per method.
- Boolean flags (`if_not_compressed`/`if_compressed`) ARE bound as `%s` params (not rendered as SQL literals like the cagg family's `if_exists`/`cascade`) — RESEARCH confirmed this is the correct idiom specifically for these two plain PostgreSQL function calls, distinct from the TimescaleDB policy-registration `=>`-literal convention used elsewhere in the file. Followed the plan's exact SQL template rather than a blanket rule.
- F04 required no production change — only a symmetry test (`newer_than`-datetime) and doc examples were added, confirming `_build_chunk_bound_fragments` already handles both bounds identically.

## Deviations from Plan

None — plan executed exactly as written; every SQL shape, guard ordering, and doc section matches the plan's Code Examples/Pattern Map exemplars verbatim.

One incidental fix applied during Task 2 verification: `black --fast --target-version py312` reformatted a single method signature in `pycopg/timescale.py` (async `decompress_chunk`, line-wrapping only, from Task 1's commit) — pure formatting, no behavior change, folded into the Task 2 commit before it was made, matching the established convention from 48-01/48-02 (local toolchain running Python 3.12 vs. a newer black target).

## Issues Encountered

None. All verification commands passed on the first attempt:
- `uv run mypy pycopg/timescale.py` → 0 errors
- `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py -k "compress_chunk or decompress_chunk or datetime_newer_than" tests/test_parity.py::test_timescale_v110_surface -x -q -o addopts=""` → 11 passed
- `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py tests/test_parity.py -x -q -o addopts=""` → 171 passed
- `cd docs && uv run sphinx-build -W -b html . _build/html -q` → 0 warnings/errors
- **Phase-gate full suite:** `PGDATABASE=pycopg_test3 uv run pytest` → 1763 passed, 2 skipped, coverage 96.37% (gate ≥95%)
- `uv run mypy pycopg/` (whole package, phase-gate) → 0 errors, 18 files
- `uv run interrogate pycopg` → 100% (gate ≥95%)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TSDB-F03 (per-chunk compression) fully complete: sync+async parity, mypy-strict clean (0 errors, whole package), interrogate 100%, ruff/black clean, injection-safe (binding, not identifier validation), TSL-gate tolerance documented.
- TSDB-F04 (show_chunks physical-time filter) verified already-shipped, symmetry-tested, and documented with both `older_than=` and `newer_than=` datetime examples.
- **Phase 48 (TimescaleDB Follow-ups) is now COMPLETE** — all 4 requirements (TSDB-F01..F04) shipped across plans 48-01, 48-02, 48-03. `test_timescale_v110_surface` frozenset is final at 4 names; no further extension expected from this phase.
- No blockers for phase 49 (ETL-INC-F01..04) or phase 50 (CRUD-F01..03 + INTRO-F01..02).

---
*Phase: 48-timescaledb-follow-ups*
*Completed: 2026-07-03*

## Self-Check: PASSED

- FOUND: `.planning/phases/48-timescaledb-follow-ups/48-03-SUMMARY.md`
- FOUND: `pycopg/timescale.py`
- FOUND commit: `fe94be6` (Task 1 feat)
- FOUND commit: `6773569` (Task 2 test)
- FOUND commit: `42389f4` (Task 3 docs)
