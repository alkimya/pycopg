---
gsd_state_version: 1.0
milestone: v1.1.0
milestone_name: Follow-ups additifs (TimescaleDB · ETL incrémental · CRUD/introspection)
status: planning
last_updated: "2026-07-02T17:49:06.216Z"
last_activity: 2026-07-02
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-02 after v1.0.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

**Current focus:** Planning next milestone. v1.0.0 "Spatial v2 + gel API" SHIPPED + CLOSED 2026-07-02 (all 7 phases 41–47 archived; public API frozen under SemVer 1.0). No active feature milestone — next work is additive 1.x point releases (ready 1.0.1 doc/metadata patch, then deferred TSDB-F/ETL-INC-F/CRUD-F/INTRO-F/SPAT-F/RASTER-F families). Next: `/gsd-new-milestone`.

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-07-02 — Milestone v1.1.0 started

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
| 43. Spatial v2 — Spatial Aggregates | 3 | 3 | Complete (verified PASSED; collect/union_aggregate + extent dual into=) |
| 44. Spatial v2 — Serialization + MVT | 3 | 3 | Complete (verified PASSED 19/19; as_geojson/as_text/as_mvt) |
| 45. API Completeness Gaps + Structured Logging | 4 | 4 | Complete (verified PASSED 6/6; code-review 5 warn → WR-01..04 fixed, WR-05+IN-* deferred) |
| 46. mypy Strict + py.typed Gate | 7 | 7 | Complete (46-01 strict config live, 46-02 foundation tier 356->303, 46-03 spatial.py 303->187 via 96 @overload stubs, 46-04 timescale.py+schema.py 187->144 via 12 @overload stubs, 46-05 etl.py+pool.py 144->76 + steps no-redef/resize unused-coroutine bugs fixed, 46-06 database.py+async_database.py 76->0, 46-07 terminal verification + CI blocking flip; FREEZE-05 complete) |
| 47. Release v1.0.0 | 3 | 3 | Complete (verified PASSED 9/9; 5 gates green cov 96.45%, annotated tag v1.0.0 pushed, OIDC publish workflow green, clean-venv smoke ok — pycopg 1.0.0 LIVE on PyPI; code-review 0 crit/2 warn: WR-01 docs still show deprecated exception names, WR-02 pyproject Beta classifier on 1.0.0 + IN-01 stale CLAUDE.md version — all non-blocking post-1.0 follow-ups) |

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
| Phase 44 P01 | 5min | 2 tasks | 2 files |
| Phase 44 P02 | 7min | 3 tasks | 2 files |
| Phase 44 P03 | 4min | 2 tasks | 5 files |
| Phase 45 P01 | 6m | 2 tasks | 4 files |
| Phase 45 P02 | 46 | 2 tasks | 4 files |
| Phase 45 P03 | 9min | 2 tasks | 5 files |
| Phase 45 P04 | 12 | 2 tasks | 6 files |
| Phase 46 P01 | 6min | 2 tasks | 2 files |
| Phase 46 P02 | 35min | 2 tasks | 9 files |
| Phase 46 P03 | ~50min | 2 tasks | 1 files |
| Phase 46 P04 | ~25min | 2 tasks | 2 files |
| Phase 46 P05 | ~40min | 2 tasks | 3 files |
| Phase 46 P06 | ~35min | 2 tasks | 4 files |
| Phase 46 P07 | 12min | 3 tasks | 1 files |
| Phase 47 P01 | 5min | 3 tasks | 4 files |
| Phase 47 P02 | 15min | 3 tasks | 5 files |
| Phase 47 P03 | 12min | 4 tasks | 0 files (gates + tag + OIDC publish + smoke) |

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
- [Phase ?]: Phase 44-01: D-06 options bitmask for ST_AsGeoJSON (include_bbox bit1 + include_crs bit2), frozen geojson result key
- [Phase ?]: Phase 44-01: D-07 conditional ST_AsText precision — None=one-arg full precision, set=two-arg; frozen wkt result key
- [Phase ?]: Phase 44-01: D-09 born-clean filter= only (no where= shim) + D-10 same-change KIND parity confirmed on as_geojson/as_text
- [Phase 44-02]: D-03 enforced: build_mvt_sql always emits ST_Transform→ST_AsMVTGeom→ST_AsMVT pipeline; outer q.geom_mvt IS NOT NULL; no raw-geometry shortcut; AS mvt alias; params=[layer_name, ext] only
- [Phase 44-02]: D-05: _run_mvt/_arun_mvt always return bytes; memoryview coerced, None→b""; never None/memoryview
- [Phase 44-02]: D-09 + no _SCALAR_HELPERS + no _HELPER_CALLS: as_mvt born-clean, bytes-only, dedicated runners; criterion #2 live proof via pure-Python _count_mvt_features decoder
- [Phase 44-03]: SPAT2-13 finalized: test_spatial_serialization_surface (named frozenset) + test_accessor_parity (auto-extend) + test_accessor_parameter_kind_parity (KIND-parity) assert full P42+P43+P44 surface on both accessors; docs/api-reference + stability + spatial guide + README all updated with born-clean filter= (22→25 methods)
- [Phase ?]: 45-01 logging substrate
- [Phase ?]: D-03 honored: transaction(isolation_level=) inside active session raises RuntimeError (TXN-01)
- [Phase ?]: D-02 two savepoint surfaces: standalone savepoint() + transaction(savepoint_name=) via psycopg native API (TXN-02)
- [Phase ?]: PARAM-01 D-12: params annotation widened to Params alias on 5 methods x 2 classes; no translator built; dict %(name)s works natively via psycopg
- [Phase ?]: HEALTH-01 D-05/D-07: health() never-raises on all four classes; pooled adds pool_stats from self.stats @property; server_version via _decode_server_version; wrapped in log_operation
- [Phase ?]: RESEARCH Q1 resolved: to_dataframe uses SQLAlchemy :name colon style; divergence documented in docstring + confirmed by test_to_dataframe_named_style
- [Phase ?]: D-09 LOG-01 complete: 13 coarse instrumentation sites wrapped; rows=None fallback for etl.run and migrations.migrate; rows=len(df/gdf) for COPY paths
- [Phase ?]: D-04 mypy strict config-as-source-of-truth: strict=true + warn_unreachable=true, no CLI --strict; sqlalchemy/psycopg/psycopg_pool overrides removed after live verify; geoalchemy2/tenacity kept (unstubbed, confirmed load-bearing)
- [Phase ?]: interrogate ignore-overloaded-functions + coverage @overload exclude_lines pre-configured ahead of ~48 later @overload stubs (spatial/timescale); both fail-under=95 bars held
- [Phase 46]: no-implicit-reexport audit: zero existing transitive re-export chains found across all 18 pycopg modules; __all__ added to all 10 foundation modules per plan requirement + future-proofing
- [Phase 46]: D-01 narrow ignores: backup.py isinstance(data,str) branches kept as defensive runtime guards against psycopg Copy.__iter__ Iterator[Buffer]-only stub; config.py load_dotenv no-op fallback signature intentionally narrower than python-dotenv real stub
- [Phase ?]: Phase 46-03: @overload triplet pattern (Literal[rows]/Literal[gdf]/str fallback) on all 16 polymorphic into= methods x 2 classes (96 stubs, symmetric); scalar helpers narrowed via cast() not overloaded; zero # type: ignore needed in spatial.py
- [Phase ?]: [Phase 46-04]: assert-for-exclusivity-narrowing reused for add_dimension's number_partitions/chunk_interval Optional narrowing (sync+async); @overload triplet pattern (Literal[df]/Literal[rows]/str fallback) applied to timescale time_bucket/time_bucket_gapfill x2 classes (12 stubs, symmetric); schema.py pure D-03 (no into= polymorphism)
- [Phase 46]: [Phase 46-05]: steps [no-redef] fixed as duplicate-annotation-only (dry_run branch always returns before the second assignment is reachable, never a runtime shadow); [unused-coroutine] real bug found+fixed at pool.py:574 (not etl.py as plan pointer suggested) -- AsyncPooledDatabase.resize() was sync calling an async psycopg_pool coroutine without await, silently never resizing
- [Phase 46]: Phase 46-06: database.py + async_database.py annotated to zero mypy strict errors (76 -> 0 package-wide); assert-for-exclusivity-narrowing extended to to_dataframe/to_geodataframe sql XOR guard; cast() at pandas to_sql()/geopandas read_postgis() unstubbed edges; __init__.py:56 gap-closure (__getattr__ -> type via cast); backup.py stale unused-ignore removed as Rule-1 side effect of cursor() typing. FREEZE-05 satisfied.
- [Phase 46]: Phase 46-07: whole-package mypy --strict verified 0 errors/18 files, coverage held 96.45% on pycopg_test3, interrogate 100%, py.typed truthful (only geoalchemy2/tenacity overrides remain); CI mypy step flipped from continue-on-error to a blocking gate (D-04) -- FREEZE-05 complete, Phase 46 fully done 7/7
- [Phase ?]: Phase 47 Plan 02: version bumped to 1.0.0 (pyproject.toml/docs/conf.py/uv.lock); pycopg/__init__.py stays dynamic via importlib.metadata
- [Phase ?]: Phase 47 Plan 02: CHANGELOG [1.0.0] assembled code-exact (D-36-03 guard) from Phases 41-46; MIGRATION.md final-reviewed with a 5th breaking-change item (mypy-strict-blocking, non-runtime) added for CHANGELOG-breaking-set symmetry + type-checking consumer note

### Pending Todos

- **1.0.1 patch (ready now, non-blocking — baked into published 1.0.0):** WR-01 `docs/api-reference.md` still shows deprecated exception names (`ExtensionNotAvailable`/`TableNotFound`/`InvalidIdentifier`) as the import surface (trips `-W error::DeprecationWarning`); WR-02 `pyproject.toml:25` classifier `Development Status :: 4 - Beta` → `5 - Production/Stable`; IN-01 `CLAUDE.md:13` Version line stale (reads v0.9.0).
- Optional: clear Nyquist VALIDATION.md artifact gaps via `/gsd-validate-phase 42|44|45` (draft) and `46|47` (missing) — functional VERIFICATION.md PASSED for all; discovery-only, see v1.0.0-MILESTONE-AUDIT.md.
- Next milestone: `/gsd-new-milestone` (or ship the 1.0.1 patch directly first).

### Blockers/Concerns

- **Local test DB env (carries forward):** default `pycopg_test`/`pycopg_test2` both broken since 2026-06-24 (TimescaleDB `.so` version drift — server expects 2.28.0/2.28.1, only 2.28.2 installed; even bare `SELECT 1` fails). Run all DB/parity tests with `PGDATABASE=pycopg_test3` (the working scratch DB). Environmental, not a code issue.
- Non-blocking carry-forward (tracked in Deferred Items below): `vulture` not wired into Makefile/CI (AUDIT-02); phases 38/39 + 42/44/45/46/47 Nyquist VALIDATION.md draft/missing; DEBT-03b + `copy_insert` session-bypass (recorded in `37-DECISIONS.md`).

## Deferred Items

| Category | Item | Status |
| -------- | ---- | ------ |
| docs (1.0.1) | WR-01 api-reference deprecated exception names; WR-02 pyproject classifier `4 - Beta`→`5`; IN-01 CLAUDE.md stale Version | NEW (v1.0.0 audit) — non-blocking, baked into published 1.0.0; ship in a 1.0.1 patch |
| nyquist | Phases 42/44/45 VALIDATION.md draft (`nyquist_compliant: false`) + 46/47 missing | NEW (v1.0.0 audit) — functional VERIFICATION.md PASSED with live evidence for all; clear via `/gsd-validate-phase 42\|44\|45\|46\|47` |
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

Last session: 2026-07-02 — milestone v1.0.0 CLOSED via `/gsd-complete-milestone`.
Stopped at: Milestone v1.0.0 "Spatial v2 + gel API" archived. Audit PASSED (24/24 requirements, 7/7 phases, integration WIRED, 0 blockers). ROADMAP/REQUIREMENTS/AUDIT archived to `milestones/v1.0.0-*`, ROADMAP collapsed, PROJECT.md fully evolved (24 reqs → Validated, Active emptied, 9 Key Decisions added, "What This Is"/Current State → v1.0.0), REQUIREMENTS.md removed (fresh for next milestone). Tag `v1.0.0` live on PyPI (from Phase 47). pycopg 1.0.0 is the frozen SemVer 1.0 surface.
Resume file: None
Next action: `/gsd-new-milestone` to start the next cycle (additive 1.x) — or ship the ready 1.0.1 doc/metadata patch first.

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
