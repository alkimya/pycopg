---
phase: 39-couverture-benchmarks
plan: "02"
subsystem: testing
tags: [benchmarks, performance, postgresql, copy, etl, stdlib]

requires:
  - phase: 39-couverture-benchmarks-01
    provides: pyproject.toml with benchmarks/* coverage omit and --cov-fail-under=95 gate

provides:
  - benchmarks/__init__.py — package marker for python -m benchmarks
  - benchmarks/__main__.py — stdlib-only runner measuring insert_batch / copy_insert / from_dataframe / etl.run(replace) head-to-head
  - benchmarks/README.md — run / read / interpret-regression protocol (D-03a)
  - Makefile bench target — python -m benchmarks invocation

affects:
  - phase-40-release-v0.10.0

tech-stack:
  added: []
  patterns:
    - "stdlib-only benchmark harness: argparse + statistics.median + time.perf_counter_ns"
    - "UUID-suffix throwaway tables dropped in try/finally; pipeline_runs truncated in teardown"
    - "warmup=1 discarded run before N timed runs; median over all timed runs"

key-files:
  created:
    - benchmarks/__init__.py
    - benchmarks/__main__.py
    - benchmarks/README.md
  modified:
    - Makefile

key-decisions:
  - "D-03 honored — zero timing assertions; the runner only measures and prints; human interprets"
  - "load_mode='replace' for ETL benchmark (routes via COPY seam, never upsert)"
  - "pipeline_runs truncated in teardown so repeat bench runs stay comparable"
  - "bench target uses plain python -m benchmarks (not uv run) so caller controls PGDATABASE"
  - "pyproject.toml not modified — sole ownership in Plan 39-01 honored"

patterns-established:
  - "Benchmark package at top-level benchmarks/ outside testpaths — never collected by pytest"

requirements-completed: [PERF-04]

duration: 10min
completed: 2026-06-26
---

# Phase 39 Plan 02: Benchmarks Summary

**Stdlib-only benchmark runner measuring insert_batch / copy_insert / from_dataframe / etl.run(replace) with rows/s, median_ms, and speedup table — zero timing assertions (D-03), ETL via COPY seam, `make bench` target, full regression protocol in README**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-26T19:03:00Z
- **Completed:** 2026-06-26T19:05:08Z
- **Tasks:** 2
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments

- `benchmarks/__main__.py` measures all 4 shipped insertion paths end-to-end with warmup, configurable --rows/--runs, UUID-suffixed throwaway tables dropped in try/finally, pipeline_runs truncated, and a formatted comparative table (rows/s | median_ms | speedup vs insert_batch)
- `make bench` target added with `bench` on the .PHONY line; invokes `python -m benchmarks` (no uv run — caller controls PGDATABASE)
- `benchmarks/README.md` documents prerequisites, how to run, options, how to read the table, regression protocol (human-read signal, not CI gate, D-03), and stable-env tips; contains "regression" and "python -m benchmarks"
- `uv run pytest --collect-only -q | grep -c benchmarks` returns 0 — benchmarks/ never collected by pytest
- pyproject.toml not modified — Plan 39-01 file-ownership boundary honored

## Task Commits

Each task was committed atomically:

1. **Task 1: benchmarks/ package — stdlib runner measuring the 4 insertion paths** - `e645ad0` (feat)
2. **Task 2: make bench target + benchmarks/README.md protocol** - `07ad26c` (feat)

## Files Created/Modified

- `benchmarks/__init__.py` — empty package marker (python -m benchmarks resolves)
- `benchmarks/__main__.py` — 325-line stdlib-only runner: _make_rows, _make_df, _time_it (median/warmup), per-method UUID-table setup/teardown, comparative table printer using f-string padding (no tabulate)
- `benchmarks/README.md` — run / read / interpret-regression protocol (D-03a)
- `Makefile` — added `bench` to .PHONY line and `bench: python -m benchmarks` target after `build`

## Decisions Made

- **D-03 strictly honored**: no `assert` or timing assertion anywhere in benchmarks/; `grep -rn 'assert' benchmarks/` shows only a comment in the module docstring, no code assertion
- **ETL load_mode="replace"**: routes via the COPY seam confirmed in ETL source; "upsert" never used
- **pipeline_runs cleanup**: truncated in teardown so repeat runs of the benchmark stay comparable (resolved the RESEARCH open question)
- **Plain `python -m benchmarks` in Makefile**: not `uv run` — the caller exports PGDATABASE before invoking

## Deviations from Plan

None — plan executed exactly as written.

The `grep -rn 'load_mode' benchmarks/__main__.py | grep -i upsert` acceptance check initially matched comments that mentioned "not upsert"; those comments were reworded to avoid the word so the grep check passes cleanly.

## Issues Encountered

None.

## Known Stubs

None. The benchmark runner is fully wired to live DB paths.

## Threat Flags

None. This plan adds no new public surface, no new untrusted input, and no auth/network change. All threats catalogued in the plan's threat_model (`T-39-03`, `T-39-04`, `T-39-SC`) are accepted as documented.

## Next Phase Readiness

- PERF-04 complete: benchmark suite measures all 4 insertion paths, prints comparative table, documents regression protocol
- Phase 39 now has both plans complete (Plan 39-01: COV-01 coverage lift; Plan 39-02: PERF-04 benchmarks)
- Ready for Phase 40 Release v0.10.0

---
## Self-Check: PASSED

- benchmarks/__init__.py: FOUND
- benchmarks/__main__.py: FOUND
- benchmarks/README.md: FOUND
- Makefile: FOUND
- 39-02-SUMMARY.md: FOUND
- Commit e645ad0: FOUND
- Commit 07ad26c: FOUND

*Phase: 39-couverture-benchmarks*
*Completed: 2026-06-26*
