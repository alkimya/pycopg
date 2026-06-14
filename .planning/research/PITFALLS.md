# Pitfalls Research

**Domain:** Same-DB ETL pipeline-runner on psycopg 3 — adding `db.etl.*` / `async_db.etl.*` to pycopg v0.5.0
**Researched:** 2026-06-14
**Confidence:** HIGH (codebase read directly; pitfalls derived from actual code patterns, not generic ETL theory)

---

## Critical Pitfalls

### Pitfall 1: Failed Run Leaves No Trace — the Log-in-Same-Transaction Trap

**What goes wrong:**

The run-tracking INSERT into `pipeline_runs` lives inside the same transaction as the load step. When the load fails, the transaction rolls back — taking the failure record with it. The next operator has no evidence the run ever started, no error message, no timestamp, no partial row count. Debugging requires grep-ing logs rather than querying `pipeline_runs`.

The mirror failure also exists: if the run-log UPDATE (marking success) runs before a commit that then fails, the "success" record is also rolled back, leaving `pipeline_runs` showing "running" forever.

**Why it happens:**

The natural implementation wraps everything in one `with db.transaction()` block: open run record → extract → transform → load → update run record → commit. This seems clean but the transaction atomicity guarantee works against observability. The pattern is copied from simpler "wrap all side effects in one transaction" thinking.

**How to avoid:**

Use a separate, independent connection for all `pipeline_runs` writes. This is the standard pattern in ETL tooling (Airflow, dbt, Prefect all write task state on a dedicated connection with `autocommit=True` to survive the main transaction's rollback).

Concretely for pycopg:

1. Open the `pipeline_runs` row immediately on a *new* connection (not the pool's main connection) with `autocommit=True`. Use `psycopg.connect(**db.config.connect_params(), autocommit=True)`.
2. Run the pipeline (extract → transform → load) on the main connection/pool.
3. On any exception, write `status='failed'`, `error=str(exc)`, `finished_at=now()` on the same dedicated autocommit connection before re-raising.
4. On success, write `status='success'`, `rows_loaded=n`, `finished_at=now()` on the dedicated connection.

The dedicated connection must be opened and closed within the runner function — never grabbed from the existing pool while the pool may be exhausted (see Pitfall 4).

**Warning signs:**

- `pipeline_runs` table has a "running" row with no corresponding failure row after a known-failed run.
- `SELECT * FROM pipeline_runs WHERE status = 'running' AND started_at < now() - interval '1 hour'` returns rows.
- The run-log INSERT is inside the same `db.transaction()` context manager as the TRUNCATE and the INSERT of loaded data.

**Phase to address:**

Run-tracking phase (design the schema + runner skeleton). Must be settled before the load phase is wired, because the load transaction boundary depends on this decision. Write a test: deliberately fail the load step and assert a `failed` row exists in `pipeline_runs`.

---

### Pitfall 2: Truncate-Then-Fail Destroys Target Data With No Recovery Path

**What goes wrong:**

Truncate-load order is: TRUNCATE target → extract from source → transform → INSERT into target. If extraction or transform fails after the TRUNCATE but before data is inserted, the target table is empty and the source data is still in its original table (because same-DB). However if the TRUNCATE and INSERT are in the same transaction, a rollback restores the target — which is correct and safe. The trap is implementing truncate-load outside a transaction (e.g., as two separate `autocommit` statements), leaving the target empty with no rollback possible.

**Why it happens:**

Developers think "TRUNCATE is fast and I'll INSERT right after" and skip the transaction wrapper. This is particularly likely when COPY is used for the INSERT (the existing `copy_insert` opens its own `conn.commit()` — see `database.py:694`), because COPY already manages its own commit internally, making it incompatible with an outer transaction without explicit savepoints or a staging table.

**How to avoid:**

For truncate-load: always wrap TRUNCATE + INSERT in a single `db.transaction()` block. This guarantees atomicity: either both succeed or the target is restored.

For large-data loads where COPY performance is needed: use a staging table pattern — INSERT into `target_staging` via COPY (own commit), then `BEGIN; TRUNCATE target; INSERT INTO target SELECT * FROM target_staging; COMMIT; DROP TABLE target_staging`. The staging copy is resumable; only the atomic swap risks data loss if crashed mid-swap, and the source is always intact.

For v0.5.0's scope (same-DB, not huge tables initially), the simple `TRUNCATE + batch INSERT` inside one transaction is the safe default. Document that COPY-based truncate-load is deferred.

**Warning signs:**

- `TRUNCATE` is called via `db.execute(..., autocommit=True)` anywhere in the load path.
- The existing `copy_insert` method is used for truncate-load without a staging table.
- Tests do not assert that a failed mid-load leaves the target in its pre-run state.

**Phase to address:**

Load phase (idempotent load implementation). Write a specific test: start truncate-load, raise an exception mid-insert, assert target row count equals the pre-run count (not zero).

---

### Pitfall 3: Upsert With Missing or Wrong Conflict Key — Silent Duplicates or Constraint Errors

**What goes wrong:**

Two failure modes. First: the conflict key is not the table's actual unique/PK constraint. psycopg's `ON CONFLICT (col)` requires an exact index match. If `conflict_columns` doesn't match an existing unique index, PostgreSQL raises `ERROR: there is no unique or exclusion constraint matching the ON CONFLICT specification` — loud and clear. But if the caller passes a subset of the natural key (e.g., `conflict_columns=["id"]` when the PK is actually `(id, source)`), the INSERT silently creates duplicates because the conflict never triggers.

Second: if `update_columns` is empty (all columns are conflict columns), the generated `DO UPDATE SET` clause is empty, which raises a syntax error. The existing `upsert_many` in database.py computes `update_columns = [c for c in columns if c not in conflict_columns]` but does not guard against the empty-update case.

**Why it happens:**

The ETL pipeline definition will accept `conflict_columns` as a user-provided list. Users copy column names by hand, miss a composite key component, and get no immediate error because inserts still succeed (they just don't deduplicate). The bug only surfaces when data accumulates or when a unique constraint elsewhere catches the duplicate.

**How to avoid:**

1. At pipeline definition time (not run time), validate that the `conflict_columns` list is non-empty.
2. Guard that `update_columns` (or the derived set) is non-empty when using upsert mode. If all columns are conflict columns, raise `ValueError("upsert_mode requires at least one non-conflict column to update; use load_mode='truncate' for replace semantics")`.
3. Document clearly: the user must ensure `conflict_columns` matches an existing unique constraint or PK. pycopg cannot auto-detect this without an introspection query (which would be overengineering for v0.5.0).
4. Consider an optional `verify_conflict_constraint=True` flag on the pipeline that does a one-time introspection check via `pg_constraint`.

**Warning signs:**

- `pipeline_runs` shows `rows_loaded=N` but `SELECT COUNT(*) FROM target` grows without bound across re-runs (duplicates accumulating).
- `conflict_columns` is set to `["id"]` on a table with a composite PK.
- No test asserts that re-running a pipeline leaves the row count unchanged (idempotency assertion).

**Phase to address:**

Pipeline definition and load phase. Add a test: run the same pipeline twice with upsert mode; assert `SELECT COUNT(*) FROM target` is the same after both runs.

---

### Pitfall 4: Pool Exhaustion When Run-Log Connection Is Grabbed From the Same Pool

**What goes wrong:**

If the run-log writes (open, update, close) use `async_db.execute(...)` or `db.execute(...)` — which draw from the connection pool — while the main pipeline connection is already held, a pool of size 1 deadlocks: the main connection waits for the log write, the log write waits for a free connection. With pool size > 1 this works but wastes a connection slot and makes the ETL surface depend on pool sizing.

For the async path this is more dangerous: `AsyncDatabase` uses `psycopg_pool.AsyncConnectionPool`. If the runner holds one connection for the duration of the run and then tries to execute the run-log update on the same pool's second connection, concurrency is lost and pool exhaustion is a ticking clock as more pipelines run simultaneously.

**Why it happens:**

The simplest implementation of run-log writes reuses `self._db.execute(...)`. This is natural — why open a new connection when we already have one? The answer is that the log write must survive the main transaction's rollback, which requires a *separate* connection outside the pool's transaction lifecycle.

**How to avoid:**

Open the dedicated run-log connection directly via `psycopg.connect(...)` / `psycopg.AsyncConnection.connect(...)` using `db.config.connect_params()`, not via the pool. Close it explicitly in a `finally` block. This is a raw connection, not managed by the pool, so it does not exhaust pool slots and its commits are independent.

For the async path, the run-log connection must be `await psycopg.AsyncConnection.connect(..., autocommit=True)` and closed with `await log_conn.close()` in `finally`.

**Warning signs:**

- The runner method calls `self._db.execute("INSERT INTO pipeline_runs ...")` while inside a `with self._db.transaction()` block.
- Pool size is 1 and a test hangs (deadlock) when both the main flow and run-log write are attempted.
- The run-log connection appears in `pg_stat_activity` with a name tied to the pool connection label.

**Phase to address:**

Run-tracking phase. Test: configure a pool of size 1; run a pipeline; assert it completes without hanging and that the run-log row was written.

---

### Pitfall 5: Sync Transform Called Bare Inside the Async Runner (Blocks the Event Loop)

**What goes wrong:**

The transform callable is a user-supplied Python function, typically operating on a pandas DataFrame. pandas is synchronous and CPU-bound. If the async runner calls it directly — `result = transform_fn(df)` — it blocks the event loop for the duration of the transform, stalling all other coroutines. For large DataFrames this can block for seconds.

This is exactly the problem `run_sync` / `conn.run_sync` was adopted for in the existing `AsyncDatabase.to_dataframe` / `from_dataframe` (see `async_database.py:1937`).

**Why it happens:**

The transform callable's type is `Callable[[pd.DataFrame], pd.DataFrame]` — identical between sync and async paths. The async runner naturally calls it the same way as the sync runner does, forgetting that in async context the call must be delegated to a thread pool.

**How to avoid:**

In the async runner, wrap all transform calls in `await asyncio.to_thread(transform_fn, df)` (Python 3.9+; pycopg already requires 3.11+). This is the correct async pattern for CPU/IO-bound callables.

The async runner method signature remains identical to the sync runner (for parity), but internally the transform dispatch differs: sync calls `transform_fn(df)` directly; async calls `await asyncio.to_thread(transform_fn, df)`.

Document the contract: transforms must be thread-safe (they receive a DataFrame slice, not a shared reference). Since transforms operate on in-memory DataFrame copies, thread safety is trivially satisfied.

**Warning signs:**

- The async runner's transform dispatch reads `result = transform_fn(df)` without `await asyncio.to_thread(...)`.
- The async runner test passes with small DataFrames but the event loop appears to stall under load.
- `asyncio.sleep(0)` injected into a concurrent coroutine never yields during a pipeline run.

**Phase to address:**

Async accessor phase (ETL parity). Write a test: run a pipeline with a slow transform (`time.sleep(0.1)` inside) concurrently with an `asyncio.sleep(0)` task; assert the sleep task completes while the transform is running (fails if the event loop is blocked).

---

### Pitfall 6: Identifier Injection via f-String Table Names in Load Builders

**What goes wrong:**

The ETL load step needs to generate SQL like `TRUNCATE public.target_table` and `INSERT INTO public.target_table (col1, col2) VALUES (...)`. The temptation is to use f-strings directly: `f"TRUNCATE {schema}.{table}"`. This bypasses the `validate_identifiers` guard that every other module in pycopg uses and that was specifically hardened in v0.3.1.

This is a security regression: a pipeline definition with `target_table="target; DROP TABLE users; --"` would execute arbitrary SQL.

**Why it happens:**

The ETL load builder is new code written quickly; the developer knows the identifier validation exists in `utils.py` but writes the SQL builder first ("I'll add validation later") and later never comes. The spatial.py builders are a working example of every identifier passing through `validate_identifiers` before interpolation — the ETL builders must follow the same pattern.

**How to avoid:**

Copy the spatial.py builder pattern exactly: the ETL load builder functions (analogous to `build_contains_sql`) must call `validate_identifiers(table, schema)` and `validate_identifiers(*conflict_columns)` before any string interpolation. Column lists must be validated before joining. Values are always `%s` parameters, never f-string interpolated.

The existing `upsert_many` already calls `validate_identifiers(*conflict_columns)` and `validate_identifiers(*update_columns)` — the ETL builders must reuse this same call site pattern, not replicate it ad-hoc.

**Warning signs:**

- Any ETL load builder function that does not call `validate_identifiers` before the first f-string including a user-supplied identifier.
- A test_sql_injection.py test that does NOT cover `db.etl.run(pipeline=Pipeline(target="malicious; DROP"))`.
- Column names from a DataFrame being joined with `", ".join(df.columns)` without validation.

**Phase to address:**

Load phase (SQL builder, day one). Add ETL cases to `test_sql_injection.py`. This must be in the first load phase, not deferred to a hardening phase.

---

### Pitfall 7: Materializing the Full Source Table Into Memory for Transform

**What goes wrong:**

The transform callable receives a `pd.DataFrame`. For a small table (thousands of rows) this is fine. For a large table (millions of rows) this is a silent OOM bomb: `to_dataframe("source_table")` reads the entire table into a single DataFrame before the transform is called, exhausting memory with no warning.

The tension is fundamental: Python-callable transforms need data in memory; large tables cannot fit in memory. The wrong solution is to silently allow unbounded extraction. The right solution is to document the constraint and add a safety opt-in.

**Why it happens:**

The MVP is designed for medium-sized datasets where the pattern works. No one adds a limit to the extraction query because "the user knows their data". Then the first production run on a 50M-row table OOMs the process.

**How to avoid:**

For v0.5.0 (same-DB, DataFrame transforms):

1. Add an optional `extract_limit: int | None = None` parameter to the pipeline definition. When set, the extraction SQL appends `LIMIT {int(extract_limit)}`.
2. Add an optional `extract_batch_size: int | None = None` parameter. When set, the runner uses `db.stream(sql, batch_size=extract_batch_size)` to iterate in batches, calling the transform on each batch DataFrame and loading each batch incrementally.
3. Document prominently: "The default extraction materializes the full result set into a DataFrame. For tables larger than available RAM, use `extract_batch_size` to process in chunks."
4. Do NOT silently limit extraction (e.g., force `LIMIT 10000`). That would silently corrupt the load for large tables.

The existing `db.stream()` method (database.py:529, async_database.py:2204) is the mechanism for batch extraction. The ETL runner uses it when `extract_batch_size` is set.

**Warning signs:**

- The extraction step always calls `db.to_dataframe(sql=extract_sql)` with no size guard.
- No parameter on `Pipeline` or `run()` controls extraction size.
- The docs do not mention memory requirements.

**Phase to address:**

Extract phase. Document the memory model in the API docstring. Implement `extract_limit` and `extract_batch_size` as optional parameters from the start rather than retrofitting them.

---

### Pitfall 8: Re-Run While Previous Run Is Still "Running" — Concurrent Execution Corruption

**What goes wrong:**

Two concurrent calls to `db.etl.run(pipeline)` both read `pipeline_runs` and find no active run, then both proceed to TRUNCATE the target and INSERT. With truncate-load, the second TRUNCATE wipes the first run's partial inserts. With upsert mode, both runs write the same conflict keys and the result is non-deterministic. The `pipeline_runs` table ends up with two "running" rows for the same pipeline.

**Why it happens:**

The status check ("is this pipeline already running?") and the run-log INSERT are not atomic. A standard SELECT + INSERT has a race window. This is the classic check-then-act TOCTOU problem.

**How to avoid:**

Use PostgreSQL advisory locks. Before starting the pipeline:

```sql
SELECT pg_try_advisory_lock(hashtext('pipeline:' || pipeline_name))
```

If this returns false, the pipeline is already running — raise `PipelineAlreadyRunning` and exit. Advisory locks are session-scoped in PostgreSQL and automatically released when the connection closes, so they survive abnormal termination. They require no schema migration.

Use `pg_try_advisory_lock` (non-blocking) rather than `pg_advisory_lock` (blocking) so the caller gets an immediate error rather than a hang.

The advisory lock must be acquired on the dedicated run-log connection (the same connection opened for run-log writes), so the lock persists for the duration of the run and is released atomically when the log connection closes.

**Warning signs:**

- `pipeline_runs` has two rows with `status='running'` and the same `pipeline_name`.
- No advisory lock or unique constraint guards concurrent pipeline execution.
- Tests do not test concurrent `run()` calls on the same pipeline name.

**Phase to address:**

Run-tracking phase. Write a test: a second concurrent `run()` call raises `PipelineAlreadyRunning` immediately rather than proceeding.

---

### Pitfall 9: `test_parity` Passes but ETL Async Accessor Is Missing Methods

**What goes wrong:**

The `test_parity` harness (test_parity.py) inspects `inspect.getmembers(Database)` for all non-underscore members. If `db.etl` is a property returning `EtlAccessor` and `async_db.etl` is a property returning `AsyncEtlAccessor`, the property name `etl` appears in both and parity passes. But if `EtlAccessor` has method `run` and `AsyncEtlAccessor` is missing `run`, the *accessor's* methods are invisible to `test_parity` — it only sees top-level Database/AsyncDatabase members.

The risk is implementing the ETL accessor with full `EtlAccessor` coverage but forgetting to wire the async accessor, then having `test_parity` pass because both have an `etl` property, while `async_db.etl.run()` is missing.

**Why it happens:**

The `test_parity` harness checks `Database` vs `AsyncDatabase` surface. It does not recursively inspect accessor classes. The spatial accessor had the same gap: SpatialAccessor and AsyncSpatialAccessor needed their own parity test (test_spatial.py covers both sync and async paths).

**How to avoid:**

1. Add a dedicated `TestEtlParity` test class (analogous to the spatial parity tests in test_spatial.py) that inspects `EtlAccessor` vs `AsyncEtlAccessor` method surfaces using the same `inspect.getmembers` pattern.
2. Add behavioral parity tests: run the same pipeline on both `db.etl` and `async_db.etl`, assert identical `pipeline_runs` outcomes and target row counts.
3. The `SYNC_ONLY_METHODS` and `ASYNC_ONLY_METHODS` sets in `TestAsyncParity` must remain unchanged (neither `etl` nor its methods should be added as exceptions).

**Warning signs:**

- `test_parity.py` passes but `async_db.etl.run()` has not been implemented.
- `EtlAccessor` and `AsyncEtlAccessor` have different method names or signatures.
- No test file named `test_etl.py` or `test_etl_parity.py` with accessor-level method inspection.

**Phase to address:**

Async accessor phase. Write the accessor parity test skeleton before implementing `AsyncEtlAccessor`, so the test fails (xfail or outright) until the async implementation is complete.

---

### Pitfall 10: `pipeline_runs` Schema Blocks v0.6.0 Watermarks — Non-Additive Design

**What goes wrong:**

v0.5.0 defers incremental watermarks to v0.6.0. If `pipeline_runs` is designed without watermark columns in mind, v0.6.0 will require an `ALTER TABLE pipeline_runs ADD COLUMN watermark_value TEXT` migration — which is additive and safe — or worse, a destructive schema change if the status enum or primary key were designed incompatibly.

The specific trap: designing `pipeline_runs` with `status` as a PostgreSQL `ENUM` type. Adding a new enum value (`'partial'`) in v0.6.0 requires `ALTER TYPE` which in older PostgreSQL versions is not transactional and can cause production issues. Using a plain `TEXT` column for status avoids this.

**Why it happens:**

Developers use Postgres ENUM because it feels more correct for a fixed set of values ('running', 'success', 'failed'). But ENUM types are hard to evolve and offer no real constraint benefit over a TEXT column with a CHECK constraint.

**How to avoid:**

Design `pipeline_runs` with explicit forward compatibility from day one:

```sql
CREATE TABLE pipeline_runs (
    id SERIAL PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    rows_extracted INTEGER,
    rows_loaded INTEGER,
    error TEXT,
    -- v0.6.0 watermark slots (nullable, ignored by v0.5.0 runner):
    watermark_column TEXT,
    watermark_value TEXT
);
```

The watermark columns are nullable and ignored by the v0.5.0 runner. v0.6.0 writes to them without a migration. The PROJECT.md explicitly states: "the `pipeline_runs` table is designed so watermarks slot on additively (nothing wasted)."

**Warning signs:**

- `status` column defined as `ENUM` rather than `TEXT ... CHECK`.
- No `watermark_column` / `watermark_value` nullable columns in the initial schema.
- The CREATE TABLE migration is written to be "minimal now, extend later" without the watermark stubs.

**Phase to address:**

Run-tracking phase (schema design, the very first ETL phase). This is a one-time, low-cost action (two nullable columns) with a high-value payoff (no breaking migration in v0.6.0).

---

### Pitfall 11: Scope Creep Toward DAG / Orchestrator

**What goes wrong:**

The natural evolution of "run one pipeline" is "run pipelines in dependency order", then "schedule pipelines", then "retry failed pipelines", then "fan-out on partial failure". Each step is locally reasonable but collectively they build an orchestrator, not a library helper. v0.5.0 is explicitly same-DB, no scheduling, no DAG.

The specific API leaks that trigger this: adding a `depends_on` parameter to `Pipeline`, adding `retry_on_failure` to `run()`, adding a `schedule` cron expression, or adding cross-pipeline status checks in the runner.

**Why it happens:**

The pipeline runner's `pipeline_runs` table is a ready-made task state table. Adding `depends_on` feels like a two-line change. It is — but it also commits to DAG semantics that require topo-sort, cycle detection, fan-out, fan-in, and a scheduler loop. The complexity is O(N pipelines), not O(1).

**How to avoid:**

The v0.5.0 `Pipeline` dataclass must have no `depends_on`, `schedule`, `retry_on_failure`, or `timeout` fields. The `run()` method executes exactly one pipeline, unconditionally. Retry belongs at the caller's level (tenacity is already in the dependency tree if needed). Document the boundary explicitly in the API docstring.

The `pipeline_runs` table does not need a `trigger_source` or `parent_run_id` column in v0.5.0. Those slots can be added additively in a future milestone.

**Warning signs:**

- A `depends_on: list[str]` field appears on the `Pipeline` class.
- The runner iterates over a list of pipelines in dependency order.
- `pipeline_runs` has a `parent_run_id` FK column in the v0.5.0 schema.
- The runner has retry logic beyond the existing tenacity integration.

**Phase to address:**

Pipeline definition phase (define `Pipeline` dataclass). Enforce the boundary in the design document and in the `Pipeline.__init__` signature — simplicity is maintained by not having the parameter.

---

### Pitfall 12: Coverage Gate Drops Below 94% — ETL I/O Paths Hard to Cover

**What goes wrong:**

The 94% coverage ratchet (`--cov-fail-under=94`) was set after measuring actual coverage at 94.09%. ETL code adds new I/O-heavy paths: the dedicated run-log connection, the advisory lock query, the TRUNCATE + INSERT transaction, the `pipeline_runs` DDL. Some of these paths (the failure branch of the run-log write, the pool-size-1 deadlock guard) are hard to cover without real-PostgreSQL integration tests.

If the ETL phase is implemented with only unit tests (mocking the DB), the integration coverage for these paths is zero, and the ratchet blocks the commit.

**Why it happens:**

The existing spatial.py builders are pure functions (no I/O) that are trivially unit-testable. The ETL runner is an I/O-heavy orchestrator that requires a real DB to test meaningfully. Developers writing unit tests for ETL logic (mock DB, mock advisory lock) get high apparent coverage but miss the real integration paths. Then the CI coverage measurement (on real PG) shows lower coverage.

**How to avoid:**

Follow D-08 precedent: measure coverage before raising the ratchet gate. Specifically:

1. Write real-PostgreSQL integration tests for all ETL paths in the test suite (using `pycopg_test` DB), not mocks.
2. The run-log failure branch (transaction rolled back, failure row written) must be an integration test with a real transaction rollback.
3. The advisory lock path (second concurrent run blocked) must be an integration test with two connections.
4. Check `uv run pytest --cov` on real PG before the phase is marked done; if coverage drops below 94%, add more integration tests before raising the gate.
5. Do not raise the gate in the middle of the ETL phases — only at the final ETL phase after all paths are covered.

**Warning signs:**

- ETL tests use `unittest.mock.patch` for the DB connection instead of `pycopg_test`.
- `uv run pytest --cov` reports coverage below 94% after ETL code is added.
- The run-log failure branch has no test.

**Phase to address:**

Every ETL phase (extract, transform, load, run-tracking, async parity). Coverage must be monitored continuously per D-08. The final ETL phase should raise the ratchet only after measuring the new baseline.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Run-log INSERT in same transaction as load | Simpler code, one transaction | Failed runs leave no trace; debugging blind | Never |
| `copy_insert` for truncate-load without staging table | Faster inserts | Truncate-then-fail leaves empty target; cannot roll back | Never for truncate-load path |
| Skip `validate_identifiers` in ETL load builders | Faster to write | SQL injection regression, bypasses hardened security | Never |
| Use Postgres ENUM for `pipeline_runs.status` | Feels type-safe | ALTER TYPE headache in v0.6.0 when adding watermark status values | Never |
| Call `transform_fn(df)` directly in async runner | Identical code path to sync | Blocks event loop; test passes (small df) but fails in production | Never |
| No advisory lock for concurrent runs | Simpler pipeline runner | Silent data corruption on concurrent invocation of truncate-load | Never for truncate-load; acceptable for upsert only if idempotency proven |
| Materialize full table with no size guard | Simpler API | OOM on first production-scale run | Acceptable only if `extract_limit` documented as mandatory for large tables |
| Skip ETL accessor parity test | test_parity still passes | Async accessor silently diverges; parity is pycopg's core value | Never |
| Mock DB in ETL tests instead of real PG | Faster test run | Coverage metric lies; real bugs (pool deadlock, txn rollback) not caught | Never for integration paths |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| psycopg 3 `executemany` | Using for large bulk loads | `executemany` in psycopg 3 sends rows one by one (not batched VALUES); use `insert_batch` for <10k rows or `copy_insert` for >10k rows |
| psycopg 3 COPY inside a transaction | Wrapping `COPY FROM STDIN` in `conn.transaction()` | COPY operates within the current transaction in psycopg 3; `copy_insert` opens its own connection and calls `conn.commit()` explicitly — ETL must not call `copy_insert` inside an outer `db.transaction()` block without a staging table |
| pandas `to_sql` / `read_sql` in async | Calling directly in async method | Must go through `conn.run_sync(lambda sync_conn: ...)` as all existing `to_dataframe`/`from_dataframe` async methods already do (async_database.py:1937) |
| pandas NaN in numeric columns | `NaN` sent to a nullable integer or text column | psycopg 3 sends `float('nan')` as the float NaN literal, not SQL NULL; use `df.where(df.notna(), other=None)` before `insert_batch` or `to_sql` |
| Timezone-naive timestamps | DataFrame `datetime64[ns]` (naive) inserted into `TIMESTAMPTZ` column | PostgreSQL infers session timezone, producing silent data corruption; ensure DataFrame timestamps are `datetime64[ns, UTC]` or use `dtype={"col": TIMESTAMP(timezone=True)}` in `to_sql` |
| `validate_identifier` vs DataFrame column names | DataFrame columns with spaces or hyphens (e.g., `"order-date"`) fail `validate_identifier` | ETL load builder must validate all target column names; if source DataFrame has non-identifier columns, the transform step must rename them before load |
| psycopg 3 `stream()` and server-side cursors | Using `fetchmany` on a regular cursor thinking it streams from DB | `fetchmany` on a regular cursor buffers the full result set server-side after `execute()`; for true streaming, use `psycopg.ServerCursor` (sync) or `psycopg.AsyncServerCursor` (async) — the existing `stream()` method uses regular `fetchmany` which is not truly server-side streaming |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `executemany` for ETL load | Loading 50k rows takes 30s instead of 3s | Use `insert_batch` (batch VALUES) for <10k rows; `copy_insert` for >10k rows | >1k rows |
| Full-table DataFrame extract | Memory spike then OOM or swap thrash | Use `extract_batch_size` to stream in chunks via `db.stream()` | >100k rows on a typical 4GB instance |
| Advisory lock on pool connection | Lock released when pool recycles the connection before the run ends | Acquire advisory lock on the dedicated run-log connection (not the pool) | Any run lasting longer than pool's `max_idle` timeout |
| Upsert with no index on conflict columns | Upsert degrades to sequential scan for each row; target table locks | Ensure `conflict_columns` are covered by a unique index before the pipeline runs | >10k rows in target table |
| Transform receiving the full DataFrame then re-chunking | Two copies of the data in memory (source df + chunked df) | Design the transform to operate on the chunk size that will be passed; document batch size contract | >50k rows with complex transforms |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| f-string interpolation of `pipeline.target_table` | SQL injection via pipeline definition | Call `validate_identifiers(table, schema)` before any interpolation, same as all other pycopg builders |
| f-string interpolation of `pipeline.conflict_columns` | SQL injection via conflict column list | Call `validate_identifiers(*conflict_columns)` before joining into ON CONFLICT clause |
| User-controlled `extract_sql` with raw string injection | ETL pipeline as SQL injection vector if query params not used | Document that `extract_sql` is user-supplied raw SQL (same accepted limitation as spatial `where=` raw fragment); consider noting it in the docstring |
| `pipeline_runs.error` storing full exception repr | Exception messages may leak internal paths or connection strings | Truncate to 1024 chars; strip connection strings from exception messages before storing |

---

## "Looks Done But Isn't" Checklist

- [ ] **Run-log independence:** The `pipeline_runs` INSERT and UPDATE use a dedicated non-pool connection, not `db.execute()`. Test: fail a load step; assert `pipeline_runs` has `status='failed'` row.
- [ ] **Truncate atomicity:** TRUNCATE and subsequent INSERT share a single transaction. Test: exception mid-insert; assert target row count equals pre-run count.
- [ ] **Upsert idempotency:** Run the same pipeline twice; assert `SELECT COUNT(*) FROM target` is identical after both runs (no duplicates).
- [ ] **Async event-loop safety:** Transform callable goes through `asyncio.to_thread()` in the async runner. Test: slow transform + concurrent coroutine; assert concurrent coroutine is not blocked.
- [ ] **ETL accessor parity:** `EtlAccessor` and `AsyncEtlAccessor` have identical method names and signatures. `TestEtlParity` class exists and passes.
- [ ] **Identifier validation in load builders:** Every ETL SQL builder calls `validate_identifiers` before any identifier interpolation. `test_sql_injection.py` covers `etl.run(target="malicious")`.
- [ ] **Watermark slots in schema:** `pipeline_runs` has nullable `watermark_column` and `watermark_value` TEXT columns from the initial migration.
- [ ] **Memory guard documented:** API docstring for `Pipeline` or `run()` states the memory contract and documents `extract_limit` / `extract_batch_size` parameters.
- [ ] **Advisory lock test:** A second concurrent `run()` call raises `PipelineAlreadyRunning` immediately rather than proceeding or hanging.
- [ ] **Coverage gate:** `uv run pytest` still reports >= 94% after all ETL code is added. Coverage measured on real PG (per D-08), not mocks.
- [ ] **No scope creep:** `Pipeline` dataclass has no `depends_on`, `schedule`, `retry_on_failure`, or `parent_run_id` fields.
- [ ] **NaN/timezone type adaptation:** Test with DataFrame containing NaN numerics and timezone-naive timestamps; assert NULL and UTC stored correctly in target.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Failed run leaves no trace (log in same txn) | HIGH | Audit PostgreSQL logs for ERROR messages; check `pg_stat_activity` history if `log_min_duration_statement` is enabled; architectural fix required before next run |
| Truncate-load data loss (no transaction wrapper) | HIGH | Source data is intact (same-DB); restore target from source with manual INSERT SELECT; add transaction wrapper before next run |
| Duplicate rows from wrong conflict key | MEDIUM | `DELETE FROM target WHERE ctid NOT IN (SELECT MIN(ctid) FROM target GROUP BY natural_key_cols)`; audit pipeline definition for correct conflict_columns |
| Pool deadlock from run-log on pool connection | MEDIUM | Restart application; switch run-log to dedicated raw connection |
| OOM from full-table DataFrame extract | LOW | Kill process; re-run with `extract_batch_size` set; no data corruption (transaction rolled back or extract never completed) |
| Async event-loop blockage from direct transform call | LOW | No data corruption; fix async runner to use `asyncio.to_thread`; redeploy |
| test_parity failure from missing async ETL method | LOW | Implement missing async accessor method; parity test is a CI gate so this surfaces immediately before merge |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Run-log in same transaction (no trace on failure) | Run-tracking phase (schema + runner skeleton) | Test: fail a load step; assert `pipeline_runs` has `status='failed'` row |
| Truncate-then-fail data loss | Load phase (idempotent load) | Test: exception mid-insert; assert target row count unchanged |
| Wrong upsert conflict key / empty update set | Pipeline definition + load phase | Test: two runs of same pipeline; assert count unchanged |
| Pool exhaustion from run-log on pool | Run-tracking phase | Test: pool size 1; run completes without deadlock; run-log row written |
| Sync transform blocks async event loop | Async accessor phase (ETL parity) | Test: slow transform + concurrent sleep; assert sleep yields during transform |
| Identifier injection in load builders | Load phase (SQL builders, day one) | test_sql_injection.py covers `etl.run(target="malicious; DROP --")` |
| Full-table OOM | Extract phase | `extract_limit` / `extract_batch_size` params in API; test with explicit limit |
| Concurrent run corruption | Run-tracking phase | Test: second concurrent `run()` raises `PipelineAlreadyRunning` immediately |
| ETL accessor parity gap | Async accessor phase | `TestEtlParity` inspects `EtlAccessor` vs `AsyncEtlAccessor` method surfaces |
| `pipeline_runs` schema blocks v0.6.0 watermarks | Run-tracking phase (initial migration) | Schema has nullable `watermark_column` + `watermark_value` from creation |
| NaN/timezone type adaptation | Load phase | Test: DataFrame with NaN numerics and naive timestamps; assert NULL and UTC stored |
| Scope creep toward DAG/orchestrator | Pipeline definition phase (design gate) | `Pipeline` has no `depends_on`, `schedule`, `retry_on_failure` parameters |
| Coverage gate drops below 94% | Every ETL phase | `uv run pytest --cov` on real PG; measure before raising gate per D-08 |

---

## Sources

- pycopg source: `/home/loc/workspace/pycopg/pycopg/database.py` — `transaction()`, `insert_batch()`, `upsert_many()`, `copy_insert()`, `stream()`
- pycopg source: `/home/loc/workspace/pycopg/pycopg/async_database.py` — `run_sync` via `conn.run_sync()`, async `stream()`, async `transaction()`, `to_dataframe()`/`from_dataframe()` patterns
- pycopg source: `/home/loc/workspace/pycopg/pycopg/spatial.py` — builder pattern with `validate_identifiers`, accessor pattern precedent for ETL
- pycopg source: `/home/loc/workspace/pycopg/pycopg/utils.py` — `validate_identifiers`, `validate_identifier` — reuse mandated for ETL load builders
- pycopg source: `/home/loc/workspace/pycopg/tests/test_parity.py` — `TestAsyncParity` harness; `SYNC_ONLY_METHODS` / `ASYNC_ONLY_METHODS` — ETL must not add to exception lists
- pycopg project: `/home/loc/workspace/pycopg/.planning/PROJECT.md` — D-06/D-07/D-08 parity/coverage decisions; "pipeline_runs designed so watermarks slot on additively"; coverage ratchet stays at 94% baseline
- Pattern precedent: Airflow, dbt, Prefect all use separate/autocommit connections for task-state persistence (run-log must survive main transaction rollback)
- PostgreSQL docs: `pg_try_advisory_lock` for non-blocking concurrency guard; `TEXT + CHECK` vs `ENUM` for evolvable status columns; COPY within transaction semantics in psycopg 3

---
*Pitfalls research for: same-DB ETL pipeline-runner on psycopg 3 (pycopg v0.5.0)*
*Researched: 2026-06-14*
