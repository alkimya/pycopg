---
phase: 49-incremental-etl-follow-ups
plan: 05
subsystem: etl
tags: [etl, concurrency, advisory-lock, postgres, sync-async-parity]

# Dependency graph
requires:
  - phase: 49-04
    provides: the completed run() body (now _run_impl) that the lock wraps; dry_run transient-RunResult precedent
  - phase: 20 (v0.5.0 ETL Pipeline Runner)
    provides: dedicated-autocommit-connection idiom + RunResult/'dry_run' transient-status precedent
provides:
  - "queries.ETL_ADVISORY_LOCK / ETL_ADVISORY_TRY_LOCK / ETL_ADVISORY_UNLOCK (hashtextextended(%s, 0), server-side key, name bound)"
  - "Pipeline.concurrency: Literal['wait','skip'] | None = None (opt-in on any pipeline, D-12)"
  - "'skipped' transient RunResult status (no pipeline_runs row, CHECK unchanged, D-13)"
  - "run() session-scoped advisory-lock wrap (sync+async): _run_impl body + thin lock wrapper, finally-release + auto-release on disconnect (D-14)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Server-side lock key via hashtextextended(name, 0) with the name BOUND as %s — never a PYTHONHASHSEED-salted Python hash() (per-process → never serializes cross-process), never interpolated (D-15)"
    - "run() = thin lock wrapper + _run_impl body: concurrency=None/dry_run delegate directly (byte-identical, no round-trip); else acquire on a DEDICATED autocommit connection, try/finally release, `with` close auto-releases on crash (D-14)"
    - "'skip'-when-held returns a transient RunResult(status='skipped', run_id=None) writing no pipeline_runs row — mirrors the dry_run early-return (D-13)"

key-files:
  created: []
  modified:
    - pycopg/queries.py
    - pycopg/etl.py
    - tests/test_etl.py
    - tests/test_etl_accessor.py
    - docs/etl.md

key-decisions:
  - "Session-scoped (pg_advisory_lock), NOT transaction-scoped (pg_advisory_xact_lock) — the lock must span from before _read_watermark through _end_run to close the watermark-read/extract race (Pitfall 1)"
  - "Dedicated THIRD connection for the lock, independent of the run-log and load-txn connections; held for the whole run span"
  - "'skipped' is a transient status like 'dry_run' — no pipeline_runs row, status CHECK constraint unchanged (D-13)"
  - "run() renamed to _run_impl + thin public run() wrapper (RESEARCH Pattern 4 / A2 refactor) — avoids re-indenting the ~300-line body and keeps the default path byte-identical"
  - "Explicit finally-unlock wrapped in try/except so a broken-connection release never masks the run exception; connection close is the crash-safety backstop (D-14)"

patterns-established:
  - "Advisory-lock wrap seam: public run() decides lock vs no-lock, _run_impl is the lock-unaware body"

# Metrics
duration: 35min
completed: 2026-07-03
---

# Phase 49 Plan 05: Advisory-lock concurrency control Summary

**Added `Pipeline.concurrency="wait"|"skip"` so a user can serialize concurrent runs of the same pipeline via a session-scoped PostgreSQL advisory lock keyed server-side on the bound pipeline name — `"wait"` blocks until a peer finishes, `"skip"` returns a transient `'skipped'` RunResult writing no `pipeline_runs` row — held on a dedicated connection for the whole run span, released in `finally` and auto-released on disconnect, full sync/async parity, default `None` byte-identical.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-03
- **Tasks:** 2/2
- **Files modified:** 5 (queries.py, etl.py, tests/test_etl.py, tests/test_etl_accessor.py, docs/etl.md)

## Accomplishments

- **Task 1 (committed 1d573fa):** Three `ETL_ADVISORY_*` constants (`hashtextextended(%s, 0)`, server-side key, name bound — D-15); `Pipeline.concurrency` Literal field + membership guard (D-12); `RunResult.status` docstring lists `'skipped'`; status CHECK untouched. Unit tests: constant SQL-shape, one-%s-each, status-CHECK-unchanged, name-bind injection, field guard.
- **Task 2 (committed 1496501):** `run()` → `_run_impl` + thin lock wrapper (both accessors, C-04); dedicated-connection session-scoped acquire/finally-release; `'skip'`-when-held transient result. Live two-connection integration: held-lock skip → `'skipped'` + no row + runs after release; skip-when-free proceeds; crash mid-run releases the lock; **`"wait"` blocks until a background holder releases then completes** (`run_done >= release time`); async skip mirror. docs/etl.md concurrency section (committed 5278bf8).

## Verification

- `pytest -k "advisory or concurrency or AdvisoryLock"` (unit + live, sync + async) → all green (5 live + 15 unit).
- Full suite `PGDATABASE=pycopg_test3 uv run pytest` → **1844 passed, 2 skipped, coverage 96.29%** (≥95% gate).
- `uv run mypy pycopg` → 0 issues / 18 files. `uv run ruff check` → clean.
- `grep -c "def run(" pycopg/etl.py` == 2, both edited (C-04); dry_run bypasses the lock.
- `queries.ETL_INIT_PIPELINE_RUNS` status CHECK unchanged (D-13). Sphinx `-W` clean; `interrogate` 100%.

## Phase 49 complete

ETL-INC-F01..F04 all shipped end-to-end. This closes the incremental-ETL follow-ups phase — 5 plans, 4 requirements, all standing-bar gates green (parity, validate_identifiers/bound-params, zero-deps, mypy-strict, cov≥95%).
