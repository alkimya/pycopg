---
gsd_state_version: 1.0
milestone: v0.9.0
milestone_name: "**Goal**: v0.9.0 is published to PyPI with all quality gates green, documentation updated, and a clean-venv smoke confirming the new surface is importable and functional"
status: verifying
stopped_at: Completed 35-02-describe-consolidation-PLAN.md
last_updated: "2026-06-25T13:02:45.282Z"
last_activity: 2026-06-25 -- Phase 36 execution started
progress:
  total_phases: 3
  completed_phases: 3
  total_plans: 7
  completed_plans: 7
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-23 after v0.8.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Phase 36 — release-v090

## Current Position

Phase: 36 (release-v090) — EXECUTING
Plan: 2 of 2
Status: Phase complete — ready for verification
Last activity: 2026-06-25 -- Phase 36 execution started

Progress: `██████░░░░` 67% (2/3 phases)

## Performance Metrics

**Gates (v0.8.0 ship — baseline for v0.9.0):**

- Coverage ratchet: ≥94% (measured 95.11% at v0.8.0 ship)
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green (no deprecated stubs left after alias removal)

**v0.9.0 phases:**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 34. CRUD Ergonomics | 3 | 3 | Complete |
| 35. Schema Introspection | 2 | 2 | Complete (verified PASSED) |
| 36. Release v0.9.0 | TBD | 0 | Not started |
| Phase 36 P01 | 60m | 5 tasks | 17 files |
| Phase 36-release-v090 P02 | 8min | 3 tasks | 0 files |

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
- [Phase ?]: _build_where_dict placed after _build_select_sql in QueryMixin — validate_identifiers-first + values-as-params pattern (T-34-01, T-34-02)
- [Phase ?]: upsert/delete_where/update_where added to both Database and AsyncDatabase with identical signatures, empty-where guard, RETURNING * for upsert, SET-then-WHERE param order
- [Phase 34-03]: exists/count/paginate/fetch_all added flat on both classes — ValueError-on-empty-where for exists (pre-cursor), count None-where routes around builder, order_by columns validated, dict_row documented in fetch_all docstring (CRUD-07 part a)
- [Phase ?]: describe composes table_info/primary_key/foreign_keys/list_indexes into one flat 4-key dict with no new SQL (D-04 anti-drift guarantee; INTRO-05/INTRO-06)
- [Phase 36 discuss 2026-06-25]: release v0.9.0 = 2 plans (36-01 content: pyproject bump + CHANGELOG [0.9.0] Added-only + docs of 12 new methods + README counts + cosmetic-debt cleanup; 36-02 release: gates + tag + OIDC publish human-gated + clean-venv smoke). D-36-01: bump ONLY pyproject (single canonical source; __version__ dynamic — never hardcode); ROADMAP criterion #1 corrected. D-36-03: CHANGELOG signature-drift guard (v0.8.0 caught 4). D-36-04: cosmetic debt (CLAUDE.md Version line, dead aliases xref, WR-01/WR-03) SOLDERED in 36-01 per user. See 36-CONTEXT.md.
- [Phase ?]: Version bump 0.8.0->0.9.0
- [Phase ?]: 36-01 gate baseline recorded for 36-02 re-confirm

### Pending Todos

None — Phases 34 + 35 complete. Next: plan Phase 36 (Release v0.9.0) with `/gsd-plan-phase 36`.

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

Last session: 2026-06-25T13:02:27.022Z
Stopped at: Completed 35-02-describe-consolidation-PLAN.md
Resume file: None
Next action: Phase 35 complete + verified — proceed to Phase 36 (Release v0.9.0) with /gsd-plan-phase 36
