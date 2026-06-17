# Phase 18: Load Modes & Extract - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 18-load-modes-extract
**Areas discussed:** Replace-mode atomicity, Load write primitive, Load SQL builders, Transform-chain errors (+ create/exists semantics, DataFrame→rows handoff)

---

## Replace-mode atomicity & write primitive

| Option | Description | Selected |
|--------|-------------|----------|
| insert_batch in db.transaction() | All modes write via psycopg primitives in one db.transaction(); replace = TRUNCATE + insert_batch; upsert = upsert_many; never to_sql for the insert. Only path that makes SC-3 atomicity literally true. | ✓ |
| to_sql + accept non-atomic | from_dataframe(if_exists='append') for insert; TRUNCATE (psycopg) and to_sql (SQLAlchemy) are separate connections → mid-load failure leaves target empty; would require relaxing SC-3. | |
| Staging-table swap | to_sql into staging, then atomic TRUNCATE+INSERT…SELECT; keeps pandas type mapping + atomicity but adds staging table + round-trips; research's large-data/COPY path, deferred for v0.5.0. | |

**User's choice:** insert_batch in db.transaction()
**Notes:** The finding that `from_dataframe` runs on the SQLAlchemy engine (not psycopg) made this decisive — atomicity (SC-3) is non-negotiable, so the row insert must be psycopg-native and inside the load transaction. Locks the write primitive for all three modes. (CONTEXT D-01.)

---

## Target existence & create semantics

| Option | Description | Selected |
|--------|-------------|----------|
| to_sql to create empty, then insert_batch | Catalog existence check; append-missing → ETLTargetNotFoundError; replace-missing → create empty table via zero-row from_dataframe(if_exists='replace'), then TRUNCATE+insert_batch atomically. Create only on first run; steady-state re-runs fully atomic. | ✓ |
| CREATE TABLE IF NOT EXISTS in-txn from DataFrame dtypes | Hand-built CREATE from DataFrame dtypes inside the same txn — fully atomic even on first run, but duplicates pandas type-mapping and is an edge-case burden (tz, object cols). | |
| Let planner decide mechanism | Lock semantics only; let planner pick create mechanism. | |

**User's choice:** to_sql to create empty, then insert_batch
**Notes:** Accepts the first-run create as a non-atomic step (target is empty anyway), keeping steady-state re-runs atomic and borrowing pandas dtype→SQL mapping for the create. (CONTEXT D-03/D-03a.)

---

## Load SQL builders

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing methods; only build_truncate_sql is new | append→insert_batch, upsert→upsert_many (both already validate identifiers), replace→build_truncate_sql (shipped) + insert_batch. No new build_upsert_sql; research sketch superseded. Least duplication; SC-6 satisfied via existing validate_identifiers call sites. | ✓ |
| Author pure builders in etl.py (mirror spatial.py) | Write build_upsert_sql()/build_append_sql() as pure DB-free functions; max spatial.py consistency but duplicates SQL insert_batch/upsert_many already generate. | |
| Let planner decide | Lock txn + validate_identifiers requirements; let planner choose. | |

**User's choice:** Reuse existing methods; only build_truncate_sql is new
**Notes:** The research's `build_upsert_sql()` and `LoadSpec` sketches are explicitly superseded. (CONTEXT D-04/D-04a.) Planner must verify insert_batch/upsert_many share an outer transaction only inside db.session() (cursor() session-awareness — CONTEXT D-02).

---

## Transform-chain errors

| Option | Description | Selected |
|--------|-------------|----------|
| Step index + function name | ETLTransformError message includes 0/1-based step index AND callable __name__ (repr fallback for lambdas), e.g. "transform step 2 ('normalize') raised ValueError: …"; original exception chained via `from exc`. Most debuggable. | ✓ |
| Function name only | Identify by __name__ only; ambiguous for repeated/anonymous functions. | |
| Step index only | Identify by position only; unambiguous but less readable. | |

**User's choice:** Step index + function name
**Notes:** Chain the original exception so the traceback lands in pipeline_runs.error_traceback (ETL-08). (CONTEXT D-05/D-06.)

---

## DataFrame → rows handoff (load input)

| Option | Description | Selected |
|--------|-------------|----------|
| Convert + NaN→None; document tz contract | Phase 18 converts DataFrame→dicts and coerces NaN/NaT→NULL; tz-naive→TIMESTAMPTZ documented as user responsibility; rows_loaded from insert return. | |
| Raw convert only; document both | No NaN coercion; document user must clean NaN + localize. Surprising default (NaN inserts wrong values). | |
| Let planner decide conversion | Lock contract (load consumes post-transform DataFrame; rows_loaded from insert return value); leave exact conversion + NaN/tz handling to planner/researcher after verifying current from_dataframe behavior. | ✓ |

**User's choice:** Let planner decide conversion
**Notes:** Contract is locked; the NaN→NULL / tz handling is a research-grade detail to resolve consistently with existing from_dataframe behavior. Both traps (NaN→float-NaN, tz-naive shift) flagged for the researcher. (CONTEXT D-07.)

---

## Claude's Discretion

- Whether the load body opens its own db.session() internally vs documents caller management (D-02 atomicity must hold regardless; recommend internal).
- Transform step index base (0 vs 1) in the ETLTransformError message.
- Exact rows_extracted source and how extract_limit is appended (LIMIT %s).
- Catalog-existence query choice (to_regclass vs information_schema) for D-03.
- run() return shape in Phase 18 (run_id / counts / dict) — Phase 19 upgrades to RunResult; keep minimal.
- DataFrame→list[dict] conversion call (to_dict / itertuples / to_records) per D-07.
- Whether Pipeline gets exported in __init__.py now or Phase 20.
- upsert on a missing target (unspecified by the 6 SCs) — lean toward ETLTargetNotFoundError for symmetry with append; planner confirms.

## Deferred Ideas

- extract_batch_size streaming (v0.6.0, ETL-STREAM-01).
- COPY-based / staging-table truncate-load (large-data fast path; v0.5.0 uses TRUNCATE + insert_batch in one txn).
- Advisory-lock concurrency guard / PipelineAlreadyRunning (Pitfall 8; not v0.5.0 per Phase 17 D-06).
- GeoDataFrame-aware load (ETL-GEO-01; opportunistic).
- RunResult / history() / last_run() / dry_run (Phase 19).
- AsyncETLAccessor parity (Phase 20).
