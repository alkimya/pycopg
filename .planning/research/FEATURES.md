# Feature Landscape

**Domain:** Python database library for PostgreSQL
**Researched:** 2026-02-11
**Confidence:** MEDIUM

## Executive Summary

Based on analysis of pycopg v0.2.0, CONCERNS.md, and patterns from mature Python database libraries (SQLAlchemy, asyncpg, psycopg3, encode/databases), this research identifies features expected in a production-ready database library consolidation release.

**Key insight:** pycopg v0.3.0 consolidation must address the 60% async/sync parity gap while adding resilience features that users expect from any production database library.

**Confidence note:** Research based on codebase analysis and training data on database library patterns (SQLAlchemy ~2.0, asyncpg ~0.29, psycopg3 ~3.1). WebSearch/WebFetch unavailable for 2026 verification, so current library versions and recent patterns may differ.

---

## Table Stakes

Features users expect in any mature database library. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Full async/sync parity** | Users choose async OR sync based on app architecture, expect same API | HIGH | Currently 40% parity - async missing DataFrame, backup, admin methods (CONCERNS.md) |
| **Consistent error handling** | All failures raise typed exceptions, not generic errors | MEDIUM | Currently missing: connection retry on transient errors, better migration error context |
| **Transaction management** | Explicit transactions with rollback, savepoints, isolation levels | MEDIUM | Exists but incomplete: no savepoint support, no isolation level control |
| **Connection pooling** | Production apps need pools for concurrency | LOW | Exists (psycopg_pool) but lacks adaptive sizing, health checks |
| **Query timeout support** | Prevent runaway queries from hanging indefinitely | MEDIUM | Missing: no statement_timeout exposed (CONCERNS.md line 75) |
| **Prepared statements** | Reuse query plans for repeated queries | LOW | psycopg3 handles internally, but no explicit API for parameterized queries reuse |
| **Named parameters** | Dict-based params more pythonic than positional %s | MEDIUM | Missing (CONCERNS.md line 171) - only %s positional params supported |
| **Comprehensive logging** | Debug connection lifecycle, query execution, errors | MEDIUM | Missing: no structured logging, no query logging |
| **Graceful degradation** | Handle missing extensions (PostGIS, TimescaleDB) without crashes | LOW | Partial: some methods check extensions, others assume (CONCERNS.md line 109) |
| **Connection health checks** | Detect stale/broken connections before use | MEDIUM | Missing: pool doesn't validate connections before checkout |
| **Clear documentation** | Every method documented with examples, error cases | MEDIUM | Exists but needs updating for v0.3.0 changes |

---

## Differentiators

Features that set pycopg apart. Not required, but valuable for positioning.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **DataFrame-first API** | Direct pandas/geopandas integration without SQLAlchemy boilerplate | LOW | Unique strength - keep and expand (currently sync-only) |
| **TimescaleDB first-class** | Hypertable, compression, retention as native methods | LOW | Exists, needs pre-condition checks (CONCERNS.md line 109) |
| **PostGIS first-class** | GeoDataFrame round-trip without geometry type guessing | MEDIUM | Exists but fragile SRID handling (CONCERNS.md line 117) |
| **Migration system** | Built-in, zero-config migrations (no Alembic/Flask-Migrate) | MEDIUM | Exists but needs rollback robustness, gap detection (CONCERNS.md line 87) |
| **High-level DDL helpers** | `add_column()`, `add_index()` without SQL strings | LOW | Exists, expand with computed columns, partitioning |
| **COPY protocol helpers** | Optimized bulk insert (10-100x faster than INSERT) | LOW | Exists (`copy_insert`), add streaming for large datasets |
| **Session mode** | Connection reuse for batch operations without pool overhead | LOW | Exists but fragile cleanup (CONCERNS.md line 100) |
| **pg_dump/restore wrappers** | Backup without shell scripts | LOW | Exists (sync only), add to async |
| **Retry policies** | Exponential backoff for transient errors (connection, serialization) | MEDIUM | Missing - critical for production (CONCERNS.md line 161) |
| **Query result streaming** | Handle 100M+ row SELECTs without OOM | MEDIUM | Async has `stream()`, sync missing (CONCERNS.md line 137) |

---

## Anti-Features

Features to explicitly NOT build in v0.3.0 consolidation.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **ORM/model layer** | Duplicates SQLAlchemy, heavy maintenance burden | Document integration with SQLAlchemy/Pydantic for models |
| **Query builder (fluent API)** | Maintenance nightmare, never as good as SQLAlchemy Core | Use raw SQL with named params; document SQLAlchemy integration |
| **Schema diff/auto-migration** | Complex, error-prone (Alembic took years to stabilize) | Keep simple numbered migrations, document manual schema changes |
| **Multi-database support** | pycopg is PostgreSQL-specific, abstract layer dilutes features | Document as PostgreSQL-only, refer to encode/databases for multi-DB |
| **GraphQL/REST auto-generation** | Out of scope, belongs in application layer | Document as data layer only |
| **Query result caching** | Application concern, adds complexity (invalidation, memory) | Document integration with Redis/Memcached (CONCERNS.md line 166) |
| **Connection encryption config** | psycopg3 handles via connection params | Document sslmode usage in Config, don't wrap |
| **Distributed transactions** | Rare need, high complexity (2PC coordinator) | Document as not supported, use application-level sagas |

---

## Feature Dependencies

```
Core Resilience
├── Retry Policy (transient errors)
│   └── Typed Exceptions (distinguish transient vs permanent)
│       └── Comprehensive Logging (debug retry attempts)
├── Connection Health Checks
│   └── Query Timeout (detect hung connections)
│
Async Parity
├── Async DataFrame Methods
│   └── Async SQLAlchemy Engine (already exists)
├── Async Backup Methods
│   └── Async subprocess handling (asyncio.create_subprocess_exec)
├── Async Admin Methods (roles, grants)
│   └── Async connection (already exists)
│
Transaction Improvements
├── Savepoints
│   └── Transaction Context (already exists)
├── Isolation Levels
│   └── Connection Config (already exists)
│
Query API
├── Named Parameters
│   └── Parameter Conversion (dict → positional)
├── Result Streaming (sync)
│   └── Cursor Iteration (server-side cursor)
│
Migration Robustness
├── Rollback Gap Detection
│   └── Migration File Validation
├── Partial Rollback Recovery
│   └── Transaction per Migration (already exists)
```

### Dependency Notes

- **Retry Policy requires Typed Exceptions:** Cannot retry without distinguishing transient (connection timeout) from permanent (syntax error) failures
- **Async Parity requires Async Subprocess:** `pg_dump`/`pg_restore` need `asyncio.create_subprocess_exec` to avoid blocking
- **Named Parameters blocks nothing:** Can add independently, converts to positional internally
- **Health Checks enhance Retry:** Proactive detection reduces retry attempts
- **Streaming conflicts with Batch Insert:** Cannot stream and batch in same query, document as separate use cases

---

## v0.3.0 Consolidation Scope

### Must Have (Table Stakes for Release)

- [ ] **Full async/sync parity** — Async DataFrame, backup, admin methods (addresses CONCERNS.md gap)
- [ ] **Retry policy with backoff** — Transient error handling (connection, serialization failures)
- [ ] **Query timeout support** — `statement_timeout` in Config, per-query override
- [ ] **Comprehensive logging** — Structured logs for connections, queries, errors (use Python logging)
- [ ] **Session mode robustness** — Fix cleanup leak (CONCERNS.md line 100), add timeout
- [ ] **Migration gap detection** — Validate sequence, detect deleted files, fail fast
- [ ] **Extension pre-checks** — All PostGIS/TimescaleDB methods validate extension exists
- [ ] **Named parameter support** — `:name` syntax converts to `%s` internally
- [ ] **Connection health checks** — Validate pool connections before checkout
- [ ] **Error context improvements** — Migration errors include file path, line number

### Should Have (Improve Production Readiness)

- [ ] **Transaction isolation levels** — SET TRANSACTION ISOLATION LEVEL via context manager
- [ ] **Savepoint support** — Nested transactions with SAVEPOINT/ROLLBACK TO
- [ ] **Result streaming (sync)** — Server-side cursors for large SELECTs
- [ ] **SRID validation** — Error on unknown CRS, never silent default (CONCERNS.md line 117)
- [ ] **Pool adaptive sizing** — Dynamic resize based on queue depth
- [ ] **Computed column helpers** — GENERATED ALWAYS AS for stored expressions
- [ ] **Connection lifecycle hooks** — on_connect, on_checkout callbacks for setup
- [ ] **Query execution hooks** — before_execute, after_execute for instrumentation
- [ ] **Batch size tuning** — Auto-detect optimal batch size based on row size

### Nice to Have (Future v0.4.0+)

- [ ] **Query builder (minimal)** — Only for WHERE clause construction, not full SQL
- [ ] **Partitioning helpers** — Create/manage table partitions (RANGE, LIST)
- [ ] **Replication slot helpers** — Logical replication setup (advanced use case)
- [ ] **NOTIFY/LISTEN helpers (sync)** — Pub/sub (async already has)
- [ ] **Advisory lock helpers** — Distributed locking (pg_advisory_lock)
- [ ] **CSV streaming import** — Chunked COPY FROM for multi-GB files (CONCERNS.md line 132)
- [ ] **Connection pool monitoring** — Metrics export (Prometheus, StatsD)
- [ ] **Slow query logging** — Auto-log queries exceeding threshold

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | v0.3.0 |
|---------|------------|---------------------|----------|--------|
| Async/sync parity | HIGH | HIGH | P1 | Yes |
| Retry policy | HIGH | MEDIUM | P1 | Yes |
| Query timeout | HIGH | LOW | P1 | Yes |
| Named parameters | HIGH | MEDIUM | P1 | Yes |
| Health checks | MEDIUM | MEDIUM | P1 | Yes |
| Migration robustness | HIGH | LOW | P1 | Yes |
| Extension pre-checks | MEDIUM | LOW | P1 | Yes |
| Logging | MEDIUM | MEDIUM | P1 | Yes |
| Session mode fixes | HIGH | LOW | P1 | Yes |
| Error context | MEDIUM | LOW | P1 | Yes |
| Isolation levels | MEDIUM | LOW | P2 | Maybe |
| Savepoints | MEDIUM | MEDIUM | P2 | Maybe |
| Sync streaming | MEDIUM | MEDIUM | P2 | Maybe |
| SRID validation | LOW | LOW | P2 | Yes |
| Pool adaptive sizing | LOW | HIGH | P2 | No |
| Computed columns | LOW | LOW | P2 | Maybe |
| Lifecycle hooks | LOW | MEDIUM | P3 | No |
| Execution hooks | LOW | MEDIUM | P3 | No |
| Partitioning | LOW | HIGH | P3 | No |
| Replication slots | LOW | HIGH | P3 | No |
| Advisory locks | LOW | LOW | P3 | No |

**Priority key:**
- P1: Must have for v0.3.0 consolidation (fixes tech debt + resilience)
- P2: Should have if time allows (production readiness)
- P3: Nice to have, defer to v0.4.0+ (advanced features)

---

## Competitor Feature Analysis

| Feature | SQLAlchemy Core | asyncpg | psycopg3 | encode/databases | pycopg v0.2.0 | pycopg v0.3.0 Target |
|---------|----------------|---------|----------|------------------|---------------|---------------------|
| **Connection pooling** | Yes (QueuePool) | Yes (pool) | Yes (pool) | Yes | Yes (psycopg_pool) | Keep |
| **Async support** | Yes (async engine) | Native | Yes (AsyncConnection) | Native | Partial (40%) | Full parity |
| **Retry on transient errors** | Yes (configurable) | No (manual) | No (manual) | No | No | Add |
| **Named parameters** | Yes (:name) | Yes ($1) | No (%s only) | Yes (:name) | No | Add |
| **Query timeout** | Yes (per-query) | Yes (timeout) | Yes (options) | Via driver | No | Add |
| **Transaction isolation** | Yes (isolation_level) | Yes | Yes | Via driver | No | Add |
| **Savepoints** | Yes | Yes | Yes | Via driver | No | Add |
| **Result streaming** | Yes (yield_per) | Yes (async iter) | Yes (cursor) | Via driver | Async only | Add sync |
| **Health checks** | Yes (pre_ping) | No | No | No | No | Add |
| **Logging/instrumentation** | Yes (events) | No (manual) | No (manual) | No | No | Add |
| **DataFrame integration** | Yes (pandas) | No | No | No | Yes (pandas/geo) | Unique strength |
| **PostGIS native** | Via GeoAlchemy2 | No | No | No | Yes | Unique strength |
| **TimescaleDB native** | No | No | No | No | Yes | Unique strength |
| **Migrations built-in** | No (Alembic) | No | No | No | Yes | Unique strength |
| **Backup/restore** | No | No | No | No | Yes (sync only) | Add async |

**Key insights:**
- **SQLAlchemy Core:** Comprehensive feature set but heavy. pycopg should match resilience features (retry, timeout, health checks) without ORM complexity.
- **asyncpg:** Fast but low-level. pycopg's high-level API (DataFrame, PostGIS) is differentiator.
- **psycopg3:** pycopg's foundation. Expose features like isolation levels, savepoints that psycopg3 supports.
- **encode/databases:** Simple async wrapper. pycopg should exceed with domain-specific features (PostGIS, TimescaleDB).

---

## Pattern Expectations (from ecosystem)

### Error Handling Pattern
```python
# Expected: Typed exceptions with context
try:
    db.execute("SELECT * FROM users")
except pycopg.ConnectionTimeout as e:
    # Retry logic
    pass
except pycopg.QueryTimeout as e:
    # Log slow query
    pass
except pycopg.IntegrityError as e:
    # Handle constraint violation
    pass
```

### Retry Pattern
```python
# Expected: Automatic retry with backoff
db = Database.from_env(
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff=ExponentialBackoff(base=1.0, max=10.0),
        retryable_errors=[ConnectionTimeout, SerializationFailure]
    )
)

# Or manual control
@db.with_retry(max_attempts=5)
def critical_operation():
    db.execute("UPDATE accounts SET balance = balance - 100")
```

### Named Parameters Pattern
```python
# Expected: Dict params like SQLAlchemy
users = db.execute(
    "SELECT * FROM users WHERE age > :min_age AND country = :country",
    {"min_age": 25, "country": "US"}
)

# Not just positional
users = db.execute(
    "SELECT * FROM users WHERE age > %s AND country = %s",
    [25, "US"]  # Less clear what params mean
)
```

### Transaction Isolation Pattern
```python
# Expected: Isolation level control
with db.transaction(isolation="SERIALIZABLE") as txn:
    # Read and write with serializable isolation
    balance = txn.fetch_val("SELECT balance FROM accounts WHERE id = %s", [1])
    txn.execute("UPDATE accounts SET balance = %s WHERE id = %s", [balance - 100, 1])
```

### Health Check Pattern
```python
# Expected: Pool validates connections
db = PooledDatabase.from_env(
    health_check=True,  # Validate before checkout
    health_check_interval=60  # Revalidate every 60s
)

# Or manual
if db.check_health():
    proceed()
```

### Streaming Pattern
```python
# Expected: Iterate large results without loading all
for batch in db.stream("SELECT * FROM huge_table", batch_size=1000):
    process(batch)

# Not: Load all into memory
rows = db.execute("SELECT * FROM huge_table")  # OOM on 100M rows
```

---

## Sources

**Analysis based on:**
- pycopg v0.2.0 codebase (database.py, async_database.py, pool.py, migrations.py, exceptions.py)
- .planning/codebase/CONCERNS.md (tech debt, bugs, missing features identified 2026-02-11)
- README.md (current feature set, API surface)

**Confidence level: MEDIUM**
- Pattern expectations based on training data for SQLAlchemy ~2.0, asyncpg ~0.29, psycopg3 ~3.1, encode/databases ~0.8
- WebSearch/WebFetch unavailable for verification against 2026 current practices
- Competitor feature comparison based on training data (pre-2025), may not reflect latest versions
- Resilience patterns (retry, timeout, health checks) are industry standard across database libraries

**Validation recommended:**
- Verify current versions of SQLAlchemy, asyncpg, encode/databases for feature parity
- Check psycopg3 documentation for features not yet exposed in pycopg
- Review 2026 best practices for async database libraries (connection pooling, error handling)

---

*Feature landscape for: pycopg v0.3.0 consolidation*
*Researched: 2026-02-11*
*Confidence: MEDIUM (codebase analysis + training data patterns, no 2026 external verification)*
