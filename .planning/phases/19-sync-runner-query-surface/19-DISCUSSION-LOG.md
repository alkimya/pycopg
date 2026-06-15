# Phase 19: Sync Runner & Query Surface - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 19-sync-runner-query-surface
**Areas discussed:** RunResult shape & error, history() limit param, dry_run semantics, RunResult construction seam

---

## RunResult shape & `error` field

| Option | Description | Selected |
|--------|-------------|----------|
| `error` = message only | `error: str \| None` = error_message column; traceback stays in DB row | ✓ |
| `error` + `error_traceback` | RunResult carries both columns | |
| `error` = exception-like object | Wrap message + traceback in a small structure | |

**User's choice:** `error` = message only (Recommended)
**Notes:** Matches SC-1's single `error` field literally; keeps repr clean. error_traceback remains queryable in the DB row for forensics. → D-03.

---

## RunResult: watermark field

| Option | Description | Selected |
|--------|-------------|----------|
| Omit watermark for now | Only the 8 SC-1 fields; add watermark in v0.6.0 | ✓ |
| Include watermark field (always None) | Forward-compatible but a dead always-None field | |

**User's choice:** Omit watermark for now (Recommended)
**Notes:** watermark column is always NULL in v0.5.0; surfacing it is noise. → D-04.

---

## RunResult: dataclass style

| Option | Description | Selected |
|--------|-------------|----------|
| frozen=True | `@dataclass(frozen=True)`, mirrors Pipeline | ✓ |
| Plain @dataclass | Mutable, mirrors Config | |

**User's choice:** frozen=True (Recommended)
**Notes:** A result is an immutable snapshot; freezing signals "snapshot, not handle". → D-01.

---

## history() limit parameter

| Option | Description | Selected |
|--------|-------------|----------|
| `limit: int = 100` default | Safe cap, caller can raise; binds to existing LIMIT %s | ✓ |
| `limit: int \| None = None` (all rows) | Returns everything by default | |
| No limit arg — fixed cap | Hidden internal cap, smallest API | |

**User's choice:** `limit: int = 100` default (Recommended)
**Notes:** Echoes the safe-default instinct (default_batch_size=1000 in Config); newest-first already locked in ETL_LIST_RUNS. → D-06.

---

## dry_run: run_id

| Option | Description | Selected |
|--------|-------------|----------|
| run_id = None | `run_id: int \| None`; None for dry runs (no DB row) | ✓ |
| run_id = 0 / -1 sentinel | Magic int sentinel | |
| run_id = generated UUID/local id | Synthetic id | |

**User's choice:** run_id = None (Recommended)
**Notes:** A dry run genuinely has no id; `if result.run_id is None` is a clean dry-run signal. Makes RunResult.run_id Optional. → D-05/D-08.

---

## dry_run: other fields

| Option | Description | Selected |
|--------|-------------|----------|
| Real extract count + timestamps, error=None | rows_extracted=len(df), in-memory timestamps | ✓ |
| Minimal — zeros/None except status | Just status='dry_run', everything else empty | |

**User's choice:** Real extract count + timestamps, error=None (Recommended)
**Notes:** Gives a meaningful "how many rows would this pull?" preview — the most useful thing a dry run can report. → D-08.

---

## RunResult construction seam

| Option | Description | Selected |
|--------|-------------|----------|
| run() SELECTs the row it just wrote | One source of truth (DB row), one shared mapper | ✓ |
| run() assembles RunResult in-memory | No extra query but risks Python-vs-DB drift | |
| Hybrid — in-memory for run, SELECT for queries | Two construction paths by design | |

**User's choice:** run() SELECTs the row it just wrote (Recommended)
**Notes:** One mapper shared with history/last_run; guaranteed-consistent values; the extra SELECT is negligible vs the load. dry_run is the sole in-memory exception (no row to map). → D-11.

---

## row→RunResult mapper location

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level pure function in etl.py | `_row_to_result(row)` next to other pure builders | ✓ |
| Static/instance method on ETLAccessor | Groups with accessor but needs no state | |
| classmethod RunResult.from_row(row) | Reads nicely but leaks DB column names into the dataclass | |

**User's choice:** Module-level pure function in etl.py (Recommended)
**Notes:** Pure, unit-testable without a DB, mirrors the existing _build_insert_sql/_step_label pattern; avoids leaking error_message/watermark column names into the public value object. → D-10.

---

## Claude's Discretion

- Whether `last_run` delegates to `history(name, limit=1)` or runs `ETL_GET_LAST_RUN` directly (D-07).
- The SELECT-by-`run_id` query for run()'s re-SELECT — likely a new `run_id`-keyed constant since existing constants filter by `pipeline_name` (D-11, flagged for researcher/planner).
- Whether to export `Pipeline`/`RunResult` from `__init__.py` now or defer to Phase 20.
- RunResult field ordering, timestamp type hints, and whether `status` is `str` vs a `Literal`.

## Deferred Ideas

- `watermark` on RunResult → v0.6.0.
- `Literal` status type / 4th persisted status → optional polish; dry_run stays RunResult-only.
- Public `__init__.py` export finalization → Phase 20.
- `AsyncETLAccessor` parity, TestEtlParity, Sphinx docs, coverage ratchet, release → Phase 20.
- `history()` paging / status/time filters → not requested for v0.5.0.
