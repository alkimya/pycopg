# Phase 17: Run-Tracking Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 17-run-tracking-foundation
**Areas discussed:** Accessor skeleton timing, Dedicated-connection lifecycle, Run-log write failure, dry_run / status CHECK, Table schema-qualification

---

## Accessor skeleton timing

| Option | Description | Selected |
|--------|-------------|----------|
| Create ETLAccessor + db.etl now | Phase 17 creates the sync ETLAccessor (init/_start_run/_end_run) AND wires lazy db.etl on Database (mirroring db.spatial). SC #2/#3 become testable now; Phase 20 "wiring" narrows to async-only. | ✓ |
| Module helpers now, accessor in Phase 20 | Free functions taking a Database; no class, no db.etl property yet; Phase 20 wraps them. Contradicts SC #2/#3 which name db.etl.init(). | |

**User's choice:** Create ETLAccessor + db.etl now (Recommended)
**Notes:** Resolves the roadmap tension (Phase 20 "lazy db.etl wiring" vs Phase 17 SC naming db.etl.init()) by narrowing Phase 20 to async-only wiring. (D-01, D-02, D-03)

---

## Dedicated-connection lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Fresh connect per write, via retry | Each _start_run/_end_run opens its own short-lived db.connect(autocommit=True) (tenacity-wrapped), writes, closes. No held state, matches lib idiom. ~2 short conns/run. | ✓ |
| One held autocommit conn for both writes | Single autocommit conn opened at run() start, used for INSERT + UPDATE, closed at end. One conn but more lifecycle/cleanup complexity; conn held across the whole load. | |

**User's choice:** Fresh connect per write, via retry (Recommended)
**Notes:** Reuses the established _connect_with_retry path; no accessor state. Separation from the load transaction is the locked invariant (ETL-08/09). (D-04, D-05)

---

## Run-log write failure (sub-question of connection lifecycle)

| Option | Description | Selected |
|--------|-------------|----------|
| Let it propagate | tenacity retries transient OperationalErrors first; if still failing, the exception propagates. A left-'running' row honestly reflects a DB problem. No silent swallowing. | ✓ |
| Swallow end-run failures, log a warning | Wrap _end_run in try/except, log WARNING, return RunResult as success anyway. Hides DB problems; row left stale silently. | |

**User's choice:** Let it propagate (Recommended)
**Notes:** Honesty over forgiveness for metadata writes; documented as a known edge. (D-06)

---

## dry_run / status CHECK

| Option | Description | Selected |
|--------|-------------|----------|
| Keep 3-valued CHECK | status IN ('running','success','failed'). dry_run (Phase 19) writes NO row (ETL-15) — it's an in-memory RunResult only, never hits the CHECK. Phase 16 DDL is final, no later migration. | ✓ |
| Add dry_run to the CHECK now | Pre-emptively widen CHECK to include 'dry_run'. Contradicts ETL-15 (no row written); dead constraint surface in v0.5.0. | |

**User's choice:** Keep 3-valued CHECK (Recommended)
**Notes:** Locks that dry_run is never persisted; confirms the Phase 16 DDL as final. (D-07)

---

## Table schema-qualification

| Option | Description | Selected |
|--------|-------------|----------|
| Unqualified / search_path, no schema option | pipeline_runs stays unqualified (resolves via search_path, usually public). ETLAccessor(db) takes no schema arg. Keeps run-log SQL as pure %s constants, no injection surface. | ✓ |
| Configurable tracking schema (ETLAccessor(schema=...)) | Add a schema param so pipeline_runs can live in e.g. 'etl'. Requires validate_identifiers + interpolation, changing the Phase 16 DDL contract. Research lists this as a Future Enhancement. | |

**User's choice:** Unqualified / search_path, no schema option (Recommended)
**Notes:** Pipeline.schema controls source/target tables (Phase 18), unrelated to the tracking table. Configurable tracking schema deferred as Future Enhancement. (D-08)

---

## Claude's Discretion

- Internal signatures of `_start_run` / `_end_run` (column set locked, packing is planner's call).
- Whether `init()` calls `ETL_INIT_PIPELINE_RUNS` directly or via `build_init_sql()`.
- Whether a thin `run()` stub lands now to make the auto-create path testable, vs. testing init/_start_run/_end_run directly and leaving `run()` to Phase 18/19.
- How `error_traceback` is captured (`traceback.format_exc()` or similar, stdlib).
- Whether `Pipeline` is exported in `__init__.py` now (currently only the ETL exceptions are).

## Deferred Ideas

- Configurable tracking-table schema (`ETLAccessor(db, schema='etl')`) — Future Enhancement, not v0.5.0.
- Swallow-and-warn on run-log write failure — considered, rejected for v0.5.0 (D-06).
- Watermark/incremental extract using the reserved `watermark` column — v0.6.0 (ETL-INC-01).
