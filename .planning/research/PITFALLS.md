# Pitfalls Research

**Domain:** TimescaleDB 2.x advanced feature wrapping in a psycopg 3 high-level Python library (pycopg v0.8.0)
**Researched:** 2026-06-22
**Confidence:** HIGH (MEDIUM for a few version-specific boundary claims noted inline)

---

## Critical Pitfalls

### Pitfall 1: CREATE MATERIALIZED VIEW (Continuous Aggregate) Cannot Run Inside a Transaction Block

**What goes wrong:**

`CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` fails with:

```
ERROR: CREATE MATERIALIZED VIEW ... WITH DATA cannot be executed within a pipeline
```

or (on some versions):

```
ERROR: REFRESH cannot run inside a transaction block
```

psycopg 3 opens an implicit transaction on every connection that is NOT in autocommit mode. Because `Database.execute()` (and every method that calls it) uses a normal connection, any call to `create_continuous_aggregate` through the standard path fires inside an implicit transaction and raises this error immediately.

**Why it happens:**

TimescaleDB's continuous aggregate DDL runs across two internal transactions: one to move the invalidation threshold and one to materialize. PostgreSQL's transaction machinery cannot enclose another BEGIN/COMMIT pair inside an open transaction, so TimescaleDB explicitly prohibits these calls inside a transaction context. The restriction has been present since TimescaleDB 1.3 and is a permanent, intentional constraint.

The ETL accessor solved the identical problem for `pipeline_runs` writes by opening a dedicated `self._db.connect(autocommit=True)` connection per call. Continuous aggregate DDL needs exactly the same structural fix — a dedicated autocommit connection per call, NOT a route through `self._db.execute()`.

**How to avoid:**

Every TimescaleDB DDL or management call that requires autocommit must open a fresh connection via `self._db.connect(autocommit=True)` instead of delegating to `self._db.execute()`. Concretely:

- `create_continuous_aggregate` — use `connect(autocommit=True)` for the `CREATE MATERIALIZED VIEW` statement.
- `refresh_continuous_aggregate` — use `connect(autocommit=True)`.
- `add_continuous_aggregate_policy` — stored procedure; also requires no enclosing transaction; use `connect(autocommit=True)` for consistency and safety.
- `drop_continuous_aggregate` — `DROP MATERIALIZED VIEW` is DDL; same rule.

For the async accessor, psycopg 3's `AsyncConnection` property `autocommit` is read-only after construction. Use `autocommit=True` at `AsyncConnection.connect()` time, or call `await conn.set_autocommit(True)` immediately after opening the connection. Never attempt `conn.autocommit = True` on an already-open async connection.

The existing `TimescaleAccessor.create_hypertable` uses `self._db.execute()` (inside an implicit transaction). `create_hypertable` happens to work because it calls a stored procedure that uses `SPI_exec` internally without requiring a top-level autocommit context. Do NOT assume other new TimescaleDB calls follow the same pattern — verify each one by reading the TimescaleDB source or testing explicitly.

**Warning signs:**

- `InFailedSqlTransaction` or `ActiveSqlTransaction` psycopg errors during tests.
- The call works when called from a fresh Python process but fails when called after any other `db.*` call in the same session.
- Integration test passes in isolation, fails when run after another test in a suite sharing a `db` instance.

**Phase to address:**

Continuous aggregate phase (Phase 30). Add an explicit autocommit guard in each affected method. Write a regression test that calls `create_continuous_aggregate` AFTER `db.execute("SELECT 1")` in the same session to prove the isolation works.

---

### Pitfall 2: refresh_continuous_aggregate Also Cannot Run Inside a Transaction Block

**What goes wrong:**

`refresh_continuous_aggregate(view, window_start, window_end)` raises:

```
ERROR: REFRESH cannot run inside a transaction block
```

This is a separate issue from Pitfall 1 — the refresh is blocked even when the view was created correctly. Any refresh call routed through `self._db.execute()` hits this error.

Additionally, data inserted inside an uncommitted client transaction is NOT visible to the refresh — the refresh reads only committed rows from the underlying hypertable. A test that inserts data and immediately calls refresh on the same connection (without committing first) will see an empty refresh result.

**Why it happens:**

Same root cause as Pitfall 1: the refresh moves the materialization watermark in one transaction and applies aggregation in a second transaction. An enclosing client transaction block prevents this.

**How to avoid:**

Same structural solution: `connect(autocommit=True)` for every refresh call. Additionally, the test fixture must ensure that data is committed before the refresh is called. Use autocommit inserts in the test setup, or call `db.execute("COMMIT")` explicitly before calling refresh.

Test shape:

```python
# 1. Insert committed data (autocommit=True or explicit commit)
db.execute("INSERT INTO metrics (time, val) VALUES (now() - INTERVAL '2 hours', 42)")
# 2. Refresh on its own autocommit connection
db.timescale.refresh_continuous_aggregate("metrics_hourly", start, end)
# 3. Assert aggregated row now exists
rows = db.execute("SELECT * FROM metrics_hourly")
assert len(rows) > 0
```

**Warning signs:**

Tests that insert data and immediately call refresh return empty results without errors — the data was not committed when refresh ran.

**Phase to address:**

Continuous aggregate phase (Phase 30). The refresh method must be on a dedicated autocommit connection. The test fixture must use committed data.

---

### Pitfall 3: drop_chunks Is Destructive and Irreversible — Easy Footgun in a High-Level API

**What goes wrong:**

`drop_chunks('my_hypertable', older_than => INTERVAL '30 days')` permanently deletes all chunks older than 30 days. There is no ROLLBACK. Data is gone. If a user calls `db.timescale.drop_chunks("metrics", "30 days")` with a wrong table name or wrong interval, they lose production data with no recovery path.

Additionally: if a continuous aggregate is defined on the hypertable and its refresh window overlaps with the dropped region, aggregate queries return incorrect results (NULL-padded or zero) for the deleted period. The aggregate view survives the drop but queries a hypertable with missing raw data.

**Why it happens:**

The function name sounds benign. A high-level convenience API makes it trivially easy to call. The `older_than` parameter accepts a plain interval string, which a user might read as "chunks from 30 days ago" when it means "all chunks whose time range is entirely before (now - 30 days)".

**How to avoid:**

1. Mark `drop_chunks` as DESTRUCTIVE and IRREVERSIBLE in the numpydoc `Notes` section. Use the word "permanent". Do not soften it.
2. Add a `dry_run: bool = False` parameter that calls `show_chunks` with the same arguments and returns the list of chunks that WOULD be dropped without actually dropping them. This mirrors the ETL dry_run pattern already in the codebase.
3. Validate that exactly one of `older_than` or `newer_than` is provided — never accept both (confusing semantics); never default both to None (which would drop every chunk).
4. Ship `show_chunks` (read-only) before `drop_chunks` so the pattern is established.

Test shape: insert data in two temporal windows, drop the older window via `drop_chunks`, assert older chunks are gone and newer chunks remain. Verify via `show_chunks` before and after. Also test `dry_run=True` returns the chunk list without removing anything.

**Warning signs:**

All hypertable data disappears after a `timescale.*` call. `drop_chunks` is the first suspect.

**Phase to address:**

Chunk management phase (whichever phase implements `show_chunks` / `drop_chunks`). The `dry_run` parameter and the DESTRUCTIVE docstring note are non-negotiable before publication.

---

### Pitfall 4: time_bucket_gapfill Bounds Cannot Be Inferred from psycopg %s Parameters

**What goes wrong:**

The query:

```sql
SELECT time_bucket_gapfill('1 hour', time) AS bucket, avg(val)
FROM metrics
WHERE time >= %s AND time < %s
GROUP BY bucket
```

with bound parameters raises:

```
ERROR: missing time_bucket_gapfill argument: could not infer start from WHERE clause
```

or:

```
ERROR: invalid time_bucket_gapfill argument: start must be a simple expression
```

`time_bucket_gapfill` requires TimescaleDB's planner hook to inspect the WHERE clause at planning time to determine the gapfill range. When values are bound as `%s` placeholders (prepared-statement parameters), the planner sees opaque plan nodes — it cannot read the literal value — so inference fails. This is not a psycopg 3 bug; it is a fundamental TimescaleDB planner constraint.

**Why it happens:**

The pycopg codebase correctly uses `%s` for all user values to prevent injection. This pattern is right for data values but is structurally incompatible with `time_bucket_gapfill`'s planner-time bound inference.

**How to avoid:**

Pass `start` and `end` as explicit arguments to `time_bucket_gapfill()` in the generated SQL:

```sql
SELECT time_bucket_gapfill('1 hour', time, %s::timestamptz, %s::timestamptz) AS bucket, avg(val)
FROM metrics
WHERE time >= %s AND time < %s
GROUP BY bucket
```

With explicit start/end arguments in the function call, TimescaleDB reads them from the function argument list at execution time — not from the WHERE clause at planning time. Bound `%s` parameters in function arguments work correctly. Only WHERE-clause inference fails.

The builder signature must accept `start` and `end` as required parameters, not optional inferrable values. If the user does not provide them, raise a clear `ValueError` before the query is sent.

`locf()` and `interpolate()` are only valid alongside `time_bucket_gapfill`. Guard against constructing a query that uses them outside a gapfill context.

**Warning signs:**

- The query works with hardcoded literal dates but fails with bound parameters.
- Error message mentions "could not infer start" or "start must be a simple expression".

**Phase to address:**

`time_bucket` / `time_bucket_gapfill` helpers phase. The builder MUST accept explicit `start` and `end` parameters and embed them as function arguments. Write a test using `datetime.now()` as a bound parameter (not a literal) to confirm the explicit-argument path works.

---

### Pitfall 5: time_bucket_gapfill MUST Appear Directly in GROUP BY — No Expression Wrapping

**What goes wrong:**

```sql
-- Fails silently or with a planner error:
SELECT time_bucket_gapfill('1 hour', time) + INTERVAL '30 minutes', avg(val)
FROM metrics
WHERE time >= '2024-01-01' AND time < '2024-01-02'
GROUP BY time_bucket_gapfill('1 hour', time) + INTERVAL '30 minutes'
```

`time_bucket_gapfill` must be a top-level reference in GROUP BY, not wrapped in any expression. Wrapping breaks TimescaleDB's planner recognition of the function.

**Why it happens:**

`time_bucket_gapfill` is a special planner-recognized function. Expression wrapping in GROUP BY defeats the recognition even if the expression is semantically equivalent.

**How to avoid:**

The builder must never wrap `time_bucket_gapfill(...)` in any expression in the GROUP BY clause. If users need an offset, apply it in a CTE or outer SELECT. Document this constraint in the method docstring.

**Phase to address:**

`time_bucket` / `time_bucket_gapfill` phase. Verify with a test that the generated SQL includes bare `time_bucket_gapfill(...)` as the GROUP BY column.

---

### Pitfall 6: add_dimension Requires an Empty Hypertable; by_range/by_hash Requires TimescaleDB >= 2.13

**What goes wrong:**

Calling `add_dimension` on a hypertable that already has data raises an error (exact message varies by version; roughly: "hypertable has existing data: cannot add partitioned dimension").

Additionally, on TimescaleDB < 2.13, calling the new `by_range('column', interval)` or `by_hash('column', partitions)` dimension builder functions fails with `UndefinedFunction`. These were introduced in TimescaleDB 2.13 as part of the "generalized hypertable DDL API" release.

The pre-2.13 positional form is deprecated but still works on 2.13+:

```sql
-- Old positional form (deprecated in 2.13, works on all 2.x):
SELECT add_dimension('table', 'column', number_partitions => 4);
SELECT add_dimension('table', 'column', chunk_time_interval => INTERVAL '1 day');
```

`number_partitions` and `chunk_time_interval` are mutually exclusive — passing both raises an error.

**Why it happens:**

The 2.13 release simplified the DDL API. Users on self-hosted PostgreSQL with an older TimescaleDB build (pre-2.13) will not have `by_range`/`by_hash`. The pycopg test environment may also be pre-2.13 — check with `SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'` before building the implementation.

**How to avoid:**

1. Validate the target hypertable is empty before calling `add_dimension`. Query `timescaledb_information.chunks` for the hypertable; if rows exist, raise a clear pycopg-domain error (not a raw psycopg `ProgrammingError`) before sending the SQL.
2. Use the pre-2.13 positional keyword form in the initial implementation — it works on both old and new 2.x. Document `by_range`/`by_hash` as a future enhancement requiring >= 2.13.
3. Validate that `number_partitions` and `chunk_time_interval` are not both provided — raise `ValueError` at call time if both are non-None.
4. Document the 2.x minimum in the docstring. If both forms are exposed in a future phase, add a version gate check (query `pg_extension.extversion`, compare semver).

**Warning signs:**

- Error about "existing data" when running `add_dimension` tests — the fixture is reusing a hypertable from a prior test that inserted data.
- `UndefinedFunction` for `by_range` or `by_hash` on the CI/local test server.

**Phase to address:**

`add_dimension` phase. Test fixture must create a fresh empty hypertable for each `add_dimension` test.

---

### Pitfall 7: Continuous Aggregate SELECT Must Use time_bucket on the Partitioning Column

**What goes wrong:**

```sql
-- Fails with a TimescaleDB error:
CREATE MATERIALIZED VIEW bad_agg WITH (timescaledb.continuous) AS
SELECT date_trunc('hour', time) AS bucket, avg(val)
FROM metrics
GROUP BY bucket;
```

TimescaleDB requires `time_bucket(interval, <partitioning_column>)` — not `date_trunc`, not a plain column reference, not an alias. The partitioning column must be the one defined as the time dimension of the hypertable.

**Why it happens:**

`date_trunc` is a plain PostgreSQL function; TimescaleDB cannot hook into its planner extension for incremental materialization. `time_bucket` is the required entry point for continuous aggregates.

**How to avoid:**

The `create_continuous_aggregate` builder should validate (heuristic only — no SQL parser) that the user-supplied aggregate SQL string contains `time_bucket(` (case-insensitive). If not found, raise a `ValueError` with a clear message before sending the DDL to the DB. This is a lightweight guard, not a parser — it catches the most common mistake.

**Phase to address:**

Continuous aggregate phase. Include the heuristic check in the builder. Test with a `date_trunc`-based query to confirm the error fires before any DB round-trip.

---

### Pitfall 8: Continuous Aggregate Policy — start_offset Must Be Greater Than end_offset

**What goes wrong:**

`add_continuous_aggregate_policy` parameters are named in a way that suggests temporal ordering (start before end chronologically), but the semantics are relative to the present:

- `start_offset` = how far BACK in time the refresh window starts (e.g., `INTERVAL '3 days'` means "start from 3 days ago")
- `end_offset` = how close to the PRESENT the refresh window ends (e.g., `INTERVAL '1 hour'` means "stop 1 hour before now")

So `start_offset > end_offset` (as intervals) is correct: start_offset must be LARGER than end_offset. If `start_offset='1 hour'` and `end_offset='3 days'`, the window is reversed and TimescaleDB will raise an error or produce undefined behavior.

Also: `NULL` for `end_offset` means "up to the present" — this materializes the current (still-open) bucket, which is incorrect. The current bucket has incomplete data. Always use a non-NULL `end_offset` of at least the bucket interval (e.g., for hourly buckets, `end_offset >= INTERVAL '1 hour'`).

**Why it happens:**

The parameter names suggest a timeline from start to end. Users coming from standard window-function thinking set `start_offset` to a small interval (close to now) and `end_offset` to a large interval (further back), which reverses the window.

**How to avoid:**

1. Validate at call time (before sending SQL) that `start_offset > end_offset` when both are non-NULL. For interval comparison, parse with Python's `datetime.timedelta` if both are Python timedelta objects; if strings, at minimum document the constraint prominently and add a test with deliberately swapped values.
2. Validate that `end_offset` is not `None` in the default call path — require explicit opt-in for the open-ended (NULL) case.
3. Document with an example showing correct ordering in the method docstring.

**Phase to address:**

Continuous aggregate phase. Test: call `add_continuous_aggregate_policy` with swapped offsets; assert a `ValueError` fires.

---

### Pitfall 9: reorder_policy Conflicts With Compression and Requires a Non-Default Index

**What goes wrong:**

Two failure modes:

1. A reorder policy on a hypertable that also has a compression policy will fail (or silently skip) when the reorder job runs on already-compressed chunks. Compressed chunks are immutable; the reorder operation cannot modify them. Early TimescaleDB versions raised an explicit error; later versions (1.7.1+) silently skip compressed chunks. Either way, the reorder policy is effectively inert for any chunk that has been compressed.

2. `add_reorder_policy` requires an existing non-default index. If the named index does not exist, the call raises an error. The default btree index on the time column does NOT count as a valid reorder target if no additional index is specified. The index must be explicitly named in the call.

**Why it happens:**

The interaction between reorder and compression is non-obvious: both operate on chunks, but compression makes chunks immutable. The documentation states "it is not recommended to combine compression with reordering" but does not prevent it at the API level. The index requirement is also not immediately obvious — users assume the hypertable's existing indexes are discoverable.

**How to avoid:**

1. If the hypertable already has compression enabled (check `timescaledb_information.hypertables.compression_enabled`), raise a `TimescaleDBError` or at minimum a prominent warning before adding a reorder policy.
2. Validate that the named index exists before calling `add_reorder_policy` — query `pg_indexes` for the index name; raise `ValueError` if not found.
3. Document in the docstring: "You can have only one reorder policy per hypertable. Reorder policies cannot reorder already-compressed chunks — do not combine with compression."

**Phase to address:**

`reorder_policy` phase. Tests: verify index existence check fires; verify the policy row appears in `timescaledb_information.jobs`; do NOT test that the scheduler fired the job.

---

## Deterministic Testing Strategy for Scheduler-Driven Policies

Policies (`add_continuous_aggregate_policy`, `add_compression_policy`, `add_retention_policy`, `add_reorder_policy`) register background jobs that run on the TimescaleDB scheduler. The scheduler is a separate background process. **Never test that a policy has FIRED in CI.** Testing scheduler firing introduces slow, flaky, environment-dependent tests that fail whenever the background worker is suppressed (as it is in many CI environments and in TimescaleDB's own test suite via `_timescaledb_internal.stop_background_workers()`).

**The correct deterministic strategy is:**

1. **Test that the policy ROW exists** after calling the add-policy method. Query `timescaledb_information.jobs`:

   ```python
   rows = db.execute(
       "SELECT * FROM timescaledb_information.jobs "
       "WHERE proc_name = 'policy_refresh_continuous_aggregate'"
   )
   assert any(r["hypertable_name"] == "metrics" for r in rows)
   ```

2. **Test manual execution** by calling `CALL run_job(job_id)` on an autocommit connection. `run_job` is a stored procedure (use `CALL`, not `SELECT`). This verifies the policy configuration is valid without depending on the scheduler.

3. **Test idempotency**: calling add-policy twice with `if_not_exists=True` must not raise an error. Calling it without `if_not_exists=True` must raise a clear error.

4. **Test removal**: after calling remove-policy, assert the job row is gone from `timescaledb_information.jobs`.

5. **For refresh correctness tests**: call `refresh_continuous_aggregate` directly (not via policy) on an autocommit connection with known committed data. Do not depend on the scheduler at all for functional correctness tests.

This strategy gives full coverage of the policy API surface without any scheduler dependency. Every test is sub-second and deterministic.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Route continuous aggregate DDL through `self._db.execute()` | Simpler code, reuses existing path | Fails immediately with transaction-block error in any normal session | Never |
| Infer gapfill bounds from WHERE clause | Looks like the time_bucket API surface | Silent failure with bound params; confusing error message | Never — always require explicit start/end |
| Skip `dry_run` on drop_chunks | Less code | Users have no safe preview before irreversible data loss | Never on a published PyPI library |
| Skip empty-hypertable check on add_dimension | Lets the DB surface the error | DB error message is cryptic; user sees nothing about why it failed | Never — validate first and raise a clear pycopg error |
| Use `by_range`/`by_hash` unconditionally | Cleaner API | Breaks silently on TimescaleDB < 2.13 | Only if 2.13 is the documented hard minimum AND CI verifies the version |
| Test policy firing by waiting for scheduler | Tests actual scheduler behavior | Flaky, slow, fails on CI where background workers are suppressed | Never — test policy row existence and manual CALL run_job() only |
| Skip reorder-vs-compression guard | Less code | Policy silently does nothing on compressed chunks; maintenance debt | Never — raise an error or at minimum a warning |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| psycopg 3 + continuous aggregate DDL | Call `self._db.execute(create_sql)` — hits implicit transaction | Open `self._db.connect(autocommit=True)` per call; close after |
| psycopg 3 async + autocommit | Set `conn.autocommit = True` (read-only on async connections after construction) | Pass `autocommit=True` to `await AsyncConnection.connect()` or call `await conn.set_autocommit(True)` immediately |
| refresh after insert in test | Data inserted in implicit transaction not visible to refresh | Use autocommit inserts in test fixtures, or explicit COMMIT before refresh |
| drop_chunks + continuous aggregate | Drop raw data in a region the cagg has not yet materialized; aggregate returns NULL for that period | Refresh the cagg BEFORE dropping raw chunks; or use retention policy which coordinates automatically |
| reorder_policy + compression_policy on same hypertable | Reorder job silently skips compressed chunks; policy appears healthy but does nothing | Treat reorder and compression as mutually exclusive; detect at add-policy time |
| time_bucket_gapfill + locf/interpolate outside gapfill context | `locf()` / `interpolate()` used in a plain time_bucket query; DB raises error | Only expose `locf`/`interpolate` as optional parameters of the gapfill builder, not standalone |
| add_continuous_aggregate_policy NULL end_offset | Open-ended window materializes the current (incomplete) bucket; incorrect aggregates | Require a non-NULL end_offset at least equal to the bucket interval |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| refresh_continuous_aggregate with NULL window_end | Full historical re-materialization on every call; query hangs | Never pass NULL as window_end; validate at call time | Any table with more than a few days of data |
| refresh including the current (still-open) bucket | Most-recent bucket returns incorrect/stale aggregates after refresh | Set window_end to `now() - bucket_interval` to exclude the current incomplete bucket | Always — the current bucket is never complete |
| show_chunks without committing prior DDL | Returns empty or stale results in the same session | Ensure CREATE MATERIALIZED VIEW is committed before show_chunks runs | Any test that chains DDL + show_chunks in the same session |
| add_dimension on a large hypertable | DB rejects with "existing data" error | Validate empty first; document that add_dimension is only valid on empty hypertables | Any hypertable with data |

---

## Version Pitfalls: TimescaleDB 2.x API Changes

| Change | Before 2.13 | From 2.13 | Consequence for pycopg |
|--------|-------------|-----------|------------------------|
| `materialized_only` default | `false` (real-time on by default) | `true` (materialized-only by default) | Expose `materialized_only` param; default `True` to match current TSDB behavior; document the change prominently |
| `add_dimension` API | Positional: `add_dimension(table, col, number_partitions=>N)` | Generalized: `add_dimension(table, by_hash(col, N))` | Use positional form (backward-compatible); document 2.13 as minimum for by_range/by_hash |
| `create_hypertable` generalized | Positional form | `by_range(col, interval)` builder form | Same — existing positional form still works in 2.x; do not switch |

### Checking the Test Environment Version

Before building `add_dimension` or any 2.13+ API calls, verify the local test server version:

```python
row = db.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")[0]
# row["extversion"] should be "2.x.y"
```

Use the pre-2.13 positional API for `add_dimension` in v0.8.0. Mark `by_range`/`by_hash` as a future enhancement if the test server is pre-2.13.

---

## "Looks Done But Isn't" Checklist

- [ ] **create_continuous_aggregate:** Uses `connect(autocommit=True)` — verify by calling it after `db.execute("SELECT 1")` without error.
- [ ] **refresh_continuous_aggregate:** Uses `connect(autocommit=True)` — verify with committed data; confirm empty result is not returned because data was uncommitted.
- [ ] **time_bucket_gapfill builder:** `start` and `end` are required, embedded as function arguments — verify with a `datetime` bound param (not hardcoded) that no "could not infer" error fires.
- [ ] **drop_chunks:** Has `dry_run` parameter returning chunk list without deleting — verify no chunks removed on `dry_run=True`.
- [ ] **add_dimension:** Empty-hypertable check fires BEFORE the SQL is sent — verify with a populated hypertable that a pycopg error (not raw psycopg ProgrammingError) is raised.
- [ ] **Continuous aggregate SQL validation:** Heuristic `time_bucket` check fires for `date_trunc`-based query before any DB round-trip.
- [ ] **add_continuous_aggregate_policy:** start_offset > end_offset validation present; NULL end_offset gated.
- [ ] **reorder_policy:** Docstring notes mutual exclusivity with compression; optional: check compression_enabled before adding the policy.
- [ ] **All policy tests:** Use row-existence check + `CALL run_job()`, never sleep-and-wait for the scheduler.
- [ ] **async parity:** Every new method has an async counterpart registered in `ACCESSOR_PAIRS` — verify `test_accessor_parity` still passes after each new method.
- [ ] **Coverage ratchet:** All new autocommit branches are covered — autocommit paths are easy to miss in happy-path-only test suites.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Continuous aggregate DDL failed in transaction | LOW | No data loss (DDL was rolled back); fix to use autocommit connection; re-run |
| drop_chunks deleted wrong data | HIGH | No rollback; restore from backup; verify backup freshness before exposing drop_chunks to users |
| drop_chunks under a cagg left stale aggregates | MEDIUM | Refresh the cagg for the dropped region (aggregates will compute from remaining data; missing raw data = NULL/zero aggregates); document the dependency |
| add_dimension on non-empty hypertable | LOW | No data modified (DB rejected the call); empty the hypertable or create a new one; re-run |
| Gapfill "could not infer" from bound params | LOW | No data loss; rebuild the query with explicit start/end arguments in the function call |
| reorder_policy silently inactive on compressed chunks | MEDIUM | Remove the reorder policy; decompress relevant chunks if needed; decide: keep reorder OR keep compression, not both |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-----------------|--------------|
| CREATE MATERIALIZED VIEW in transaction block | Continuous aggregate phase (Phase 30) | Test: call after `db.execute("SELECT 1")` — no transaction-block error |
| refresh in transaction block | Continuous aggregate phase (Phase 30) | Test: refresh on autocommit path with committed data — no error, correct results |
| refresh of uncommitted data | Continuous aggregate phase (Phase 30) | Test: insert + immediate refresh without commit — empty result; insert + commit + refresh — non-empty |
| drop_chunks irreversible without dry_run | Chunk management phase | Test: dry_run=True returns chunk list without dropping; verify chunk count unchanged |
| gapfill bounds not inferred from %s params | time_bucket_gapfill phase | Test: run gapfill with `datetime.now()` bound param — no "could not infer" error |
| gapfill not bare in GROUP BY | time_bucket_gapfill phase | Test: inspect generated SQL — GROUP BY contains bare `time_bucket_gapfill(...)` |
| add_dimension on non-empty hypertable | add_dimension phase | Test: populated hypertable raises pycopg error before DB round-trip |
| add_dimension by_range/by_hash on < 2.13 | add_dimension phase | Verify TSDB version; use positional API by default in v0.8.0 |
| Policy firing tested via scheduler | All policy phases | All policy tests use row-existence check + `CALL run_job()` |
| reorder + compression conflict | reorder_policy phase | Docstring Notes + optional guard; test verifies error or warning fires |
| materialized_only default change in 2.13 | Continuous aggregate phase | Expose param, default True; test both modes |
| NULL window_end on refresh | Continuous aggregate phase | Validate: None end raises ValueError before SQL is sent |
| start_offset <= end_offset on cagg policy | Continuous aggregate phase | Test: swapped offsets raise ValueError |
| Continuous aggregate using date_trunc not time_bucket | Continuous aggregate phase | Heuristic check raises ValueError for date_trunc query |

---

## Sources

- [REFRESH cannot run inside a transaction block — timescale/timescaledb#1218](https://github.com/timescale/timescaledb/issues/1218)
- [CREATE MATERIALIZED VIEW WITH DATA cannot be executed within a pipeline — timescale/timescaledb#5377](https://github.com/timescale/timescaledb/issues/5377)
- [time_bucket_gapfill "invalid time_bucket_gapfill argument" via REST endpoint — timescale/timescaledb#4279](https://github.com/timescale/timescaledb/issues/4279)
- [time_bucket_gapfill cannot infer start and finish from subquery — timescale/timescaledb#7605](https://github.com/timescale/timescaledb/issues/7605)
- [time_bucket_gapfill fails to infer from NULL comparison — timescale/timescaledb#8525](https://github.com/timescale/timescaledb/issues/8525)
- [add_dimension() documentation (tigerdata.com)](https://www.tigerdata.com/docs/api/latest/hypertable/add_dimension)
- [add_reorder_policy() documentation (timescale.com)](https://docs.timescale.com/api/latest/hypertable/add_reorder_policy/)
- [refresh_continuous_aggregate() documentation (tigerdata.com)](https://www.tigerdata.com/docs/api/latest/continuous-aggregates/refresh_continuous_aggregate)
- [add_continuous_aggregate_policy() documentation (tigerdata.com)](https://www.tigerdata.com/docs/api/latest/continuous-aggregates/add_continuous_aggregate_policy)
- [Reorder job fails on compressed chunks — timescale/timescaledb#1810](https://github.com/timescale/timescaledb/issues/1810)
- [TimescaleDB 2.13.0 release notes — materialized_only default change](https://github.com/timescale/timescaledb/releases/tag/2.13.0)
- [drop_chunks documentation (tigerdata.com)](https://www.tigerdata.com/docs/api/latest/hypertable/drop_chunks)
- [psycopg 3 transaction management — autocommit](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Working with TimescaleDB in CI — autocommit for materialized views (wazeem.com)](https://wazeem.com/100/working-with-timescaledb-in-continuous-integration-automating-materialized-view-creation/)
- pycopg source: `/home/loc/workspace/pycopg/pycopg/etl.py` — autocommit isolation pattern for run-log writes (direct precedent for the cagg autocommit fix)
- pycopg source: `/home/loc/workspace/pycopg/pycopg/timescale.py` — existing TimescaleAccessor pattern; confirms `create_hypertable` uses `self._db.execute()` (safe for stored procedures, not safe for cagg DDL)

---
*Pitfalls research for: TimescaleDB 2.x advanced features in a psycopg 3 Python library wrapper (pycopg v0.8.0)*
*Researched: 2026-06-22*
