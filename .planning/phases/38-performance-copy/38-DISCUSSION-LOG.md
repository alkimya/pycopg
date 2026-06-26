# Phase 38: Performance COPY - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-26
**Phase:** 38-performance-copy
**Areas discussed:** DDL & dtype strategy, ETL materialization & seam, Connection & atomicity, Perf verification scope

---

## DDL & dtype strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: to_sql DDL + COPY data | Keep `df.head(0).to_sql(if_exists/index/dtype)` for table creation, then stream rows via COPY. Reuses etl.py:1381 precedent; preserves dtype/index/if_exists/primary_key for free; lowest risk. | ✓ |
| Full COPY + own type inference | Drop to_sql; infer SQL types ourselves, emit CREATE TABLE, then COPY. Removes SQLAlchemy from path but reimplements type mapping + dtype + if_exists — higher risk, touches contract. | |

**User's choice:** Hybrid: to_sql DDL + COPY data
**Notes:** `dtype` is absent from PERF-01's preserved-contract list but the Hybrid keeps it working anyway. Mechanical follow-ups captured in CONTEXT D-01a: `index=True` ⇒ `df.reset_index()` so the index column lands in the COPY stream; `append`-to-missing still auto-creates via the `head(0)` DDL call; `add_primary_key` post-step unchanged.

---

## ETL materialization & seam

| Option | Description | Selected |
|--------|-------------|----------|
| Stream rows into COPY, no full-frame copy | Feed `cur.copy(...).write_row(...)` on the seam cursor, NaN/NaT→None per-value instead of `astype(object)`+`to_dict`. Maximal PERF-02 win; append/replace only, upsert untouched. | ✓ |
| Keep row build, just swap INSERT→COPY | Still build a cleaned row iterable but route through COPY. Simpler diff, leaves most materialization cost — weaker against PERF-02. | |

**User's choice:** Stream rows into COPY, no full-frame copy
**Notes:** Seam preservation is an architectural lock (D-02a): COPY runs inline on the txn cursor at etl.py:1415, never via public `copy_insert`. Correctness constraints captured (D-02b): emptiness detection moves to `df.empty`/`len(df)`, columns to `df.columns`, "0 rows → success, no watermark advance" preserved, `cur.rowcount` after COPY still feeds `rows_loaded`. Scope: append/replace→COPY, upsert→INSERT…ON CONFLICT (COPY has no ON CONFLICT).

---

## Connection & atomicity

| Option | Description | Selected |
|--------|-------------|----------|
| Own connection (preserve today's behavior) | Acquire `self.connect()` for COPY like `copy_insert`. `from_dataframe` already uses the SQLAlchemy engine pool (not session-aware) — own connection keeps that isolation. Zero regression, non-breaking. | ✓ |
| Make from_dataframe session-aware | Run COPY on an active `db.session()` connection. More 'correct' but a behavior change + pulls deferred WR-03 forward. | |

**User's choice (connection):** Own connection (preserve today's behavior)

| Option | Description | Selected |
|--------|-------------|----------|
| Accept + document the two-step | DDL (`to_sql`) commits on engine, then COPY on separate psycopg conn. On COPY failure, table is replaced-but-empty. `replace` already means destroy-and-rebuild; document the contract. Simplest. | ✓ |
| Invest in atomic DDL+COPY | CREATE/REPLACE + COPY in one psycopg transaction so COPY failure rolls back the table. Stronger integrity, but cross-driver bridging + more risk. | |

**User's choice (atomicity):** Accept + document the two-step
**Notes:** Connection choice avoids pulling 37-REVIEW WR-03 (`copy_insert` session bypass, deferred to v1.0.0) forward. Atomicity tradeoff documented as part of the `from_dataframe` contract.

---

## Perf verification scope

| Option | Description | Selected |
|--------|-------------|----------|
| Behavior + assert-COPY-used here; benchmark → Ph39 | Phase 38 tests: contract preserved + assert COPY is the path taken (spy `cur.copy` / no `to_sql` data write). Throughput/benchmark deferred to Phase 39 (PERF-04). Avoids timing flakiness. | ✓ |
| Include a throughput test in Phase 38 | Timing-based assertion that COPY is faster. Closer to PERF-01's literal wording but flaky and duplicates Phase 39's benchmark suite. | |

**User's choice:** Behavior + assert-COPY-used here; benchmark → Ph39
**Notes:** Resolves the ROADMAP ("observable behavior") vs REQUIREMENTS PERF-01 ("throughput gain") wording tension by placing throughput measurement in Phase 39's PERF-04 benchmark suite. Keeps Phase 38 free of timing-based flakiness right after Phase 37 de-flaked the suite.

---

## Claude's Discretion

- Exact NaN/NaT → None normalization mechanism under COPY (D-02) — researcher picks, preserving type fidelity (lean: light mask/iteration, not full-frame `astype(object)`).
- Shape of a shared cursor-parameterized COPY-streaming helper reused by `from_dataframe` + ETL seam (D-01/D-02) — planner decides extract-vs-local; constraint: must operate on a provided cursor (to honor the seam) without opening its own connection.
- Exact site of the spy/assert-COPY-used test (D-06) — researcher/planner picks (mock `cur.copy`, or assert absence of `to_sql` data write).

## Deferred Ideas

- PERF-04 (benchmark suite + protocol + ~100k-row measurement) → Phase 39.
- COV-01 (coverage ratchet 94→95) → Phase 39 (do NOT touch `--cov-fail-under` here).
- REL-10 (release v0.10.0) → Phase 40.
- COPY binary (PERF-F01) + explicit numpy vectorization (PERF-F02) → v2.
- `from_dataframe` session-aware / WR-03 hardening → v1.0.0 (already deferred in Phase 37).
- Atomic DDL+COPY for `from_dataframe replace` → out of scope this milestone (D-04).
