---
gsd_state_version: 1.0
milestone: v1.2.0
milestone_name: Polish & finitions additives
status: executing
stopped_at: Completed 52-02-PLAN.md
last_updated: "2026-07-04T21:31:02.806Z"
last_activity: 2026-07-04 -- Phase 52 Plan 02 (length/is_valid/is_valid_reason, SPAT-F02+SPAT-F05) complete
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 6
  completed_plans: 2
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-04 after v1.1.0 milestone close)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

**Current focus:** Phase 52 — spatial-finish

## Current Position

Phase: 52 (spatial-finish) — EXECUTING
Plan: 3 of 6 (Plan 01 SPAT-F01 gridSize= complete; Plan 02 SPAT-F02+SPAT-F05 length/is_valid/is_valid_reason complete, 3/3 tasks)
Status: Ready to execute
Last activity: 2026-07-04 -- Phase 52 Plan 02 (length/is_valid/is_valid_reason, SPAT-F02+SPAT-F05) complete

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
| Phase 48 P01 | 15min | 2 tasks | 3 files |
| Phase 48 P02 | 20min | 3 tasks | 2 files |
| Phase 48 P03 | 25min | 3 tasks | 4 files |
| Phase 50 P01 | 15min | 3 tasks | 7 files |
| Phase 50 P02 | 18min | 3 tasks | 10 files |
| Phase 50 P03 | 15min | 2 tasks | 8 files |
| Phase 50 P04 | ~25min | 3 tasks | 6 files |
| Phase 52 P01 | 7min | 3 tasks | 2 files |
| Phase 52 P02 | 20min | 3 tasks | 2 files |

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
- [Phase ?]: 48-01: drop_continuous_aggregate + remove_continuous_aggregate_policy use plain self._db.execute (RESEARCH D-05), not the autocommit seam reserved for create/refresh
- [Phase ?]: 48-01: remove_continuous_aggregate_policy binds current if_exists param name (TSDB 2.8+), never deprecated if_not_exists (Pitfall 1)
- [Phase ?]: 48-02: origin binds bare typed %s, offset binds %s::interval, mutual-exclusion ValueError guard fires client-side before SQL build (D-07)
- [Phase ?]: 48-02: F02 is a param-only addition to existing time_bucket name -- no new entry in test_timescale_v110_surface, parity covered by test_accessor_parameter_kind_parity
- [Phase 48-03]: compress_chunk/decompress_chunk skip validate_identifiers — chunk is a bound %s::regclass value, not an identifier (RESEARCH D-10/D-11 carve-out)
- [Phase 48-03]: if_not_compressed/if_compressed bound as %s params (not literal-boolean like the cagg family) — confirmed correct idiom for these plain function calls
- [Phase 48-03]: TSDB-F04 required zero production change — verified + documented already-shipped newer_than/older_than symmetry
- [Phase 49-01]: Pipeline.initial_watermark frozen field (default None = byte-identical pre-F01); D-01 seed-floor-only (consulted only when no stored watermark, ignored after first max(col) recorded); D-02 guard requires incremental_column + scalar {datetime,int,str} allowlist via _encode_watermark; fallback applied at all 4 run() call sites (sync+async real+dry) with explicit is-None (0 is a valid floor), _read_watermark signature unchanged; Sequence branch of guard deferred to 49-03, composite run() seed to 49-04 (scalar cast placeholder). C-04 both run() edited same commit. DEVIATION: live-DB seed tests in test_etl_accessor.py (fixtures live there), guards in test_etl.py
- [Phase 49-05]: advisory-lock concurrency (F04, phase complete). 3 queries.py constants ETL_ADVISORY_LOCK/TRY_LOCK/UNLOCK derive key server-side via hashtextextended(%s,0), name BOUND (never Python hash() PYTHONHASHSEED-salted, never interpolated D-15). Pipeline.concurrency Literal[wait,skip]|None opt-in on ANY pipeline (D-12). run() renamed _run_impl + thin lock wrapper (both accessors C-04): concurrency=None/dry_run delegate byte-identical; else session-scoped lock on DEDICATED 3rd autocommit connection (Pitfall 1) spanning read→extract→load→record; skip+held→transient RunResult(status=skipped,run_id=None) NO pipeline_runs row (D-13, status CHECK unchanged); wait blocks; finally-unlock (try/except defensive) + `with` close auto-releases on crash (D-14). Live 2-connection: skip-when-held→skipped+no-row+runs-after-release, crash-releases, wait-blocks-until-peer-releases (run_done>=release), async mirror. Full suite 1844@96.29%, mypy 0, Sphinx -W clean, interrogate 100%. **PHASE 49 COMPLETE: ETL-INC-F01..F04 all shipped.**
- [Phase 49-04]: composite watermark run() WIRING (F03 end-to-end). 4 pure helpers replace the 4 duplicated capture blocks + 49-03 fail-loud guards: _capture_watermark (scalar max / composite greatest-ROW via sort_values reading each element from its OWN sorted column sorted_df[c].iloc[-1] — NOT a row Series which promotes int→float, NOT per-column maxes D-10; per-element NaN void Pitfall 4), _coerce_watermark_scalar, _reconcile_watermark_binds (single %s→:wm byte-identical, composite→:wm{i}), _encode_watermark_value (scalar/composite persist). Wired all 4 forks C-04; _read_watermark + wm/read_floor widened to CompositeWatermark tuple; composite+lookback→ETLError (unsupported). Live proof: recorded (2,1) NOT (2,99), second-run (day,seq)>(recorded) filter, composite seed floor, async mirror. BUG FOUND+FIXED: .iloc[-1][c] row-Series int→float promotion false-tripped float-reject (caught by helper smoke test). Full suite 1828 passed @96.30%, etl.py 97%, mypy 0, Sphinx -W clean, interrogate 100%. docs/etl.md composite/boundary section corrected.
- [Phase 49-03]: composite watermark PURE layer. incremental_column widened str|Sequence[str]|None (str stays scalar, sequence→tuple normalize in __post_init__, empty→ValueError, D-09); _validate_incremental splats validate_identifiers over elements (D-10); D-04 composite initial_watermark guard (same-length + per-element _encode_watermark allowlist + tuple-normalize; single-col now rejects sequence seed, closes 49-01 gap). Builder composite branch WHERE (c1,c2) op (%s,%s) row-value compare, 1 bound %s/element (pulled into Task-1 commit for mypy). New _encode_composite_watermark + 'composite' decode tag (dispatcher + _decode_scalar_watermark, per-element reuse, zero migration C-02); RunResult.watermark_used/recorded widened to tuple. DEVIATION: run() NOT untouched — 4 fail-loud composite-capture guards + _read_watermark cast are the 49-04 seam (no composite run() behavior yet). mypy strict green, 305 passed.
- [Phase 49-02]: incremental_inclusive (bool, >= boundary) + incremental_lookback (timedelta|int, read-window overlap) frozen fields, defaults (False,None) byte-identical (D-05); _build_incremental_extract_sql gains kw-only inclusive (op literal from bool, validate_identifiers still line 1); new pure _apply_lookback helper (isinstance dispatch datetime→timedelta / int→int; str + type-mismatch → ETLError runtime, D-06). read_floor = wm - lookback at all 4 run() forks BEFORE _do_extract; recorded watermark stays true max(col) (D-07 — capture block untouched); RunResult.watermark_used = adjusted read floor. D-08 overlap replay = safe idempotent upsert no-op (C-01). C-04 both run()+both _do_extract same commit. Composite-watermark lookback semantics undefined → 49-04 to decide (likely reject). DEVIATION: live divergence tests in test_etl_accessor.py, builder+construction guards in test_etl.py
- [Phase 50]: CRUD-F01: QueryMixin._resolve_predicate centralizes D-02/D-03/D-04 guards for all 5 predicate helpers x2 classes; destructive guard checks the resolved fragment (post-resolve), a non-empty where_sql satisfies it (D-03)
- [Phase 50]: 50-02: Page defined in database.py (RunResult precedent); paginate_page/paginate_keyset carry no @overload (Page is the unconditional return type)
- [Phase 50-03]: D-13/D-14 confirmed as researched: dedicated pg_catalog queries required (pg_matviews for names, pg_attribute/pg_class relkind='m' for columns); views()/table_info() left unchanged
- [Phase 50-03]: validate_identifiers kept as defense-in-depth on materialized_view_columns even though name/schema only ever reach the query as bound %s params (never interpolated)
- [Phase 50-04]: D-11/D-12 confirmed as researched: describe(into=...) keyword param, default 'dict' byte-identical to v0.9.0 (C-03); TableDescription typed wrapper for 'dataclass', columns-section DataFrame for 'dataframe'
- [Phase 50-04]: pandas imported top-level in schema.py (import pandas as pd), matching the etl.py precedent for a hard runtime dependency -- not the lazy per-function import used by to_dataframe/time_bucket, since describe's dataframe branch needs pd.DataFrame at every call

**v1.2.0 roadmap locked (2026-07-04):** 3 phases (52-54), continuing numbering from Phase 51. Phase 52 (Spatial Finish, SPAT-F01..F06) and Phase 53 (CRUD Symmetry + Introspection Follow-ups, CRUD-F04..F06 + INTRO-F03/F04) are independent surfaces (spatial.py vs database.py/schema.py) — either could run first, executed in numeric order. Phase 54 (Release v1.2.0) folds in the two low-risk hygiene requirements (DOC-14, TOOL-01) alongside REL-13, avoiding a 4th thin phase per standard-granularity guidance. 14/14 requirements mapped, 0 unmapped.

- [Phase 52]: Phase 52-01: gridSize= threaded through _build_binary_geom_sql + union/difference/intersection builders and accessors (sync+async), byte-identical None path (D-03), pure passthrough no client guard (D-02), no server-version pre-check (D-04)
- [Phase ?]: Phase 52-02: build_length_sql/build_is_valid_sql/build_is_valid_reason_sql mirror build_perimeter_sql exactly (validate_identifiers first, bare AS labels D-09); length reuses _validate_unit (D-10, ST_Length=0 for non-linear geometries); is_valid/is_valid_reason registered in _SCALAR_HELPERS so into=gdf fails fast (D-12)

### Pending Todos

- The 1.0.1 doc/metadata patch (WR-01/WR-02/IN-01) was folded into v1.1.0 Phase 51 (DOC-13) — CLOSED, no longer pending.
- Optional: clear Nyquist VALIDATION.md artifact gaps via `/gsd-validate-phase 42|44|45` (draft) and `46|47` (missing) — functional VERIFICATION.md PASSED for all; discovery-only, see v1.0.0-MILESTONE-AUDIT.md.
- v1.2.0 roadmap created (Phases 52-54) — next: `/gsd-plan-phase 52`.

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
| v1.1.0 | TSDB-F01..F04: cagg lifecycle removal, time_bucket origin/offset, compress/decompress_chunk, show_chunks physical-time filters | MAPPED to Phase 48 (2026-07-02 roadmap) |
| v1.1.0 | ETL-INC-F01..F04: initial_watermark, configurable boundary, multi-column watermark, advisory-lock concurrency | MAPPED to Phase 49 (2026-07-02 roadmap) |
| v1.1.0 | CRUD-F01..F03, INTRO-F01..F02: raw-SQL escape hatch, keyset pagination, page envelope, describe dataclass/DataFrame, materialized_views | MAPPED to Phase 50 (2026-07-02 roadmap) |
| future | ETL-INC-F05: CDC / WAL change capture | deferred out of v1.1.0 (2026-07-02) — large distinct subsystem, future ETL milestone |
| v1.2.0 | CRUD-F04..F06, INTRO-F03/F04: select_where/find, get/find_one, insert, column_exists, table_size | MAPPED to Phase 53 (2026-07-04 roadmap) |
| v1.2.0 | DOC-14, TOOL-01, REL-13: doc prose fix, vulture wiring, release | MAPPED to Phase 54 (2026-07-04 roadmap) |
| v1.2.0 | SPAT-F01: gridSize precision on overlay functions (GEOS ≥ 3.9) | MAPPED to Phase 52 (2026-07-04 roadmap) — no longer deferred |
| v2 | RASTER-F01: PostGIS raster I/O | deferred post-1.0 per 2026-06-27 cadrage |

## Session Continuity

Last session: 2026-07-04T21:31:02.796Z
Stopped at: Completed 52-02-PLAN.md
Resume file: None
Next action: Continue Phase 52 — execute Plan 03 (next SPAT-F0x plan in the 6-plan Spatial Finish sequence).

## Operator Next Steps

- Continue executing Phase 52 (Spatial Finish) — Plans 01/02 of 6 complete (SPAT-F01, SPAT-F02+F05); 4 plans remaining (SPAT-F03/F04/F06).
