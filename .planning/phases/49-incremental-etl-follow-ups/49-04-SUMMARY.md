---
phase: 49-incremental-etl-follow-ups
plan: 04
subsystem: etl
tags: [etl, incremental, watermark, composite, postgres, sync-async-parity]

# Dependency graph
requires:
  - phase: 49-03
    provides: composite builder (row-value compare) + _encode_composite_watermark/'composite' decode + widened RunResult + the 4 fail-loud run() seams
provides:
  - "_capture_watermark(df, col): single-column max + composite greatest-ROW capture (sorted last row, per-element NaN void)"
  - "_coerce_watermark_scalar shared coercion; _reconcile_watermark_binds multi-%s→named binds; _encode_watermark_value scalar/composite persist dispatcher"
  - "Composite watermark observable end-to-end in run() (sync+async, real+dry): capture → filter → record → RunResult tuple"
  - "_read_watermark widened to the composite tuple; composite+lookback raises ETLError (unsupported)"
affects: [49-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Composite max-ROW = df.sort_values(cols) reading each element from its OWN sorted column (sorted_df[c].iloc[-1]) — NEVER a cross-column row Series (which promotes int keys to float and false-trips the float-reject) and NEVER per-column maxes (D-10, Pitfall 3)"
    - "Per-element NaN void: any NaN in the captured tuple → record nothing this run (Pitfall 4 / C-03)"
    - "Multi-placeholder reconciliation: single %s keeps the historical :wm bind (byte-identical); composite maps each %s → distinct :wm{i} named bind"
    - "Shared pure helpers collapse the 4 duplicated run() capture blocks to one call each — kills the fully-duplicated-block drift risk (Pitfall 6)"

key-files:
  created: []
  modified:
    - pycopg/etl.py
    - tests/test_etl.py
    - tests/test_etl_accessor.py
    - docs/etl.md

key-decisions:
  - "Composite recorded watermark = the true greatest ROW (sorted last), proven live: (2, 1) NOT the fabricated per-column-max (2, 99) — the definitive D-10 correctness guard"
  - "Read each composite element from its own sorted column (native dtype), not from a row Series — fixes a real int→float promotion bug found in smoke testing that would false-trip the float-reject"
  - "incremental_lookback is unsupported for a composite watermark floor → ETLError at run time (composite lookback semantics undefined; resolved per 49-02/03 notes)"
  - "RunResult.watermark_recorded surfaces the composite tuple (via _row_to_result → _decode_watermark); watermark_used surfaces the composite seed/read floor tuple"
  - "Missing-column error keeps the scalar repr byte-identical (D-A3 sync/async message parity test); composite reports the list of missing key columns"

patterns-established:
  - "_capture_watermark / _reconcile_watermark_binds / _encode_watermark_value: the reusable scalar-or-composite watermark seam for run()"

# Metrics
duration: 40min
completed: 2026-07-03
---

# Phase 49 Plan 04: Composite watermark run() wiring (end-to-end) Summary

**Made the composite watermark observable end-to-end: `run()` (both accessors, real + dry) now captures the true greatest ROW (sorted last row, never per-column maxes, per-element NaN void), reconciles the multi-`%s` row-value filter into distinct named binds, and persists/decodes the composite envelope — proven live with the (2, 1)-not-(2, 99) correctness fixture, second-run strict-greater row-value filter, composite seed floor, and a sync/async-parity mirror.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-07-03
- **Tasks:** 2/2
- **Files modified:** 4 (pycopg/etl.py, tests/test_etl.py, tests/test_etl_accessor.py, docs/etl.md)

## Accomplishments

- **Task 1 (committed b5f6d93):** Four pure helpers (`_capture_watermark`, `_coerce_watermark_scalar`, `_reconcile_watermark_binds`, `_encode_watermark_value`) replace the 4 duplicated run() capture blocks + the 49-03 fail-loud guards. Wired at all four run() forks (C-04); `_read_watermark` + wm/read_floor types widened; composite+lookback → ETLError. Unit tests: sorted-last-ROW (2,1) not (2,99), scalar regression, native-type preservation, NaN-void, empty, missing-column, `:wm`/`:wm{i}` reconciliation.
- **Task 2 (committed 94b287d):** Live-DB correctness — recorded (2,1) not (2,99); second-run `(day,seq) > (recorded)` strict-greater filter; composite seed floor; async mirror; non-upsert composite guard (C-01). Docs: composite example + envelope shape + D-08 note in the Pipeline docstring; docs/etl.md incremental section corrected (stale "composite not supported"/"exclusive boundary" replaced with a v1.1.0 boundary-config + composite subsection).

## Bug found + fixed during implementation

- Composite capture initially read the max row via `df.sort_values(cols).iloc[-1][c]`. Extracting a whole ROW as a Series promotes mixed int/float columns to a common dtype, so an integer key element (`day=2`) became `2.0` and false-tripped the float-reject `ETLError`. Fixed by reading each element from its own sorted column (`sorted_df[c].iloc[-1]`), preserving native dtypes. Caught by smoke-testing the helper before wiring — a reminder that the row-Series dtype trap is easy to miss.

## Verification

- `pytest -k "composite or Composite"` (unit + live, sync + async) → 34 passed.
- Full suite `PGDATABASE=pycopg_test3 uv run pytest` → **1828 passed, 2 skipped, coverage 96.30%** (≥95% gate; etl.py 97%).
- `uv run mypy pycopg` → 0 issues / 18 files. `uv run ruff check` → clean.
- `grep -c "def run(" pycopg/etl.py` == 2, both edited (C-04).
- Sphinx `-W` build clean; `interrogate` 100%.

## Notes for downstream (49-05)

- ETL-INC-F03 is complete end-to-end. 49-05 (advisory-lock concurrency) is independent of the watermark surface — it adds `Pipeline.concurrency`, a `'skipped'` RunResult status, and `ETL_ADVISORY_*` queries.
- The composite watermark surface is now the reference for the run() seam shape (`_capture_watermark` / `_reconcile_watermark_binds`).
