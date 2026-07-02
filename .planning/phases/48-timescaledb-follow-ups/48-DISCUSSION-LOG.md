# Phase 48: TimescaleDB Follow-ups - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-02
**Phase:** 48-timescaledb-follow-ups
**Areas discussed:** F04 already done?, Cagg teardown (F01), Bucket alignment (F02), Chunk compression (F03)

---

## F04 — show_chunks physical-time filter

Scouting finding: `show_chunks(older_than=, newer_than=)` already accepts interval-str AND absolute datetime, sync + async, with tests, since v0.8.0.

| Option | Description | Selected |
|--------|-------------|----------|
| Verify + doc only | Treat F04 as satisfied: add explicit datetime-path test if missing, confirm in verification, mark done. No new API. | ✓ |
| There's a nuance | User intended something distinct (chunk creation time, status filter, other semantic). | |
| Drop F04 from phase | Consider fully closed by v0.8.0, remove from Phase 48 scope entirely. | |

**User's choice:** Verify + doc only
**Notes:** Confirmed the requirement text and success criterion #4 are already met by shipped code. `test_show_chunks_sql_shape_datetime_older_than` already covers the absolute-datetime path; only micro-gap is a symmetric `newer_than`-datetime shape test.

---

## Cagg teardown (F01)

| Option | Description | Selected |
|--------|-------------|----------|
| if_exists + cascade | drop_continuous_aggregate(name, *, cascade=False, if_exists=False); remove_continuous_aggregate_policy(name, *, if_exists=True). Mirrors TimescaleDB semantics. | ✓ |
| if_exists only | if_exists on both, no cascade param on drop. | |
| Minimal (no knobs) | Bare drop/remove, no idempotency/cascade params. | |

**User's choice:** if_exists + cascade
**Notes:** Policy remover defaults `if_exists=True` (symmetric with add_...'s if_not_exists=True); drop defaults `if_exists=False` (destructive op explicit). Autocommit-seam need for the drop left as a research question.

---

## Bucket alignment (F02)

| Option | Description | Selected |
|--------|-------------|----------|
| Client-side guard | origin: datetime\|None, offset: str\|None, both kw-only default None; raise ValueError before DB if both non-None. Matches codebase convention. | ✓ |
| Defer to DB | Same types but let TimescaleDB raise its own error when both given. | |
| origin only | Add only origin=, skip offset= (narrower than requirement). | |

**User's choice:** Client-side guard
**Notes:** origin binds typed %s, offset binds %s::interval. Extends existing `_build_time_bucket_sql`; keep validate_identifiers first + KIND-parity overloads.

---

## Chunk compression (F03)

**Question A — idempotency flags:**

| Option | Description | Selected |
|--------|-------------|----------|
| Expose, default True | compress_chunk(chunk, *, if_not_compressed=True) / decompress_chunk(chunk, *, if_compressed=True). Idempotent by default. | ✓ |
| Expose, default False | Same flags, default False — strict, raises on already-(de)compressed. | |
| No flags | Bare compress/decompress, rely on TimescaleDB defaults. | |

**Question B — return value:**

| Option | Description | Selected |
|--------|-------------|----------|
| None (void) | Consistent with enable_compression / add_compression_policy / add_reorder_policy. | ✓ |
| Chunk name (str) | Return the fully-qualified chunk name (mirrors TimescaleDB's regclass return). | |

**User's choice:** Expose flags default True; return None
**Notes:** chunk bound as %s::regclass (accepts show_chunks output), never interpolated. Exact arg names + Apache/TSL availability left as a research question.

---

## Claude's Discretion

- D-05: whether `DROP MATERIALIZED VIEW` on a cagg needs the `connect(autocommit=True)` seam — researcher/planner to confirm against live TSDB 2.28.
- D-11: exact `if_not_compressed`/`if_compressed` argument names + Community/Apache availability for compress_chunk — researcher/planner to confirm.
- Test layering (mock SQL-shape + optional TSL-guarded live-DB integration) follows existing `tests/test_timescale.py` structure.

## Deferred Ideas

- `time_bucket_gapfill` origin/offset — only if trivially free during F02, else future follow-up.
- F03 batch/multi-chunk compress (compress-by-bound like drop_chunks) — not in the per-chunk requirement; future ergonomic.
- Milestone-level deferrals already recorded: ETL-INC-F05 (CDC/WAL), SPAT-F01 (gridSize), RASTER-F01 (raster).
