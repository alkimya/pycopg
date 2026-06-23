---
gsd_state_version: 1.0
milestone: v0.8.0
milestone_name: TimescaleDB avancé
status: executing
stopped_at: "Completed 33-02-PLAN.md (docs rewrite: timescaledb.md + api-reference.md + README)"
last_updated: "2026-06-23T16:35:30Z"
last_activity: 2026-06-23 -- Phase 33 Plan 02 executed (docs rewrite: 3 files, 9 new TimescaleDB methods documented)
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 11
  completed_plans: 9
  percent: 82
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-22)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Phase 33 — release-v0-8-0

## Current Position

Phase: 33 (release-v0-8-0) — EXECUTING
Plan: 3 of 3
Status: Executing Phase 33 (Plans 01-02 complete)
Last activity: 2026-06-23 -- Phase 33 Plan 02 executed (docs rewrite: 3 files, 9 new TimescaleDB methods documented)

## Performance Metrics

**Gates (v0.7.0 ship — baseline for v0.8.0):**

- Coverage ratchet: ≥94% (measured 95.11% at v0.7.0 ship)
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green (no deprecated stubs left after alias removal)

**v0.8.0 phases:**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 30. Chunk Management & Partitioning | 3 | 3 | COMPLETE (46 tests, TS-ADV-10, cov 94.96%) |
| 31. Continuous Aggregate Lifecycle | 3 | 3 | COMPLETE (11 policy tests, TS-ADV-03, cov 95.05%) |
| 32. Query Helpers & Parity Verification | 2 | 2 | COMPLETE (TS-ADV-06/07/10, cov 95.11%) |
| 33. Release v0.8.0 | 3 | 2 | In Progress (Plans 01-02: version bump + CHANGELOG + docs rewrite) |
| Phase 30 P01 | 210 | 2 tasks | 3 files |
| Phase 30 P02 | 480 | 2 tasks | 3 files |
| Phase 30 P03 | 1080 | 3 tasks | 2 files |
| Phase 31 P01 | 15m | 2 tasks | 2 files |
| Phase 31 P02 | 15m | 2 tasks | 2 files |
| Phase 31 P03 | 20m | 3 tasks | 2 files |
| Phase 32 P01 | 25m | 3 tasks | 1 files |
| Phase 32 P02 | 20m | 3 tasks | 2 files |
| Phase 33 P01 | 2m | 3 tasks | 4 files |

## Accumulated Context

### Decisions

**v0.8.0 scope locked (2026-06-22):**

- Target: TimescaleDB 2.x only (no 1.x shims); `by_range`/`by_hash` form for `add_dimension` — confirm local TSDB version at Phase 30 plan time
- Pattern: pure-builder + `validate_identifiers` + `%s` params + lazy accessor + sync/async parity (same as spatial/etl/timescale-basics)
- `create_continuous_aggregate` and `refresh_continuous_aggregate` MUST use dedicated `connect(autocommit=True)` connection — cannot route through `self._db.execute()` (TimescaleDB transaction-block restriction, confirmed GitHub issues #1218/#2876/#5377)
- `add_continuous_aggregate_policy` uses PLAIN `self._db.execute` (D-01 confirmed at execution time — NOT autocommit seam; matches the 3 shipped policy methods)
- Continuous aggregate trio ships together (Phase 31) — create + refresh + policy are an indivisible lifecycle
- `time_bucket_gapfill` requires explicit `start`/`finish` positional arguments inside the function call (not WHERE-clause inference — `%s` bound params are opaque to the TSDB planner hook, confirmed issues #4279/#7605/#8525)
- `drop_chunks` with both bounds `None` raises `ValueError` before any DB call; `dry_run=True` delegates to `show_chunks`; docstring marks DESTRUCTIVE/IRREVERSIBLE
- `add_dimension` validates empty hypertable and mutual-exclusivity of `number_partitions`/`chunk_interval` before sending SQL
- `create_continuous_aggregate` heuristic: raises `ValueError` if `select_sql` does not contain `time_bucket(`
- Policy tests: job-row existence in `timescaledb_information.jobs` + `CALL run_job(job_id)` on autocommit; never sleep-and-wait for scheduler
- Only `pycopg/timescale.py` and `pycopg/queries.py` change; flat core + all other accessors untouched
- `test_accessor_parity` already covers `(TimescaleAccessor, AsyncTimescaleAccessor)` via `ACCESSOR_PAIRS` — no registry change needed
- TS-ADV-10 parity assigned to Phase 32 (last feature phase, where the full 9-method surface exists)
- Zero new runtime dependencies; coverage ratchet ≥94% (baseline 95.11%)

**Phase 30 planning (2026-06-22) — research-driven decision changes:**

- TSDB version confirmed **2.28.0** (live `SELECT extversion`) → `add_dimension` uses modern `by_hash`/`by_range`; no pre-2.13 fallback.
- **D-08 RESHAPED:** the "empty/non-empty hypertable raises" premise is FALSE on 2.28's builder form (succeeds on populated tables). `add_dimension` instead wraps the **duplicate-dimension** error (TS160, `if_not_exists=False` path) as `TimescaleError`. The earlier STATE decision "validates empty hypertable" is superseded.
- **D-12 added:** local/CI is Apache-licensed → `add_reorder_policy` raises `FeatureNotSupported`. Mock SQL-shape test is authoritative; live test tolerates it; job-row assertion exercises only on Community builds. (Same constraint will apply to Phase 31's cagg policy tests.)
- **show_chunks** = native `show_chunks()` SRF JOINed to `timescaledb_information.chunks` (`%%I.%%I::regclass` key, `ORDER BY range_start ASC`); **drop_chunks** = capture-before-drop (drop SRF returns text + rows vanish post-drop). New 3rd file `pycopg/exceptions.py` (`TimescaleError`) + new `tests/test_timescale.py`.
- [Phase ?]: refresh_continuous_aggregate type guard
- [Phase ?]: Phase 32-01: time_bucket/time_bucket_gapfill query helpers on both accessors (sync+async); builder owns fixed AS bucket alias D-01; into=(df,rows) timescale-local D-03; gapfill double-binds start/finish D-10; no semantic guards D-09; zero new deps/autocommit D-12
- [Phase 32-02]: two-layer tests — time_bucket asserts REAL output (Apache-free), time_bucket_gapfill uses try/except FeatureNotSupported (TSL-gated on local Apache 2.28, D-08 corrected at plan time, mirrors Phase-31 caggs); mock tests authoritative for SQL shape + double-bind (D-10) + awaited async has_extension (D-07) + into=gdf ValueError pre-DB (D-03); explicit 9-name v0.8.0 surface frozenset asserted as subset of both classes (D-11), ACCESSOR_PAIRS untouched; cov 95.11%

### Pending Todos

None — roadmap created, ready to plan.

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — fixture-isolation bug, not v0.8.0 code; use `-o addopts=""` for targeted runs.
- One ~2.7% flaky bound-param test surfaced during Phase 28 — watch for re-flake.
- ~~**Phase 30 research flag:** confirm TSDB version~~ RESOLVED 2026-06-22: live = 2.28.0 → modern `by_hash`/`by_range`.
- ~~**Phase 32 research flag:** verify `to_dataframe` `%s`-to-named-bind conversion path~~ RESOLVED: plan 01 used a timescale-local `_to_named_binds` copy (D-06); plan 02 mock tests confirm `:p0` named binds + dict params reach `to_dataframe`.
- ~~**Phase 31 carry-forward:**~~ RESOLVED 2026-06-23: all 3 cagg methods use mock-authoritative + license-tolerant strategy for Apache build.

## Deferred Items

| Category | Item | Status |
| -------- | ---- | ------ |
| nyquist | Phase 22/23/24 VALIDATION.md left `draft` | deferred from v0.6.0 — verified PASSED via VERIFICATION.md |
| tech_debt | WR-02: dead monkeypatches in `test_sql_injection.py` async fixture | housekeeping; non-blocking |
| tech_debt | `CLAUDE.md` "Version" line stale (reads v0.5.0; actual v0.7.0) | cosmetic doc lag, carried since v0.6.0 |
| future | ETL-INC-F01: `initial_watermark` first-run bounding | deferred to a future ETL milestone |
| future | ETL-INC-F02: configurable `>` vs `>=` boundary | deferred to a future ETL milestone |
| future | ETL-INC-F03: multi-column / composite watermarks | deferred to a future ETL milestone |
| future | ETL-INC-F04: advisory-lock concurrency for `append` + incremental | deferred to a future ETL milestone |
| future | ETL-INC-F05: CDC / WAL-based change capture | deferred to a future ETL milestone |

## Session Continuity

Last session: 2026-06-23T16:35:30Z
Stopped at: Completed 33-02-PLAN.md (docs rewrite: timescaledb.md + api-reference.md + README)
Resume file: .planning/phases/33-release-v0-8-0/33-03-PLAN.md
Next action: /gsd-execute-phase 33 (Plan 03 — quality gates + human-gated tag/publish)

## Operator Next Steps

- Execute Phase 33 Plan 03 (quality gates + tag + publish) with `/gsd-execute-phase 33`
