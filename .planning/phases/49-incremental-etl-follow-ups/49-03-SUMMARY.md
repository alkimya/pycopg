---
phase: 49-incremental-etl-follow-ups
plan: 03
subsystem: etl
tags: [etl, incremental, watermark, composite, postgres, mypy-strict]

# Dependency graph
requires:
  - phase: 49-02
    provides: _build_incremental_extract_sql inclusive param + run() read-floor sites the composite branch extends
  - phase: 22 (v0.7.0 Incremental ETL)
    provides: _encode_watermark/_decode_watermark scalar codec + _validate_incremental
provides:
  - "incremental_column widened to str | Sequence[str] | None (composite normalized to tuple[str,...], D-09)"
  - "_build_incremental_extract_sql composite branch: WHERE (c1, c2) {op} (%s, %s) row-value compare (D-10)"
  - "_encode_composite_watermark + 'composite' envelope tag in _decode_watermark (D-11), reusing the frozen per-scalar codec element-wise"
  - "D-04 composite initial_watermark guard (same-length sequence, per-element allowlist, normalized to tuple)"
  - "RunResult.watermark_used/watermark_recorded widened to include the composite tuple"
affects: [49-04, 49-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "str-stays-scalar / any-other-sequence→tuple normalization (inverse polarity to conflict_columns str-reject) — the composite normalization idiom"
    - "Native Postgres row-value lexicographic compare (c1, c2) > (%s, %s) — one bound %s per element, no client-side tuple emulation"
    - "_decode_watermark split into dispatcher + _decode_scalar_watermark so the composite branch reuses the scalar decoder per element (scalar return stays narrow)"
    - "Per-element codec reuse (bool-before-int/float per element, never bulk isinstance — Pitfall 2)"
    - "Fail-loud narrowing guard at each run() max-capture site as the 49-04 seam (composite CAPTURE not yet recorded); keeps mypy-strict green without implementing composite run()"

key-files:
  created: []
  modified:
    - pycopg/etl.py
    - tests/test_etl.py

key-decisions:
  - "incremental_column str stays single-column (byte-identical); a sequence normalizes to tuple[str,...] in __post_init__ (D-09). Empty sequence → ValueError."
  - "_validate_incremental splats validate_identifiers(*column) over every composite element as line 1 (D-10, C-04 injection safety)"
  - "D-04 composite initial_watermark: matching-length sequence, each element allowlist-checked via _encode_watermark, normalized to tuple; a single-column key now REJECTS a sequence seed (closes the 49-01 deferred Sequence branch)"
  - "'composite' envelope is additive to the three frozen scalar tags — single-column JSONB rows decode exactly as before (zero migration, C-02)"
  - "RunResult widened to include the composite tuple in Task 2 (codec surface), so 49-04 need not re-touch RunResult"

patterns-established:
  - "Composite watermark surface: field-widen → row-value builder → envelope codec, all pure/unit-testable without run()"

# DEVIATIONS
deviations:
  - "Task-boundary rebalanced for mypy-strict: the plan put the builder composite branch in Task 2, but widening incremental_column (Task 1) forces the _do_extract builder call to accept a composite type — so the builder composite branch was pulled into the Task-1 commit (field + its consumer belong together for mypy-green). Task 2 became the codec ('composite' tag) + RunResult widening. Both deliverables land; only the commit boundary moved."
  - "run() was NOT left untouched (the plan framed 49-03 as non-run()): widening the field cascades mypy into the 4 run() max-capture forks. Added a fail-loud narrowing guard (composite incremental_column 'not yet recorded by run(); wiring lands in 49-04') at each site + a documented cast in _read_watermark. These are the clean seam 49-04 replaces — no composite run() BEHAVIOR is implemented here, and no 49-03 test runs a composite pipeline."
  - "_build_incremental_extract_sql composite guards datetime/int/str via the same isinstance-str check; composite watermark values bound one-%s-per-element."

requirements-completed: [ETL-INC-F03]

# Metrics
duration: 35min
completed: 2026-07-03
---

# Phase 49 Plan 03: Composite multi-column watermark (pure layer) Summary

**Widened `incremental_column` to accept a composite (multi-column) key normalized to a tuple, added the native Postgres row-value compare `WHERE (c1, c2) > (%s, %s)` in the extract builder, and a `"composite"` JSONB envelope tag that reuses the frozen per-scalar codec element-wise — all the pure/testable surfaces of ETL-INC-F03, with the single-column path byte-identical and zero JSONB migration. `run()` composite wiring (capture + persist) is the fail-loud seam handed to 49-04.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-03
- **Tasks:** 2/2
- **Files modified:** 2 (pycopg/etl.py, tests/test_etl.py)

## Accomplishments

- **Task 1 (committed 7c2a7c1):** `incremental_column: str | Sequence[str] | None`; str-stays-scalar / sequence→tuple normalization + empty-guard (D-09); `_validate_incremental` splat (D-10); D-04 composite `initial_watermark` guard (length-match + per-element allowlist + tuple-normalize, and single-column-rejects-sequence closing the 49-01 gap); `_build_incremental_extract_sql` composite row-value branch (pulled in for mypy-green); fail-loud composite-capture guards at the 4 run() forks. Tests: construction/normalization + D-04 + builder SQL shape (both source kinds, `>`/`>=`) + composite injection + scalar byte-identical regression.
- **Task 2 (committed 75e0d24):** `_encode_composite_watermark` + `"composite"` decode branch (dispatcher + `_decode_scalar_watermark`), per-element codec reuse; `RunResult.watermark_used/watermark_recorded` widened; `_read_watermark` scalar cast (49-04 seam). Tests: envelope shape, tuple decode, mixed-type round-trip, per-element bool/float rejection, scalar zero-migration regression, unknown-tag guard.

## Verification

- `pytest tests/test_etl.py -k "TestCompositeWatermark or composite or TestEncodeDecodeWatermark or TestBuildIncrementalExtractSql"` → all green.
- `pytest tests/test_etl.py tests/test_etl_accessor.py tests/test_parity.py` → 305 passed (no regressions; scalar run() paths unaffected).
- `uv run mypy pycopg` → 0 issues / 18 files. `uv run ruff check` → clean.

## Notes for downstream plans (49-04)

- **Replace the 4 fail-loud guards** (`composite incremental_column is not yet recorded by run()`) with real composite max-ROW capture: for a tuple `col`, capture `(max/last row values)` aligned to the columns, encode via `_encode_composite_watermark`, persist.
- **Widen `_read_watermark`** return to include the tuple and remove the two documented casts, so a stored composite watermark reads back as the tuple floor.
- **Composite + lookback:** `_apply_lookback` is scalar-only; decide composite lookback semantics (likely reject / not-applicable for a composite floor) when wiring run().
- Builder + codec are done — 49-04 is purely the ~280-line duplicated run() capture/persist wiring (edit BOTH sync + async, RESEARCH Pitfall 6).
