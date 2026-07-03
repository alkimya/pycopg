# Phase 49: Incremental ETL Follow-ups - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-03
**Phase:** 49-incremental-etl-follow-ups
**Areas discussed:** F01 first-run seed, F02 boundary knobs, F03 composite key, F04 advisory lock

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| F01 first-run seed | initial_watermark semantics/type/empty-batch/composite | ✓ |
| F02 boundary knobs | inclusive >= and/or lookback overlap | ✓ |
| F03 composite key | multi-column watermark shape/compare/envelope | ✓ |
| F04 advisory lock | block-vs-refuse, surface, scope, key derivation | ✓ |

**User's choice:** all four (one area per requirement, ETL-INC-F01..F04).

---

## F01 first-run seed (`initial_watermark`)

**Q1 — behavior once set**

| Option | Description | Selected |
|--------|-------------|----------|
| Seed-floor only | Used only when no stored wm exists; after first success, ignored forever | ✓ |
| Persistent lower clamp | max(initial, stored) on every run | |

**Q2 — field placement / validation**

| Option | Description | Selected |
|--------|-------------|----------|
| New frozen Pipeline field | requires incremental_column; {datetime,int,str} allowlist | ✓ |
| run() keyword param | pass at call time | |

**Q3 — empty first (seeded) batch**

| Option | Description | Selected |
|--------|-------------|----------|
| Record nothing, re-seed next run | consistent with shipped empty-batch rule | ✓ |
| Persist initial_watermark as the wm | advances despite no load | |

**User's choice:** seed-floor-only · new frozen Pipeline field · re-seed on empty first batch.
**Notes:** All three fall out of the existing `_read_watermark(None)` full-load path — minimal new logic.

---

## F02 boundary knobs (`>=` and/or lookback)

**Q1 — how the two controls are exposed**

| Option | Description | Selected |
|--------|-------------|----------|
| Two independent kw-only fields | incremental_inclusive: bool + incremental_lookback; orthogonal | ✓ |
| Single boundary mode enum | folds the bool into an enum | |

**Q2 — lookback type / application**

| Option | Description | Selected |
|--------|-------------|----------|
| timedelta\|int, subtracted in Python | recorded wm stays true max; str+lookback → ETLError at run | ✓ |
| Interval string | %s::interval, datetime-only, pushes arithmetic to SQL | |

**Q3 — boundary/overlap replay**

| Option | Description | Selected |
|--------|-------------|----------|
| Accept + document | safe by upsert idempotency (incremental already requires upsert) | ✓ |
| Add row dedup | extra state, zero correctness gain | |

**User's choice:** two orthogonal fields · timedelta\|int subtracted in Python · accept+document.
**Notes:** Default (False, None) is byte-identical to today. Lookback widens the read window only; the recorded high-water mark is always the true max(col).

---

## F03 composite (multi-column) watermark

**Q1 — field shape**

| Option | Description | Selected |
|--------|-------------|----------|
| Widen incremental_column | str \| Sequence[str]; normalize→tuple like conflict_columns | ✓ |
| New incremental_columns field | two fields + mutual-exclusion guard | |

**Q2 — comparison + computation**

| Option | Description | Selected |
|--------|-------------|----------|
| Row-value compare + max-row | (c1,c2) > (%s,%s) lexicographic; recorded = real greatest row | ✓ |
| Per-column AND + per-column max | WRONG — fabricates a tuple no row has, skips rows | |

**Q3 — JSONB envelope back-compat**

| Option | Description | Selected |
|--------|-------------|----------|
| New 'composite' tag, single unchanged | single-scalar shape verbatim; composite = new tagged shape | ✓ |
| Always wrap as a values list | re-shapes stored rows, saves nothing | |

**User's choice:** widen incremental_column · row-value compare + max-row · new 'composite' tag.
**Notes:** Zero migration — old single-scalar rows read exactly as before; `_decode_watermark` dispatches on the type tag. Composite makes `initial_watermark` a matching-length sequence (validation rule recorded in CONTEXT D-04).

---

## F04 advisory-lock concurrency

**Q1 — surface / opt-in**

| Option | Description | Selected |
|--------|-------------|----------|
| Opt-in Pipeline field | concurrency: Literal['wait','skip']\|None=None; None=off | ✓ |
| run() keyword param | runtime-scoped, splits config across surfaces | |

**Q2 — concurrency='skip' + lock held**

| Option | Description | Selected |
|--------|-------------|----------|
| Transient 'skipped' RunResult | run_id=None, no row (mirrors dry_run); no CHECK migration | ✓ |
| Raise ETLConcurrentRunError | fail-fast, forces try/except everywhere | |

**Q3 — lock scope / lifecycle**

| Option | Description | Selected |
|--------|-------------|----------|
| Session lock, dedicated conn, finally | covers full read→extract→load→record span; auto-release on close | ✓ |
| Transaction-scoped xact lock | only guards load txn; watermark-read race stays open | |

**Q4 — key derivation**

| Option | Description | Selected |
|--------|-------------|----------|
| DB-side hashtextextended | pg_try_advisory_lock(hashtextextended(%s,0)); deterministic cross-process | ✓ |
| Python-side hash | PYTHONHASHSEED-salted → different key per process → no serialization | |

**User's choice:** opt-in Pipeline field · transient 'skipped' RunResult · session lock on dedicated conn released in finally · DB-side hashtextextended key.
**Notes:** Available to all pipelines (not just incremental). 'skipped' is a documented transient status like 'dry_run' — never persisted, so no `pipeline_runs.status` CHECK change.

---

## Claude's Discretion

- Exact new SQL constant names/placement in `queries.py`; `hashtextextended` availability confirmation + `pg_try_advisory_lock` return handling.
- Composite max-row computation mechanism (`sort_values`/`nlargest`/equivalent) — any true lexicographic max-row satisfies D-10.
- Test layering (mock SQL-shape + live-DB; advisory-lock needs two sessions).
- `RunResult` field additions — none required; mirror the `watermark_used`/`watermark_recorded` optional pattern if one is added.

## Deferred Ideas

- ETL-INC-F05 (CDC / WAL change capture) — deferred 2026-07-02, large distinct subsystem. Don't re-litigate.
- Cross-pipeline / global advisory locks (F04 is per-pipeline on `pipeline.name`).
- `concurrency` as a `run()`-call override (decided as a Pipeline field).
- Surfacing the lookback-applied floor / seed on `RunResult`.
- Milestone-level deferrals: SPAT-F01 (gridSize), RASTER-F01 (raster).
