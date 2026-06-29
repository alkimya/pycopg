---
gsd_state_version: 1.0
milestone: v1.0.0
milestone_name: Spatial v2 + gel API
status: verifying
stopped_at: Phase 43 Plan 02 complete (extent method)
last_updated: "2026-06-29T16:12:03.047Z"
last_activity: 2026-06-29
progress:
  total_phases: 7
  completed_phases: 3
  total_plans: 11
  completed_plans: 11
  percent: 43
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-27 after v0.10.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

**Current focus:** Phase 43 — spatial-v2-spatial-aggregates

## Current Position

Phase: 44
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-06-29

## Performance Metrics

**Gates at v0.10.0 ship (2026-06-26) — baseline for v1.0.0:**

- Coverage ratchet: ≥95% (measured 96.32% at v0.10.0 ship; lifted from 94 in COV-01)
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green

**v1.0.0 phases (Phases 41-47):**

| Phase | Plans | Complete | Status |
| ----- | ----- | -------- | ------ |
| 41. API Homogenization | 5 | 5 | Complete (verified PASSED 10/10; code-review CR-01 async-parity blocker found+fixed) |
| 42. Spatial v2 — Processing Helpers | 3 | 3 | Complete (verified PASSED) |
| 43. Spatial v2 — Spatial Aggregates | 3 | 1 | Executing (P01 complete: collect_geometries + union_aggregate) |
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
| Phase 41 P01 | 13m | 2 tasks | 2 files |
| Phase 41 P03 | 90 minutes | 2 tasks | 2 files |
| Phase 41 P04 | 3.5h | 3 tasks | 17 files |
| Phase 41 P05 | 30m | 2 tasks | 4 files |
| Phase 42 P01 | 6min | 3 tasks | 2 files |
| Phase 42 P02 | 18 minutes | 3 tasks | 2 files |
| Phase 42 P03 | 8 minutes | 3 tasks | 4 files |
| Phase 43 P01 | 5 minutes | 2 tasks | 2 files |
| Phase 43 P02 | 5 minutes | 2 tasks | 2 files |
| Phase 43 P03 | 5 minutes | 3 tasks | 5 files |

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

- [Phase ?]: D-04 enforced: builders get clean filter= rename (no shim); accessors get filter=/where= shim with stacklevel=2
- [Phase ?]: FREEZE-03: kw-only * enforced on all 100+ public methods across 7 accessor families + flat core (D-03)
- [Phase ?]: D2/D5 carve-out: execute/fetch_one/fetch_val/fetch_all/stream/maint.explain keep params positional (raw-SQL execution primitives)
- [Phase ?]: D3: time_bucket/time_bucket_gapfill where=→filter= with one-cycle DeprecationWarning shim (stacklevel=2)
- [Phase ?]: FREEZE-04: docs/stability.md published with SemVer contract, deprecation timeline (remove in 2.0), support matrix (pyproject.toml grounded), Stable API Contract table (FREEZE-03 audit), API stability tiers
- [Phase ?]: D-08 relaxation documented: deprecated exception aliases warn at import/access (not catch-time), PEP 562 __getattr__, intentional design recorded in MIGRATION + stability.md
- [Phase 42]: Shared _build_binary_geom_sql helper for DRY binary builders; each keeps own injection test + D-01 result column
- [Phase 43-01]: _append_tail extended with keyword-only group_by (D-03); _build_agg_geom_sql shared for collect/union_aggregate; group_by=[] raises ValueError; str->list normalize at accessor level; born-clean filter= only
- [Phase ?]: D-02: make_valid method whitelist bound through %s; D-05: simplify tolerance kw-only; D-09: structure tested live unguarded (PostGIS 3.6.4)
- [Phase ?]: D-04: build_extent_sql sees into= (exception) — one builder, one branch; extent NOT in _SCALAR_HELPERS; into='gdf' valid via box2d::geometry cast
- [Phase ?]: D-05: srid=4326 keyword-only on extent, int(srid) injection-safe, consulted only on gdf cast (T-43-03)

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

Last session: 2026-06-29T16:03:25.197Z
Stopped at: Phase 43 Plan 02 complete (extent method)
Resume file: None
Next action: Execute Phase 43 Plan 02 (extent method)

## Operator Next Steps

- Execute Phase 43 Plan 02 with `/gsd-execute-phase 43 02`
