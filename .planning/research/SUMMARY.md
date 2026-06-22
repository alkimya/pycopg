# Project Research Summary

**Project:** pycopg v0.8.0 — TimescaleDB Advanced Features
**Domain:** TimescaleDB 2.x time-series API extension for an existing psycopg 3 high-level Python library
**Researched:** 2026-06-22
**Confidence:** HIGH

## Executive Summary

pycopg v0.8.0 extends the existing `db.timescale.*` accessor (created in v0.6.0 with 6 hypertable/compression/retention methods) with nine new advanced TimescaleDB 2.x features: the full continuous aggregate lifecycle (`create_continuous_aggregate`, `refresh_continuous_aggregate`, `add_continuous_aggregate_policy`), chunk management (`show_chunks`, `drop_chunks`), query helpers (`time_bucket`, `time_bucket_gapfill`), multi-dimensional partitioning (`add_dimension`), and a reorder policy (`add_reorder_policy`). All nine methods follow the existing pure-builder + `validate_identifiers` + `%s`-params + lazy-accessor + sync/async-parity contract already proven in the spatial, ETL, and timescale-basics phases. Zero new runtime dependencies are required, and the ≥94% coverage ratchet must be maintained.

The single architectural constraint that dominates this milestone is the autocommit/transaction-block seam: `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` and `CALL refresh_continuous_aggregate(...)` cannot execute inside a PostgreSQL transaction block because TimescaleDB runs internal multi-transaction operations for both. The ETL accessor already solved the identical problem via `self._db.connect(autocommit=True)` for run-log isolation — that pattern must be reused verbatim for CAGG DDL and refresh. Every other new method (chunk management, query helpers, `add_dimension`, `add_reorder_policy`) is fully transaction-safe and uses the standard `self._db.execute()` path with no new connection management.

The top implementation risks beyond the autocommit seam are: (1) `time_bucket_gapfill` requires `start` and `finish` as explicit function arguments (not WHERE-clause inference) because psycopg 3 bound `%s` parameters are opaque to TimescaleDB's planner hook; (2) `drop_chunks` is destructive and irreversible and requires a `dry_run` guard before publication; (3) `add_dimension`'s `by_range`/`by_hash` form requires TimescaleDB >= 2.13 — the pre-2.13 positional keyword form should be used as the safe default until the local test server version is confirmed; (4) the recurring async guard gotcha (`await` omission on `has_extension`) must be explicitly audited on every new async method; (5) policy/scheduler tests must use `CALL run_job(job_id)` plus job-row-existence checks, never sleep-and-wait.

## Key Findings

### Recommended Stack

No stack additions are required. All v0.8.0 features are buildable with the existing runtime stack (psycopg >=3.1.0, psycopg_pool, pandas, geopandas, tenacity). The `autocommit=True` parameter on `psycopg.connect()` (Option A) is the correct psycopg 3 API for the CAGG DDL seam — setting `conn.autocommit = True` on an already-open async connection is read-only after construction, so `autocommit=True` must be passed at `AsyncConnection.connect()` time.

**Core technologies (unchanged from existing stack):**
- **psycopg 3 (3.3.4):** primary driver — `connect(autocommit=True)` is the CAGG DDL seam
- **pandas 2.x:** DataFrame return path for `time_bucket`/`time_bucket_gapfill` query helpers
- **TimescaleDB 2.x (floor):** all features except `add_dimension` modern API; 2.13+ for `by_range`/`by_hash`; 2.9+ for `time_bucket_gapfill` timezone parameter

**Open question 1 — confirm local TSDB version before finalizing `add_dimension`:**
Run `SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'` on the test server. If >= 2.13, use `by_range`/`by_hash`; if pre-2.13, use the positional keyword form. This determines which SQL form to build in Phase 30.

### Expected Features

**Must have (table stakes — block the milestone if absent):**
- **TS-ADV-01 `create_continuous_aggregate`** — flagship TSDB feature; accessor is incomplete without it
- **TS-ADV-02 `refresh_continuous_aggregate`** — manual window refresh; paired with create
- **TS-ADV-03 `add_continuous_aggregate_policy`** — auto-refresh scheduler; completes the CAGG lifecycle
- **TS-ADV-04 `show_chunks`** — baseline chunk inspection; prerequisite for safe drop_chunks usage
- **TS-ADV-05 `drop_chunks`** — operational chunk removal with `dry_run` guard (non-negotiable)

**Should have (differentiators — high value, low additional cost):**
- **TS-ADV-06 `time_bucket` helper** — removes boilerplate for the most common TSDB query pattern; returns DataFrame
- **TS-ADV-07 `time_bucket_gapfill` helper** — gapfill with `locf`/`interpolate` via `aggregates` strings; explicit `start`/`finish` required
- **TS-ADV-08 `add_dimension`** — multi-dimensional partitioning for IoT/multi-tenant workloads
- **TS-ADV-09 `add_reorder_policy`** — chunk reorder background optimization

**Defer (v2+):**
- `remove_continuous_aggregate_policy` / `drop_continuous_aggregate` — raw SQL works; low value
- `time_bucket` with `origin`/`offset` params — edge case; users write raw SQL
- `locf`/`interpolate` as first-class Python methods — misleading outside gapfill context
- `compress_chunk`/`decompress_chunk` manual per-chunk calls — advanced operational, out of scope
- `show_chunks` with `created_before`/`created_after` — rarely needed physical metadata filter

**Open question 2 — confirm `to_dataframe` bind-param path for `into="df"`:**
The ARCHITECTURE.md notes that `to_dataframe` uses SQLAlchemy `text()` which requires `%s` to `:p0` conversion via the `_to_named_binds` pattern from `spatial.py`. Verify this path works before Phase 32 (`time_bucket`/`time_bucket_gapfill`) to avoid a runtime failure on `into="df"`.

### Architecture Approach

All new code lives in exactly two files: `pycopg/timescale.py` (9 methods x 2 sync/async = 18 new method bodies + `_check_tsdb_into` helper) and `pycopg/queries.py` (3 new SQL constants: `TSDB_SHOW_CHUNKS`, `TSDB_DROP_CHUNKS`, `TSDB_LIST_CONTINUOUS_AGGREGATES`). No other file is modified. The `ACCESSOR_PAIRS` entry in `tests/test_parity.py` already covers `(TimescaleAccessor, AsyncTimescaleAccessor)` — no registry change needed.

**Major components:**
1. **`TimescaleAccessor` / `AsyncTimescaleAccessor` (pycopg/timescale.py):** all 9 new methods in 3 integration patterns
2. **Pattern 1 — standard pure-builder (7 methods):** `show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy`, `add_continuous_aggregate_policy`, `time_bucket`, `time_bucket_gapfill` — use `self._db.execute()` / `self._db.to_dataframe()`; no new seams
3. **Pattern 2 — autocommit seam (2 methods):** `create_continuous_aggregate`, `refresh_continuous_aggregate` — always open a dedicated `self._db.connect(autocommit=True)` connection; mirrors `ETLAccessor._start_run`/`_end_run` exactly
4. **Pattern 3 — query helpers with `into=` return (2 methods):** `time_bucket`, `time_bucket_gapfill` — use spatial accessor's `into="rows"/"df"` pattern; `_check_tsdb_into` rejects `into="gdf"` (no geometry column)
5. **`pycopg/queries.py` additions:** `TSDB_SHOW_CHUNKS`, `TSDB_DROP_CHUNKS` as `%s`-parameterized constants; `TSDB_LIST_CONTINUOUS_AGGREGATES` for optional `list_continuous_aggregates` method

### Critical Pitfalls

1. **CAGG DDL + refresh cannot run inside a transaction block** — both `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` and `CALL refresh_continuous_aggregate(...)` internally run multiple transactions, making them incompatible with any enclosing transaction. Must always use `self._db.connect(autocommit=True)`. Never route through `self._db.execute()`. The ETL accessor's `_start_run`/`_end_run` autocommit pattern is the direct precedent.

2. **`time_bucket_gapfill` bounds broken with `%s` WHERE inference** — TimescaleDB's planner hook cannot read bound parameters in WHERE clauses at planning time. Pass `start` and `finish` as explicit positional arguments inside the `time_bucket_gapfill(interval, col, %s, %s)` function call, not as WHERE filters. Both are required non-optional parameters.

3. **`drop_chunks` is destructive and irreversible** — implement `dry_run: bool = False` that delegates to `show_chunks` to preview without deleting. Require at least one of `older_than`/`newer_than` (both None raises `ValueError`). Mark as DESTRUCTIVE/IRREVERSIBLE in docstring Notes.

4. **`add_dimension` requires empty hypertable + TSDB >= 2.13 for `by_range`/`by_hash`** — validate the target hypertable is empty before sending SQL (raise a pycopg-domain error, not raw psycopg `ProgrammingError`). Use the pre-2.13 positional keyword form as the default unless the test server is confirmed 2.13+.

5. **Async extension guard `await` omission** — recurring Phase 23 gotcha: `if not self._db.schema.has_extension("timescaledb"):` in async context silently never raises (coroutine is truthy). Every new async method must use `if not await self._db.schema.has_extension("timescaledb"):`. Audit all async methods before shipping each phase.

6. **Policy tests must not use scheduler sleep-and-wait** — verify policies via row existence in `timescaledb_information.jobs` + `CALL run_job(job_id)` on an autocommit connection. Scheduler-based tests are flaky and suppressed in most CI environments.

## Implications for Roadmap

Based on combined research, the recommended phase structure is:

### Phase 30: Pure-builder chunk + partitioning methods (show_chunks, drop_chunks, add_dimension, add_reorder_policy)

**Rationale:** These are the simplest four methods — no new connection management, no autocommit seam, no query-builder complexity. They establish correct `by_hash`/`by_range` SQL form on the real test server before any riskier work. If `add_dimension`'s `by_range`/`by_hash` API breaks (TSDB version < 2.13), it surfaces cheaply here without contaminating the CAGG phase.

**Delivers:** 4 methods x 2 (sync/async) = 8 new method bodies. `TSDB_SHOW_CHUNKS` and `TSDB_DROP_CHUNKS` in `queries.py`. `dry_run` guard on `drop_chunks`. Empty-hypertable validation on `add_dimension`. Integration tests confirm correct chunk listing/dropping, dimension addition, and reorder policy registration.

**Features:** TS-ADV-04, TS-ADV-05, TS-ADV-08, TS-ADV-09

**Avoids:** Pitfalls 3 (drop_chunks destructive), 4 (add_dimension empty hypertable + version), 5 (async guard), 6 (scheduler sleep-wait)

**Research flag:** Standard patterns — no deeper research phase needed. Confirm TSDB version at plan/execute time.

### Phase 31: Continuous aggregate lifecycle (create, refresh, add_policy)

**Rationale:** The riskiest phase: two methods require the autocommit seam (a new precedent on `TimescaleAccessor`), the async guard gotcha is most dangerous here, and `create_continuous_aggregate` accepts a raw SQL fragment (`select_sql`) that cannot be parameterized. Must ship all three methods together (create + refresh + policy) as they form an indivisible lifecycle.

**Delivers:** 3 methods x 2 (sync/async) = 6 new method bodies. `TSDB_LIST_CONTINUOUS_AGGREGATES` in `queries.py`. Integration tests: create a cagg, verify in `timescaledb_information.continuous_aggregates`, refresh with committed data, verify materialized rows, add and verify policy via `run_job`.

**Features:** TS-ADV-01, TS-ADV-02, TS-ADV-03

**Avoids:** Pitfalls 1 (CAGG in transaction block), 2 (refresh in transaction block), 5 (async guard), 6 (scheduler), date_trunc heuristic check, start_offset > end_offset validation, NULL window_end guard

**Research flag:** Plan must explicitly verify: (a) `create_continuous_aggregate` works after `db.execute("SELECT 1")` in the same session; (b) whether `add_continuous_aggregate_policy` needs autocommit — use autocommit for all three CAGG methods to be safe and consistent regardless.

### Phase 32: Query helpers (time_bucket, time_bucket_gapfill)

**Rationale:** These return data, not management results, and are most useful when querying against a continuous aggregate from Phase 31. The `into="df"` path requires the `_to_named_binds` SQLAlchemy pattern from `spatial.py` — verify before coding. `time_bucket_gapfill`'s explicit `start`/`finish` parameter requirement is the key structural constraint.

**Delivers:** 2 methods x 2 (sync/async) = 4 new method bodies. `_check_tsdb_into` module-level helper. Integration tests: `time_bucket` returning `list[dict]` and `pd.DataFrame`, `time_bucket_gapfill` with `datetime.now()` bound params (confirms no "could not infer" error), both on real hypertable data.

**Features:** TS-ADV-06, TS-ADV-07

**Avoids:** gapfill bounds broken with %s WHERE inference, gapfill not bare in GROUP BY, `into="gdf"` rejected

**Research flag:** Verify `to_dataframe` `%s` vs named-bind path at plan time by reading `spatial.py` `_to_named_binds` and the `to_dataframe` call site.

### Phase 33: Release v0.8.0

**Rationale:** Standard release phase — version bump in two places, CHANGELOG `[0.8.0]` Added section, Sphinx docs, 4-gate CI verify, human-gated tag v0.8.0 + OIDC publish, clean-venv smoke test. Mirrors Phase 29 structure exactly.

**Delivers:** Published v0.8.0 on PyPI. Updated README + Sphinx API docs for 9 new methods.

**Research flag:** Standard release pattern — no research phase needed. Direct precedent: Phase 29.

### Phase Ordering Rationale

- **Phase 30 before 31:** Pure-builder methods prove API shapes (especially `add_dimension` version-dependent SQL) cheaply before the harder CAGG phase.
- **Phase 31 before 32:** Query helpers are most naturally tested against a continuous aggregate; Phase 31 provides a realistic test fixture.
- **CAGG trio ships together (Phase 31):** `create` + `refresh` + `add_policy` are an indivisible lifecycle. Splitting them would leave an incomplete CAGG surface.
- **Chunk management + partitioning together (Phase 30):** All four are pure-builder with no autocommit complexity; grouping minimizes phase count while keeping each phase coherent.

### Research Flags

Phases needing plan-time verification:
- **Phase 30:** Confirm TSDB version (`SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'`) to choose `add_dimension` SQL form.
- **Phase 31:** Confirm `add_continuous_aggregate_policy` autocommit vs transaction-safe decision.
- **Phase 32:** Verify `to_dataframe` `%s` to named-bind conversion path before coding `into="df"`.

Phases with standard patterns (skip research-phase):
- **Phase 33:** Release pattern fully established via Phase 29.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All features verified against official tigerdata.com API docs; psycopg 3 autocommit API confirmed; zero new runtime deps verified |
| Features | HIGH | All 9 feature signatures verified against TimescaleDB 2.x official docs; return shapes consistent with existing accessor patterns |
| Architecture | HIGH | Based on direct source reading of timescale.py, spatial.py, etl.py, queries.py, tests/test_parity.py; all integration seams are pre-existing |
| Pitfalls | HIGH | Transaction-block restriction confirmed via TimescaleDB GitHub issues (#1218, #2876, #5377); gapfill bound-param failure confirmed via TSDB issues (#4279, #7605, #8525) |

**Overall confidence:** HIGH

### Gaps to Address

- **`add_dimension` SQL form:** Use the pre-2.13 positional keyword form in Phase 30 planning unless the test server is confirmed 2.13+ at plan time. Check with `SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'`.
- **`into="df"` bind-param conversion:** Verify whether `to_dataframe` already handles `%s` natively or requires `_to_named_binds` SQLAlchemy conversion at the start of Phase 32.
- **`add_continuous_aggregate_policy` autocommit vs transaction-safe:** STACK.md classifies it as transaction-safe; PITFALLS.md recommends autocommit for consistency. Use autocommit for all three CAGG methods — decide and lock at Phase 31 plan time.

## Sources

### Primary (HIGH confidence)
- TimescaleDB API docs (tigerdata.com) — all 9 function signatures verified
- TimescaleDB GitHub issues #1218, #2876 — `refresh_continuous_aggregate` transaction-block restriction confirmed
- TimescaleDB GitHub issues #5377 — `CREATE MATERIALIZED VIEW WITH DATA` pipeline restriction confirmed
- TimescaleDB GitHub issues #4279, #7605, #8525 — `time_bucket_gapfill` bound-param inference failure confirmed
- TimescaleDB 2.13.0 release notes — `materialized_only` default change + `by_range`/`by_hash` introduction
- psycopg 3 docs — `autocommit=True` on `connect()` API
- pycopg source: pycopg/timescale.py, pycopg/spatial.py, pycopg/etl.py, pycopg/queries.py, tests/test_parity.py (direct source reading)
- pycopg .planning/PROJECT.md — v0.8.0 scope lock, locked decisions, zero-dep constraint

### Secondary (MEDIUM confidence)
- Community: wazeem.com — autocommit for TimescaleDB materialized views in CI
- WebSearch — `add_reorder_policy` parameter confirmation

---
*Research completed: 2026-06-22*
*Ready for roadmap: yes*
