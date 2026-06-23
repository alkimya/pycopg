---
gsd_state_version: 1.0
milestone: v0.8.0
milestone_name: TimescaleDB avancé
status: Awaiting next milestone
stopped_at: Milestone v0.8.0 closed and archived — awaiting /gsd-new-milestone (v0.9.0)
last_updated: "2026-06-23T19:41:34.591Z"
last_activity: 2026-06-23 — Milestone v0.8.0 completed and archived
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 11
  completed_plans: 11
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-23 after v0.8.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Planning next milestone (v0.9.0 CRUD ergonomique + introspection — candidate)

## Current Position

Phase: Milestone v0.8.0 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-23 — Milestone v0.8.0 completed and archived

## Performance Metrics

**Gates (v0.8.0 ship — baseline for v0.9.0):**

- Coverage ratchet: ≥94% (measured 95.11% at v0.8.0 ship)
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green (no deprecated stubs left after alias removal)

**v0.8.0 phases:**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 30. Chunk Management & Partitioning | 3 | 3 | COMPLETE (46 tests, TS-ADV-10, cov 94.96%) |
| 31. Continuous Aggregate Lifecycle | 3 | 3 | COMPLETE (11 policy tests, TS-ADV-03, cov 95.05%) |
| 32. Query Helpers & Parity Verification | 2 | 2 | COMPLETE (TS-ADV-06/07/10, cov 95.11%) |
| 33. Release v0.8.0 | 3 | 3 | COMPLETE (4 gates PASS, OIDC publish run 28044147070, v0.8.0 live PyPI 2026-06-23) |
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

v0.8.0 milestone closed — the full decision log (scope + 7 v0.8.0 Key Decisions incl. the D-08 license reversal) lives in `.planning/PROJECT.md` Key Decisions and `.planning/milestones/v0.8.0-ROADMAP.md`. Cleared here at milestone close.

### Pending Todos

None — v0.8.0 closed; run `/gsd-new-milestone` to scope v0.9.0.

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — fixture-isolation bug, not v0.8.0 code; use `-o addopts=""` for targeted runs.
- One ~2.7% flaky bound-param test surfaced during Phase 28 — watch for re-flake.

## Deferred Items

| Category | Item | Status |
| -------- | ---- | ------ |
| nyquist | Phase 22/23/24 VALIDATION.md left `draft` | deferred from v0.6.0 — verified PASSED via VERIFICATION.md |
| tech_debt | WR-02: dead monkeypatches in `test_sql_injection.py` async fixture | housekeeping; non-blocking |
| tech_debt | `CLAUDE.md` "Version" line stale (reads v0.5.0; actual v0.8.0) | cosmetic doc lag, carried since v0.6.0 |
| tech_debt | Stale `pycopg.aliases` Sphinx xref in accessor docstrings (IN-01/IN-02) | cosmetic; `aliases.py` deleted v0.7.0 |
| tech_debt | v0.8.0 review warnings: WR-01 case-sensitive `time_bucket(` guard, WR-03 INTERVAL-literal-vs-`%s`, `%`-in-structural-SQL, IN-03 `chunk_seq` helper | advisory, not blocking |
| future | TSDB-F01: `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` removal | deferred from v0.8.0 |
| future | TSDB-F02: `time_bucket` `origin`/`offset` alignment params | deferred from v0.8.0 |
| future | TSDB-F03: `compress_chunk` / `decompress_chunk` per-chunk control | deferred from v0.8.0 |
| future | TSDB-F04: `show_chunks` physical-time (`created_before`/`after`) filters | deferred from v0.8.0 |
| future | ETL-INC-F01: `initial_watermark` first-run bounding | deferred to a future ETL milestone |
| future | ETL-INC-F02: configurable `>` vs `>=` boundary | deferred to a future ETL milestone |
| future | ETL-INC-F03: multi-column / composite watermarks | deferred to a future ETL milestone |
| future | ETL-INC-F04: advisory-lock concurrency for `append` + incremental | deferred to a future ETL milestone |
| future | ETL-INC-F05: CDC / WAL-based change capture | deferred to a future ETL milestone |

## Session Continuity

Last session: 2026-06-23 — milestone v0.8.0 closed and archived
Stopped at: Milestone v0.8.0 closed (ROADMAP collapsed, REQUIREMENTS archived + removed, PROJECT/RETROSPECTIVE evolved)
Resume file: None — milestone complete
Next action: /gsd-new-milestone (v0.9.0 CRUD ergonomique + introspection — candidate)

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
