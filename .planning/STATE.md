---
gsd_state_version: 1.0
milestone: v0.10.0
milestone_name: Durcissement & Performance
status: planning
last_updated: "2026-06-25T15:19:01.966Z"
last_activity: 2026-06-25
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-25 after v0.9.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Planning next milestone (v1.0.0 "Spatial v2 + stabilisation API") — start with `/gsd-new-milestone`.

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-06-25 — Milestone v0.10.0 started

## Performance Metrics

**Gates (v0.9.0 ship — baseline for v1.0.0):**

- Coverage ratchet: ≥94% (measured 94.11% at v0.9.0 ship)
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green

**v0.9.0 phases (all complete, shipped 2026-06-25):**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 34. CRUD Ergonomics | 3 | 3 | Complete (verified PASSED 13/13) |
| 35. Schema Introspection | 2 | 2 | Complete (verified PASSED 5/5) |
| 36. Release v0.9.0 | 2 | 2 | Complete (verified PASSED 9/9) |

## Accumulated Context

### Decisions

Full decision log lives in PROJECT.md (Key Decisions table — 5 v0.9.0 rows added at close + the v0.6.0 `db.meta.*` decision flipped to ✓ Resolved). v0.9.0 in one line: 12 additive methods at full parity via one shared `_build_where_dict` builder + `describe` pure-composition; introspection stays on `db.schema.*` (no `db.meta.*` carve); `__version__` dynamic; human-gated OIDC publish.

### Pending Todos

None — milestone v0.9.0 closed. Next: `/gsd-new-milestone` (v1.0.0).

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — fixture-isolation bug, not v0.9.0 code; use `-o addopts=""` for targeted runs. (Carried; not a regression.)
- One ~2.7% flaky bound-param test surfaced during Phase 28 — watch for re-flake.
- Local `pycopg_test` DB unusable since 2026-06-24 (TSDB catalog mismatch) — run DB/parity tests with `PGDATABASE=pycopg_test2`.

## Deferred Items

| Category | Item | Status |
| -------- | ---- | ------ |
| nyquist | Phase 22/23/24 VALIDATION.md left `draft` | deferred from v0.6.0 — verified PASSED via VERIFICATION.md |
| tech_debt | WR-02: dead monkeypatches in `test_sql_injection.py` async fixture | housekeeping; non-blocking |
| tech_debt | v0.8.0 review warnings: WR-01 case-sensitive `time_bucket(` guard, WR-03 INTERVAL-literal-vs-`%s`, `%`-in-structural-SQL, IN-03 `chunk_seq` helper | advisory, not blocking |
| tech_debt | v0.9.0 advisory: `test_sequences_async` weak assertion (36 WR-01); `upsert` docstring missing `Raises` (34 IN-03); duplicated `import uuid`/ad-hoc helpers in async tests (34 IN-04) | cosmetic; non-blocking |
| tech_debt | 4 pre-existing ruff errors (N818/W291/F841/E722) in files not modified this milestone | not a quality gate |
| ~~resolved~~ | ~~`CLAUDE.md` "Version" line stale~~ + ~~`pycopg.aliases` Sphinx xref in accessor docstrings~~ | RESOLVED in v0.9.0 (Phase 36 D-36-04) |
| future | TSDB-F01: `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` removal | deferred from v0.8.0 |
| future | TSDB-F02: `time_bucket` `origin`/`offset` alignment params | deferred from v0.8.0 |
| future | TSDB-F03: `compress_chunk` / `decompress_chunk` per-chunk control | deferred from v0.8.0 |
| future | TSDB-F04: `show_chunks` physical-time (`created_before`/`after`) filters | deferred from v0.8.0 |
| future | ETL-INC-F01: `initial_watermark` first-run bounding | deferred to a future ETL milestone |
| future | ETL-INC-F02: configurable `>` vs `>=` boundary | deferred to a future ETL milestone |
| future | ETL-INC-F03: multi-column / composite watermarks | deferred to a future ETL milestone |
| future | ETL-INC-F04: advisory-lock concurrency for `append` + incremental | deferred to a future ETL milestone |
| future | ETL-INC-F05: CDC / WAL-based change capture | deferred to a future ETL milestone |
| v2 | CRUD-F01: raw-SQL escape hatch for `where=` | deferred from v0.9.0 cadrage |
| v2 | CRUD-F02: `paginate` keyset/cursor pagination | deferred from v0.9.0 cadrage |
| v2 | CRUD-F03: `paginate` page-envelope with total count + has_next | deferred from v0.9.0 cadrage |
| v2 | INTRO-F01: `describe` output as rich dataclass / DataFrame rendering | deferred from v0.9.0 cadrage |
| v2 | INTRO-F02: `materialized_views()` and per-view column introspection | deferred from v0.9.0 cadrage |

## Session Continuity

Last session: 2026-06-25 — milestone v0.9.0 closed + archived
Stopped at: Milestone v0.9.0 complete (3 phases, 7 plans, audit PASSED, integration WIRED)
Resume file: None
Next action: Start the next milestone (v1.0.0 "Spatial v2 + stabilisation API") with /gsd-new-milestone

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
