---
gsd_state_version: 1.0
milestone: v1.0.0
milestone_name: Spatial v2 + gel API
status: Roadmap ready
stopped_at: Phase 41 context gathered
last_updated: "2026-06-28T10:13:15.565Z"
last_activity: "2026-06-27 — Roadmap created (7 phases: 41-47, 24 requirements mapped)"
progress:
  total_phases: 7
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-27 after v0.10.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

**Current focus:** v1.0.0 Spatial v2 + gel API — roadmap created, ready to plan Phase 41

## Current Position

Phase: Not started (roadmap defined — Phase 41 next)
Plan: —
Status: Roadmap ready
Last activity: 2026-06-27 — Roadmap created (7 phases: 41-47, 24 requirements mapped)

## Performance Metrics

**Gates at v0.10.0 ship (2026-06-26) — baseline for v1.0.0:**

- Coverage ratchet: ≥95% (measured 96.32% at v0.10.0 ship; lifted from 94 in COV-01)
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green

**v1.0.0 phases (Phases 41-47):**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 41. API Homogenization | ? | 0 | Not started |
| 42. Spatial v2 — Processing Helpers | ? | 0 | Not started |
| 43. Spatial v2 — Spatial Aggregates | ? | 0 | Not started |
| 44. Spatial v2 — Serialization + MVT | ? | 0 | Not started |
| 45. API Completeness Gaps + Structured Logging | ? | 0 | Not started |
| 46. mypy Strict + py.typed Gate | ? | 0 | Not started |
| 47. Release v1.0.0 | ? | 0 | Not started |

**v0.10.0 phases (all complete, shipped 2026-06-26):**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 37. Dette & Audit | 5 | 5 | Complete (verified PASSED 5/5) |
| 38. Performance COPY | 3 | 3 | Complete (verified PASSED 4/4) |
| 39. Couverture & Benchmarks | 2 | 2 | Complete (verified PASSED 7/7) |
| 40. Release v0.10.0 | 2 | 2 | Complete (shipped — tag + OIDC publish + smoke) |

## Accumulated Context

### Decisions

v0.10.0 SHIPPED + CLOSED 2026-06-26/27: internal hardening + COPY performance, no public API change. Split decision (2026-06-25): v0.10.0 = durcissement + perf, then v1.0.0 = spatial v2 + gel API. Full v0.10.0 decision log lives in PROJECT.md (Key Decisions table) and the per-phase `*-SUMMARY.md` / `37-DECISIONS.md` files.

**v1.0.0 roadmap locked (2026-06-27):** 7 phases (41-47), dependency-fixed build order confirmed by research/SUMMARY.md.

- Phase 41 (Homogenization) MUST precede all spatial work — new builders adopt `filter=` from day one and exception renames precede mypy-strict.
- Phases 42-44 are sequential spatial sub-phases: processing → aggregates → serialization/MVT.
- Phase 45 (API gaps + logging) is purely additive to the flat core; no dependency on spatial.py.
- Phase 46 (mypy strict) is LAST before release — all renaming, new builders, and signatures must be complete first. Start by measuring error count.
- Phase 47 (Release) closes the milestone.

**Key cross-cutting constraints for all spatial phases:** `validate_identifiers` is line 1 of every new SQL builder + a dedicated injection test (the v0.10.0 COPY-rewrite green-suite lesson). Full sync/async parity enforced by `test_accessor_parity`. Zero new runtime dependencies.

### Pending Todos

- None — roadmap created. Next: `/gsd-plan-phase 41`.

### Blockers/Concerns

- Local `pycopg_test` DB unusable since 2026-06-24 (TSDB catalog mismatch) — run DB/parity tests with `PGDATABASE=pycopg_test2` (PostGIS now enabled on it). Carries into v1.0.0.
- v0.10.0 non-blocking carry-forward: phases 38/39 Nyquist VALIDATION.md draft; `vulture` not wired into Makefile/CI; DEBT-03b + copy_insert session-bypass deferred to v1.0.0.
- Phase 46 (mypy strict) error count unknown until Phase 46 starts — measure first. If >100 errors, plan as multi-session.
- Phase 44 (as_mvt) MVT decode strategy in CI must be decided at plan time (structural byte check vs. mapbox-vector-tile parser).

## Deferred Items

| Category | Item | Status |
| -------- | ---- | ------ |
| nyquist | Phases 38/39 VALIDATION.md draft (`nyquist_compliant: false` for 38) | NEW (v0.10.0 audit) — functional VERIFICATION.md PASSED with live evidence; clear retroactively via `/gsd-validate-phase 38` (and `39`) |
| toolchain | AUDIT-02: `vulture` not wired into Makefile/CI target | NEW (v0.10.0 audit) — `vulture_whitelist.py` + dev-dep exist but must be run manually; dead-code scan can't drift-detect |
| tech_debt | DEBT-03b + 37-REVIEW WR-03 `copy_insert` session bypass | **CLOSED-with-justification, deferred to v1.0.0** — WR-03 INTERVAL-literal, %/structural-SQL UX, IN-03 `chunk_seq`, copy_insert session semantics; recorded in `37-DECISIONS.md` §1/§2 |
| process | Phase 40 (release) has no VERIFICATION.md | Verified via the ship gate (tag + OIDC publish + clean-venv smoke) — release-phase convention, not a coverage gap |
| future | TSDB-F01: `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` removal | deferred from v0.8.0 |
| future | TSDB-F02: `time_bucket` `origin`/`offset` alignment params | deferred from v0.8.0 |
| future | TSDB-F03: `compress_chunk` / `decompress_chunk` per-chunk control | deferred from v0.8.0 |
| future | TSDB-F04: `show_chunks` physical-time filters | deferred from v0.8.0 |
| future | ETL-INC-F01..F05: incremental ETL follow-ups | deferred to a future ETL milestone |
| v2 | CRUD-F01..F03, INTRO-F01..F02 | deferred from v0.9.0 cadrage |
| v2 | SPAT-F01: gridSize precision on overlay functions (GEOS ≥ 3.9) | deferred from v1.0.0 cadrage |
| v2 | RASTER-F01: PostGIS raster I/O | deferred post-1.0 per 2026-06-27 cadrage |

## Session Continuity

Last session: 2026-06-28T09:40:49.986Z
Stopped at: Phase 41 context gathered
Resume file: .planning/phases/41-api-homogenization/41-CONTEXT.md
Next action: Plan Phase 41 with `/gsd-plan-phase 41`

## Operator Next Steps

- Start Phase 41 with `/gsd-plan-phase 41`
