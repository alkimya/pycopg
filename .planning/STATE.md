---
gsd_state_version: 1.0
milestone: v0.9.0
milestone_name: "**Goal**: v0.9.0 is published to PyPI with all quality gates green, documentation updated, and a clean-venv smoke confirming the new surface is importable and functional"
status: planning
stopped_at: Phase 34 context gathered
last_updated: "2026-06-24T14:40:13.269Z"
last_activity: 2026-06-24 — Roadmap created (Phases 34-36, 15 requirements mapped)
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-23 after v0.8.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** v0.9.0 — CRUD ergonomique + introspection enrichie (Phase 34 next)

## Current Position

Phase: 34 — CRUD Ergonomics (not started)
Plan: —
Status: Roadmap created; ready to plan Phase 34
Last activity: 2026-06-24 — Roadmap created (Phases 34-36, 15 requirements mapped)

Progress: `░░░░░░░░░░` 0% (0/3 phases)

## Performance Metrics

**Gates (v0.8.0 ship — baseline for v0.9.0):**

- Coverage ratchet: ≥94% (measured 95.11% at v0.8.0 ship)
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green (no deprecated stubs left after alias removal)

**v0.9.0 phases:**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 34. CRUD Ergonomics | TBD | 0 | Not started |
| 35. Schema Introspection | TBD | 0 | Not started |
| 36. Release v0.9.0 | TBD | 0 | Not started |

## Accumulated Context

### Decisions

**Locked at cadrage (2026-06-24):**

- Both feature families (CRUD + introspection) in one milestone — low risk, additive
- CRUD helpers land on the flat transactional core next to `upsert_many`/`insert_many`/`fetch_one`/`fetch_val`; NO `db.meta.*` carve
- Introspection helpers extend existing `db.schema.*` (`SchemaAccessor`/`AsyncSchemaAccessor` in `pycopg/schema.py`) — purely additive, no new accessor, no deprecation cycle
- `where=` predicate convention: dict of equality conditions (`{col: val}`) → AND-ed equality; columns validated via `validate_identifiers`; values bound as `%s`
- Builder-pur + accessor pattern: `validate_identifiers` first, user values as `%s`, pure `(sql, params)` builders, lazy accessor, full sync/async parity verified by `test_accessor_parity`
- Zero new runtime dependencies; CHANGELOG `[0.9.0]` Added-only (no MIGRATION guide needed)
- Release human-gated at the irreversible PyPI publish step (project convention)

### Pending Todos

None — start Phase 34 with `/gsd-plan-phase 34`.

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — fixture-isolation bug, not v0.9.0 code; use `-o addopts=""` for targeted runs.
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
| v2 | CRUD-F01: raw-SQL escape hatch for `where=` | deferred from v0.9.0 cadrage |
| v2 | CRUD-F02: `paginate` keyset/cursor pagination | deferred from v0.9.0 cadrage |
| v2 | CRUD-F03: `paginate` page-envelope with total count + has_next | deferred from v0.9.0 cadrage |
| v2 | INTRO-F01: `describe` output as rich dataclass / DataFrame rendering | deferred from v0.9.0 cadrage |
| v2 | INTRO-F02: `materialized_views()` and per-view column introspection | deferred from v0.9.0 cadrage |

## Session Continuity

Last session: 2026-06-24T14:40:13.241Z
Stopped at: Phase 34 context gathered
Resume file: .planning/phases/34-crud-ergonomics/34-CONTEXT.md
Next action: /gsd-plan-phase 34
