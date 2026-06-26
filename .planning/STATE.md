---
gsd_state_version: 1.0
milestone: v0.10.0
milestone_name: Durcissement & Performance
status: executing
stopped_at: Phase 37 Plan 04 complete
last_updated: "2026-06-26T07:45:00Z"
last_activity: 2026-06-26 -- Phase 37 Plan 04 executed (DEBT-05 TableNotFound raise site + DEBT-03a advisory fixes)
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 5
  completed_plans: 4
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-25 after v0.9.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Phase 37 — dette-audit

## Current Position

Phase: 37 (dette-audit) — EXECUTING
Plan: 5 of 5
Status: Ready to execute
Last activity: 2026-06-26 -- Phase 37 Plan 04 complete (DEBT-05 TableNotFound raise site + DEBT-03a advisory fixes)

Progress: [ Phase 37 · Phase 38 · Phase 39 · Phase 40 ] — 0/4 complete

## Performance Metrics

**Gates (v0.9.0 ship — baseline for v0.10.0):**

- Coverage ratchet: ≥94% (measured 94.11% at v0.9.0 ship) — target: ≥95% at v0.10.0 ship
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green

**v0.10.0 phases (current milestone):**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 37. Dette & Audit | TBD | 0 | Not started |
| 38. Performance COPY | TBD | 0 | Not started |
| 39. Couverture & Benchmarks | TBD | 0 | Not started |
| 40. Release v0.10.0 | TBD | 0 | Not started |

**v0.9.0 phases (all complete, shipped 2026-06-25):**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 34. CRUD Ergonomics | 3 | 3 | Complete (verified PASSED 13/13) |
| 35. Schema Introspection | 2 | 2 | Complete (verified PASSED 5/5) |
| 36. Release v0.9.0 | 2 | 2 | Complete (verified PASSED 9/9) |
| Phase 37 P01 | 8min | 3 tasks | 3 files |

## Accumulated Context

### Decisions

v0.10.0 cadrage (2026-06-25): split assumé — v0.10.0 = durcissement + perf (ce milestone), puis v1.0.0 = spatial v2 + gel API. Non-cassant, zéro nouvelle dépendance runtime (benchmarks en dev-group). Phase ordering: Dette & Audit first (clean base), then COPY perf (PERF-01..03 + parity), then coverage lift + benchmarks (COV-01 lands AFTER perf additions that raise coverage; PERF-04 benchmark suite lands here too), then release.

Full decision log lives in PROJECT.md (Key Decisions table).

- [Phase ?]: Phase 37 (37-01): N818 suppressed via ruff per-file-ignore on pycopg/exceptions.py, NOT renamed — public exception names, rename deferred to v1.0.0 API freeze (D-01a)
- [Phase ?]: Phase 37 (37-01): vulture + pytest-randomly added to dev-group; vulture allowlist as .py whitelist file; seed lists only the 4 public-exception false positives, scan-driven refinement deferred to Plan 05 (D-07)
- [Phase 37 P02]: D-01b applied — 34 ruff errors in tests/ fixed mechanically (W291×5, F841×24, E722×5); live run exposed 3 more F841 than RESEARCH predicted (truncated output); `uv run ruff check pycopg tests` exits 0
- [Phase 37 P02]: D-04 resolved — dead db.role_exists + db.has_extension monkeypatches removed from async_db fixture in test_sql_injection.py; live real_schema.has_extension patch preserved
- [Phase 37 P03]: D-05 resolved — test_async_transaction_fix uses yielded psycopg conn inside transaction() (avoids auto-commit ProgrammingError); RESET application_name in finally prevents pool state leak; test_create_spatial_index_name_parameter uses UUID table name; watermark spy tests annotated with DEBT-01 rationale; full suite 1332 passed deterministically under pytest-randomly
- [Phase 37 P03]: 3 pre-existing PostGIS env failures (PostGIS not installed in pycopg_test2) logged for Plan 05 disposition
- [Phase 37 P04]: DEBT-05 resolved — TableNotFound raised in truncate_table (sync + async) after table_exists guard; validate_identifiers runs first (builder-pur invariant preserved); TDD RED/GREEN committed
- [Phase 37 P04]: DEBT-03a resolved — WR-01 case-insensitive time_bucket guard (select_sql.lower()), upsert Raises docstrings (sync + async), test_sequences_async asserts f"{t}_id_seq" in seqs, import uuid de-duplicated to top-level in test_async_database.py

### Pending Todos

- Plan Phase 37 (`/gsd-plan-phase 37`)

### Blockers/Concerns

- RESOLVED (Plan 37-03): `test_async_transaction_fix`, `test_create_spatial_index_name_parameter`, ~2.7% bound-param watermark test — all DEBT-01 fixture-isolation fixes applied; full suite 1332 passed under pytest-randomly
- 3 pre-existing PostGIS env failures (test_postgis_errors.py) — PostGIS not installed in pycopg_test2; for Plan 05 disposition
- Local `pycopg_test` DB unusable since 2026-06-24 (TSDB catalog mismatch) — run DB/parity tests with `PGDATABASE=pycopg_test2`.

## Deferred Items

| Category | Item | Status |
| -------- | ---- | ------ |
| nyquist | Phase 22/23/24 VALIDATION.md left `draft` | TARGETED by NYQ-01 in Phase 37 |
| tech_debt | WR-02: dead monkeypatches in `test_sql_injection.py` async fixture | RESOLVED — Plan 37-02 (DEBT-04) |
| tech_debt | v0.8.0 review warnings: WR-01 (RESOLVED Plan 37-04), WR-03, `%`-in-structural-SQL, IN-03 `chunk_seq` | WR-01 RESOLVED; WR-03/%-SQL/IN-03 deferred to Plan 37-05 per DEBT-03b |
| tech_debt | v0.9.0 advisory: `test_sequences_async` weak assertion; `upsert` docstring missing `Raises`; dup `import uuid`/ad-hoc helpers | RESOLVED — Plan 37-04 (DEBT-03a); all 4 items closed |
| tech_debt | 4 pre-existing ruff errors (N818/W291/F841/E722) | RESOLVED — Plans 37-01+02 (DEBT-02); ruff exits 0 |
| tech_debt | `TableNotFound` exported but never raised internally | RESOLVED — Plan 37-04 (DEBT-05); raise site in truncate_table (sync + async) |
| future | TSDB-F01: `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` removal | deferred from v0.8.0 |
| future | TSDB-F02: `time_bucket` `origin`/`offset` alignment params | deferred from v0.8.0 |
| future | TSDB-F03: `compress_chunk` / `decompress_chunk` per-chunk control | deferred from v0.8.0 |
| future | TSDB-F04: `show_chunks` physical-time filters | deferred from v0.8.0 |
| future | ETL-INC-F01..F05: incremental ETL follow-ups | deferred to a future ETL milestone |
| v2 | CRUD-F01..F03, INTRO-F01..F02 | deferred from v0.9.0 cadrage |

## Session Continuity

Last session: 2026-06-26T07:45:00Z
Stopped at: Phase 37 Plan 04 complete
Resume file: .planning/phases/37-dette-audit/37-04-SUMMARY.md
Next action: `/gsd-execute-phase 37` (Plan 05)

## Operator Next Steps

- Run `/gsd-execute-phase 37` to continue Phase 37 with Plan 05
