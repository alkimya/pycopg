# Phase 28: Incremental ETL — Extract, RunResult & Async Parity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-21
**Phase:** 28-incremental-etl-extract-runresult-async-parity
**Areas discussed:** RunResult & history() shape, dry_run incremental semantics, Async parity port, Docs + parity-test fact

---

## RunResult & history() shape

How should `history()` / `last_run()` populate `watermark_used` for past rows,
given `watermark_used` (the filter floor applied) is not stored — only
`watermark_recorded` (the persisted high-water mark = the `pipeline_runs.watermark`
column) is?

| Option | Description | Selected |
|--------|-------------|----------|
| None for stored rows | `watermark_used` only set on `RunResult` from `run()`/`dry_run`; `history()`/`last_run()` set it `None` (no `used` column). Recorded always surfaced from the row. No schema change. | ✓ |
| Store watermark_used too | Add a second JSONB column to `pipeline_runs` + SQL + encode/decode + migration. Heavier; fuller audit trail. | |
| Derive from prior row | Compute `watermark_used` of row N as `watermark_recorded` of the previous successful row. Approximation; breaks on empty/failed runs; fragile. | |

**User's choice:** None for stored rows (→ D-A1)
**Notes:** Keeps the v0.5.0-reserved single `watermark JSONB` column sufficient,
no migration. Non-incremental pipelines → both fields `None` everywhere
(roadmap SC-3); `_row_to_result` maps NULL → `None` (D-A1a).

---

## dry_run incremental semantics

Should `dry_run` apply the `WHERE col > wm` filter (faithful preview) and report
`watermark_used` + the would-be `watermark_recorded`, writing no row?

| Option | Description | Selected |
|--------|-------------|----------|
| Filtered preview | Reads prior watermark, applies the same WHERE filter as a real run, sets `watermark_used` = floor and `watermark_recorded` = max(col) of the filtered raw batch (None if empty/all-NULL). `rows_extracted` reflects the real would-be pull. No row written. | ✓ |
| Unfiltered + computed marks | Keeps extracting the full source but still reports the marks. `rows_extracted` is misleading for incremental pipelines. | |

**User's choice:** Filtered preview (→ D-A2)
**Notes:** Consequence D-A2a — both the dry-run fork and the real path must apply
the *same* filter, so the watermark read + filtered extract should be factored to
prevent drift (exact factoring is planner discretion).

---

## Async parity port

Confirm `AsyncETLAccessor` becomes a strict 1:1 behavioral mirror — the full
Phase-27+28 stack ported (async `_read_watermark`, `_end_run(watermark=)`,
max-capture with guards, WHERE filter, RunResult fields, dry_run) with identical
guard semantics and `ETLError` message text.

| Option | Description | Selected |
|--------|-------------|----------|
| Strict 1:1 mirror | Identical guard logic + identical `ETLError` messages + identical empty/all-NULL/float handling. Only mechanical diffs: `await`, `asyncio.to_thread`. | ✓ |
| Mirror, async-idiomatic msgs OK | Same behavior but allow slightly different async message text. Risks parity-test drift. | |

**User's choice:** Strict 1:1 mirror (→ D-A3)
**Notes:** Verified async accessor has ZERO watermark wiring today (no `watermark`
refs at/after line 1334; `_end_run` still on `ETL_UPDATE_RUN`; no async
`_read_watermark`). Core Value = strict sync/async parity.

---

## Docs + parity-test fact

How deep should the `docs/etl.md` incremental section go; and how is the
backfill/reset workflow prescribed given there is no reset API and
`initial_watermark` is deferred?

**Docs depth:**

| Option | Description | Selected |
|--------|-------------|----------|
| Contract + worked example | Worked Pipeline example + watermark-column requirements + upsert requirement + RunResult fields + dry_run + backfill/reset. Covers ETL-INC-12 fully. | ✓ |
| Minimal contract only | Requirements list + backfill note, no example. Thinner. | |
| Full tutorial | Multi-run narrative + troubleshooting + operator guidance. More than ETL-INC-12 needs. | |

**User's choice:** Contract + worked example (→ D-A4)

**Reset method:**

| Option | Description | Selected |
|--------|-------------|----------|
| Manual SQL, documented | Document `UPDATE pipeline_runs SET watermark = NULL WHERE pipeline_name = %s` (or DELETE rows) to force a full reload; next `run()` reads None → full load. Note `initial_watermark` coming in v0.8.0. No new code. | ✓ |
| Add a reset helper now | Add `db.etl.reset_watermark(name)`. Scope creep — not in any ETL-INC-* requirement. | |

**User's choice:** Manual SQL, documented (→ D-A5)
**Notes:** During this area, surfaced a **fact correction**: roadmap SC-5's
`TestEtlParity` reference is stale — that class was removed; ETL parity is now
covered by `test_accessor_parity` over `ACCESSOR_PAIRS` (`test_parity.py:516`).
Recorded in CONTEXT.md so downstream agents do NOT restore a `TestEtlParity` class.

---

## Claude's Discretion

- Exact factoring of the shared filtered-extract path (helper vs inline mirror).
- Whether `_row_to_result` decodes the watermark inline or via a tiny guarded helper.
- Integration-test placement / fixture reuse (extend the Phase-27 incremental test classes).
- Docstring wording (numpydoc shallow, `interrogate ≥ 95`).
- Whether async incremental integration tests reuse sync fixtures or define async mirrors.
- `extract_limit` + watermark-filter composition ordering (LIMIT on the filtered subquery).

## Deferred Ideas

- `initial_watermark` first-run bound — v0.8.0 (ETL-INC-F01).
- Configurable `>=` boundary / late-data lookback — v0.8.0 (ETL-INC-F02).
- Multi-column / composite watermarks — deferred (ETL-INC-F03).
- Public `db.etl.reset_watermark()` helper — rejected as scope creep (D-A5).
- `float` watermark support — out of scope for v0.7.0 (ETLError raised).
- Storing `watermark_used` in `pipeline_runs` (extra column) — rejected (D-A1).
- v0.7.0 release mechanics — Phase 29 (REL-07).
