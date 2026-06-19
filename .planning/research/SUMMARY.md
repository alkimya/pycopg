# Project Research Summary

**Project:** pycopg v0.7.0 — Alias Removal + Incremental ETL
**Domain:** High-level Python PostgreSQL library — watermark-based incremental ETL extension
**Researched:** 2026-06-19
**Confidence:** HIGH

## Executive Summary

pycopg v0.7.0 is a two-workstream release built on top of the v0.5.0 ETL runner. The first workstream (ALIAS-RM-01) is purely mechanical: hard-remove 56 deprecated flat-accessor aliases that have been emitting `DeprecationWarning` since v0.6.0, ship a MIGRATION v0.6→v0.7 guide with a 1:1 replacement table, and add a `[Breaking]` CHANGELOG section. No research was needed here; no design decisions remain open. The second workstream (ETL-INC-01..10) wires the `pipeline_runs.watermark JSONB` column — reserved and always NULL since v0.5.0 — into a fully declarative watermark-based incremental loading loop via a new `Pipeline.incremental_column` optional field.

The incremental ETL feature is entirely additive. Zero new runtime dependencies are required (psycopg 3.3.4, pandas 2.x, and stdlib are sufficient). The implementation slots into three seams already present in the v0.5.0 architecture: the `pipeline_runs.watermark JSONB` column, the autocommit run-log connection pattern, and the existing `_end_run` success/failure path split. The canonical loop is: read last successful watermark → if NULL do full load else apply `WHERE col > watermark` filter → after successful load compute `max(incremental_column)` from the raw extracted batch (before transforms) → write typed JSONB envelope on success only. Full sync/async parity is non-negotiable.

The principal risk is the `>` vs `>=` boundary decision and its interaction with `load_mode="append"` (see Open Decisions — this must be resolved before Phase 26). Secondary risks are well-understood and mitigated: transform-drops-watermark-column (compute max before transforms), advance-on-failed-load (write watermark only on success path), JSONB round-trip type drift (tagged `{"value":..., "type":"..."}` envelope via `Jsonb()`), and unbounded first-run full load (document prominently; `initial_watermark` parameter as escape hatch).

## Key Findings

### Recommended Stack

Zero new runtime dependencies confirmed (HIGH — live-verified against psycopg 3.3.4).

**Core technologies:**

- **Python 3.11+:** `datetime.fromisoformat` full ISO 8601 support required
- **psycopg 3.3.4 `Jsonb`:** write path for JSONB watermark envelope; `json.loads` automatic on read via `JsonbLoader`; no global adapter mutation
- **pandas 2.x `Series.max()`:** returns `pd.Timestamp` (datetime) or `np.int64` (integer); both handled by `_encode_watermark`
- **numpy (transitive):** `isinstance(val, np.integer)` required in `_encode_watermark`

**Two new SQL constants in `queries.py` (additive only):**

- `ETL_GET_LAST_SUCCESS_WATERMARK` — `WHERE status='success' AND watermark IS NOT NULL ORDER BY started_at DESC LIMIT 1`
- `ETL_UPDATE_RUN_WITH_WATERMARK` — success-path UPDATE including `watermark = %s`; `ETL_UPDATE_RUN` unchanged for failure path

No schema migration. `pipeline_runs.watermark JSONB` exists in all installed schemas since v0.5.0 DDL.

### Expected Features

All 10 incremental features are P1. There are no P2/P3 items — the loop only works when all parts are correct.

**Must have (ETL-INC-01..10):**

- **ETL-INC-01** `Pipeline.incremental_column: str | None = None` — `replace` forbidden at construction; identifier validated via `validate_identifiers`
- **ETL-INC-02** First-run full load — NULL watermark = no filter; write `max(col)` after success
- **ETL-INC-03** `WHERE col > last_watermark` exclusive filter — SQL sources wrapped as subquery; table sources get WHERE appended; watermark value always passed as `%s` parameter (never interpolated)
- **ETL-INC-04** Record `max(incremental_column)` on success — computed from RAW batch BEFORE transforms
- **ETL-INC-05** Empty batch — success + `rows_loaded=0` + prior watermark preserved (never write NULL)
- **ETL-INC-06** `RunResult` + 2 fields: `watermark_used: Any | None`, `watermark_recorded: Any | None`
- **ETL-INC-07** `history()` returns watermark fields — falls out of ETL-INC-06; no query change
- **ETL-INC-08** `dry_run=True` — reads watermark (read-only), applies filter, computes would-be max, writes nothing
- **ETL-INC-09** Backfill/reset documented — no new code
- **ETL-INC-10** Full sync/async parity — `AsyncETLAccessor` mirrors all; `TestEtlParity` extended

**Defer to v0.8+:** configurable `>` vs `>=`; multi-column watermarks; CDC/WAL; late-data lookback; scheduler integration; advisory locks for concurrent-run protection.

### Architecture Approach

All changes are additive to the existing dual-connection ETL architecture. Two new insertion points in `ETLAccessor.run()` (and async mirror): watermark read before extract; watermark compute + conditional write after successful load. Pure builder functions follow the existing module-level, no-I/O, identifier-validating pattern.

**Components touched:**

1. **`Pipeline` dataclass** — `incremental_column` field + `__post_init__` guard
2. **`ETLAccessor` / `AsyncETLAccessor`** — `_read_watermark(name)` helper; modified `_end_run(... watermark=None)`; modified `run()` extract step
3. **`queries.py`** — 2 new SQL constants; all existing constants unchanged
4. **`RunResult`** — 2 new fields defaulting to `None`; `_row_to_result` updated
5. **New tests** — `tests/test_etl_incremental.py` + `tests/test_etl_incremental_async.py`

**Alias removal touches:** `database.py`, `async_database.py`, alias test stubs, `MIGRATION.md`, `CHANGELOG.md`.

### Critical Pitfalls

1. **Transform drops watermark column** — compute `max(incremental_column)` from the RAW extracted DataFrame BEFORE transform chain; assert column presence; raise `ETLIncrementalError` (not `KeyError`). Highest-priority structural decision — must be locked in Phase 26 design.
2. **Watermark advances on failed load** — write watermark ONLY on success path; `except` block calls `_end_run` without `watermark` arg. Test: fail load → assert `watermark IS NULL` on that run row → assert next run re-extracts from prior watermark.
3. **Boundary/equal-timestamp data loss with `append`** — `>` filter silently drops rows sharing exact boundary timestamp. For non-unique timestamp columns + append mode, this is silent data loss. (See Open Decisions.)
4. **JSONB round-trip type drift** — typed envelope `{"value": ..., "type": "timestamptz"|"bigint"|"float"|"text"}` via `Jsonb()`. Naive datetime strings (no `+00:00`) interpreted in session timezone by PostgreSQL. Write round-trip unit tests for all types before wiring runner.
5. **Unbounded first-run full load** — NULL watermark = full extract of entire source. Document prominently. `initial_watermark` parameter is the clean escape hatch.

## Open Decisions for Requirements

**One genuine split across all 4 researchers — must be resolved before Phase 26 planning.**

### Boundary + `append` safety: ALLOW or FORBID `incremental_column` + `load_mode="append"`?

All researchers agree on `>` (exclusive) as the filter operator. They diverge on construction-time validation:

**Position A — ALLOW (FEATURES view):**
`>` already avoids re-loading the boundary row. For pipelines with strictly monotonic unique watermark columns (e.g., `BIGSERIAL id`), `append` is safe. Forbidding it forces unnecessary `upsert` + `conflict_columns` on users with clean integer keys.
Proposal: allow `append`; document constraint ("watermark column must be unique and strictly increasing"); emit warning if `conflict_columns` absent.

**Position B — FORBID (PITFALLS view):**
Most real-world timestamp watermark columns are non-unique (multiple rows can share the same `updated_at` second). Silent data loss is worse than an upfront `ValueError`. Upsert makes the pipeline idempotent regardless of column uniqueness.
Proposal: raise `ValueError` at `Pipeline` `__post_init__` when `incremental_column` + `load_mode="append"`; add `append_incremental_unsafe=True` opt-in to override.

**Impact:** One line in `__post_init__`, significant user-experience and correctness consequences. Requirements must pick one. Do not defer to implementation.

## Implications for Roadmap

Phases continue from Phase 25 (v0.6.0 closed at Phase 24). Suggested 5 phases (25–29):

### Phase 25 — Alias Removal (ALIAS-RM-01)

**Rationale:** Mechanical debt, zero ETL coupling; resolves WR-01 (IDE signature degradation, 3 phases deep) immediately; keeps ETL git diff clean.
**Delivers:** Hard removal of 56 deprecated aliases; MIGRATION v0.6→v0.7 with 1:1 table; `[Breaking]` CHANGELOG section; parity tests updated.
**Research flag:** Skip — mechanical, no open questions.

### Phase 26 — Incremental ETL: Pure Layer

**Rationale:** Pure functions and `Pipeline` field are the foundation; unit-testable without DB; validates the `append` boundary decision before touching live connections.
**Delivers:** `Pipeline.incremental_column` + `__post_init__` validations (locked boundary decision); pure builders (`build_wrapped_source_sql`, `build_incremental_table_sql`, `build_incremental_where_clause`, `_compute_new_watermark`); `_encode_watermark` / `_decode_watermark` with round-trip type tests.
**Avoids:** Transform-drops-watermark (locks "compute pre-transform" contract); JSONB type drift (round-trip tests before runner).

### Phase 27 — Incremental ETL: Run-Log Integration

**Rationale:** `_read_watermark` and modified `_end_run` proven in isolation before wiring into full `run()` body; invariant tests (no-advance-on-failure) are easier to write against these helpers alone.
**Delivers:** `_read_watermark(name)` + async mirror; `_end_run(..., watermark=None)` + dispatch to `ETL_UPDATE_RUN_WITH_WATERMARK`; 2 new SQL constants; integration tests: first-run writes watermark, failure does NOT advance, empty batch does NOT advance.

### Phase 28 — Incremental ETL: Extract Integration + Async Parity + RunResult

**Rationale:** Extract modification is the riskiest change (SQL injection surface, subquery wrapping); builds on proven Phase 26 builders and Phase 27 run-log integration.
**Delivers:** `run()` modified extract step (incremental filter injection); `RunResult.watermark_used` + `watermark_recorded`; `_row_to_result` update; `dry_run=True` with incremental; end-to-end integration tests; `TestEtlParity` extended; subquery alias locked as a constant.

### Phase 29 — Release v0.7.0

**Delivers:** CHANGELOG `[0.7.0]` finalized; MIGRATION v0.6→v0.7 complete; version bump; Sphinx docs; PyPI publish.
**Gates:** coverage ≥ 94%, `interrogate ≥ 95%`, Sphinx `-W` clean, `-W error::DeprecationWarning` passes.

### Phase Ordering Rationale

- Phase 25 first: independent mechanical workstream, resolves WR-01, keeps ETL diffs clean
- Phase 26 before 27: pure functions exist before accessors call them; no-DB unit tests give fast feedback
- Phase 27 before 28: invariant (no-advance-on-fail) proven in isolation before buried in full `run()` body
- Phase 28 last for incremental: riskiest SQL construction change; builds on all prior phases
- Phase 29 gated on full integration suite, coverage, and interrogate

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Live-verified: psycopg 3.3.4 Jsonb round-trip, pandas max() types, numpy isinstance, datetime.fromisoformat 3.11+ |
| Features | HIGH | 10 features fully specified with dependency graph; codebase-anchored; ecosystem cross-check (dlt, Matillion, Fivetran, ADF) |
| Architecture | HIGH | Direct source reading of etl.py and queries.py; all integration points located and documented |
| Pitfalls | HIGH | Derived from direct code reading of ETL success/failure path; cross-checked against Airbyte/dbt/Debezium CDC literature |

**Overall confidence:** HIGH

### Gaps to Address

- **`append` + `incremental_column` boundary decision:** Must be resolved in REQUIREMENTS before Phase 26. See Open Decisions.
- **`initial_watermark` parameter scope:** PITFALLS recommends it; FEATURES/ARCHITECTURE treat first-run as documented behavior. Requirements decides: in v0.7.0 or defer to v0.8?
- **`RunResult.watermark_used` population mechanism:** `_row_to_result` only sees what was recorded, not what was used as filter. Requirements/Phase 28 picks: pass `watermark_used` as a param, or capture inline in `run()`.
- **Subquery alias constant:** Lock as a named constant in Phase 26, not left to implementor.
- **Concurrent-run documentation scope:** Document in Phase 28 that concurrent runs are safe only with `upsert`; for `append` + incremental the caller must ensure non-overlapping runs.

## Sources

### Primary (HIGH confidence)

- `pycopg/etl.py` — ETLAccessor.run(), _end_run, _start_run, Pipeline.__post_init__, all existing builders; async mirror
- `pycopg/queries.py` — ETL_INIT_PIPELINE_RUNS (watermark JSONB confirmed), ETL_UPDATE_RUN, ETL_GET_LAST_RUN
- `.planning/PROJECT.md` — v0.7.0 locked scope; phase numbering; dual-connection invariant
- psycopg 3 JSON adaptation — Context7 `/psycopg/psycopg` + live import test (psycopg 3.3.4); `JsonbLoader.load()` source inspection
- pandas `Series.max()` — live tests (pd.Timestamp, np.int64, pd.NaT on empty)
- Python 3.11+ `datetime.fromisoformat` — stdlib docs

### Secondary (MEDIUM confidence)

- dlt incremental loading docs — boundary operator comparison (`>=` with content-hash dedup)
- Matillion, ETLworks, Azure FastTrack HWM docs — `>` (exclusive) as industry standard HWM pattern
- Fivetran incremental pipeline blog — first-run full sync pattern
- Airbyte, dbt, Debezium CDC docs — snapshot hazard, read-committed incremental ETL gap

---
*Research completed: 2026-06-19*
*Ready for roadmap: yes*
