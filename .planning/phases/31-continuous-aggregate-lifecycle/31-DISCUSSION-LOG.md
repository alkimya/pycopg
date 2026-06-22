# Phase 31: Continuous Aggregate Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-22
**Phase:** 31-Continuous Aggregate Lifecycle
**Areas discussed:** Policy connection path, Offset validation strictness, create() WITH-clause options, refresh() window types

---

## Policy connection path

Resolves a contradiction between STATE.md ("policy also uses autocommit for consistency/safety")
and milestone research (Pattern 1 lists the policy under standard `execute()`). Verified in code
that all three shipped policy methods (`add_compression_policy`, `add_retention_policy`,
`add_reorder_policy`) use plain `self._db.execute()` — `add_*_policy()` is a transaction-safe
function call, not multi-transaction DDL.

| Option | Description | Selected |
|--------|-------------|----------|
| Plain execute() (match Phase 30) | `add_continuous_aggregate_policy` uses `self._db.execute()` like the 3 shipped policy methods; only create+refresh get the autocommit seam | ✓ |
| Autocommit seam (all 3 share it) | Policy also opens `connect(autocommit=True)` for "consistency"; diverges from shipped policy methods, adds an unnecessary seam | |

**User's choice:** Plain execute() (match Phase 30)
**Notes:** Becomes CONTEXT D-01. The STATE.md "consistency" note predates Phase 30 proving the
policy precedent and is superseded. Only create + refresh get the `connect(autocommit=True)` seam.

---

## Offset validation strictness

ROADMAP criterion #3 wants `start_offset` shorter-than `end_offset` to raise `ValueError` before
any DB round-trip. Comparing arbitrary interval strings in Python is calendar-ambiguous and
zero-new-deps forbids a parser; the DB enforces ordering correctly.

| Option | Description | Selected |
|--------|-------------|----------|
| Best-effort guard, DB is authority | Syntax-validate both; Python `ValueError` only for unambiguous same-unit forms; mixed/calendar units defer to the DB | ✓ |
| Strict parse-and-compare all | Full interval-to-seconds parser; month/year approximations risk wrongly rejecting valid configs; fragile bespoke code | |
| Syntax-only, defer compare to DB | No Python magnitude comparison at all; misses the "ValueError before round-trip" part of the criterion | |

**User's choice:** Best-effort guard, DB is authority
**Notes:** Becomes CONTEXT D-07. Honest about the limit, satisfies the common case, no new deps.
DB documented as final authority on offset ordering.

---

## create() WITH-clause options

| Option | Description | Selected |
|--------|-------------|----------|
| Keep the 2 flags exactly | Only `materialized_only` (default True) + `with_no_data` (default False) render into the WITH clause; matches REQUIREMENTS verbatim | ✓ |
| Add create_group_indexes flag | Extra TSDB index-control knob; beyond REQUIREMENTS scope, rarely touched, arguably scope creep | |

**User's choice:** Keep the 2 flags exactly
**Notes:** Becomes CONTEXT D-03. `create_group_indexes` and other knobs deferred — user writes raw
SQL for advanced options.

---

## refresh() window types

Phase 30 `drop_chunks` set a `str|datetime|None` type-driven-cast precedent, but a cagg refresh
window is an **absolute** materialization range, so a relative interval makes little sense.

| Option | Description | Selected |
|--------|-------------|----------|
| datetime\|None only, both-None=full | Accept `datetime` (bare `%s`) or `None`; both-None = full refresh (NULL, NULL); reject `str` with a clear ValueError | ✓ |
| Mirror drop_chunks str\|datetime\|None | Same cast as Phase 30; but relative-interval refresh windows are semantically odd | |
| datetime\|date\|None | Like option 1 but also accept `date`; slightly more forgiving | |

**User's choice:** datetime|None only, both-None=full
**Notes:** Becomes CONTEXT D-05/D-06. Deliberate divergence from Phase-30 `drop_chunks` — flagged
for the planner so it doesn't blindly copy the type-driven interval cast. One-side NULL =
open-ended.

---

## Claude's Discretion

- Exact `queries.py` constant name(s) if any are added (optional `TSDB_LIST_CONTINUOUS_AGGREGATES`
  for test info-view JOINs — planner's call).
- The precise set of "unambiguous same-unit" interval forms the D-07 best-effort comparator parses.
- Exact `ValueError` / docstring wording for the `time_bucket(` heuristic, the `str` rejection on
  refresh windows, and the offset-ordering guard.
- Whether the autocommit seam uses `conn.execute(...)` directly or an explicit
  `conn.cursor(...) as cur` (create/refresh return None, so a plain `conn.execute` may suffice).

## Deferred Ideas

- `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` (lifecycle removal) → TSDB-F01.
- `create_group_indexes` and other cagg `WITH (...)` knobs → deferred (D-03).
- cagg-on-cagg waterfall as a dedicated API → out of scope (write `FROM schema.lower_cagg`).
- `time_bucket` / `time_bucket_gapfill` query helpers → Phase 32.
- Full TS-ADV-10 9-method parity + all-autocommit-branch coverage gate → Phase 32.
