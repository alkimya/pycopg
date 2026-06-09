# Phase 11: Parité sync/async complète - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-09
**Phase:** 11-parit-sync-async-compl-te
**Areas discussed:** Async driver URL (C3), Async close() (C2), Parity test depth (PAR-08), listen() parity, Parity test scope (PAR-08), Signature alignment direction (PAR-07)

---

## Async driver URL (C3 / PAR-06)

| Option | Description | Selected |
|--------|-------------|----------|
| New `Config.async_url` property | Dedicated property returning `postgresql+psycopg_async://`; sync `url` untouched; testable without a DB. | ✓ |
| Inline `.replace()` in `async_engine` | Transform `config.url` → `+psycopg_async` inside `async_engine` only; smaller change but logic in async_database.py. | |
| Planner decides | Leave mechanism to planner; only the async driver requirement is locked. | |

**User's choice:** New `Config.async_url` property
**Notes:** Explicit, testable without a DB, keeps transformation logic out of async_database.py. → D-04.

---

## Async close() (C2 / PAR-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Dispose async engine (await) | `close()` awaits `self._async_engine.dispose()` if created, sets to None — mirrors sync exactly. | ✓ |
| Planner decides exact form | Locked: must dispose; planner handles None-guard/idempotency. | |

**User's choice:** Dispose async engine (await)
**Notes:** Mirror sync `Database.close()` exactly. None-guard/idempotency left to planner. → D-05.

---

## Parity test depth (PAR-08)

| Option | Description | Selected |
|--------|-------------|----------|
| Mocked behavior + return shape | Mocked tests asserting same SQL / same return shape; no real DB for the parity layer. | |
| Full integration parity | Run each paired method against the real PostgreSQL test DB on both sides, assert identical results. | ✓ |
| Planner decides | Locked: beyond names; planner picks the mix. | |

**User's choice:** Full integration parity
**Notes:** Strongest guarantee; scoped to this phase's pairs in the follow-up question below. → D-03.

---

## listen() parity

| Option | Description | Selected |
|--------|-------------|----------|
| Keep listen async-only | sync gets notify/insert_many/upsert_many/stream (PAR-03) but NOT listen; documented in ASYNC_ONLY_METHODS. | ✓ |
| Add sync listen() too | Blocking generator-based sync listen() for full symmetry. | |
| Planner decides | Locked: PAR-03 four methods mirror; planner decides listen. | |

**User's choice:** Keep listen async-only
**Notes:** A blocking synchronous LISTEN is an anti-pattern; documented exception, not an omission. → D-06.

---

## Parity test scope (PAR-08 follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Paired methods only | Real-DB parity assertions only for this phase's pairs (13 mirrored + C1 + 4 PAR-07 aligned); introspection tests remain full-surface guard. | ✓ |
| All shared methods | Real-DB result-equality for every method on both classes; maximal but large overlap + slower CI. | |
| Planner decides breadth | Locked: integration parity with identical results; planner picks coverage to hit goal + 90. | |

**User's choice:** Paired methods only
**Notes:** Avoids redundant overlap with existing per-class integration suites. → D-03.

---

## Signature alignment direction (PAR-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Async adopts sync's richer signature | async create_extension gains `schema`, async create_schema gains `owner`, table_info/list_roles match sync; no breaking change for sync users. | ✓ |
| Pick simplest common subset | Strip params from sync to match async; BREAKS sync users; not recommended. | |
| Planner decides per method | Locked: signatures align; planner picks direction, defaulting to no breaking sync change. | |

**User's choice:** Async adopts sync's richer signature
**Notes:** Sync is the established, core-value API; async catches up. No sync breaking change. → D-07.

---

## Claude's Discretion

- Mechanical mirror implementation of the 13 missing methods + async `create`/`create_from_env` constructors (D-01, D-02).
- Exact per-pair parity assertions and which pairs beyond the core to cover for 90 (D-03).
- None-guard / idempotency of async `close()` (D-05).
- Coverage backfill strategy to reach 90 cleanly (D-08).
- Maintenance of `test_parity.py` allow-lists as implementations land.
- Docstring style of new methods (follow existing file style; numpydoc homogenization is Phase 13).

## Deferred Ideas

- Refactoring (`base.py`/`queries.py`, pure builders, ~48% dedup) — Phase 12.
- numpydoc docstrings + interrogate ≥ 95 + real exceptions (V2) + mypy — Phase 13.
- Spatial helpers (`db.spatial.*`) — Phase 14.
- Blocking sync `listen()` — rejected by design (anti-pattern), not deferred.
- Broader robustness concerns (per-query statement_timeout, adaptive pool, streaming backpressure, SRID inference) — backlog / future milestones.
