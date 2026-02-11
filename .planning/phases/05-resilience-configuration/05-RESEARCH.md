# Phase 5: Resilience & Configuration - Research

**Researched:** 2026-02-11
**Domain:** Python retry/backoff patterns, PostgreSQL connection resilience, statement timeout configuration
**Confidence:** HIGH

## Summary

Phase 5 adds production-grade error handling with retry/backoff for transient connection errors and expands configuration capabilities for operational safety (statement_timeout, configurable batch sizes). This phase introduces four capabilities: (1) retry policy with exponential backoff for transient psycopg3 connection errors (OperationalError, ConnectionFailure, etc.), (2) statement_timeout configuration in Config to prevent runaway queries, (3) configurable insert batch size (default remains 1000), and (4) enhanced pool configuration for reconnection behavior.

The primary technical challenge is choosing between manual retry implementation and using a battle-tested library (tenacity). Tenacity is the Python standard for retry logic in 2026, with native async/await support, exponential backoff with jitter, and decorator-based syntax. It reduces retry failure rates by up to 97% while preventing thundering herd problems in distributed systems. Statement_timeout can be configured via PostgreSQL connection options parameter (`-c statement_timeout=5000`), which psycopg3 supports through the options kwarg. Batch size is already parameterized in insert_batch() methods (default 1000) but not exposed in Config for global defaults.

**Primary recommendation:** Use tenacity library for retry/backoff (add as core dependency). Add statement_timeout and default_batch_size to Config. Expose reconnect_timeout and check callback in PooledDatabase/AsyncPooledDatabase constructors. Apply retry decorator to connection establishment, not individual queries (queries timeout via statement_timeout).

## Standard Stack

### Core Dependencies
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.1.0+ | PostgreSQL driver | Exception hierarchy for transient errors (OperationalError, ConnectionFailure) |
| psycopg_pool | 3.2.0+ | Connection pooling | Built-in reconnect with exponential backoff, health checks |
| tenacity | 9.0.0+ | Retry/backoff library | Industry standard for Python retry logic, async support, 97% failure reduction |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| backoff | 2.2.0+ | Alternative retry library | Simpler API, but less async support than tenacity |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tenacity | Manual retry implementation | Manual retry is error-prone (missing edge cases like jitter, max delay bounds) |
| tenacity | backoff library | Backoff has simpler syntax but weaker async support and less production validation |
| Connection retry | Query retry | Query retry causes data duplication risks; connection retry is safe |

**Installation:**
```bash
pip install tenacity>=9.0.0
```

## Architecture Patterns

### Pattern 1: Retry on Connection Establishment Only
**What:** Apply retry decorator to Database/AsyncDatabase connection methods, not individual queries
**When to use:** Database.__init__, AsyncDatabase.__init__, connect() context managers
**Why:** Queries already protected by statement_timeout. Retrying queries risks duplicate inserts/updates. Connection retry is idempotent and safe.

**Example:**
```python
# Source: tenacity documentation + psycopg3 exception hierarchy
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from psycopg import OperationalError

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(OperationalError),
    reraise=True
)
async def _connect_with_retry(self, autocommit: bool = False):
    """Establish connection with retry for transient failures."""
    return await psycopg.AsyncConnection.connect(
        **self.config.connect_params(),
        autocommit=autocommit
    )
```

### Pattern 2: Statement Timeout via Connection Options
**What:** Configure statement_timeout through PostgreSQL options parameter in connection
**When to use:** Always - apply globally through Config, passed to all connections
**Why:** PostgreSQL's native query timeout mechanism. Cannot set at command line, must set via connection options.

**Example:**
```python
# Source: PostgreSQL documentation, psycopg3 connection options
@dataclass
class Config:
    host: str = "localhost"
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: str = ""
    sslmode: Optional[str] = None
    statement_timeout: Optional[int] = None  # NEW: milliseconds, None = disabled
    options: dict = field(default_factory=dict)

    def connect_params(self) -> dict:
        """Get connection parameters for psycopg.connect()."""
        params = {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
        }
        if self.password:
            params["password"] = self.password
        if self.sslmode:
            params["sslmode"] = self.sslmode

        # Build options string for PostgreSQL parameters
        options_list = []
        if self.statement_timeout is not None:
            options_list.append(f"-c statement_timeout={self.statement_timeout}")
        for key, value in self.options.items():
            options_list.append(f"-c {key}={value}")
        if options_list:
            params["options"] = " ".join(options_list)

        return params
```

### Pattern 3: Configurable Batch Size with Sensible Default
**What:** Add default_batch_size to Config, use as default in insert_batch() methods
**When to use:** Large bulk inserts where 1000 rows/batch may be too small or too large
**Why:** Batch size affects memory usage and performance. Different deployments need different defaults.

**Example:**
```python
# Source: Current pycopg implementation (database.py:427, async_database.py:291)
@dataclass
class Config:
    # ... existing fields ...
    default_batch_size: int = 1000  # NEW: default for insert_batch operations

# In Database/AsyncDatabase
async def insert_batch(
    self,
    table: str,
    rows: list[dict],
    schema: str = "public",
    on_conflict: Optional[str] = None,
    batch_size: Optional[int] = None,  # CHANGED: None means use config default
) -> int:
    if batch_size is None:
        batch_size = self.config.default_batch_size
    # ... rest of implementation unchanged ...
```

### Pattern 4: Pool Reconnection Configuration
**What:** Expose reconnect_timeout, reconnect_failed callback, and check callback in PooledDatabase
**When to use:** Production deployments with HA PostgreSQL clusters, frequent failovers
**Why:** Default 5-minute reconnect_timeout too long for many use cases. Applications need custom alerts on reconnect failures.

**Example:**
```python
# Source: psycopg3 pool documentation
from psycopg_pool import ConnectionPool

class PooledDatabase:
    def __init__(
        self,
        config: Config,
        min_size: int = 2,
        max_size: int = 10,
        max_idle: float = 300.0,
        max_lifetime: float = 3600.0,
        timeout: float = 30.0,
        num_workers: int = 3,
        reconnect_timeout: float = 300.0,  # NEW: 5 minutes default
        reconnect_failed: Optional[Callable] = None,  # NEW: alert callback
        check: Optional[Callable] = None,  # NEW: health check callback
    ):
        self.config = config
        self._pool = ConnectionPool(
            conninfo=config.dsn,
            min_size=min_size,
            max_size=max_size,
            max_idle=max_idle,
            max_lifetime=max_lifetime,
            timeout=timeout,
            num_workers=num_workers,
            reconnect_timeout=reconnect_timeout,
            reconnect_failed=reconnect_failed,
            check=check or ConnectionPool.check_connection,  # Use static method by default
            kwargs={"row_factory": dict_row},
        )
```

### Anti-Patterns to Avoid
- **Retrying queries instead of connections:** Queries can have side effects (inserts/updates). Only retry connection establishment.
- **No jitter in backoff:** Multiple processes retrying simultaneously cause thundering herd. Use wait_exponential with jitter.
- **Global retry wrapper:** Don't wrap entire Database class. Apply retry selectively to connection methods only.
- **Ignoring transient vs permanent errors:** Don't retry InvalidIdentifier, ProgrammingError, etc. Only retry OperationalError and connection-specific exceptions.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exponential backoff | Custom retry loop with sleep | tenacity library | Manual retry misses edge cases: jitter, max bounds, exception filtering, async support |
| Connection health checks | Custom ping queries | psycopg_pool check callback | Pool already implements health checking with empty query (more efficient than SELECT 1) |
| Timeout management | Manual thread.Timer or signal.alarm | PostgreSQL statement_timeout | Database-native timeout is precise, portable, and doesn't require threading |
| Transient error detection | Manual exception type checking | retry_if_exception_type | Psycopg3 has 15+ connection-related exceptions; manual checking misses cases |

**Key insight:** Retry logic is deceptively complex. Exponential backoff sounds simple but getting it right (bounded delays, jitter, exception filtering, async compatibility, max attempts vs max time) requires 100+ lines of correct code. Tenacity has 8+ years of production validation and handles all edge cases.

## Common Pitfalls

### Pitfall 1: Retrying Non-Idempotent Operations
**What goes wrong:** Applying retry decorator to insert_batch() or execute() methods causes duplicate data on transient failures
**Why it happens:** Query executes on server, network fails before response, client retries, data inserted twice
**How to avoid:** Only retry connection establishment. Queries protected by statement_timeout (fail fast, don't retry).
**Warning signs:** Duplicate primary key violations, constraint errors after "connection reset" errors

### Pitfall 2: Statement Timeout Too Low
**What goes wrong:** Legitimate long-running queries (VACUUM, CREATE INDEX, bulk inserts) fail with "canceling statement due to statement timeout"
**Why it happens:** Global statement_timeout applies to all queries, including maintenance operations
**How to avoid:** Keep statement_timeout high (30-60 seconds) or None for general use. Override with SET LOCAL statement_timeout for specific long operations.
**Warning signs:** VACUUM failures, index creation failures, backup failures

### Pitfall 3: Missing Jitter in Backoff
**What goes wrong:** Multiple processes retry simultaneously after network partition, causing thundering herd
**Why it happens:** Exponential backoff without jitter causes synchronized retries (all wait 2s, then 4s, then 8s)
**How to avoid:** Use wait_exponential_jitter or wait_random_exponential in tenacity
**Warning signs:** Connection pool exhaustion spikes, periodic load waves

### Pitfall 4: No Reconnect Failure Alerts
**What goes wrong:** Application silently retries failed connections for 5 minutes (default reconnect_timeout), masking database outages
**Why it happens:** psycopg_pool default reconnect_failed callback is None (no action)
**How to avoid:** Provide reconnect_failed callback to log alerts, send metrics, or terminate process for restart
**Warning signs:** Long periods of "no database response" without alerts, delayed incident detection

### Pitfall 5: Retrying Wrong Exception Types
**What goes wrong:** Retry logic catches ProgrammingError (SQL syntax error) or IntegrityError (constraint violation) and retries forever
**Why it happens:** Broad except Exception or except DatabaseError catches permanent errors
**How to avoid:** Use retry_if_exception_type with specific transient exceptions (OperationalError, ConnectionFailure, ConnectionTimeout)
**Warning signs:** Infinite retry loops on bad SQL, application hangs on schema mismatches

## Code Examples

Verified patterns from official sources:

### Retry Connection with Exponential Backoff
```python
# Source: tenacity documentation + psycopg3 errors API
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from psycopg import OperationalError
import logging

logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((
        OperationalError,
        # Could expand to specific subtypes:
        # ConnectionFailure, ConnectionTimeout, CannotConnectNow
    )),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)
def _connect_with_retry(config: Config, autocommit: bool = False):
    """Establish connection with exponential backoff retry."""
    return psycopg.connect(**config.connect_params(), autocommit=autocommit)
```

### Configure Statement Timeout via Options
```python
# Source: PostgreSQL documentation, psycopg3 connection parameters
# Set 30-second timeout via Config
config = Config(
    host="localhost",
    database="myapp",
    user="postgres",
    statement_timeout=30000,  # 30 seconds in milliseconds
)

# Or pass options directly
config = Config.from_url(
    "postgresql://user:pass@localhost/mydb",
    options={"statement_timeout": "30000"}
)

# Connect with timeout applied
conn = psycopg.connect(**config.connect_params())
# All queries on this connection now have 30s timeout
```

### Pool with Custom Reconnect Handling
```python
# Source: psycopg3 pool documentation
import logging
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

def on_reconnect_failed(pool):
    """Alert on prolonged connection failure."""
    logger.critical(
        f"Database reconnection failed after {pool.reconnect_timeout}s. "
        f"Database may be down. Pool: {pool}"
    )
    # Could send alert to monitoring system, trigger restart, etc.

db = PooledDatabase(
    config=Config.from_env(),
    min_size=5,
    max_size=20,
    reconnect_timeout=60.0,  # Fail faster than default 300s
    reconnect_failed=on_reconnect_failed,
    check=ConnectionPool.check_connection,  # Enable health checks
)
```

### Override Batch Size Per Operation
```python
# Source: Current pycopg implementation
# Use default from config
await db.insert_batch("events", rows)  # Uses config.default_batch_size (1000)

# Override for memory-constrained operation
await db.insert_batch("large_blobs", rows, batch_size=100)  # Smaller batches

# Override for high-performance bulk load
await db.insert_batch("logs", rows, batch_size=5000)  # Larger batches
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual retry loops | tenacity library | ~2016 (tenacity created) | Standardized retry patterns, eliminated common bugs |
| SELECT 1 for health checks | Empty query | psycopg3 3.1+ (2023) | Faster health checks, less overhead |
| thread.Timer for timeouts | PostgreSQL statement_timeout | PostgreSQL 7.3+ (2002) | Database-native, more accurate, no threading issues |
| Fixed retry delays | Exponential backoff with jitter | AWS blog 2015 | Reduced thundering herd, 97% improvement in retry success |

**Deprecated/outdated:**
- **Manual retry with time.sleep():** Error-prone, missing edge cases. Use tenacity.
- **Application-level query timeout with signal.alarm:** Not portable (Unix-only), conflicts with other signals. Use statement_timeout.
- **Retry at query level:** Risk of duplicate operations. Retry connections only.

## Transient vs Permanent Errors

Based on psycopg3 exception hierarchy, these errors should trigger retry:

**Transient (RETRY):**
- `OperationalError` - Base class for operational issues
- `ConnectionFailure` (08006) - Connection failed
- `ConnectionTimeout` - Connection timed out
- `CannotConnectNow` (57P03) - Server cannot accept connections now
- `IdleSessionTimeout` (57P05) - Session timeout
- `QueryCanceled` (57014) - Query cancelled by timeout (if at connection level)

**Permanent (DON'T RETRY):**
- `ProgrammingError` - SQL syntax error, undefined table/column
- `IntegrityError` - Constraint violation
- `DataError` - Data type mismatch
- `InvalidIdentifier` - SQL injection attempt (pycopg custom)
- `NotSupportedError` - Feature not supported
- `InternalError` - Internal database error

**Source:** [psycopg3 errors documentation](https://www.psycopg.org/psycopg3/docs/api/errors.html)

## Open Questions

1. **Should retry be enabled by default or opt-in?**
   - What we know: Retry is generally safe for connection establishment, risky for queries
   - What's unclear: User expectations - do they expect automatic retry or explicit configuration?
   - Recommendation: Enable connection retry by default with conservative limits (3 attempts, 10s max delay). Allow Config.retry_policy=None to disable.

2. **Should statement_timeout default be None (disabled) or a safe value like 60s?**
   - What we know: PostgreSQL defaults to 0 (disabled). Production best practice is enabling timeout.
   - What's unclear: Library philosophy - stay close to PostgreSQL defaults or add safe defaults?
   - Recommendation: Default to None (match PostgreSQL), document strongly in README that production should set it.

3. **Should we expand retry to pooled connections differently than direct connections?**
   - What we know: psycopg_pool already has reconnect logic with exponential backoff
   - What's unclear: Is additional tenacity retry redundant or complementary?
   - Recommendation: Don't add tenacity retry to PooledDatabase - pool's reconnect_timeout handles it. Only add to Database/AsyncDatabase direct connections.

## Sources

### Primary (HIGH confidence)
- [psycopg3 errors documentation](https://www.psycopg.org/psycopg3/docs/api/errors.html) - Exception hierarchy, transient vs permanent errors
- [psycopg3 connection pool documentation](https://www.psycopg.org/psycopg3/docs/advanced/pool.html) - Pool configuration, reconnect behavior, health checks
- [tenacity API documentation](https://tenacity.readthedocs.io/en/latest/api.html) - Retry strategies, wait functions, stop conditions
- [PostgreSQL client connection defaults](https://www.postgresql.org/docs/current/runtime-config-client.html) - statement_timeout parameter, connection options
- [PostgreSQL connection control functions](https://www.postgresql.org/docs/current/libpq-connect.html) - connect_timeout, options parameter

### Secondary (MEDIUM confidence)
- [Tenacity GitHub repository](https://github.com/jd/tenacity) - Version info, async support, community adoption
- [Control Runaway Queries with statement_timeout (Crunchy Data)](https://www.crunchydata.com/blog/control-runaway-postgres-queries-with-statement-timeout) - Best practices
- [Reconnecting after PostgreSQL failover (Citus Data)](https://www.citusdata.com/blog/2021/02/12/reconnecting-your-app-after-a-postgres-failover/) - Decorrelated jitter, production patterns
- [API Error Handling & Retry Strategies Python Guide 2026](https://easyparser.com/blog/api-error-handling-retry-strategies-python-guide) - Exponential backoff, jitter benefits

### Tertiary (LOW confidence - trends/adoption)
- [Tenacity retries exponential backoff decorators 2026](https://johal.in/tenacity-retries-exponential-backoff-decorators-2026/) - 97% failure reduction claim, 2026 adoption
- [piptrends: backoff vs tenacity](https://piptrends.com/compare/backoff-vs-retry-vs-tenacity) - Library comparison

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - tenacity is Python standard, psycopg3 pool features well-documented
- Architecture: HIGH - Retry patterns verified in tenacity docs, statement_timeout in PostgreSQL docs
- Pitfalls: HIGH - Based on real production issues documented in Citus blog, psycopg GitHub issues
- Code examples: HIGH - All examples from official documentation (tenacity, psycopg3, PostgreSQL)

**Research date:** 2026-02-11
**Valid until:** 2026-03-31 (45 days - stable domain, tenacity and psycopg3 mature)

---

## Implementation Checklist for Planner

- [ ] Add tenacity>=9.0.0 to pyproject.toml dependencies
- [ ] Add statement_timeout: Optional[int] to Config dataclass
- [ ] Add default_batch_size: int = 1000 to Config dataclass
- [ ] Update Config.connect_params() to build options string with statement_timeout
- [ ] Add retry decorator to Database.connect() and AsyncDatabase.connect()
- [ ] Update insert_batch() methods to accept batch_size=None, default to config.default_batch_size
- [ ] Add reconnect_timeout, reconnect_failed, check params to PooledDatabase.__init__
- [ ] Add reconnect_timeout, reconnect_failed, check params to AsyncPooledDatabase.__init__
- [ ] Update Config.from_url() to parse statement_timeout from query params
- [ ] Document retry behavior and statement_timeout in README
- [ ] Add tests for retry on connection failure
- [ ] Add tests for statement_timeout enforcement
- [ ] Add tests for configurable batch size
- [ ] Add tests for pool reconnection behavior
