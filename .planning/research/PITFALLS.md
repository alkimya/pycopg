# Pitfalls Research: Python Database Library Consolidation

**Domain:** Python database abstraction libraries (PostgreSQL)
**Researched:** 2026-02-11
**Confidence:** MEDIUM-HIGH

## Critical Pitfalls

### Pitfall 1: Incomplete Async Parity Creates Silent Feature Gaps

**What goes wrong:**
AsyncDatabase is missing ~60% of Database methods (DataFrame ops, backup/restore, extensive admin). Users discover missing methods at runtime, not import time. No type hints or documentation warn about incomplete parity.

**Why it happens:**
- Async methods require different implementation (await, AsyncIterator, asynccontextmanager)
- DataFrame/SQLAlchemy integration is inherently synchronous (pandas/geopandas lack async support)
- Developers add features to sync first, defer async "for later"
- No automated parity checking enforces feature completeness

**How to avoid:**
1. **Document divergence explicitly** - README comparison matrix showing which methods exist in each
2. **Raise NotImplementedError with helpful messages** - Add stubs for missing methods that explain why unavailable
3. **Use shared base class or protocol** - Define interface, mark async-incompatible methods clearly
4. **Automated parity tests** - CI checks that every Database method either exists in AsyncDatabase or has documented exception

**Warning signs:**
- Users file issues like "AsyncDatabase doesn't have X method"
- Documentation doesn't mention sync vs async differences
- No tests comparing method lists between Database and AsyncDatabase
- Import errors discovered at runtime instead of type-check time

**Phase to address:**
Phase 1 (API Audit) - Document all gaps, add NotImplementedError stubs, create parity comparison matrix

---

### Pitfall 2: Connection Lifecycle Leaks in Session Mode Exception Paths

**What goes wrong:**
In session mode, if exception occurs during cleanup (`_session_conn.close()` line 352), connection stays alive but `_session_conn` eventually set to None. Connection leaks accumulate, exhausting database connection limits. Subsequent session attempts create new connections without closing orphaned ones.

**Why it happens:**
- Cleanup logic: `finally` block in lines 350-353 (database.py) sets `_session_conn = None` after close
- If `close()` raises exception, `_session_conn` may stay populated OR be set to None while connection remains open
- No timeout for idle session connections
- No protection against reentry beyond single RuntimeError check

**How to avoid:**
1. **Separate state tracking from resource cleanup** - Use try/finally to guarantee `_session_conn = None` even if close fails
2. **Track connection state separately** - Add `_session_active` flag independent of connection object
3. **Add connection timeout** - Set `idle_in_transaction_session_timeout` at connection level
4. **Catch and log cleanup errors** - Wrap `close()` in try/except, log but don't reraise during cleanup

**Warning signs:**
- PostgreSQL connection count grows over time without returning to baseline
- "Too many connections" errors after extended running
- Tests pass individually but fail when run in suite (connection exhaustion)
- `pg_stat_activity` shows IDLE connections from application long after requests complete

**Phase to address:**
Phase 2 (Connection Lifecycle) - Refactor session cleanup with guaranteed state reset, add connection timeout config

---

### Pitfall 3: Silent Migration File Skipping Masks Configuration Errors

**What goes wrong:**
`_get_migrations()` (line 152-153) catches MigrationError and continues silently. User creates `001-create_users.sql` (dash instead of underscore) but migration is skipped without warning. Database state diverges from expected without indication.

**Why it happens:**
- Defensive programming assumes some .sql files may not be migrations
- No distinction between "invalid migration file" vs "non-migration SQL file"
- Silent error handling prioritizes robustness over visibility
- No logging or validation feedback during migration discovery

**How to avoid:**
1. **Log skipped files at WARNING level** - `logger.warning(f"Skipping invalid migration file: {f.name}")`
2. **Validate migration directory on init** - Check all .sql files match pattern, fail fast on invalid names
3. **Strict mode option** - `strict=True` parameter makes invalid files raise error instead of skip
4. **Migration validation command** - `migrator.validate()` checks all files parseable before migrate

**Warning signs:**
- Migration count lower than number of .sql files in directory
- Migrations directory has files with similar but incorrect naming patterns
- Database schema missing expected tables/columns after migrate
- No log output during migration discovery phase

**Phase to address:**
Phase 3 (Migration Reliability) - Add logging to skipped files, create validation command, add strict mode

---

### Pitfall 4: Retry/Backoff Absence Amplifies Transient Network Errors

**What goes wrong:**
Single transient connection error (network hiccup, database restart, connection pool exhaustion on server) causes entire operation to fail. Users must implement retry logic in every callsite. Long-running batch operations fail 90% complete due to momentary network issue.

**Why it happens:**
- psycopg raises `OperationalError` for transient issues, but pycopg doesn't distinguish transient from permanent
- No retry policy at Database/AsyncDatabase level
- Operations assumed to be atomic and short-lived (not true for migrations, batch inserts, pg_dump)
- Connection errors treated same as SQL syntax errors

**How to avoid:**
1. **Categorize exceptions** - Distinguish transient (connection timeout, server shutdown) from permanent (auth failure, missing database)
2. **Exponential backoff decorator** - `@retry(on=[OperationalError], max_attempts=3, backoff=exponential)`
3. **Operation-level retry config** - `execute(..., retry_policy=RetryPolicy(max_attempts=3))`
4. **Circuit breaker for permanent failures** - Stop retrying after N consecutive failures of same type

**Warning signs:**
- Application logs show identical connection errors repeatedly in quick succession
- Operations fail with "connection reset by peer" or "server closed the connection unexpectedly"
- Batch operations fail near completion and must restart from beginning
- Users implementing their own retry wrappers around pycopg methods

**Phase to address:**
Phase 4 (Resilience) - Add retry policy to Config, implement backoff decorator, categorize exception types

---

### Pitfall 5: Real Database Testing Without Isolation Causes Cascade Failures

**What goes wrong:**
Tests run against real PostgreSQL (`pycopg_test` database) without proper isolation. One test creates table `users`, another test assumes it doesn't exist. Test execution order matters. Parallel test execution causes conflicts. CI randomly fails with "table already exists" or "table does not exist".

**Why it happens:**
- Shared database state across tests
- Cleanup (DROP/TRUNCATE) in teardown misses edge cases (transactions not committed, cascade dependencies)
- Tests not idempotent - assume clean slate but don't guarantee it
- No per-test schema isolation or database cloning

**How to avoid:**
1. **Per-test schema isolation** - Create `test_schema_{uuid}` for each test, drop in teardown
2. **Transaction rollback pattern** - Run each test in transaction, rollback at end (if DDL allows)
3. **Fixture-based database cloning** - Use template database, clone for each test/class
4. **Cleanup verification** - Assert no leftover objects before AND after each test
5. **Parallel execution safety** - Use pytest-xdist with per-worker database or schema

**Warning signs:**
- Tests pass individually (`pytest test_database.py::test_create_table`) but fail in suite
- Tests fail differently on different runs (flaky tests)
- CI failures don't reproduce locally
- Error messages like "relation already exists" or "relation does not exist"
- Tests fail when run in parallel but pass serially

**Phase to address:**
Phase 5 (Test Infrastructure) - Implement per-test schema isolation, add cleanup verification, enable parallel testing

---

### Pitfall 6: Breaking Changes Without Migration Path Strand Existing Users

**What goes wrong:**
v0.3.0 renames methods, changes signatures, removes deprecated APIs. Users upgrade via `pip install --upgrade pycopg` and application breaks at runtime. No warnings, no deprecation period, no migration guide. Production incidents spike after upgrade.

**Why it happens:**
- "Breaking changes allowed" interpreted as "no migration support needed"
- Assumption users read changelogs before upgrading
- No versioning strategy for API compatibility
- Type hints change but runtime errors only discovered in production

**How to avoid:**
1. **Deprecation warnings before removal** - Use `warnings.warn()` for 1-2 versions before breaking change
2. **Compatibility shims** - Keep old names as aliases with deprecation warnings
3. **Migration guide in CHANGELOG** - Before/after examples for every breaking change
4. **Semver enforcement** - 0.2.0 → 0.3.0 signals breaking changes, document in release notes
5. **Runtime version checks** - Allow users to pin API version: `Database(config, api_version="0.2")`

**Warning signs:**
- GitHub issues titled "Upgrade to 0.3.0 broke our application"
- Questions like "What happened to Database.from_dataframe()?"
- No deprecation warnings in 0.2.x versions
- CHANGELOG has "Breaking Changes" section but no migration examples
- Type hints incompatible between versions but no runtime errors until production

**Phase to address:**
Phase 6 (Breaking Changes Management) - Add deprecation warnings, create migration guide, implement compatibility shims where feasible

---

### Pitfall 7: Mixing Sync/Async in Event Loop Creates Deadlocks

**What goes wrong:**
User calls sync `Database.execute()` from within async function. Thread blocks waiting for connection, but connection callback needs event loop. Deadlock or `RuntimeError: cannot schedule new futures after shutdown`. Subtle - works in simple cases, fails under load.

**Why it happens:**
- Python asyncio doesn't prevent calling sync code from async context
- psycopg sync connection works "by accident" in simple async contexts
- Database and AsyncDatabase both exposed, users mix them
- No clear documentation about sync/async boundaries

**How to avoid:**
1. **Detect event loop and warn** - Check `asyncio.get_running_loop()` in Database methods, warn if exists
2. **Separate imports** - Put AsyncDatabase in `pycopg.async_api`, make mixing harder
3. **Document sync/async rules** - Clear warning in README: "Never call Database from async functions"
4. **Provide sync-from-async helper** - `await db.run_in_executor(sync_operation)` pattern

**Warning signs:**
- Users report hangs when using Database in async web frameworks (FastAPI, aiohttp)
- Errors like "RuntimeError: Task attached to a different loop"
- Code works with small datasets, hangs with large datasets (connection pool exhaustion)
- Deadlocks in CI but not local development

**Phase to address:**
Phase 2 (Connection Lifecycle) - Add event loop detection, document sync/async boundaries clearly

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip async parity for DataFrame methods | Ship AsyncDatabase faster, avoid complex sync/async bridge | Users blocked from async data pipelines, inconsistent API | Never - document as limitation instead |
| Hardcode batch size to 1000 | Simple default, no config complexity | Memory issues with wide rows, performance issues with narrow rows | MVP only - must add tuning docs |
| Silent SRID defaulting to 4326 | Spatial operations work without config | Subtle spatial analysis bugs, data misalignment | Never - require explicit SRID or error |
| No retry by default | Simple implementation, predictable behavior | Production instability from transient errors | Only if documented as "not production-ready" |
| Shared test database without isolation | Fast test setup, simple CI | Flaky tests, parallel execution impossible | Local dev only, never CI |
| Execute pg_dump via subprocess | Avoids reimplementing pg_dump protocol | Password in environment, process control complexity | Acceptable - standard PostgreSQL practice |
| Monolithic Database class (2299 lines) | Everything in one place, easy to find | Hard to test, hard to extend, navigation difficult | Refactor before adding more features |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| SQLAlchemy for DataFrames | Mixing psycopg connection with SQLAlchemy engine causes connection leaks | Use SQLAlchemy engine exclusively for DataFrame ops, psycopg for everything else |
| AsyncDatabase with FastAPI | Calling sync Database methods from FastAPI async endpoints causes blocking | Always use AsyncDatabase in async web frameworks |
| TimescaleDB operations | Calling compression/retention before creating hypertable gives cryptic errors | Check extension exists AND table is hypertable before all timescale ops |
| PostGIS SRID inference | Assuming gdf.crs.to_epsg() always works silently defaults to 4326 | Require explicit SRID parameter, error if CRS cannot be determined |
| Connection pooling | Using PooledDatabase with long-running operations exhausts pool | Set timeout, use session mode, or increase pool size for batch operations |
| Migration rollback | Assuming DOWN section exists causes error on rollback attempt | Check for DOWN section before allowing rollback, document as optional |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| fetchall() on large result sets | OOM errors, application freeze | Use cursor iteration or streaming API | >100k rows with wide tables |
| Connection per operation (no pooling) | High latency, connection exhaustion | Use PooledDatabase or session mode | >10 concurrent requests |
| No statement_timeout | Long-running queries never timeout, block connections | Set statement_timeout in Config | First unbounded query (SELECT * JOIN) |
| insert_batch with huge batches | Memory spike, transaction timeout | Chunk into smaller batches, tune batch_size | >10k rows or wide rows (>100 columns) |
| Sync Database in async framework | Thread pool exhaustion, blocking event loop | Use AsyncDatabase exclusively | First high-concurrency load test |
| Missing indexes on migration tracking | Migration status queries slow with many migrations | Index on schema_migrations(version) | >1000 migrations |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging connection strings with passwords | Credentials in log files, error tracking services | Mask passwords in Config.url/dsn, warn in docstrings |
| SQL identifier validation bypass | SQL injection via crafted schema/table names | Never allow user input directly as identifiers without validation |
| PGPASSWORD in subprocess environment | Password visible in process environment during pg_dump | Document as unavoidable PostgreSQL limitation, consider .pgpass |
| No SSL/TLS connection enforcement | Man-in-the-middle attacks, credential interception | Add sslmode parameter to Config, default to 'require' |
| Overly permissive role grants | Application users with superuser or DDL permissions | Document principle of least privilege, provide grant templates |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| RuntimeError on missing async method | Users discover incompleteness at runtime | Provide NotImplementedError with helpful message linking docs |
| Silent migration file skipping | Database state diverges from expected | Log skipped files, provide validation command |
| No feedback during long operations | Users think pg_dump/migrate is hung | Add progress callbacks or verbose mode |
| Cryptic psycopg errors propagated | "server closed connection unexpectedly" without context | Catch and wrap with operation context ("Failed during migration 005_...") |
| No connection string validation | Errors on first execute instead of at init | Validate config on Database creation, test connection if requested |

## "Looks Done But Isn't" Checklist

- [ ] **Async parity:** Verify all Database methods either exist in AsyncDatabase OR explicitly documented as unavailable
- [ ] **Connection cleanup:** Check session mode cleans up connections even if close() raises exception
- [ ] **Migration validation:** Confirm all .sql files in migrations/ are valid migrations (no silent skips)
- [ ] **Test isolation:** Verify each test can run independently and in parallel without conflicts
- [ ] **Error categorization:** Confirm transient errors (connection reset) distinguished from permanent (auth failure)
- [ ] **Retry logic:** Check retry happens for appropriate errors, doesn't retry on SQL syntax errors
- [ ] **Breaking changes:** Verify deprecation warnings exist in 0.2.x for features removed in 0.3.0
- [ ] **SRID handling:** Confirm spatial operations require explicit SRID, never silently default
- [ ] **Pool exhaustion:** Check PooledDatabase handles timeout gracefully, doesn't deadlock
- [ ] **Transaction isolation:** Verify migrations run in transaction, rollback on failure (or document as not transactional)

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Connection leak from session mode | LOW | Add connection timeout config, restart application |
| Silent migration skipping | HIGH | Write manual migration to reconcile DB state, fix file naming |
| Async/sync mixing deadlock | MEDIUM | Refactor to use AsyncDatabase, add event loop detection |
| Test database pollution | LOW | Drop and recreate test database, improve cleanup |
| Breaking change without migration | MEDIUM | Release patch with compatibility shim, document migration path |
| SRID silent defaulting | HIGH | Audit all spatial data, re-import with correct SRID |
| Missing retry causing production failures | MEDIUM | Add retry at application level temporarily, upgrade to version with retry |
| Pool exhaustion | LOW | Increase pool size via resize(), add connection timeout |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Incomplete async parity | Phase 1 (API Audit) | All Database methods have AsyncDatabase equivalent OR documented exception |
| Session connection leaks | Phase 2 (Connection Lifecycle) | Stress test session mode with exception injection, no leaked connections |
| Silent migration skipping | Phase 3 (Migration Reliability) | Invalid migration filenames logged at WARNING level |
| No retry/backoff | Phase 4 (Resilience) | Transient connection errors retry 3x with exponential backoff |
| Test isolation failures | Phase 5 (Test Infrastructure) | Tests pass in parallel with pytest-xdist |
| Breaking changes without migration | Phase 6 (Breaking Changes Management) | All breaking changes have deprecation warnings in 0.2.x |
| Sync/async mixing | Phase 2 (Connection Lifecycle) | Database methods warn if called from async context |
| SRID silent defaulting | Phase 4 (Resilience) | from_geodataframe requires srid param or raises error |

## Domain-Specific Warnings

### PostgreSQL-Specific

**DDL requires autocommit:**
Many Database methods (`create_database`, `create_extension`, `vacuum`) require `autocommit=True`. If called within transaction, PostgreSQL raises cryptic "cannot run inside a transaction block" error.

**Prevention:** Document autocommit requirement in docstrings, auto-enable for known DDL operations

---

**pg_dump blocking behavior:**
`pg_dump` subprocess blocks Python process. Async users expect non-blocking. No async version available because subprocess I/O.

**Prevention:** Document as sync-only operation, consider ThreadPoolExecutor wrapper for AsyncDatabase

---

**TimescaleDB hypertable restrictions:**
Once table converted to hypertable, cannot drop columns or alter primary key. Silent failure if attempted.

**Prevention:** Document restrictions in create_hypertable docstring, check for hypertable before destructive operations

---

### Python Async-Specific

**Context manager cleanup timing:**
`async with db.transaction()` commits/rollbacks on exit, but if exception during cleanup, may leak transaction state.

**Prevention:** psycopg handles this correctly, but document that user code in finally block sees committed/rolled-back state

---

**Event loop closure:**
If AsyncDatabase instance outlives event loop, connection cleanup fails. Common in pytest with async fixtures.

**Prevention:** Always use `async with AsyncDatabase()` pattern or call `await db.close()` explicitly

---

**Asyncio subprocess limitations:**
`asyncio.create_subprocess_exec` doesn't support all subprocess features (pg_dump piping). Forces sync subprocess usage.

**Prevention:** Document pg_dump/pg_restore as sync-only even in AsyncDatabase

---

### Testing-Specific

**DDL not transactional:**
CREATE/DROP TABLE cannot rollback. Per-test transaction isolation doesn't work for DDL-heavy tests.

**Prevention:** Use per-test schema instead of per-test transaction for tests with DDL

---

**PostgreSQL template database corruption:**
If test crashes during write to template, all future clones corrupted. Rare but catastrophic.

**Prevention:** Never write to template database, only clone from it. Use template0 as base if needed

---

**Connection pool interference:**
PooledDatabase maintains background workers. If not closed in test teardown, workers interfere with next test.

**Prevention:** Always call `db.close()` or use context manager in pooling tests

---

## Sources

**Confidence: MEDIUM-HIGH**

- **HIGH confidence sources:**
  - pycopg codebase analysis (database.py, async_database.py, migrations.py, pool.py)
  - .planning/codebase/CONCERNS.md (known bugs and tech debt)
  - Python training data on asyncio patterns and database library patterns

- **MEDIUM confidence sources (training data, needs verification):**
  - psycopg3 async behavior and connection pooling patterns
  - Common Python library migration/versioning practices
  - PostgreSQL testing best practices

- **Areas needing verification:**
  - Specific psycopg3 retry/backoff recommendations (not found in codebase)
  - Latest PostgreSQL DDL transaction behavior changes
  - Modern pytest-asyncio fixture patterns

**Recommendations:**
- Verify retry/backoff patterns against psycopg3 official docs when available
- Validate test isolation strategies against actual CI environment
- Confirm breaking change migration practices against PyPI ecosystem norms

---

*Pitfalls research for: Python Database Library Consolidation (pycopg v0.3.0)*
*Researched: 2026-02-11*
*Note: WebSearch/WebFetch unavailable during research. Findings based on codebase analysis, known issues documentation, and training data. Mark as needing validation for production use.*
