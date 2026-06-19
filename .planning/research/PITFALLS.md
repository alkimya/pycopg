# Pitfalls Research

**Domain:** Watermark-based incremental ETL added to pycopg v0.7.0 (`Pipeline.incremental_column`, `pipeline_runs.watermark JSONB`, append/upsert only)
**Researched:** 2026-06-19
**Confidence:** HIGH (pitfalls derived from direct code reading of `etl.py` and `queries.py`, cross-checked against the locked scope in PROJECT.md)

---

## Critical Pitfalls

### Pitfall 1: Inclusive vs. Exclusive Boundary — The `>` vs `>=` Trade-Off

**What goes wrong:**

Two symmetrical failure modes sit on opposite sides of the same boundary operator.

Using `>=` re-loads the watermark row on every subsequent run. If the previous run's high-water mark was `2024-01-01 12:00:00`, the next run's filter `WHERE updated_at >= '2024-01-01 12:00:00'` re-extracts every row that matches that exact timestamp. With `load_mode="append"` this produces duplicates immediately. With `load_mode="upsert"` no duplicate rows are written, but the boundary row is re-processed in every run — an unnecessary at-least-once re-send that can cause side effects in transforms.

Using `>` skips the re-processing but silently drops any source rows that committed at exactly the watermark timestamp. In a table with second-granularity `updated_at` and any kind of concurrent writes, multiple rows share the same max timestamp. The batch captured on run N has max `updated_at = T`. On run N+1, the filter `WHERE updated_at > T` silently discards all rows that were written at exactly time T but missed the run-N snapshot (late arrivals, concurrent commits not yet visible at extract time).

**Why it happens:**

The temptation is to implement `>` because it "avoids re-processing". It does, at the cost of losing boundary-timestamp rows that commit between the run's extract and its watermark advancement. The loss is silent: no error, no missing-row log, just a gap in the target table.

**How to avoid:**

Use `>` as the default and require `load_mode="upsert"` for any table with non-unique timestamps (at-least-once semantics: the boundary row is never skipped; if it is re-sent it is idempotent via ON CONFLICT). Document the trade-off explicitly:

- `>` + `upsert`: at-least-once with idempotent re-processing. Correct and safe. Requires `conflict_columns`.
- `>` + `append`: at-most-once. Correct only when the watermark column is strictly monotonic and unique across all rows (auto-increment ID). Unsafe for timestamp columns.
- `>=` + `upsert`: also at-least-once safe but unnecessarily re-processes the boundary row on every run.
- `>=` + `append`: always-duplicates. Reject at construction time (enforce: `incremental_column` + `load_mode="append"` raises `ValueError` unless the user explicitly opts into `append_incremental_unsafe=True`).

Concretely: in `Pipeline.__post_init__`, add: if `incremental_column` is set and `load_mode == "append"`, raise `ValueError("incremental_column with load_mode='append' risks duplicates; use load_mode='upsert' or confirm idempotency via conflict_columns")`.

The filter injected into the SQL source wrap must use `col > %s` (strict greater-than) and the docstring must explain the at-least-once contract for upsert.

**Warning signs:**

- Filter uses `>=` and `load_mode="append"` — re-processing every run doubles the target rows.
- Filter uses `>` and `load_mode="append"` — silent data loss on any table with non-unique timestamps.
- Tests do not include a scenario where two source rows share the same max timestamp; only one runs per test.

**Phase to address:**

Phase 25 (Pipeline incremental design and `__post_init__` validation). The `>` vs `>=` decision must be locked in the constructor validation and documented in the API docstring before any runner code is written. Add a test: two source rows at the same timestamp; verify both are captured by the next incremental run.

---

### Pitfall 2: Low-Resolution or Non-Monotonic Watermark Column

**What goes wrong:**

The watermark is only as good as the column it tracks. Three common failure modes:

1. **Second-granularity timestamps (`TIMESTAMP` without fractional seconds):** A batch completes at `12:00:00.500`. PostgreSQL stores the max as `12:00:00` (second boundary). New rows written at `12:00:00.800` (still the same second) are stored as `12:00:00`. Next run filter: `WHERE col > '12:00:00'` — those rows are included. Appears correct. But if the column is truly `TIMESTAMP(0)`, new rows at `12:00:00` are stored as `12:00:00`, and the filter `col > '12:00:00'` skips them silently.

2. **Application-layer `updated_at` set by the client:** If the application inserts rows with `updated_at = datetime.now()` on the writer's clock and the writer machine has clock skew (even 1–2 seconds of NTP drift), a row written at wall-clock `T+1s` may arrive in PostgreSQL with `updated_at = T-0.5s`. The watermark from the previous run was `T`. Next run filter: `WHERE col > T` — the late-clock row at `T-0.5s` is silently skipped forever.

3. **`updated_at` updated by application logic, not DB trigger:** Bulk update statements (`UPDATE table SET updated_at = now() WHERE ...`) are correct. But application code that forgets to set `updated_at` on an UPDATE leaves stale timestamps. The watermark never advances past those rows because the filter doesn't see them as new.

**Why it happens:**

Developers pick `updated_at` because it semantically means "last changed" without auditing whether the column is set reliably by a DB-level trigger or by fallible application code. Clock skew is invisible in development (same machine) and surfaces only in distributed production environments.

**How to avoid:**

Document clearly: `incremental_column` must be a column that is:
- Set by a database-level `DEFAULT now()` or `BEFORE UPDATE` trigger (not application code).
- Of type `TIMESTAMPTZ` with microsecond precision (not `TIMESTAMP(0)`).
- Monotonically non-decreasing under inserts (can share values; must not go backwards).

For integer/sequence watermarks (auto-increment `id`), the above constraints reduce to: must be strictly increasing per INSERT. Sequence columns are ideal watermark candidates.

In the `Pipeline` docstring for `incremental_column`, list these constraints explicitly. pycopg cannot validate them at construction time (no schema introspection at pipeline-define time), but the docstring is the contract.

**Warning signs:**

- Watermark column is `TIMESTAMP` (no timezone, no fractional seconds).
- `updated_at` is set by application code without a DB trigger fallback.
- Test environment is single-machine (clock skew not observable); clock-skew scenarios not in the test suite.
- Two consecutive incremental runs on a static dataset extract 0 rows but the target is known to be incomplete.

**Phase to address:**

Phase 25 (API design + docstring). The column contract belongs in `Pipeline.incremental_column` docstring. Add a test with an integer sequence watermark and a test with a `TIMESTAMPTZ` microsecond watermark; include a negative test where a source row has a timestamp 1 second before the current watermark and assert it is NOT re-extracted (proves the boundary semantics are as documented).

---

### Pitfall 3: Advancing the Watermark on a Failed or Partially-Applied Load

**What goes wrong:**

The watermark is written to `pipeline_runs.watermark` as part of `_end_run`. If the watermark is written before confirming the load transaction committed — or if `_end_run` is called with `"success"` when the load raised an exception that was caught and swallowed — the next run starts from a watermark that skips rows whose load never completed. Those rows are silently dropped from the target forever.

Looking at the current `_end_run` implementation: it runs on a dedicated autocommit connection, independent of the load transaction. This is correct for failure visibility (the failed run row commits even when the load rolls back) but requires care for the success path: the watermark must only be written AFTER the load transaction's `COMMIT` is confirmed. If the load transaction is inside `with self._db.session(): with self._db.transaction() as conn:` and the watermark is written in the `except` block by mistake, or if the code writes the watermark in `_end_run` before the `with` block exits, the watermark advances even when the load rolled back.

Current code structure in `etl.py` (lines 994–1005):
```
try:
    ... load transaction ...
except Exception as exc:
    self._end_run(run_id, "failed", ...)  # <-- correct: failed path
    raise

self._end_run(run_id, "success", ...)  # <-- correct: only reached on success
return self._fetch_run_result(run_id)
```

The pattern is correct for the non-incremental path. For the incremental path, the `max(col)` watermark value must be computed and passed to `_end_run` only on the success path, never on the failure path. The `except` block must pass `watermark=None` (or not update the watermark column at all).

**Why it happens:**

The `_end_run` function currently does not write the watermark column — `ETL_UPDATE_RUN` in `queries.py` (lines 270–279) does not include a `watermark = %s` SET clause. When watermark support is added, the temptation is to add `watermark = %s` to `ETL_UPDATE_RUN` and pass the computed watermark in every `_end_run` call. If the `except` path then passes the computed watermark (which was set before the exception), the watermark advances on failure.

**How to avoid:**

Two design choices, either is safe:

Option A (recommended): Add `watermark` as a keyword argument to `_end_run(... watermark=None)`. On the success path, pass `watermark=json.dumps({"col": col_name, "value": serialized_value})`. On the failure path, always pass `watermark=None` (do not update the watermark column). The `ETL_UPDATE_RUN` query only sets `watermark` when the argument is non-None, or use a separate `ETL_UPDATE_RUN_WITH_WATERMARK` constant that includes `watermark = %s`.

Option B: Keep `ETL_UPDATE_RUN` unchanged (no watermark column); add a separate `ETL_SET_WATERMARK` query run only on the success path after `_end_run`. This makes the watermark write visibly separate from the status update.

Either way: the test must verify that after a deliberately-failed load, the `pipeline_runs.watermark` for that run row is NULL, and the next successful run re-extracts the full delta from the previous successful watermark.

**Warning signs:**

- `_end_run` receives the computed watermark value in the `except` block as well as the success block.
- `ETL_UPDATE_RUN` sets `watermark = %s` unconditionally and the caller passes the watermark from a pre-exception code path.
- No test asserts that a failed incremental run does not advance the watermark.

**Phase to address:**

Phase 25 or 26 (whichever phase implements the runner + watermark write). This must be verified with a test: deliberately fail the load of an incremental pipeline; assert `pipeline_runs.watermark IS NULL` for the failed run row; assert the next successful run re-extracts rows from the pre-failure watermark.

---

### Pitfall 4: Snapshot Hazard — Computing max(col) From the Extracted Batch While Concurrent Writes Occur

**What goes wrong:**

The incremental ETL sequence is:
1. Read `last_watermark` from `pipeline_runs`.
2. Extract: `SELECT * FROM source WHERE col > last_watermark`.
3. Transform.
4. Load.
5. Compute new watermark: `max(col)` from the extracted DataFrame.
6. Write new watermark to `pipeline_runs`.

Between steps 2 and 6, concurrent transactions in the source table may INSERT new rows with `col` values between `last_watermark` and `new_watermark`. Those rows are NOT in the extracted DataFrame (they committed after the snapshot of step 2) but they ARE older than the new watermark. The next run filter `WHERE col > new_watermark` skips them silently — they are lost.

This is the fundamental "read committed snapshot hazard" in incremental ETL. It is unavoidable without a read-committed snapshot isolation or a CDC mechanism. The risk is proportional to:
- Write throughput on the source table during the ETL window.
- Duration of the extract step (longer = more concurrent commits sneak in).

For pycopg's same-DB scope, the source and target are in the same PostgreSQL instance, and the extract uses psycopg 3 with `READ COMMITTED` (default). In READ COMMITTED, each statement sees a snapshot of rows committed before that statement began — not a consistent snapshot for the entire transaction. So concurrent commits during the extract are invisible to step 2 but have `col` values inside the `[last_watermark, new_watermark]` range.

**Why it happens:**

Developers compute `new_watermark = df[incremental_column].max()` from the batch DataFrame and assume it is safe to use as the next filter boundary. This is correct only if the source table has no concurrent writes during the extract window — which is true in practice for batch-overnight ETL but false for any near-real-time pipeline.

**How to avoid:**

Two mitigations (implement the first, document the second):

1. **Compute the watermark from the DB, not the batch:** Instead of `df[col].max()`, run `SELECT max(col) FROM source WHERE col > last_watermark` as a separate query using a snapshot taken at the start of the run. Use `BEGIN ISOLATION LEVEL REPEATABLE READ` for the extract query so the snapshot is consistent. Then advance only to the max that was visible at the start of the run, not the running max at the time of step 5.

   For v0.7.0's scope (no streaming, full-batch extract into DataFrame), this reduces to: capture `new_watermark = db.fetch_val("SELECT max({col}) FROM ...")` at the same time as (or before) the extract, using the same transaction snapshot. This requires the extract and the watermark-max query to share a transaction (not use `autocommit`).

2. **Document the gap and recommend a safe-lag offset:** For append-only sources, document: "To avoid losing concurrent inserts at the boundary, set `watermark_lag_seconds=N` to advance the watermark to `max(col) - N seconds`. This causes each run to re-extract the last N seconds of data, which upsert mode handles idempotently."

   For v0.7.0 MVP with upsert mode: the combination of `>` filter and idempotent upsert means boundary-row re-processing is safe. The snapshot hazard only causes data loss if a concurrent row's `col` value falls exactly in the gap between `last_watermark` and `max(extracted_batch_col)`. With upsert, those rows are loaded on the next run if they share the new watermark value (picked up by the `>=` window). Document this residual risk.

**Warning signs:**

- `new_watermark` is computed from `df[incremental_column].max()` with no consideration of concurrent transactions.
- The extract uses a regular `to_dataframe` call (autocommit connection, READ COMMITTED) with no snapshot isolation.
- No test simulates a concurrent insert between extract and watermark-advance.

**Phase to address:**

Phase 26 (runner implementation, watermark compute logic). Document the isolation level used and the residual gap. The MVP v0.7.0 may accept the gap with documentation; a future milestone can add snapshot isolation or `watermark_lag`.

---

### Pitfall 5: NULLs in the Watermark Column

**What goes wrong:**

`df[incremental_column].max()` in pandas returns `NaN` (for numeric columns) or `NaT` (for datetime columns) when the column contains only NULL values. The NaN/NaT → None coercion (`df.astype(object).where(pd.notnull(df), None)`) is already applied to the loaded rows, but the watermark computation happens after this coercion on a potentially all-None column. `None` as a JSONB watermark means the next run reads `watermark IS NULL` and falls back to a full load — which is safe but may be unexpected.

A more dangerous failure: if the source table has NULLs mixed with valid timestamps in `incremental_column`, the `max()` in pandas silently ignores NULLs and returns the non-NULL max. This is correct Python/pandas behavior but means NULL-valued rows are never included in the `col > last_watermark` filter (PostgreSQL `NULL > T` is `NULL`, which evaluates as `false` in a `WHERE` clause). Those rows are silently excluded from every incremental run.

**Why it happens:**

The watermark column is chosen by the user without verification that it is `NOT NULL`. NULL semantics in SQL WHERE clauses (`NULL > value` = `NULL`, not `TRUE`) mean NULL rows are invisible to the filter. Pandas `max()` silently drops NULLs when computing the watermark, so the code appears correct but the NULL rows are never loaded.

**How to avoid:**

1. At construction time, do not attempt to validate the column's nullability (schema introspection at define-time is overengineering for v0.7.0).
2. At run time, after computing `watermark_value = df[incremental_column].max()`, check: `if pd.isna(watermark_value): raise ETLIncrementalError("incremental_column '{col}' produced a NULL watermark — column may be all-NULL or not present in the extracted batch")`.
3. In the docstring: "The `incremental_column` must be `NOT NULL` in the source table. Rows with `NULL` in this column are excluded by the `WHERE col > %s` filter and will never be loaded incrementally."
4. For the SQL source wrap, `SELECT * FROM (<sql>) sub WHERE col > %s` correctly excludes NULL-col rows (SQL NULL comparison returns NULL, not TRUE). This is the documented behavior, not a bug — but must be called out.

**Warning signs:**

- `incremental_column` points to a nullable column with no NOT NULL constraint in the source table.
- The extracted DataFrame has `df[incremental_column].isna().any()` but no error is raised.
- The watermark value stored in `pipeline_runs.watermark` is `null` (JSON null) after a run that extracted rows — indicates the watermark column was all-NULL in the batch.

**Phase to address:**

Phase 26 (runner implementation). Add NULL watermark detection after `max()` computation. Add test: source table with one row having `NULL` in `incremental_column`; assert the runner raises or warns; assert the NULL row is not silently loaded and then lost.

---

### Pitfall 6: JSONB Serialization Round-Trip Type Drift

**What goes wrong:**

The watermark is stored as `pipeline_runs.watermark JSONB` (per the existing DDL in `queries.py`). The round-trip `Python value → JSON string → JSONB → Python value` introduces type drift for several types:

1. **`datetime` → JSON string → text comparison on next run:** If the watermark is a `datetime` object serialized to JSON as `"2024-01-01T12:00:00+00:00"`, it is read back as a string. The incremental filter then compares `col > '2024-01-01T12:00:00+00:00'` where `col` is a `TIMESTAMPTZ`. PostgreSQL will cast the string literal to `TIMESTAMPTZ` for comparison (implicit cast), which works — but the round-trip must preserve the timezone designator. A naive `datetime.isoformat()` without `+00:00` or `Z` produces a timezone-naive string that PostgreSQL interprets in the session timezone, not UTC, causing offset-by-N-hours skips.

2. **`Decimal` → float precision loss:** A numeric watermark column with type `NUMERIC(18,6)` returns a `Decimal` from psycopg 3. `json.dumps(Decimal("123456789012.123456"))` raises `TypeError`. A naïve `float(watermark_value)` loses precision. `str(watermark_value)` is safe for JSON storage but must be deserialized as `Decimal`, not `float`, on read.

3. **Large integer (`BIGINT`) → float:** JSON numbers have no integer/float distinction. `json.dumps({"value": 9007199254740993})` → `9007199254740993` (correct). `json.loads(...)["value"]` → `9007199254740993` (Python int, correct). But some JSON libraries round large integers to float; verify `json.loads` returns `int` for integers within Python's arbitrary precision range.

4. **psycopg 3 returns the `watermark` column as a Python `dict`** (JSONB → dict via the built-in adapter). Reading `row["watermark"]` gives `{"col": "updated_at", "value": "2024-01-01T12:00:00+00:00"}` — the value is a string, not a `datetime`. The filter param `%s` sent to psycopg 3 with a string value for a `TIMESTAMPTZ` column works via implicit PostgreSQL cast, but must be tested explicitly.

**Why it happens:**

JSON is the natural "schema-free" storage for a dynamic watermark value, but it erases Python/PostgreSQL type information. The developer serializes a `datetime` with `isoformat()` without confirming the round-trip produces the exact same value (timezone offset intact, microseconds intact) and that PostgreSQL accepts the string for comparison with the source column type.

**How to avoid:**

Define a strict serialization contract for the watermark JSONB:
- `datetime`/`date`: serialize with `isoformat()` only after ensuring `tzinfo=UTC` (enforce `datetime.now(UTC)`, not naive `datetime.now()`). Deserialize via `datetime.fromisoformat()`.
- `int` / `BIGINT`: serialize as JSON integer (no quotes). Deserialize as Python `int`. Test with values > 2^53.
- `Decimal` / `NUMERIC`: serialize as quoted string (`str(value)`). Deserialize as `Decimal`. Never via `float`.
- `date`: serialize as `"YYYY-MM-DD"` string; deserialize via `datetime.date.fromisoformat()`.

Store in JSONB as `{"col": "<column_name>", "value": <serialized>, "type": "datetime"|"int"|"decimal"|"date"}` so the reader knows which deserializer to apply.

The `type` discriminator field removes guessing and allows forward-compatible extensions.

Write a round-trip test for each supported type: `serialize(v) → store as JSONB → read back → deserialize → assert == v` with no precision loss and correct timezone.

**Warning signs:**

- Watermark is serialized via `json.dumps({"value": watermark_value})` without handling `datetime` types (raises `TypeError`).
- Round-trip test not present in the test suite.
- Timezone-naive `datetime` values are used as watermarks on `TIMESTAMPTZ` columns.
- Large integer watermarks are deserialized as `float` and compared with `==` to the original (fails above 2^53).

**Phase to address:**

Phase 25 or 26 (whichever defines the watermark serialization utilities). Write the round-trip test before wiring the runner. The serialization helpers must be pure functions (no DB), unit-testable without a real PostgreSQL instance.

---

### Pitfall 7: Transform Chain Drops the Watermark Column Before max() Is Computed

**What goes wrong:**

The watermark is computed from the post-transform DataFrame: `new_watermark = df[incremental_column].max()`. If any transform step drops the `incremental_column` (e.g., `df.drop(columns=["updated_at"])` or a `df[["col1", "col2"]]` column selection that omits it), the `df[incremental_column]` lookup raises `KeyError`. This is a runtime error, not a construction-time error — it surfaces only on the first incremental run.

Worse: if the transform renames the column (`df.rename(columns={"updated_at": "ts"})`), the `max()` on the original name raises `KeyError`. The new name is `ts` but the pipeline still references `incremental_column="updated_at"`.

Even more subtle: a transform that **modifies** the watermark column's values (`df["updated_at"] = df["updated_at"].dt.tz_convert("US/Eastern")`) computes the watermark in the wrong timezone. The loaded column has US/Eastern timestamps but the watermark is in UTC. Next run: `WHERE updated_at > <UTC watermark>` — the filter is against the original source column (still UTC), so this is actually correct for filtering. But the stored watermark is in US/Eastern, so the comparison `UTC_column > Eastern_watermark` works only because PostgreSQL normalizes TIMESTAMPTZ. Not a bug per se, but timezone confusion is a latent maintenance trap.

**Why it happens:**

The transform chain was designed (in v0.5.0) to be a black box that receives a DataFrame and returns a DataFrame. The pipeline runner trusts that the returned DataFrame has all the columns needed for the load. No contract was established about which columns must survive the transform. Adding `incremental_column` introduces a new contract: the column must survive the transform chain with its original name and type intact.

**How to avoid:**

**Compute `max(col)` BEFORE the transform chain, from the raw extracted DataFrame.** This is the correct approach:

```python
# After extract, before transform:
if pipeline.incremental_column:
    col = pipeline.incremental_column
    if col not in df.columns:
        raise ETLIncrementalError(f"incremental_column '{col}' not found in extracted data")
    new_watermark_raw = df[col].max()

# After transform chain:
# Use new_watermark_raw (not df[col].max() post-transform)
```

The watermark represents the high-water mark of the **source** data, not the transformed data. Computing it from the raw extract is semantically correct and immune to transform side effects.

**Alternatively** (less preferred): validate at construction time that `incremental_column` will survive transforms — but this is impossible without running the transforms, which requires data.

The better guard is the extraction-time check: before running any transform, assert `incremental_column in df.columns`. This gives a clear error at the right moment instead of a cryptic `KeyError` deep in the runner.

**Warning signs:**

- `df[incremental_column].max()` appears after the transform loop in the runner code.
- No check that `incremental_column in df.columns` appears before the transform chain.
- A transform in the test suite drops a column but the test does not assert the incremental column is preserved.

**Phase to address:**

Phase 25 or 26 (runner design, this is the highest-priority structural decision for incremental ETL). The watermark computation point must be locked in the design doc before implementation. Write a test: a transform that drops the watermark column; assert the runner raises `ETLIncrementalError` (not `KeyError`), and the message names the missing column and the transform step.

---

### Pitfall 8: First-Run Full Load on a Huge Table With No Bound

**What goes wrong:**

When `pipeline_runs.watermark IS NULL` (no previous successful run), the incremental pipeline falls back to a full load: `SELECT * FROM source` with no WHERE clause. If the source table has 100M rows, this materializes the entire table into a DataFrame (`to_dataframe()`) before the first incremental watermark is established. The process OOMs or the load takes hours.

Unlike the non-incremental case (where the user can set `extract_limit`), the incremental full-load-first-run is triggered automatically and invisibly on the very first call to `run()`. The user has no immediate indication that "first run = full load" until the process hangs.

**Why it happens:**

The design decision ("first run = full load then record max(col)") is correct for correctness (no data missed) but hazardous for large tables. The hazard is that the user declares an incremental pipeline expecting fast incremental loads, not knowing the first run is slow.

**How to avoid:**

1. Add `first_run_limit: int | None = None` to `Pipeline`. When set and `watermark IS NULL`, the full load uses `LIMIT first_run_limit`. Document: "Use `first_run_limit` to bound the first full load on large tables; subsequent runs are incremental."

2. In the API docstring for `incremental_column`, add a prominent note: "**First run:** When no prior watermark exists, the full source table is extracted. For large tables, set `extract_limit` or `first_run_limit` to bound the initial load."

3. Alternatively: require the user to pass `initial_watermark` to the `Pipeline` — a value below which all data is considered already loaded. This avoids the full-load-first-run entirely. Document: "If the target already has data from a manual seed, set `initial_watermark` to the max value in the target to skip re-loading existing data."

For v0.7.0 scope: implement the `initial_watermark` parameter on `Pipeline` (serialized to JSONB on construction or checked at run time if no watermark row exists) as the clean solution. The first incremental run then starts from `initial_watermark` instead of NULL, allowing the user to pre-seed the watermark without a full load.

**Warning signs:**

- No `initial_watermark` or `first_run_limit` parameter on `Pipeline`.
- The first incremental run on any source table > 10k rows generates a full-table `to_dataframe()` call.
- Docs do not mention the first-run full-load behavior.

**Phase to address:**

Phase 25 (Pipeline design). `initial_watermark` parameter should be on the `Pipeline` dataclass from the start, not retrofitted. Add a test: a Pipeline with `initial_watermark=100` on a table with rows 1–200; assert the first run extracts only rows 101–200.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Compute watermark from post-transform DataFrame | Simpler code, one DataFrame reference | Transform drops watermark column → KeyError; wrong timezone if transform mutates timestamps | Never; compute from pre-transform raw extract |
| Use `>=` for the incremental filter | "Safer", never skips | Re-processes boundary row every run; with append mode produces duplicates on every run | Never for append; only if explicitly documented for upsert |
| Serialize watermark as bare `json.dumps(value)` without type tag | Fewer lines | datetime loses timezone; Decimal raises TypeError; large int becomes float | Never; use typed serialization with discriminator |
| Write watermark in `_end_run` on both success and failure paths | DRY, single `_end_run` call | Failed load advances watermark; next run skips rows silently | Never |
| Allow `incremental_column` with `load_mode="replace"` | Fewer validation rules | `replace` TRUNCATE wipes target before incremental load; on failure, target is empty AND watermark may be stale | Never; forbidden at construction time per locked scope |
| Skip `initial_watermark` / `first_run_limit` | Smaller API surface | First run silently full-loads a huge table; OOM with no warning | Acceptable only for tables known to be small; unacceptable as a general default |
| Skip NULL watermark check after `df[col].max()` | Simpler runner | `NaT`/`NaN` written to JSONB as JSON null; next run re-does full load silently | Never; raise `ETLIncrementalError` on NULL watermark |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| psycopg 3 JSONB adapter | Reading `row["watermark"]` and assuming it returns a typed Python value | psycopg 3 deserializes JSONB to `dict`/`list`/`str`/`int`/`float`/`None`; datetime strings are returned as `str`, not `datetime`; apply type-discriminator deserialization on read |
| psycopg 3 `%s` with datetime string from JSONB | Sending the raw string `"2024-01-01T12:00:00+00:00"` as a `%s` param to compare with `TIMESTAMPTZ` | PostgreSQL casts the ISO-8601 string implicitly; works but must be tested; naive strings (no `+00:00`) are interpreted in session timezone — always include timezone offset |
| pandas `df[col].max()` on datetime column | Returns `pd.Timestamp` (timezone-aware or naive depending on column dtype) | Must convert to Python `datetime` with explicit UTC tzinfo before serializing: `ts.to_pydatetime().astimezone(UTC)` |
| `ETL_UPDATE_RUN` query | Adding `watermark = %s` to the existing UPDATE without a separate success-only code path | The UPDATE currently runs on both success and failure paths; adding watermark here writes it on failure too; use a separate query constant or add a `watermark` optional kwarg with None-check |
| SQL subquery wrap for incremental filter | `SELECT * FROM (<sql>) sub WHERE col > %s` — subquery alias `sub` conflicts with source SQL using the same alias | Use a unique internal alias like `_pycopg_etl_src` that is unlikely to conflict with user SQL |
| `to_dataframe` with bound `%s` watermark parameter | `to_dataframe` uses named params (`:lim`) in the extract path; incremental `%s` for the watermark must match psycopg 3's positional param syntax | Verify whether `to_dataframe` accepts positional `%s` or requires named params `:param`; the current extract-limit path uses `:lim` (named); the watermark param must use the same convention consistently |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-batch extract into DataFrame on first incremental run | OOM or multi-minute stall on first run of any large table | Add `initial_watermark` parameter to skip full load; document the first-run behavior prominently | Any source table > available RAM / 2 |
| No index on `incremental_column` in source table | Each incremental run does a sequential scan of the full source table | Document that `incremental_column` must be indexed; the subquery-wrap `WHERE col > %s` cannot use an index if none exists | >100k rows |
| `pipeline_runs` table unbounded growth with high-frequency runs | `history()` / `last_run()` queries slow; `pipeline_runs` becomes large | Add `retention_days` cleanup utility or document manual pruning; the `SELECT * ... LIMIT %s` in `ETL_LIST_RUNS` limits reads but not table size | >1M run rows (~years of hourly runs) |
| Reading last watermark from `pipeline_runs` scans all rows for the pipeline | `last_run()` uses `ORDER BY started_at DESC LIMIT 1` — requires a sort | Ensure `pipeline_runs(pipeline_name, started_at)` has a composite index; or add `status='success'` filter to read only successful watermarks | >10k runs per pipeline |
| Incremental filter on a non-indexed column causes full subquery scan | Incremental run slower than full load | Same as index trap above; the subquery `SELECT * FROM (source) sub WHERE col > %s` evaluates the full source then filters — no pushdown through a user-written subquery | >50k rows in source |

---

## "Looks Done But Isn't" Checklist

- [ ] **Boundary semantics locked:** `>` (strict) used for the filter; documented as at-least-once when combined with upsert. Construction-time `ValueError` raised when `incremental_column` + `load_mode="append"` are combined without explicit opt-in.
- [ ] **Watermark computed pre-transform:** `df[incremental_column].max()` called on the raw extracted DataFrame, before the transform chain. Column presence check `incremental_column in df.columns` asserted before transforms run.
- [ ] **Watermark advanced only on success:** `_end_run` with `watermark=` value is called only on the success path. The `except` block calls `_end_run` with `watermark=None`. Test: fail a load; assert `pipeline_runs.watermark IS NULL` for that run.
- [ ] **Watermark round-trip type-safe:** Serialization handles `datetime` (timezone-aware), `int`, `Decimal`, and `date`. Round-trip test for each type. Large integers (> 2^53) tested.
- [ ] **NULL watermark detected:** After `max()`, check `pd.isna(new_watermark_raw)` and raise `ETLIncrementalError`. Test: all-NULL watermark column raises, not silently stores JSON null.
- [ ] **First-run bound available:** `initial_watermark` or `first_run_limit` parameter on `Pipeline`. Documented in API docstring. Test: first incremental run with `initial_watermark=N` extracts only rows > N.
- [ ] **`incremental_column` + `replace` rejected:** `Pipeline.__post_init__` raises `ValueError` for this combination. Test at construction time.
- [ ] **SQL subquery alias unique:** The internal alias in the subquery wrap is `_pycopg_etl_src` (or similar), not `sub` or `t`, to avoid alias conflicts in complex user SQL.
- [ ] **Async parity:** `AsyncETLAccessor.run()` has identical incremental logic to `ETLAccessor.run()`. `TestEtlParity` covers the incremental path.
- [ ] **`ETL_UPDATE_RUN` or watermark write clearly success-only:** The queries.py constant or its usage explicitly documents that `watermark` is written only on success.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Watermark advanced on failed load | HIGH | Manually `UPDATE pipeline_runs SET watermark = '<previous_good_watermark>' WHERE pipeline_name = '...' AND run_id = <failed_run_id>`; or insert a synthetic success row with the prior watermark; re-run to re-extract the skipped delta |
| Snapshot hazard — rows lost at boundary | MEDIUM | Identify the gap period (between last successful watermark and `now() - safety_lag`); manually backfill: `INSERT INTO target SELECT * FROM source WHERE col BETWEEN last_watermark AND new_watermark` with conflict handling; re-run incremental from corrected watermark |
| Transform drops watermark column | LOW | No data loss (run fails before load); fix the transform to preserve `incremental_column`; re-run |
| JSONB type drift (datetime stored as naive string) | MEDIUM | Correct the serialization code; patch existing watermark rows: `UPDATE pipeline_runs SET watermark = jsonb_set(watermark, '{value}', to_json(watermark->>'value' || '+00:00')::jsonb) WHERE ...`; re-run to verify |
| First-run OOM on huge table | LOW | No data loss (extract failed before load); add `initial_watermark` or `first_run_limit`; re-run |
| NULL watermark column rows silently skipped | LOW-MEDIUM | Identify NULL-watermark rows in source; load them manually or via a `load_mode="append"` pipeline with explicit SQL filter; document the NOT NULL constraint for `incremental_column` |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Inclusive/exclusive boundary (`>` vs `>=`) | Phase 25 — Pipeline design + `__post_init__` | Test: two rows at same max timestamp; assert both captured on next run |
| Low-resolution / non-monotonic watermark column | Phase 25 — API docstring contract | Test: second-granularity timestamp and integer sequence watermarks |
| Watermark advanced on failed load | Phase 26 — Runner implementation | Test: fail load; assert `watermark IS NULL` on failed run; next run re-extracts |
| Snapshot hazard (concurrent inserts at boundary) | Phase 26 — Runner implementation + docs | Document isolation level and residual risk; optional `watermark_lag` for future |
| NULLs in watermark column | Phase 26 — Runner implementation | Test: all-NULL watermark column raises `ETLIncrementalError` |
| JSONB serialization type drift | Phase 25 or 26 — Watermark serialization utilities | Round-trip test for datetime/int/Decimal/date |
| Transform drops watermark column | Phase 25 or 26 — Runner design (compute pre-transform) | Test: transform drops column; assert `ETLIncrementalError` with column name |
| First-run full load on huge table | Phase 25 — Pipeline design (`initial_watermark` param) | Test: `initial_watermark=N` skips rows <= N on first run |

---

## Note on Alias Removal (ALIAS-RM-01)

The one pitfall worth flagging for the alias removal sub-feature: **silently breaking callers who still use the flat API.** The 56 deprecated aliases (`db.create_hypertable(...)`, `db.vacuum(...)`, etc.) have been emitting `DeprecationWarning` since v0.6.0. Hard-removing them in v0.7.0 is a breaking change. Users who pinned `pycopg>=0.6.0` without an upper bound will hit `AttributeError` on upgrade with no clear error message beyond the attribute name.

Prevention: CHANGELOG `[0.7.0]` must have a `**Breaking**` section listing all 56 removed names with their accessor replacements (1:1 table, same as the MIGRATION v0.5→v0.6 guide). The MIGRATION v0.6→v0.7 guide must be prepended to MIGRATION.md. The `AttributeError` raised by Python when the stub is gone has no context — the MIGRATION guide is the only user-facing recovery path.

No deep pitfall research is needed for this sub-feature; it is mechanical (delete a block, update tests, update docs). The one operational risk is forgetting to update `test_parity.py` to remove the now-deleted method names from any exception lists, causing a false-pass on parity when both sides simply lack the method.

---

## Sources

- `/home/loc/workspace/pycopg/pycopg/etl.py` — current `ETLAccessor.run()` and `AsyncETLAccessor.run()` implementation; transform chain; NaN coercion; `_end_run` call sites (success vs. failure paths)
- `/home/loc/workspace/pycopg/pycopg/queries.py` — `ETL_INIT_PIPELINE_RUNS` (watermark JSONB column present, always NULL); `ETL_UPDATE_RUN` (does NOT currently write `watermark`); `ETL_GET_LAST_RUN` (used to retrieve last watermark for next run)
- `/home/loc/workspace/pycopg/.planning/PROJECT.md` — v0.7.0 locked scope decisions (incremental_column, `>` filter, first-run = full load, append/upsert only, `replace` forbidden, zero new runtime deps)
- Incremental ETL design literature: the `>` vs `>=` boundary trade-off is documented in Airbyte, dbt, and Debezium documentation; the snapshot hazard is the standard "read-committed incremental ETL gap" problem discussed in Flink and Spark Structured Streaming CDC documentation
- psycopg 3 JSONB adapter behavior: psycopg 3 docs (built-in JSON adaptation — dicts/lists/primitives, no automatic datetime deserialization)
- pandas `max()` behavior on nullable columns: returns `NaN`/`NaT` for all-null series; ignores NULLs in mixed series (skipna=True by default)

---
*Pitfalls research for: watermark-based incremental ETL (pycopg v0.7.0, `Pipeline.incremental_column`, `pipeline_runs.watermark JSONB`)*
*Researched: 2026-06-19*
