---
gsd_state_version: 1.0
milestone: v0.10.0
milestone_name: Durcissement & Performance
status: planning
stopped_at: Phase 37 context gathered
last_updated: "2026-06-25T17:23:04.877Z"
last_activity: 2026-06-25 — v0.10.0 roadmap created (4 phases, 15 requirements mapped)
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-25 after v0.9.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** v0.10.0 "Durcissement & Performance" — Phases 37-40. Start with `/gsd-plan-phase 37`.

## Current Position

Phase: 37 (not started)
Plan: —
Status: Roadmap defined — ready to plan Phase 37
Last activity: 2026-06-25 — v0.10.0 roadmap created (4 phases, 15 requirements mapped)

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

## Accumulated Context

### Decisions

v0.10.0 cadrage (2026-06-25): split assumé — v0.10.0 = durcissement + perf (ce milestone), puis v1.0.0 = spatial v2 + gel API. Non-cassant, zéro nouvelle dépendance runtime (benchmarks en dev-group). Phase ordering: Dette & Audit first (clean base), then COPY perf (PERF-01..03 + parity), then coverage lift + benchmarks (COV-01 lands AFTER perf additions that raise coverage; PERF-04 benchmark suite lands here too), then release.

Full decision log lives in PROJECT.md (Key Decisions table).

### Pending Todos

- Plan Phase 37 (`/gsd-plan-phase 37`)

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — fixture-isolation bug, targeted by DEBT-01 in Phase 37.
- One ~2.7% flaky bound-param test surfaced during Phase 28 — also targeted by DEBT-01.
- Local `pycopg_test` DB unusable since 2026-06-24 (TSDB catalog mismatch) — run DB/parity tests with `PGDATABASE=pycopg_test2`.

## Deferred Items

| Category | Item | Status |
| -------- | ---- | ------ |
| nyquist | Phase 22/23/24 VALIDATION.md left `draft` | TARGETED by NYQ-01 in Phase 37 |
| tech_debt | WR-02: dead monkeypatches in `test_sql_injection.py` async fixture | TARGETED by DEBT-04 in Phase 37 |
| tech_debt | v0.8.0 review warnings: WR-01, WR-03, `%`-in-structural-SQL, IN-03 `chunk_seq` | TARGETED by DEBT-03 in Phase 37 |
| tech_debt | v0.9.0 advisory: `test_sequences_async` weak assertion; `upsert` docstring missing `Raises`; dup `import uuid`/ad-hoc helpers | TARGETED by DEBT-03 in Phase 37 |
| tech_debt | 4 pre-existing ruff errors (N818/W291/F841/E722) | TARGETED by DEBT-02 in Phase 37 |
| tech_debt | `TableNotFound` exported but never raised internally | TARGETED by DEBT-05 in Phase 37 |
| future | TSDB-F01: `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` removal | deferred from v0.8.0 |
| future | TSDB-F02: `time_bucket` `origin`/`offset` alignment params | deferred from v0.8.0 |
| future | TSDB-F03: `compress_chunk` / `decompress_chunk` per-chunk control | deferred from v0.8.0 |
| future | TSDB-F04: `show_chunks` physical-time filters | deferred from v0.8.0 |
| future | ETL-INC-F01..F05: incremental ETL follow-ups | deferred to a future ETL milestone |
| v2 | CRUD-F01..F03, INTRO-F01..F02 | deferred from v0.9.0 cadrage |

## Session Continuity

Last session: 2026-06-25T17:23:04.854Z
Stopped at: Phase 37 context gathered
Resume file: .planning/phases/37-dette-audit/37-CONTEXT.md
Next action: `/gsd-plan-phase 37`

## Operator Next Steps

- Run `/gsd-plan-phase 37` to plan Phase 37: Dette & Audit
