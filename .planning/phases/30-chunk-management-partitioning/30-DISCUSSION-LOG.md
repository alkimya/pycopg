# Phase 30: Chunk Management & Partitioning - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-22
**Phase:** 30-Chunk Management & Partitioning
**Areas discussed:** Chunk bound value types, Chunk return shape, add_dimension empty-HT error, Test placement & fixtures

---

## Chunk bound value types (`older_than` / `newer_than`)

| Option | Description | Selected |
|--------|-------------|----------|
| Both: str interval + datetime | Accept str interval AND Python datetime; bind as %s, let Postgres/TSDB resolve. Type hint `str \| datetime \| None`. | ✓ |
| Interval string only | Only interval strings, validated via validate_interval. Simplest; absolute-timestamp users fall back to raw SQL. | |
| Any value, pass through | Accept Any/object, bind %s, no validation. | |

**User's choice:** Both: str interval + datetime
**Notes:** Follow-up on the binding mechanism — a plain `%s` interval string arrives as `text` and errors, so the builder must cast per Python type.

### Bind cast (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Branch on type, cast str as ::interval | isinstance check: str → `%s::interval`, datetime → bare `%s` (psycopg adapts to timestamptz). Per-bound arg + cast. | ✓ |
| Always ::interval, reject datetime | Drop datetime support (reverses prior choice). | |
| Defer exact cast to research | Lock "both accepted", leave cast mechanism to researcher. | |

**User's choice:** Branch on type, cast str as ::interval

---

## Chunk return shape & ordering

| Option | Description | Selected |
|--------|-------------|----------|
| Fully-qualified, drop mirrors show | Return `_timescaledb_internal._hyper_1_2_chunk`; drop_chunks (+ dry_run) returns identical list. | ✓ |
| Bare chunk name | `_hyper_1_2_chunk` without schema prefix. | |
| Defer exact text form to research | Lock shape/sort, let researcher confirm regclass→text rendering. | |

**User's choice:** Fully-qualified, drop mirrors show

### Ordering (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Sort oldest-first by chunk range | Order by chunk time range ascending (range_start). Intuitive + stable; needs ordering by range, not bare SRF output. | ✓ |
| Native function order, no sort | Whatever show_chunks() yields, unsorted. | |
| Sort by name string | Lexicographic — but `_hyper_1_10` sorts before `_hyper_1_2`. | |

**User's choice:** Sort oldest-first by chunk range

---

## add_dimension empty-HT error

| Option | Description | Selected |
|--------|-------------|----------|
| New TimescaleError, catch + re-raise | Add TimescaleError(PycopgError); attempt DDL, catch psycopg failure, re-raise. No extra round-trip; reusable. | ✓ |
| Pre-check emptiness, then raise | SELECT EXISTS probe before DDL; extra round-trip, no error-parsing reliance. | |
| Reuse existing PycopgError | Re-raise generic PycopgError, no new class. | |

**User's choice:** New TimescaleError, catch + re-raise

### Exception name (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| TimescaleError, milestone-wide | General TimescaleDB-domain error, reusable across v0.8.0 (Phases 31-32). | ✓ |
| HypertableNotEmpty, specific | Narrowly named, single-use. | |
| Defer naming to planner | Lock behavior, let planner name it. | |

**User's choice:** TimescaleError, milestone-wide
**Notes:** Acknowledged this adds `pycopg/exceptions.py` to the Phase 30 change set (beyond the milestone plan's "timescale.py + queries.py only" assumption) — intentional and expected.

---

## Test placement & fixtures

| Option | Description | Selected |
|--------|-------------|----------|
| New tests/test_timescale.py | Dedicated file for all v0.8.0 advanced TSDB tests (sync+async), porting ts_db skip-fixture; Phases 31-32 extend it. | ✓ |
| Extend TestDatabaseTimescaleCoverage | Add to existing class in test_database_integration.py. | |
| Defer to planner | Lock fixture reuse, let planner pick file. | |

**User's choice:** New tests/test_timescale.py

---

## Claude's Discretion

- Exact `queries.py` constant names and whether drop_chunks' preview re-invokes show_chunks vs shares an internal builder.
- The precise `TimescaleError` message wording for the non-empty-hypertable case.
- Whether `chunk_interval` needs `validate_interval`, consistent with existing timescale.py usage.

## Deferred Ideas

- `show_chunks` `created_before`/`created_after` physical-time filters → TSDB-F04.
- Per-chunk `compress_chunk`/`decompress_chunk` → TSDB-F03.
- Continuous-aggregate lifecycle + `time_bucket`/`gapfill` helpers → Phases 31/32 (in milestone, not this phase).

No scope-creep requests arose during discussion.
