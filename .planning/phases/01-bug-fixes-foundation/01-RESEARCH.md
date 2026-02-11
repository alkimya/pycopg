# Phase 1: Bug Fixes & Foundation - Research

**Researched:** 2026-02-11
**Domain:** Python error handling, PostgreSQL connection lifecycle, psycopg3 transaction states
**Confidence:** HIGH

## Summary

Phase 1 fixes five critical bugs in pycopg's connection lifecycle, migration parsing, extension validation, and SRID inference. Research focused on psycopg3's transaction state machine, Python's exception cleanup guarantees, logging best practices for library code, and GeoPandas CRS handling.

**Primary findings:**
1. psycopg3 context managers require explicit try/finally for cleanup guarantee when close() might fail
2. TransactionStatus has 5 states (IDLE, ACTIVE, INTRANS, INERROR, UNKNOWN) but current code only checks IDLE
3. Python logging standard for libraries: WARNING level for operational issues, no handlers except NullHandler
4. GeoPandas to_epsg() can fail on unknown CRS - requires explicit exception handling vs. silent default
5. Extension validation follows has_extension() pattern already in codebase (lines 684-694, 1205-1206, 1338-1339 in database.py)

**Primary recommendation:** Use try/finally for session cleanup, expand TransactionStatus checks to all non-IDLE states, add Python logging module with library-safe configuration, replace silent SRID default with explicit error.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Implementation Decisions**

- Error behavior: SRID inference failure, extension-not-found errors, cleanup failures, transaction detection issues — Claude has full discretion on exception types, error messages, and whether to use custom exceptions vs standard ones
- Error message tone: Claude decides (technical vs approachable) based on what fits pycopg's existing patterns
- Cleanup error handling in session mode (original error vs chained): Claude's discretion

- Logging strategy: Migration parser silent-skip → WARNING is required by roadmap; Whether to audit and fix other silent-failure patterns: Claude's discretion; Cleanup failure log level: Claude's discretion; Extension validation happy-path logging: Claude's discretion; Follow whatever logging pattern already exists in the codebase (investigate during research)

- Backwards compatibility: v0.3.0 is a consolidation release — breaking changes are allowed; User may have code depending on buggy behavior (e.g., SRID=4326 default) but hasn't checked — assume clean breaks are acceptable; Claude decides per-fix whether to hard break, deprecation-warn, or provide migration path — evaluate each case individually; Where to document behavior changes (code docstrings vs CHANGELOG only): Claude's discretion

- Validation scope: TimescaleDB extension validation is required by roadmap; Whether to also add PostGIS validation in this phase: Claude's discretion (evaluate scope fit); Validation timing (per-call vs cached): Claude's discretion; Version checking vs existence-only: Claude's discretion; Session mode transaction fix scope (just TransactionStatus vs also connection liveness): Claude's discretion

### Claude's Discretion

The user granted maximum autonomy across all four discussion areas. Claude has flexibility on:
- Exception types and error message design
- Logging levels and scope of logging fixes
- Breaking change strategy per bug fix
- Validation depth and timing
- Whether to extend fixes beyond the strict 5-bug scope when the same pattern applies

### Specific Ideas

No specific requirements — open to standard approaches. User trusts Claude's judgment on all implementation details for this phase.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.x | PostgreSQL adapter | Modern async support, connection pooling, improved API over psycopg2 |
| Python logging | stdlib | Library logging | Standard library, zero dependencies, follows PEP 282 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| geopandas | Current | Spatial data handling | Already used in codebase for PostGIS operations |
| pyproj | Current | CRS transformations | Dependency of geopandas, provides to_epsg() |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python logging | print() statements | logging provides levels, filtering, library-safe patterns |
| Custom exceptions | Built-in exceptions | Custom exceptions provide better API clarity, already in pycopg.exceptions |

**Installation:**
No new dependencies required - all fixes use existing stack.

## Architecture Patterns

### Recommended Project Structure
Current structure is appropriate - no changes needed:
```
pycopg/
├── database.py          # Sync Database class
├── async_database.py    # Async Database class
├── migrations.py        # Migration system
├── exceptions.py        # Custom exceptions
└── utils.py            # Validation helpers
```

### Pattern 1: Guaranteed Cleanup with try/finally
**What:** Wrap context manager cleanup in try/finally to guarantee execution even if close() raises
**When to use:** Session mode cleanup where connection.close() might fail but cleanup state must reset
**Example:**
```python
# Current buggy pattern (database.py lines 340-353)
@contextmanager
def session(self, autocommit: bool = False):
    self._session_conn = psycopg.connect(...)
    try:
        yield self
    finally:
        if not autocommit:
            self._session_conn.commit()
        self._session_conn.close()  # BUG: if close() raises, _session_conn never set to None
        self._session_conn = None

# Fixed pattern with guaranteed cleanup
@contextmanager
def session(self, autocommit: bool = False):
    self._session_conn = psycopg.connect(...)
    try:
        yield self
    finally:
        try:
            if not autocommit:
                self._session_conn.commit()
            self._session_conn.close()
        finally:
            self._session_conn = None  # ALWAYS executes
```
**Source:** [Python 'finally' block: Ensuring cleanup and reliability](https://www.w3resource.com/python-interview/explain-the-purpose-of-the-finally-block-in-a-try-except-finally-structure.php)

### Pattern 2: Complete TransactionStatus State Handling
**What:** Check all psycopg3 TransactionStatus states, not just IDLE
**When to use:** Implicit transaction detection in session mode (cursor method)
**Example:**
```python
# Current buggy pattern (database.py line 281)
if not autocommit and self._session_conn.info.transaction_status == TransactionStatus.IDLE:
    self._session_conn.commit()

# Fixed pattern checking all transaction states
from psycopg.pq import TransactionStatus

# IDLE = 0, ACTIVE = 1, INTRANS = 2, INERROR = 3, UNKNOWN = 4
if not autocommit:
    status = self._session_conn.info.transaction_status
    if status == TransactionStatus.IDLE:
        # No transaction open, commit is a no-op but safe
        self._session_conn.commit()
    elif status == TransactionStatus.INTRANS:
        # Valid transaction open, commit it
        self._session_conn.commit()
    elif status == TransactionStatus.INERROR:
        # Failed transaction, must rollback
        self._session_conn.rollback()
    # ACTIVE and UNKNOWN states should not occur in cursor context exit
```
**Source:** [Transactions management - psycopg 3.3.3.dev1 documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [psycopg - PostgreSQL database adapter for Python](https://access.crunchydata.com/documentation/psycopg3/3.1.9/api/pq.html)

### Pattern 3: Library-Safe Logging
**What:** Use Python logging module following library best practices
**When to use:** Migration parser warnings, extension validation failures, cleanup errors
**Example:**
```python
import logging

# Module-level logger (library best practice)
logger = logging.getLogger(__name__)

# In migration parser (migrations.py line 152)
for f in files:
    try:
        migrations.append(Migration(f))
    except MigrationError as e:
        logger.warning("Skipping invalid migration file %s: %s", f.name, e)
        continue
```
**Source:** [Logging HOWTO — Python 3.14.3 documentation](https://docs.python.org/3/howto/logging.html), [Python Logging Best Practices: Complete Guide 2026](https://www.carmatec.com/blog/python-logging-best-practices-complete-guide/)

### Pattern 4: Extension Validation Before Use
**What:** Check has_extension() before calling extension-specific functions
**When to use:** All TimescaleDB operations (create_hypertable, enable_compression, add_retention_policy, etc.)
**Example:**
```python
# Already exists for create_hypertable (database.py lines 1338-1339)
if not self.has_extension("timescaledb"):
    raise RuntimeError("TimescaleDB extension not installed...")

# Apply same pattern to all TimescaleDB methods:
# - enable_compression (line 1354)
# - add_compression_policy (line 1393)
# - add_retention_policy (line 1416)
```

### Pattern 5: Explicit CRS Error Handling
**What:** Catch to_epsg() exceptions and raise explicit error instead of silent default
**When to use:** from_geodataframe SRID inference
**Example:**
```python
# Current buggy pattern (database.py lines 1208-1213)
if srid is None and gdf.crs is not None:
    try:
        srid = gdf.crs.to_epsg()
    except Exception:
        srid = 4326  # BUG: Silent default masks unknown CRS

# Fixed pattern with explicit error
if srid is None:
    if gdf.crs is None:
        raise ValueError(
            "GeoDataFrame has no CRS defined. "
            "Set gdf.crs or provide explicit srid parameter."
        )
    try:
        srid = gdf.crs.to_epsg()
        if srid is None:
            raise ValueError(f"Cannot determine EPSG code for CRS: {gdf.crs}")
    except Exception as e:
        raise ValueError(
            f"Failed to infer SRID from CRS {gdf.crs}. "
            f"Provide explicit srid parameter. Error: {e}"
        ) from e
```
**Source:** [BUG: to_postgis uses wrong SRID for CRS with ESRI authority · Issue #2414 · geopandas/geopandas](https://github.com/geopandas/geopandas/issues/2414)

### Anti-Patterns to Avoid
- **Silent exception swallowing:** `except Exception: pass` or `except Exception: default_value` hides real errors
- **Single TransactionStatus check:** Only checking IDLE misses INTRANS and INERROR states
- **No logging in libraries:** Print statements or no logging makes debugging impossible for users
- **Cleanup without finally:** Relying on context manager exit without nested try/finally risks state corruption

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Logging system | Custom print/debug framework | Python stdlib logging | Mature, configurable, library-safe, follows PEP 282 |
| Exception chaining | Manual error wrapping | `raise ... from e` syntax | Preserves stack traces, standard Python 3 feature |
| Transaction state detection | Custom SQL queries | psycopg3 TransactionStatus enum | Direct access to libpq state, authoritative source |

**Key insight:** psycopg3 and Python stdlib provide all primitives needed. Custom solutions would be worse because:
1. Python logging is deeply integrated with ecosystem tooling (pytest, structlog, sentry, etc.)
2. Transaction status from libpq is the source of truth - SQL queries would be stale snapshots
3. Exception chaining is optimized at interpreter level for performance and debuggability

## Common Pitfalls

### Pitfall 1: Assuming context manager guarantees cleanup
**What goes wrong:** If the cleanup code itself raises an exception, subsequent cleanup steps are skipped
**Why it happens:** Single try/finally doesn't protect against cleanup failures
**How to avoid:** Nested try/finally blocks - outer finally for state reset, inner try/finally for resource cleanup
**Warning signs:** Connection leaks in session mode after exceptions, "_session_conn already set" errors on retry

**Example of the bug:**
```python
# Lines 340-353 in database.py
try:
    yield self
finally:
    if not autocommit:
        self._session_conn.commit()  # Might raise
    self._session_conn.close()       # Might raise, skipping line below
    self._session_conn = None        # NEVER EXECUTES if close() raises
```

### Pitfall 2: Incomplete transaction state handling
**What goes wrong:** Only checking IDLE state misses implicit transactions (INTRANS) and failed transactions (INERROR)
**Why it happens:** Assumption that IDLE is the only "safe" state to commit in
**How to avoid:** Handle all 5 TransactionStatus states explicitly, with appropriate action for each
**Warning signs:** Uncommitted data in session mode, transaction isolation violations, "cannot commit - no transaction" errors

**From psycopg3 docs:** TransactionStatus values are IDLE (0), ACTIVE (1), INTRANS (2), INERROR (3), UNKNOWN (4)
- IDLE: Not in transaction, safe to commit (no-op)
- INTRANS: Valid transaction open, MUST commit or data loss
- INERROR: Failed transaction, MUST rollback before new commands

### Pitfall 3: Library logging with handlers or wrong levels
**What goes wrong:** Adding handlers or logging at INFO/DEBUG by default spams user applications
**Why it happens:** Application logging patterns don't apply to libraries
**How to avoid:** Use WARNING level for operational issues, never add handlers except NullHandler
**Warning signs:** User complaints about verbose output, inability to control library log levels

**Best practice from Python docs:** "It is strongly advised that you do not add any handlers other than NullHandler to your library's loggers"

### Pitfall 4: Silent CRS inference failures
**What goes wrong:** Defaulting to EPSG:4326 when CRS is unknown silently creates wrong spatial data
**Why it happens:** Trying to be "helpful" by providing a default instead of failing fast
**How to avoid:** Explicit error when SRID cannot be determined, force user to provide correct value
**Warning signs:** Spatial queries returning wrong results, data in wrong coordinate system discovered later

**Real-world impact:** Wrong SRID can cause:
- Distance calculations off by orders of magnitude
- Spatial joins missing valid matches
- Map rendering at wrong locations
- Compliance failures for GIS data standards

## Code Examples

Verified patterns from official sources and existing codebase:

### Guaranteed Cleanup Pattern
```python
# Source: Python docs on finally blocks
@contextmanager
def session(self, autocommit: bool = False) -> Iterator["Database"]:
    if self._session_conn is not None:
        raise RuntimeError("Already in session mode. Nested sessions are not supported.")

    self._session_conn = psycopg.connect(
        **self.config.connect_params(),
        autocommit=autocommit
    )
    try:
        yield self
    finally:
        # Nested try/finally ensures state cleanup even if connection ops fail
        try:
            if not autocommit:
                self._session_conn.commit()
            self._session_conn.close()
        except Exception as e:
            # Log cleanup failure but don't suppress it
            logger.warning("Session cleanup failed: %s", e)
            raise
        finally:
            # ALWAYS executes - guaranteed state reset
            self._session_conn = None
```

### Complete Transaction State Handling
```python
# Source: psycopg3 docs on TransactionStatus
from psycopg.pq import TransactionStatus

@contextmanager
def cursor(self, autocommit: bool = False) -> Iterator[psycopg.Cursor]:
    if self._session_conn is not None:
        with self._session_conn.cursor(row_factory=dict_row) as cur:
            yield cur
            if not autocommit:
                # Handle all transaction states properly
                status = self._session_conn.info.transaction_status
                if status == TransactionStatus.INTRANS:
                    # Valid transaction, commit it
                    self._session_conn.commit()
                elif status == TransactionStatus.INERROR:
                    # Failed transaction, rollback required
                    self._session_conn.rollback()
                # IDLE: no transaction, nothing to commit
                # ACTIVE/UNKNOWN: should not occur at cursor exit
    else:
        with self.connect(autocommit=autocommit) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                yield cur
                if not autocommit:
                    conn.commit()
```

### Library-Safe Logging
```python
# Source: Python logging docs and best practices
import logging

# Module-level logger (follows __name__ pattern)
logger = logging.getLogger(__name__)

class Migrator:
    def _get_migrations(self) -> list[Migration]:
        """Get all migration files sorted by version."""
        files = sorted(self.migrations_dir.glob("*.sql"))
        migrations = []
        for f in files:
            try:
                migrations.append(Migration(f))
            except MigrationError as e:
                # WARNING level appropriate for operational issues in libraries
                logger.warning(
                    "Skipping invalid migration file '%s': %s",
                    f.name, e
                )
                continue
        return sorted(migrations, key=lambda m: m.version)
```

### Extension Validation Pattern
```python
# Source: Existing pycopg code (database.py lines 1338-1339)
def enable_compression(
    self,
    table: str,
    segment_by: Optional[str | list[str]] = None,
    order_by: Optional[str | list[str]] = None,
    schema: str = "public",
) -> None:
    """Enable compression on a hypertable."""
    # Validate extension exists before calling TimescaleDB functions
    if not self.has_extension("timescaledb"):
        raise RuntimeError(
            "TimescaleDB extension not installed. "
            "Run db.create_extension('timescaledb') first."
        )

    validate_identifiers(table, schema)
    # ... rest of implementation
```

### Explicit SRID Error Handling
```python
# Source: GeoPandas issues and best practices
def from_geodataframe(
    self,
    gdf: "gpd.GeoDataFrame",
    table: str,
    schema: str = "public",
    if_exists: Literal["fail", "replace", "append"] = "fail",
    primary_key: Optional[str | list[str]] = None,
    spatial_index: bool = True,
    geometry_column: str = "geometry",
    srid: Optional[int] = None,
) -> None:
    """Create or append to table from GeoDataFrame."""
    if not self.has_extension("postgis"):
        raise RuntimeError(
            "PostGIS extension not installed. "
            "Run db.create_extension('postgis') first."
        )

    # Explicit SRID handling - no silent defaults
    if srid is None:
        if gdf.crs is None:
            raise ValueError(
                "GeoDataFrame has no CRS defined. "
                "Set gdf.crs or provide explicit srid parameter."
            )
        try:
            srid = gdf.crs.to_epsg()
            if srid is None:
                raise ValueError(
                    f"Cannot determine EPSG code for CRS: {gdf.crs}. "
                    f"Provide explicit srid parameter."
                )
        except Exception as e:
            raise ValueError(
                f"Failed to infer SRID from CRS {gdf.crs}. "
                f"Provide explicit srid parameter. Error: {e}"
            ) from e

    # ... rest of implementation
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| psycopg2 context manager keeps connection open | psycopg3 context manager closes connection on exit | psycopg3 release (2021+) | More explicit transaction management, can't reuse connection across with blocks |
| Print statements for debugging | Python logging module | Standard library feature | Configurable output, library-safe patterns |
| Silent exception swallowing | Exception chaining with `from` | Python 3.0+ | Preserves full stack traces for debugging |
| Manual transaction state queries | psycopg3 TransactionStatus enum | psycopg3 release | Direct libpq state access, authoritative |

**Deprecated/outdated:**
- psycopg2 connection context manager behavior (doesn't close)
- Silent defaults for unknown CRS (GeoPandas community consensus: explicit errors better)
- Checking only IDLE transaction state (incomplete, misses INTRANS and INERROR)

## Open Questions

1. **Cleanup error handling strategy**
   - What we know: Session cleanup can fail if close() raises
   - What's unclear: Should cleanup errors be logged and re-raised, or logged and suppressed?
   - Recommendation: Log and re-raise to surface connection issues, but guarantee state cleanup in finally

2. **Extension validation scope for PostGIS**
   - What we know: User gave discretion on adding PostGIS validation this phase
   - What's unclear: Does PostGIS follow same pattern as TimescaleDB?
   - Recommendation: Yes - add validation to from_geodataframe since it already checks has_extension(), apply same pattern for consistency

3. **Logging levels for different failures**
   - What we know: Migration parser should use WARNING for skipped files
   - What's unclear: What level for cleanup failures, extension missing, SRID inference failures?
   - Recommendation: WARNING for skipped migrations (operational issue), no logging for validation errors (raise exceptions instead - errors are exceptional)

4. **Breaking change communication**
   - What we know: v0.3.0 allows breaking changes, user discretion on per-fix strategy
   - What's unclear: Should changes be documented in code docstrings, CHANGELOG, or both?
   - Recommendation: Both - update docstrings for API changes (especially from_geodataframe SRID behavior), comprehensive CHANGELOG entry for migration guide

## Sources

### Primary (HIGH confidence)
- [Transactions management - psycopg 3.3.3.dev1 documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html) - TransactionStatus states
- [psycopg - PostgreSQL database adapter for Python](https://access.crunchydata.com/documentation/psycopg3/3.1.9/api/pq.html) - TransactionStatus enum values
- [Connection classes - psycopg 3.3.3.dev1 documentation](https://www.psycopg.org/psycopg3/docs/api/connections.html) - Context manager behavior
- [Python 'finally' block: Ensuring cleanup and reliability](https://www.w3resource.com/python-interview/explain-the-purpose-of-the-finally-block-in-a-try-except-finally-structure.php) - Finally execution guarantees
- [Logging HOWTO — Python 3.14.3 documentation](https://docs.python.org/3/howto/logging.html) - Library logging best practices
- [Python Logging Best Practices: Complete Guide 2026](https://www.carmatec.com/blog/python-logging-best-practices-complete-guide/) - WARNING level for libraries
- Existing pycopg codebase (database.py, migrations.py, exceptions.py) - Current patterns

### Secondary (MEDIUM confidence)
- [BUG: to_postgis uses wrong SRID for CRS with ESRI authority · Issue #2414 · geopandas/geopandas](https://github.com/geopandas/geopandas/issues/2414) - CRS inference issues
- [10 Best Practices for Logging in Python | Better Stack Community](https://betterstack.com/community/guides/logging/python/python-logging-best-practices/) - Logging patterns
- [PostgreSQL: Documentation: 18: CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) - Extension validation

### Tertiary (LOW confidence)
None - all findings verified with official documentation or existing code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Existing dependencies, no new additions required
- Architecture: HIGH - Patterns from official psycopg3 docs and Python stdlib docs
- Pitfalls: HIGH - Verified against existing codebase bugs and official documentation
- Code examples: HIGH - All examples from official sources or existing working code

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (30 days - stable APIs, unlikely to change)

**Current codebase state:**
- No logging module currently used (grep found zero imports)
- Custom exceptions already defined in exceptions.py
- Extension validation pattern exists for 2/3 use cases (PostGIS in from_geodataframe, TimescaleDB in create_hypertable)
- Session cleanup bug confirmed at database.py lines 340-353
- TransactionStatus single-state check confirmed at database.py line 281
- SRID silent default confirmed at database.py lines 1208-1213
- Migration parser silent skip confirmed at migrations.py line 152

**Breaking changes required:**
1. BUG-05 (SRID inference): from_geodataframe will raise ValueError instead of defaulting to 4326
2. All others are bug fixes with backward-compatible behavior (no API changes)
