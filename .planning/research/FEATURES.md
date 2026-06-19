# Feature Research — Incremental ETL (v0.7.0)

**Domain:** Watermark-based incremental ETL for a high-level Python PostgreSQL library
**Researched:** 2026-06-19
**Confidence:** HIGH (codebase analysis + ecosystem verification via dlt, Matillion, Fivetran, ETLworks docs)

---

## Context: What v0.7.0 Adds

v0.5.0 shipped a full-load declarative ETL runner (`db.etl.run(pipeline)`). The `pipeline_runs` table already has a reserved nullable `watermark JSONB` column (always NULL so far). v0.7.0 wires that column: a new `Pipeline.incremental_column` field activates watermark-based incremental loading without any schema migration. Everything described here is an additive extension of the existing surface — no existing behavior changes.

**Existing surface this builds on (do not re-research):**

- `Pipeline` frozen dataclass: `name`, `source`, `target`, `load_mode`, `conflict_columns`, `schema`, `transform`, `extract_limit`
- `RunResult`: `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, `error`
- `ETLAccessor.run()` / `AsyncETLAccessor.run()` (sync + async parity)
- `history(name)`, `last_run(name)`, `dry_run=True`
- `pipeline_runs` table: run-tracking isolation via dedicated autocommit connections; `watermark JSONB` column reserved

---

## The Canonical Incremental-Load Loop

This is the behavior users will assume based on every incremental ETL tool they have used:

```
1. Read last_watermark = SELECT watermark FROM pipeline_runs
                         WHERE pipeline_name = :name AND status = 'success'
                         ORDER BY finished_at DESC LIMIT 1
   → NULL on first run (no prior successful run)

2. Build filter:
   - NULL watermark  → no WHERE clause (full load)
   - has watermark   → WHERE {incremental_column} > {last_watermark}

3. Extract delta via filtered source query
   (SQL sources: wrapped as subquery + WHERE col > %s)
   (table sources: SELECT * FROM schema.table WHERE col > %s)

4. Load delta using load_mode (append or upsert)

5. Compute new_watermark = MAX(incremental_column) from extracted batch
   → NULL if batch was empty (no new rows)

6. Record run row with:
   - status = 'success'
   - watermark = {"column": "col_name", "value": new_watermark_serialized}
   → If batch was empty: copy last_watermark unchanged (no regression)
```

Users understand this loop implicitly. Any deviation from it — particularly a watermark that regresses, silently re-processes rows, or skips rows at the boundary — will be perceived as a bug.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist when `Pipeline.incremental_column` is set. Missing any of these makes the feature feel broken or incomplete.

---

#### ETL-INC-01 — `Pipeline.incremental_column` field (declaration)

- **Why expected:** Every incremental ETL tool (dlt, Fivetran, Matillion, ADF) exposes a single cursor/watermark column declaration. Users expect to write `Pipeline(..., incremental_column="updated_at")` and have the library handle filter generation automatically.
- **Complexity:** LOW
- **Depends on:** existing `Pipeline` frozen dataclass — adds one optional field `incremental_column: str | None = None`
- **Notes:**
  - Construction-time validation: `incremental_column` + `load_mode='replace'` → raise `ValueError` (locked scope decision)
  - Construction-time validation: `incremental_column` requires `incremental_column` to be a valid identifier (passes `validate_identifiers`)
  - `incremental_column=None` (default) = existing full-load behavior, unchanged
  - The column must appear in the SELECT output of the source query — the library cannot validate this at construction time, only at run time when the extracted DataFrame columns are known

#### ETL-INC-02 — First-run full load then record watermark

- **Why expected:** Users understand that the first run is always a full load (no prior watermark). Every incremental tool (dlt, Airflow) follows this: "first run seeds the state". Users would find it surprising and confusing if the first run filtered on a non-existent watermark.
- **Complexity:** LOW
- **Depends on:** `last_run()` to detect absence of a prior successful watermark; existing extract path
- **Notes:**
  - "First run" = no successful run row exists for this pipeline name, OR no prior run has a non-null `watermark`
  - First run executes with no filter (same extract path as non-incremental)
  - After a successful first run, `watermark` is written to `pipeline_runs` as `{"column": "<col>", "value": <max_value>}`
  - A failed first run records `status='failed'` with NULL watermark — the next run is still treated as a first run (full load)

#### ETL-INC-03 — `>` (exclusive) watermark filter for subsequent runs

- **Why expected:** All major tools use a strict-greater-than filter for the lower watermark bound by default: `WHERE col > last_watermark`. This is the safe, non-duplicating default for both append and upsert modes. See boundary analysis in the Anti-Features section for full reasoning.
- **Complexity:** MEDIUM
- **Depends on:** `_is_sql_source` heuristic; new `_build_incremental_sql` builder; `validate_identifiers`
- **Notes:**
  - SQL sources: wrapped as `SELECT * FROM (<original_sql>) AS _etl_inc WHERE <col> > %s`
  - Table sources: `SELECT * FROM <schema>.<table> WHERE <col> > %s`
  - The watermark value is always passed as a `%s` parameter — never f-string interpolated (security invariant inherited from the existing codebase)
  - `incremental_column` is validated with `validate_identifiers` before any identifier interpolation into the WHERE clause
  - The watermark value extracted from `pipeline_runs.watermark JSONB` is deserialized to the appropriate Python type before use as a parameter. For timestamps this is a `datetime`; for integers it is an `int`.

#### ETL-INC-04 — Record new high-water mark on success

- **Why expected:** Watermark state must persist across runs. Users expect that a successful run advances the watermark to `max(incremental_column)` of the batch just loaded. The existing `pipeline_runs.watermark JSONB` column is purpose-built for this.
- **Complexity:** LOW
- **Depends on:** `ETL_UPDATE_RUN` query — must be extended to also write `watermark`; or a separate update
- **Notes:**
  - New watermark = `max(df[incremental_column])` computed on the extracted+transformed DataFrame before load
  - Stored as `{"column": "<col_name>", "value": <serialized_value>}` in `pipeline_runs.watermark JSONB`
  - Datetime values serialized as ISO-8601 strings in JSONB; integer values stored as JSON numbers
  - The JSONB envelope carries the column name so `history()` can surface it unambiguously without needing to know the pipeline's current config
  - If the extracted batch is empty (zero rows after filter), the new watermark equals the last watermark (no regression). The run records `status='success'`, `rows_loaded=0`, and the prior watermark is copied forward.

#### ETL-INC-05 — Empty-batch handling (no new rows since last run)

- **Why expected:** Incremental pipelines are run on a schedule. Many runs will produce zero new rows. Users expect: successful run, rows_loaded=0, watermark unchanged, no error.
- **Complexity:** LOW
- **Depends on:** existing empty-DataFrame path in `ETLAccessor.run()` (already returns early with 0 rows_loaded)
- **Notes:**
  - Empty batch → skip load → record success with watermark = last_watermark (unchanged)
  - This is a normal, expected outcome — NOT an error or warning
  - `RunResult.rows_extracted = 0`, `RunResult.rows_loaded = 0`
  - The watermark value recorded in `pipeline_runs` must not be NULL (use last watermark) — a NULL watermark on the next run would trigger a full reload, which would be a severe regression

#### ETL-INC-06 — `RunResult` exposes watermark used and recorded

- **Why expected:** Users running `db.etl.run(pipeline)` need to see what filter was applied and what watermark was recorded. Without this, debugging incremental runs requires querying `pipeline_runs` directly.
- **Complexity:** LOW
- **Depends on:** `RunResult` frozen dataclass — adds 2 new fields
- **Notes:**
  - Two new `RunResult` fields: `watermark_used: Any | None` and `watermark_recorded: Any | None`
  - `watermark_used`: the value read from prior `pipeline_runs.watermark` and used as the filter threshold (None for first run / full-load runs)
  - `watermark_recorded`: the new `max(col)` value stored after this run (None for failed runs; same as `watermark_used` for empty-batch runs; None for non-incremental pipelines)
  - For non-incremental pipelines (no `incremental_column`): both fields are `None`
  - `_row_to_result` must be updated to read `watermark` from the `pipeline_runs` row and parse it

#### ETL-INC-07 — `history()` returns watermark fields per run

- **Why expected:** `history()` returns `list[RunResult]`. Since `RunResult` now carries watermark fields, `history()` automatically exposes the full watermark progression across runs. Users expect to be able to audit which watermark each run used and recorded.
- **Complexity:** LOW (falls out of ETL-INC-06 if `_row_to_result` is updated correctly)
- **Depends on:** ETL-INC-06 (`RunResult` watermark fields); `ETL_LIST_RUNS` already does `SELECT *` which includes `watermark` JSONB
- **Notes:**
  - No change to `history()` signature or query — it already does `SELECT *`
  - Only `_row_to_result` needs updating to parse `pipeline_runs.watermark JSONB` → `watermark_used` / `watermark_recorded`
  - The JSONB envelope `{"column": ..., "value": ...}` is the serialization format; deserialization happens in `_row_to_result`

#### ETL-INC-08 — `dry_run=True` with incremental: compute filter, return would-be max, write nothing

- **Why expected:** Users expect `dry_run=True` to show them exactly what an incremental run would do — what filter would be applied, how many rows would be extracted, and what the new watermark would be — without writing anything. This is the primary testing workflow for incremental pipelines.
- **Complexity:** LOW
- **Depends on:** existing `dry_run` fork in `ETLAccessor.run()` (already forks before `init()`/`_start_run()`)
- **Notes:**
  - `dry_run=True` with incremental: reads the last watermark from `pipeline_runs` (read-only, autocommit connection), builds the filter, extracts the delta, computes `max(col)` on the result
  - Returns `RunResult(status='dry_run', rows_extracted=N, rows_loaded=0, watermark_used=<last>, watermark_recorded=<would_be_max>)`
  - No `pipeline_runs` row is written (consistent with existing `dry_run` contract)
  - `dry_run=True` on a pipeline with no prior successful run: extracts the full source (no filter), `watermark_used=None`, `watermark_recorded=<max_of_full_extract>`
  - If `pipeline_runs` does not exist yet: `dry_run` does NOT create it (consistent with existing behavior — `dry_run` writes nothing)

#### ETL-INC-09 — Backfill / reset: delete successful runs to force full reload

- **Why expected:** Users need a "reset" mechanism to re-process all history. This is a universal pattern: dlt has `--full-refresh`, Fivetran has "resync". Without a documented reset path, users are stuck if their incremental state is corrupted.
- **Complexity:** NONE (no new code) — operational pattern, documented behavior
- **Depends on:** existing `pipeline_runs` table; user-accessible `pipeline_runs` table is part of the public contract
- **Notes:**
  - Reset = user deletes (or `UPDATE ... SET watermark = NULL`) the `pipeline_runs` rows for the pipeline name, then re-runs
  - Alternatively: delete the `success` status rows; next run finds no prior successful watermark → full load
  - This requires NO new library code — the `pipeline_runs` table is the user's interface. Document it clearly in docstrings and CHANGELOG.
  - The library's responsibility: ensure a run with NULL watermark is always treated as a first run (full load). That guarantee is the reset mechanism.
  - Anti-pattern to avoid: a "reset" API method on the accessor — this would encourage replacing the user's own data management with a library call, which creates an abstraction leak

#### ETL-INC-10 — Full sync/async parity for incremental

- **Why expected:** pycopg's Core Value is full sync/async parity. Every behavior described in ETL-INC-01 through ETL-INC-09 must exist identically in `AsyncETLAccessor`. This is non-negotiable.
- **Complexity:** MEDIUM (mirroring, not original logic)
- **Depends on:** all ETL-INC-01..09 implemented in `ETLAccessor`; `AsyncETLAccessor` mirrors verbatim
- **Notes:**
  - `TestEtlParity` harness must be extended to register incremental pipeline pairs
  - The new `watermark_used` / `watermark_recorded` fields on `RunResult` are shared between sync and async paths — no divergence
  - Async watermark read (to get last watermark) uses existing `connect(autocommit=True)` pattern

---

### Differentiators (Competitive Advantage for This Library)

Features that go beyond the minimum loop described above. Not assumed, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **`watermark_used` / `watermark_recorded` on `RunResult`** | Users see filter applied + new state in the return value of `run()`. No separate query needed to audit what happened. | LOW | Fields: `Any \| None`. Non-incremental pipelines carry `None`. Falls out of `_row_to_result` update. |
| **Empty-batch watermark preservation** | Zero new rows → watermark does NOT regress to NULL. Next run filters from the same point. | LOW | Critical correctness property — many tools get this wrong on first implementation. |
| **`dry_run=True` reads last watermark** | Simulate exactly what the next real run would do, including reading the current watermark. Decision-support for debugging without side effects. | LOW | Extends existing `dry_run` path; adds one read-only autocommit query. |
| **`incremental_column` validated as SQL identifier at construction** | Prevents injection at pipeline definition time, not at run time. Consistent with existing codebase security model. | LOW | `validate_identifiers(pipeline.incremental_column)` in `Pipeline.__post_init__`. |
| **Table source incremental (not just SQL source)** | `source="events"` (table name) + `incremental_column="created_at"` works without the user writing SQL. The library generates `SELECT * FROM schema.table WHERE col > %s`. | LOW | Already handled by the `_is_sql_source` branch split — just add WHERE to the table-source path. |

---

### Anti-Features (Explicitly Out of Scope for v0.7.0)

These are commonly requested in incremental ETL contexts but explicitly out of scope. Do NOT include them.

| Anti-Feature | Why Requested | Why Out of Scope | What to Do Instead |
|--------------|---------------|------------------|--------------------|
| **`>=` (inclusive) boundary as default** | "I want to re-process the boundary row to be safe" | Creates silent duplicates for `append` mode. Correct for upsert but confusing as a default. Boundary decision must be single and consistent. | Use `>` (exclusive). Document that for upsert, idempotency means re-processing boundary rows is safe anyway. Users with late-arriving data should use a safety window in their source SQL manually. |
| **`load_mode='replace'` with `incremental_column`** | "I want to replace the last N rows" | Replace means TRUNCATE + full reload — semantically incompatible with incremental filtering. Ambiguous and dangerous. | Locked scope: `ValueError` at construction time. Users who want rolling-window replacement should use `source="SELECT * FROM t WHERE ..."` in a non-incremental pipeline. |
| **Multi-column composite watermarks** | "My table has (tenant_id, updated_at) as the cursor" | Composite watermarks require tuple comparison semantics that differ across PostgreSQL types. State management and serialization complexity is high. | Users should use a single `max(incremental_column)` via their `source` SQL to synthesize a single cursor column. |
| **Configurable `>` vs `>=` boundary** | "Let me choose inclusive or exclusive per pipeline" | Two modes with overlapping semantics confuse users and test matrices. One safe default is better than two options. | Document the `>` default clearly. Upsert users are safe either way. |
| **CDC log decoding (WAL / logical replication)** | "I want change data capture without a watermark column" | Requires `pg_logical` or `wal2json`, replication slots, and a completely different extraction architecture. Out of scope for a high-level library. | Scope boundary: same-DB, declarative single-column watermark only. |
| **Scheduler / cron integration** | "Run this pipeline every 5 minutes" | pycopg is a library, not a daemon. Scheduling is the caller's responsibility. | Document: call `db.etl.run(pipeline)` from your scheduler (APScheduler, cron, Airflow). |
| **Cross-run deduplication by content hash** | "Deduplicate rows where the content matches regardless of watermark" | Requires hashing every row and maintaining a seen-set — O(N) state per run. Scope creep. | Use `load_mode='upsert'` with `conflict_columns` for content-keyed deduplication. |
| **Late-arriving data / out-of-order events** | "Events arrive up to 5 minutes late — add a safety lookback window" | Safety windows require configurable overlap logic and change the watermark semantics significantly. | Users who need late-data tolerance should shift the watermark back in their source SQL: `WHERE col > (last_watermark - INTERVAL '5 minutes')` and use `load_mode='upsert'`. |

---

## The `>` vs `>=` Boundary Decision (Critical)

This is the single most important behavioral decision for the incremental feature. The answer must be unambiguous.

### The Tradeoff

| Operator | Filter | For `append` | For `upsert` |
|----------|--------|-------------|-------------|
| `>` (exclusive) | `WHERE col > last_watermark` | Safe: no re-processing of already-loaded rows | Also safe: skips the boundary row (which was already loaded and committed to target) |
| `>=` (inclusive) | `WHERE col >= last_watermark` | Unsafe: re-inserts the row(s) at the exact watermark value → duplicates | Safe: re-upserting is idempotent, but wastes a row-load per run |

### Root Cause of the Tension

The watermark is `max(col)` of the last successful batch. The row(s) that produced that max have already been loaded. Using `>=` re-fetches them on the next run.

- For `upsert`: re-fetching those rows is harmless (ON CONFLICT DO UPDATE produces the same row state).
- For `append`: re-fetching those rows inserts them again → duplicate rows in the target.

### Recommended Default: `>` (exclusive) for both modes

**Rationale:**

1. **`append` requires `>`** — there is no safe alternative for append mode. `>=` produces duplicates; duplicates in an append target are almost always a data quality bug.

2. **`>` is also correct for `upsert`** — the boundary row was already loaded. Skipping it on re-read is the correct behavior: do not re-process what is already reflected in the target. The upsert idempotency guarantee still holds for any new rows with the same key.

3. **Industry standard** — Matillion, ETLworks, Azure Data Factory, and most documented HWM ETL patterns use `WHERE col > last_hwm` (exclusive). dlt uses `>=` by default but only because it pairs it with content-hash deduplication, which pycopg does not implement.

4. **Single operator, no configuration** — exposing a `boundary='gt'/'gte'` option creates two modes with overlapping semantics, confusing test matrices, and documentation complexity. One operator, documented clearly, is better.

**Documented caveat for timestamp watermarks:**

If `incremental_column` is a timestamp with second-level granularity (e.g., `TIMESTAMP` without microseconds) and multiple rows can share the same timestamp, rows that share the same value as `max(col)` of the last batch will be missed in the next run with `>`. The correct approach is:

- Use a column with high granularity (microsecond `TIMESTAMPTZ`) or a monotonic integer (BIGSERIAL) as `incremental_column`.
- If the source column has low granularity, use `load_mode='upsert'` + `conflict_columns` — upsert idempotency covers the corner case.
- Document this explicitly in the `Pipeline.incremental_column` docstring.

**Summary:** `>` is the recommended and only supported boundary. Document the timestamp-granularity caveat. Recommend `upsert` when the watermark column may have tied values.

---

## Feature Dependencies

```
ETL-INC-01  Pipeline.incremental_column field
    └──enables──> ETL-INC-03  Filter generation (> last_watermark)
    └──requires──> validation: load_mode != 'replace' (raise ValueError)
    └──requires──> validate_identifiers(incremental_column)

ETL-INC-02  First-run full load
    └──requires──> ETL-INC-01 (incremental_column set)
    └──requires──> last_run() or equivalent watermark-read query
                       [EXISTING last_run() queries pipeline_runs]

ETL-INC-03  Exclusive filter (col > watermark)
    └──requires──> ETL-INC-02 (watermark-read logic)
    └──requires──> _build_incremental_sql (new pure builder)
    └──depends on──> validate_identifiers [EXISTING]

ETL-INC-04  Record new high-water mark
    └──requires──> ETL-INC-03 (batch extracted with filter)
    └──requires──> ETL_UPDATE_RUN extension to write watermark JSONB
                       [pipeline_runs.watermark column ALREADY EXISTS]
    └──requires──> max(df[incremental_column]) computation

ETL-INC-05  Empty-batch handling
    └──requires──> ETL-INC-04 (copy prior watermark, no regression)
    └──depends on──> existing empty-DataFrame early-return path [EXISTING]

ETL-INC-06  RunResult watermark fields
    └──requires──> ETL-INC-04 (watermark stored in pipeline_runs row)
    └──requires──> _row_to_result update to parse watermark JSONB
    └──requires──> RunResult new fields: watermark_used, watermark_recorded
                       [RunResult is frozen dataclass — add 2 fields]

ETL-INC-07  history() returns watermark fields
    └──falls out of──> ETL-INC-06 (_row_to_result updated)
    └──no query change needed──> ETL_LIST_RUNS already does SELECT *

ETL-INC-08  dry_run with incremental
    └──requires──> ETL-INC-02 (watermark-read logic, read-only)
    └──requires──> ETL-INC-03 (filter generation, applied to extract)
    └──depends on──> existing dry_run fork [EXISTING]

ETL-INC-09  Backfill / reset (documented pattern, no new code)
    └──depends on──> pipeline_runs.watermark column [EXISTING]
    └──depends on──> first-run-on-NULL-watermark behavior [ETL-INC-02]

ETL-INC-10  Async parity
    └──mirrors──> ETL-INC-01..09 in AsyncETLAccessor
    └──extends──> TestEtlParity [EXISTING harness]
```

### Dependency Notes

- **ETL-INC-06 (RunResult watermark fields) is a breaking extension.** Adding 2 fields to a frozen dataclass is non-breaking for existing callers that do not unpack `RunResult` positionally. Since `RunResult` is constructed only inside `etl.py` and never by users directly, this is safe. Document in CHANGELOG.
- **ETL-INC-04 requires updating `ETL_UPDATE_RUN`.** The existing query in `queries.py` does not write `watermark`. Two approaches: (a) add `watermark = %s` to the single UPDATE and pass NULL for non-incremental runs, or (b) add a separate UPDATE for watermark. Option (a) is simpler and keeps the single `_end_run` call shape; prefer it.
- **ETL-INC-03 (filter SQL builder) must be a pure builder** — consistent with the existing `_build_insert_sql`, `_build_upsert_sql` pattern. No I/O, no `self`, returns `(sql, params)` tuple, validates identifiers first.
- **`last_run()` is not sufficient to read the last watermark** — it returns the most recent run regardless of status. The watermark must be read from the most recent **successful** run (status='success' with non-null watermark). This requires either a new query constant or a filter on the existing `ETL_GET_LAST_RUN`.

---

## MVP Definition (v0.7.0 Incremental ETL Set)

### Must Ship

- [ ] ETL-INC-01 — `Pipeline.incremental_column` field with construction-time validation
- [ ] ETL-INC-02 — First-run full load (NULL watermark → no filter)
- [ ] ETL-INC-03 — `>` exclusive watermark filter for subsequent runs
- [ ] ETL-INC-04 — Record `max(col)` as new watermark on success
- [ ] ETL-INC-05 — Empty-batch handling: success + 0 rows + watermark preserved
- [ ] ETL-INC-06 — `RunResult.watermark_used` and `RunResult.watermark_recorded` fields
- [ ] ETL-INC-07 — `history()` returns watermark fields (falls out of ETL-INC-06)
- [ ] ETL-INC-08 — `dry_run=True` with incremental: compute filter + would-be max, write nothing
- [ ] ETL-INC-09 — Backfill / reset documented (no new code)
- [ ] ETL-INC-10 — Full sync/async parity for all above

### Explicitly Deferred (do not scope into v0.7.0)

- Configurable `>` vs `>=` boundary option — single operator is better than two
- Multi-column composite watermarks — complexity without clear use case
- CDC / WAL decoding — different architecture entirely
- Late-arriving data lookback window — user-level concern, handle in source SQL
- Scheduler / cron integration — out of scope for a library

---

## Impact on Existing `RunResult` / `history()` / `dry_run` Surface

This section documents the exact changes to each existing surface.

### `RunResult` (etl.py)

**Current fields (8):** `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, `error`

**New fields (2):** `watermark_used: Any | None`, `watermark_recorded: Any | None`

- Both default to `None` for non-incremental pipelines — no caller breakage for existing users
- `watermark_used`: the Python value extracted from the prior run's `watermark JSONB`, used as the `>` filter threshold
- `watermark_recorded`: the Python value of `max(incremental_column)` stored in this run's `watermark JSONB`
- `_row_to_result` must parse `pipeline_runs.watermark` (a JSONB dict) → extract `value` key → assign to both fields with appropriate semantics (used = prior watermark by definition, so `_row_to_result` cannot reconstruct `watermark_used` from the row alone; `watermark_used` must be passed into `_row_to_result` or carried separately)

**Design note:** `_row_to_result` takes a row from the DB which only knows what was recorded, not what was used as the filter. The runner must capture `watermark_used` before the run and pass it alongside the completed row. Two options: (a) add `watermark_used` as a parameter to `_row_to_result`, or (b) build `RunResult` inline in `run()` for the incremental path. Option (a) preserves the existing `_fetch_run_result → _row_to_result` pipeline for non-incremental runs.

### `history()` / `last_run()`

No signature change. `RunResult` objects returned by these methods will have `watermark_used` and `watermark_recorded` populated if the run was incremental (non-null `pipeline_runs.watermark`), else `None`. No query changes — `ETL_LIST_RUNS` already does `SELECT *`.

### `dry_run=True`

**Current behavior:** extract + transform only, no load, no `pipeline_runs` row, returns `RunResult(status='dry_run', rows_loaded=0, run_id=None)`.

**New behavior with `incremental_column`:**
- Read last watermark from `pipeline_runs` on a read-only autocommit connection (if table exists; if not, treat as first run)
- Apply the `>` filter in the extract
- Compute `max(incremental_column)` from the extracted DataFrame
- Return `RunResult(status='dry_run', rows_loaded=0, run_id=None, watermark_used=<last>, watermark_recorded=<would_be_max>)`
- Write nothing (consistent with existing contract)

### `ETL_UPDATE_RUN` (queries.py)

**Current:** 7-parameter UPDATE (status, finished_at, rows_extracted, rows_loaded, error_message, error_traceback, run_id) — no watermark write.

**New:** 8-parameter UPDATE adding `watermark = %s` as the 7th positional parameter (before `run_id`). Pass `None` for non-incremental runs — stores NULL, consistent with current state of all existing rows.

### New `ETL_GET_LAST_WATERMARK` query (queries.py)

```sql
SELECT watermark
FROM pipeline_runs
WHERE pipeline_name = %s
  AND status = 'success'
  AND watermark IS NOT NULL
ORDER BY finished_at DESC
LIMIT 1
```

This is distinct from `ETL_GET_LAST_RUN` (which returns the most recent run regardless of status or watermark). Incremental runs must read from the most recent **successful** run that has a watermark.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| ETL-INC-01 Pipeline.incremental_column | HIGH | LOW | P1 — entry point |
| ETL-INC-02 First-run full load | HIGH | LOW | P1 — correctness |
| ETL-INC-03 Exclusive `>` filter | HIGH | MEDIUM | P1 — core mechanism |
| ETL-INC-04 Record watermark | HIGH | LOW | P1 — state persistence |
| ETL-INC-05 Empty-batch handling | HIGH | LOW | P1 — correctness |
| ETL-INC-06 RunResult watermark fields | MEDIUM | LOW | P1 — observability |
| ETL-INC-07 history() watermark fields | MEDIUM | LOW | P1 — falls out of INC-06 |
| ETL-INC-08 dry_run incremental | MEDIUM | LOW | P1 — testing workflow |
| ETL-INC-09 Backfill docs | MEDIUM | NONE | P1 — essential escape hatch |
| ETL-INC-10 Async parity | HIGH | MEDIUM | P1 — core value |

All items are P1. There are no P2/P3 items — the incremental feature is only useful when all parts of the state loop are correct.

---

## Ecosystem Reference

| Design Decision | dlt | Fivetran / Matillion / ADF | This library |
|----------------|-----|---------------------------|--------------|
| Watermark field | `@dlt.resource(incremental=dlt.sources.incremental("col"))` | Cursor field config per connector | `Pipeline.incremental_column` declarative field |
| Default boundary | `>=` (inclusive) — pairs with content-hash dedup | `>` (exclusive) — standard HWM | `>` (exclusive) — simpler, no hash state |
| State storage | Pipeline state file or DB table | Connector-managed | `pipeline_runs.watermark JSONB` (already exists) |
| First run | Full load | Full sync | Full load (NULL watermark → no filter) |
| Empty batch | Success, state unchanged | Success | Success, watermark copied from prior run |
| Reset / backfill | `--full-refresh` flag | Manual resync button | Delete `pipeline_runs` rows, next run is full load |
| Dry run | Not a primary concept | Not applicable | `dry_run=True` reads watermark + applies filter + returns would-be max |

---

## Sources

- [dlt Cursor-based incremental loading](https://dlthub.com/docs/general-usage/incremental/cursor)
- [dlt Incremental loading overview](https://dlthub.com/docs/general-usage/incremental-loading)
- [Matillion ETL: Incremental / High Water Mark loading](https://docs.matillion.com/metl/docs/2506598/)
- [ETLworks: Change Replication using HWM](https://support.etlworks.com/hc/en-us/articles/360014718933-Change-Replication-using-High-Watermark-HWM)
- [Fivetran: Building efficient data pipelines with incremental updates](https://www.fivetran.com/blog/building-efficient-data-pipelines-with-incremental-updates)
- [Microsoft FastTrack: Robust data ingestion with high-watermarking](https://techcommunity.microsoft.com/t5/fasttrack-for-azure/robust-data-ingestion-with-high-watermarking/ba-p/3707480)
- pycopg codebase: `pycopg/etl.py`, `pycopg/queries.py`
- pycopg project context: `.planning/PROJECT.md`

---

*Feature landscape for: pycopg v0.7.0 Incremental ETL*
*Researched: 2026-06-19*
*Confidence: HIGH on table-stakes scope (clear codebase anchor + consistent ecosystem evidence); HIGH on boundary decision (> vs >= — multiple independent sources converge on > as standard HWM pattern; dlt's >= is explicitly paired with deduplication that pycopg does not implement)*
