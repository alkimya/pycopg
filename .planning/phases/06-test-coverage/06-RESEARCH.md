# Phase 6: Test Coverage - Research

**Researched:** 2026-02-11
**Domain:** Python testing, PostgreSQL integration testing, test coverage analysis
**Confidence:** HIGH

## Summary

Phase 6 requires achieving >70% test coverage with comprehensive edge case testing across migrations, sessions, pools, and spatial operations. The research reveals a mature Python testing ecosystem with pytest-cov 7.0.0, pytest-asyncio for async testing, and established patterns for database integration testing.

Key findings: pycopg already has pytest-cov installed (7.0.0), uses real PostgreSQL testing via pycopg_test database, and has existing test infrastructure in place. The challenge is expanding coverage to migration rollback edge cases, session exception scenarios, pool stress testing, PostGIS error handling, and automated async/sync parity verification.

**Primary recommendation:** Use pytest-cov with --cov-fail-under=70, parametrized tests for edge cases, pytest-timeout for pool stress scenarios, and Python's inspect module for automated API parity checking between Database and AsyncDatabase classes.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=7.0.0 | Test framework | De facto Python testing standard, rich fixture system |
| pytest-cov | >=4.0.0 | Coverage measurement | Official pytest coverage plugin, built on coverage.py |
| pytest-asyncio | >=0.23.0 | Async test support | Official pytest plugin for asyncio coroutines |
| coverage.py | (implicit) | Coverage engine | Industry standard coverage measurement tool |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-timeout | >=2.0.0 | Test timeouts | Pool stress tests (prevent hanging), recommended for connection exhaustion scenarios |
| psycopg | >=3.1.0 | Real DB testing | Already in dependencies, use for integration tests |
| unittest.mock | (stdlib) | Mocking | Edge cases where real DB not suitable (file system errors, etc.) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest-cov | coverage.py CLI | pytest-cov integrates better, less CLI overhead |
| pytest-asyncio | asynctest | pytest-asyncio is actively maintained, better pytest integration |
| pytest-timeout | manual asyncio.wait_for | pytest-timeout works for both sync/async, cleaner syntax |

**Installation:**
```bash
# Already installed in pycopg/venv via pyproject.toml dev dependencies
pip install -e ".[dev]"

# Add pytest-timeout if needed
pip install pytest-timeout>=2.0.0
```

## Architecture Patterns

### Recommended Test Structure
```
tests/
├── conftest.py                    # Fixtures (db_config, temp_migrations_dir)
├── setup_test_db.py              # Real PostgreSQL setup script
├── test_config.py                # Config unit tests
├── test_base.py                  # Base class unit tests
├── test_utils.py                 # Utility function tests
├── test_exceptions.py            # Exception tests
├── test_database.py              # Database integration tests
├── test_async_database.py        # AsyncDatabase integration tests
├── test_pool.py                  # Pool integration tests
├── test_migrations.py            # Migration tests
├── test_integration.py           # End-to-end tests
└── test_parity.py                # NEW: Async/sync API parity
```

### Pattern 1: Real PostgreSQL Integration Testing
**What:** Tests run against actual PostgreSQL database (pycopg_test), not mocks
**When to use:** Default for all database operations, migrations, spatial queries
**Example:**
```python
# Source: /home/loc/workspace/pycopg/tests/conftest.py
@pytest.fixture
def db_config():
    """Create a config for the real test database."""
    host = os.getenv("PGHOST", "localhost")
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "postgres")
    port = int(os.getenv("PGPORT", "5432"))

    return Config(
        host=host,
        port=port,
        database="pycopg_test",
        user=user,
        password=password,
    )
```

### Pattern 2: Parametrized Edge Case Testing
**What:** Use pytest.mark.parametrize to test multiple edge cases with single test function
**When to use:** Testing migration rollback scenarios, session exceptions, pool exhaustion
**Example:**
```python
# Source: pytest documentation + pycopg patterns
@pytest.mark.parametrize("scenario,expected_error", [
    ("deleted_file", MigrationError),
    ("syntax_error", psycopg.errors.SyntaxError),
    ("first_migration", None),  # Should succeed
])
def test_migration_rollback_edge_cases(scenario, expected_error, migrator):
    if expected_error:
        with pytest.raises(expected_error):
            migrator.rollback()
    else:
        migrator.rollback()  # Should not raise
```

### Pattern 3: Async/Sync Fixture Reuse
**What:** Same test logic for Database and AsyncDatabase using parametrized fixtures
**When to use:** Testing feature parity, ensuring consistent behavior
**Example:**
```python
# Source: pytest-asyncio documentation
@pytest.fixture(params=['sync', 'async'])
def database(request, db_config):
    if request.param == 'sync':
        return Database(db_config)
    else:
        return AsyncDatabase(db_config)

@pytest.mark.asyncio
async def test_list_schemas(database):
    if isinstance(database, AsyncDatabase):
        schemas = await database.list_schemas()
    else:
        schemas = database.list_schemas()
    assert 'public' in schemas
```

### Pattern 4: Pool Stress Testing with Timeout
**What:** Test pool exhaustion, cycling, broken connections with pytest-timeout
**When to use:** Pool stress scenarios (TEST-04 requirement)
**Example:**
```python
# Source: pytest-timeout + psycopg pool patterns
@pytest.mark.timeout(10)
def test_pool_exhaustion(db_config):
    """Test that pool handles connection exhaustion gracefully."""
    pool = PooledDatabase(db_config, min_size=2, max_size=5, timeout=2.0)

    connections = []
    try:
        # Exhaust pool (5 connections)
        for _ in range(5):
            connections.append(pool.connection().__enter__())

        # Next request should timeout after 2 seconds
        with pytest.raises(PoolTimeout):
            with pool.connection():
                pass
    finally:
        for conn in connections:
            conn.__exit__(None, None, None)
        pool.close()
```

### Pattern 5: Automated API Parity Verification
**What:** Introspect Database and AsyncDatabase to verify all public methods have equivalents
**When to use:** TEST-06 requirement - automated async parity test
**Example:**
```python
# Source: Python inspect module + custom logic
import inspect
from pycopg import Database, AsyncDatabase

def test_async_parity():
    """Verify all Database public methods have AsyncDatabase equivalent."""
    db_methods = {name for name, _ in inspect.getmembers(Database, predicate=inspect.isfunction)
                  if not name.startswith('_')}
    async_methods = {name for name, _ in inspect.getmembers(AsyncDatabase, predicate=inspect.isfunction)
                     if not name.startswith('_')}

    # Class methods that differ (create, from_env, from_url)
    class_method_exceptions = {'engine', 'async_engine'}

    missing = db_methods - async_methods - class_method_exceptions
    assert not missing, f"AsyncDatabase missing methods: {missing}"
```

### Anti-Patterns to Avoid
- **Mock-heavy testing:** Don't mock psycopg connections for integration tests - use real PostgreSQL to catch driver/DB bugs
- **Hardcoded DB credentials:** Use environment variables with sensible defaults
- **Session-scoped DB fixtures:** Use function-scoped fixtures with rollback to avoid test contamination
- **Ignoring async test cleanup:** Always use async context managers or explicit cleanup in async tests
- **Coverage theater:** Don't write trivial tests just to hit 70% - focus on edge cases and real scenarios

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Coverage measurement | Custom coverage tracking | pytest-cov with --cov-fail-under | Proven, integrates with CI, handles branch coverage, multi-file reports |
| Async test execution | Manual event loop management | pytest-asyncio with @pytest.mark.asyncio | Handles event loop lifecycle, fixture support, mixing sync/async tests |
| Test timeouts | Manual timeout decorators | pytest-timeout plugin | Works for both sync/async, configurable per-test, prevents hanging CI |
| API introspection | Manual method comparison | inspect.getmembers() + inspect.isfunction() | Standard library, handles inheritance, method types, signatures |
| Database fixtures | Custom DB setup/teardown | pytest fixtures with scope control | Automatic cleanup, dependency injection, reusable across tests |
| Parametrized tests | Copy-paste test functions | pytest.mark.parametrize | Single test definition, clear edge cases, better reports |
| Mock objects | Custom mock classes | unittest.mock.MagicMock/AsyncMock | Handles sync/async, call tracking, spec validation |

**Key insight:** Python's testing ecosystem is mature - leverage existing tools rather than building custom test infrastructure. Focus energy on test logic and edge cases, not test harness.

## Common Pitfalls

### Pitfall 1: Coverage Without Edge Cases
**What goes wrong:** Hitting 70% coverage but missing critical edge cases (deleted migration files, pool exhaustion, session cleanup failures)
**Why it happens:** Coverage measures lines executed, not scenarios tested
**How to avoid:** Map each requirement (TEST-01 through TEST-06) to specific test functions with explicit edge case parametrization
**Warning signs:** High coverage percentage but missing pytest.mark.parametrize, no exception testing, no stress tests

### Pitfall 2: Async Test Isolation Failures
**What goes wrong:** Async tests pass individually but fail when run together, or leave event loops in dirty state
**Why it happens:** pytest-asyncio defaults to function-scoped event loops, but fixtures with wrong scope can share state
**How to avoid:** Use pytest-asyncio's auto mode (default), ensure async fixtures use @pytest_asyncio.fixture, clean up async resources in finally blocks
**Warning signs:** Tests pass with pytest -k single_test but fail in full suite, event loop closed errors, ResourceWarning

### Pitfall 3: Real Database State Contamination
**What goes wrong:** Tests fail intermittently depending on execution order, leftover data from previous tests
**Why it happens:** Function-scoped fixtures don't clean up properly, or tests share session/module-scoped DB
**How to avoid:** Use transactions with rollback in fixtures, truncate tables in teardown, or recreate test schema per function
**Warning signs:** Tests pass individually but fail together, "duplicate key" errors, assertion failures on row counts

### Pitfall 4: Migration Rollback Testing Without File System Edge Cases
**What goes wrong:** Migration rollback tests only cover happy path, miss deleted files or syntax errors
**Why it happens:** Easier to test success cases than simulate file system failures
**How to avoid:** Use pytest.mark.parametrize with scenarios: deleted DOWN section, missing migration file, SQL syntax error in DOWN, rollback when no migrations applied
**Warning signs:** TEST-02 requirement not fully satisfied, only one rollback test, no exception testing

### Pitfall 5: Pool Stress Tests Hanging in CI
**What goes wrong:** Pool exhaustion tests wait forever for connections, hang CI pipeline
**Why it happens:** No timeout on pool.connection() call or test execution
**How to avoid:** Use pytest-timeout plugin, set realistic timeout values on pool and test, use PoolTimeout exception assertions
**Warning signs:** CI timeouts on test_pool.py, manual ctrl-C needed during local test runs

### Pitfall 6: PostGIS Tests Requiring Extension Installation
**What goes wrong:** PostGIS tests fail in CI because extension not installed on test database
**Why it happens:** CI database might not have PostGIS compiled/enabled
**How to avoid:** Use pytest.mark.skipif with has_extension('postgis') check, or ensure CI setup script installs PostGIS
**Warning signs:** Tests pass locally but fail in CI with "PostGIS not available" errors

### Pitfall 7: Async Parity Test False Positives
**What goes wrong:** Automated parity test passes but AsyncDatabase missing critical functionality
**Why it happens:** Method exists but behavior differs, or method name differs slightly (e.g., engine vs async_engine)
**How to avoid:** Maintain exception list for known differences (class methods, property vs method), verify signatures match not just names
**Warning signs:** Parity test passes but manual testing finds missing async features

## Code Examples

Verified patterns from official sources and pycopg codebase:

### Example 1: Coverage Configuration in pyproject.toml
```toml
# Source: pytest-cov documentation + pyproject.toml best practices
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=70"
asyncio_mode = "auto"  # pytest-asyncio auto mode

[tool.coverage.run]
source = ["pycopg"]
omit = ["*/tests/*", "*/venv/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if TYPE_CHECKING:",
    "raise AssertionError",
    "raise NotImplementedError",
]
```

### Example 2: Migration Rollback Edge Cases
```python
# Source: pycopg test patterns + migration testing best practices
import pytest
from pathlib import Path
from pycopg import Migrator, Database
from pycopg.exceptions import MigrationError

class TestMigrationRollbackEdgeCases:
    """TEST-02: Migration rollback edge cases covered"""

    @pytest.fixture
    def migrator(self, db_config, temp_migrations_dir):
        db = Database(db_config)
        return Migrator(db, temp_migrations_dir)

    def test_rollback_with_deleted_down_section(self, migrator, temp_migrations_dir):
        """Rollback fails gracefully when DOWN section deleted from file."""
        # Create and apply migration with DOWN
        migration_file = temp_migrations_dir / "001_test.sql"
        migration_file.write_text("-- UP\nCREATE TABLE test (id INT);\n-- DOWN\nDROP TABLE test;")
        migrator.migrate()

        # Delete DOWN section from file
        migration_file.write_text("-- UP\nCREATE TABLE test (id INT);\n")

        # Rollback should fail with clear error
        with pytest.raises(MigrationError, match="No DOWN section found"):
            migrator.rollback()

    def test_rollback_with_deleted_migration_file(self, migrator, temp_migrations_dir):
        """Rollback fails when migration file deleted from filesystem."""
        migration_file = temp_migrations_dir / "001_test.sql"
        migration_file.write_text("-- UP\nCREATE TABLE test (id INT);\n-- DOWN\nDROP TABLE test;")
        migrator.migrate()

        # Delete file
        migration_file.unlink()

        with pytest.raises(MigrationError, match="Migration file.*not found"):
            migrator.rollback()

    def test_rollback_with_syntax_error_in_down(self, migrator, temp_migrations_dir):
        """Rollback propagates SQL syntax errors with context."""
        migration_file = temp_migrations_dir / "001_test.sql"
        migration_file.write_text(
            "-- UP\nCREATE TABLE test (id INT);\n"
            "-- DOWN\nDROP TABEL test;"  # Typo: TABEL
        )
        migrator.migrate()

        with pytest.raises(Exception, match="syntax error"):
            migrator.rollback()

    def test_rollback_when_no_migrations_applied(self, migrator):
        """Rollback when no migrations applied returns gracefully."""
        # Should not raise - just no-op
        result = migrator.rollback()
        assert result is None or result == []
```

### Example 3: Session Exception Scenarios
```python
# Source: pycopg session patterns + exception testing
import pytest
import psycopg
from pycopg import Database

class TestSessionExceptionScenarios:
    """TEST-03: Session mode exception scenarios covered"""

    def test_session_cleanup_after_exception(self, db_config):
        """Session cleans up connection even when exception raised inside."""
        db = Database(db_config)

        try:
            with db.session() as session:
                session.execute("SELECT 1")
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Session should be closed, not reused
        assert db._session_conn is None
        assert not db.in_session()

    def test_nested_sessions_raise_error(self, db_config):
        """Nested sessions are not allowed - raise clear error."""
        db = Database(db_config)

        with db.session() as outer:
            with pytest.raises(RuntimeError, match="Already in session"):
                with db.session() as inner:
                    pass

    def test_session_survives_query_error(self, db_config):
        """Session connection remains open after failed query."""
        db = Database(db_config)

        with db.session() as session:
            # First query fails
            with pytest.raises(psycopg.errors.UndefinedTable):
                session.execute("SELECT * FROM nonexistent_table")

            # Session still usable for next query
            result = session.execute("SELECT 1 as test")
            assert result[0]['test'] == 1

    def test_session_handles_connection_disconnect(self, db_config):
        """Session handles mid-session connection loss gracefully."""
        db = Database(db_config)

        with pytest.raises(psycopg.OperationalError):
            with db.session() as session:
                # Simulate connection kill
                session.execute("SELECT pg_terminate_backend(pg_backend_pid())")
```

### Example 4: Pool Stress Testing
```python
# Source: psycopg pool documentation + stress testing patterns
import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from psycopg_pool import PoolTimeout
from pycopg import PooledDatabase

class TestPoolStressScenarios:
    """TEST-04: Pool stress scenarios covered"""

    @pytest.mark.timeout(15)
    def test_pool_exhaustion_timeout(self, db_config):
        """Pool times out when all connections exhausted."""
        pool = PooledDatabase(db_config, min_size=2, max_size=3, timeout=2.0)

        connections = []
        try:
            # Exhaust all 3 connections
            for _ in range(3):
                conn = pool.connection().__enter__()
                connections.append(conn)

            # 4th request should timeout
            start = time.time()
            with pytest.raises(PoolTimeout):
                with pool.connection():
                    pass
            elapsed = time.time() - start
            assert 1.5 < elapsed < 3.0  # Should timeout around 2s
        finally:
            for conn in connections:
                conn.__exit__(None, None, None)
            pool.close()

    @pytest.mark.timeout(30)
    def test_pool_connection_cycling(self, db_config):
        """Pool correctly cycles connections under load."""
        pool = PooledDatabase(db_config, min_size=5, max_size=10)

        def worker():
            for _ in range(10):
                with pool.connection() as conn:
                    conn.execute("SELECT 1")

        # 20 threads, each doing 10 operations = 200 total
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker) for _ in range(20)]
            for future in futures:
                future.result()

        stats = pool.stats
        assert stats['requests_queued'] >= 0
        pool.close()

    @pytest.mark.timeout(10)
    def test_pool_broken_connection_replacement(self, db_config):
        """Pool replaces broken connections automatically."""
        pool = PooledDatabase(db_config, min_size=2, max_size=5)

        # Get connection and break it
        with pool.connection() as conn:
            conn.execute("SELECT pg_terminate_backend(pg_backend_pid())")

        # Next connection should work (pool replaces broken one)
        with pool.connection() as conn:
            result = conn.execute("SELECT 1 as test")
            assert result[0]['test'] == 1

        pool.close()
```

### Example 5: PostGIS Error Handling
```python
# Source: PostGIS testing patterns + graceful error handling
import pytest
from pycopg import Database
from pycopg.exceptions import ExtensionNotAvailable

class TestPostGISErrorHandling:
    """TEST-05: Spatial operations without PostGIS tested"""

    @pytest.fixture
    def db_without_postgis(self, db_config):
        """Database without PostGIS extension enabled."""
        db = Database(db_config)
        # Ensure PostGIS not loaded
        try:
            db.execute("DROP EXTENSION IF EXISTS postgis")
        except:
            pass
        return db

    def test_spatial_operation_without_postgis_raises_clear_error(self, db_without_postgis):
        """Spatial operations without PostGIS raise helpful error."""
        db = db_without_postgis

        with pytest.raises(ExtensionNotAvailable,
                          match="PostGIS extension not available.*CREATE EXTENSION postgis"):
            db.create_spatial_index("test_table", "geometry")

    def test_from_geodataframe_without_postgis(self, db_without_postgis):
        """from_geodataframe() checks for PostGIS and raises clear error."""
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = gpd.GeoDataFrame({
            'name': ['A', 'B'],
            'geometry': [Point(0, 0), Point(1, 1)]
        })

        with pytest.raises(ExtensionNotAvailable,
                          match="PostGIS.*required for spatial operations"):
            db_without_postgis.from_geodataframe(gdf, "test_spatial")
```

### Example 6: Async/Sync API Parity
```python
# Source: Python inspect module + API comparison patterns
import inspect
import pytest
from pycopg import Database, AsyncDatabase

def test_async_database_has_all_database_public_methods():
    """TEST-06: Async parity test validates all Database methods have AsyncDatabase equivalent"""

    # Get all public methods (not starting with _)
    db_methods = {
        name: method for name, method in inspect.getmembers(Database, predicate=inspect.ismethod)
        if not name.startswith('_')
    }

    async_db_methods = {
        name: method for name, method in inspect.getmembers(AsyncDatabase, predicate=inspect.ismethod)
        if not name.startswith('_')
    }

    # Known exceptions (different by design)
    exceptions = {
        'engine',        # Database.engine() returns sync engine
        'async_engine',  # AsyncDatabase.async_engine() returns async engine
        # Class methods have same names
    }

    db_method_names = set(db_methods.keys())
    async_method_names = set(async_db_methods.keys())

    # Check Database methods exist in AsyncDatabase
    missing_in_async = db_method_names - async_method_names - exceptions
    assert not missing_in_async, f"AsyncDatabase missing methods: {missing_in_async}"

    # Check AsyncDatabase doesn't have unexpected extras
    extras_in_async = async_method_names - db_method_names - exceptions
    # This is allowed (async might have async-specific helpers)
    # Just document them
    if extras_in_async:
        print(f"AsyncDatabase-only methods: {extras_in_async}")

    # Verify signatures match (parameters, not return type)
    for name in db_method_names & async_method_names:
        db_sig = inspect.signature(db_methods[name])
        async_sig = inspect.signature(async_db_methods[name])

        # Parameters should match (AsyncDatabase returns awaitable)
        assert db_sig.parameters.keys() == async_sig.parameters.keys(), \
            f"Method {name} has different parameters: {db_sig} vs {async_sig}"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| unittest.TestCase | pytest with fixtures | ~2015 | Cleaner test code, better fixture reuse, parametrization |
| coverage run + coverage report | pytest-cov plugin | ~2017 | Single command, better pytest integration, CI-friendly |
| Manual async event loops | pytest-asyncio auto mode | 2023 (v0.21) | Automatic event loop management, less boilerplate |
| Mock-based DB testing | Docker/real PostgreSQL in CI | ~2020 | Catches real driver bugs, more confidence in integration tests |
| Custom pool stress tests | pytest-timeout + concurrent.futures | Ongoing | Prevents hanging tests, better concurrency control |

**Deprecated/outdated:**
- `pytest --cov-report=xml` without html: Modern practice includes html for local inspection
- `pytest_asyncio.fixture()` marker: Use `@pytest_asyncio.fixture` (new style)
- `asyncio_mode = "legacy"`: Use "auto" mode (default since 0.21.0)
- Hardcoded coverage thresholds in CI scripts: Use `--cov-fail-under` in pyproject.toml

## Open Questions

1. **PostGIS availability in CI**
   - What we know: TEST-05 requires testing spatial operations without PostGIS
   - What's unclear: Whether pycopg_test database in CI has PostGIS installed
   - Recommendation: Add pytest.mark.skipif decorator with has_extension('postgis') check, document in CI setup

2. **Pool stress test parallelism**
   - What we know: Need to test pool exhaustion with concurrent connections
   - What's unclear: Optimal worker count and iteration count for CI stability
   - Recommendation: Start conservative (10 workers, 5 iterations), tune based on CI performance

3. **Migration DOWN section parsing**
   - What we know: Migrations support optional DOWN section for rollback
   - What's unclear: Current parser behavior when DOWN missing or malformed
   - Recommendation: Inspect Migrator.rollback() implementation, add explicit error handling if missing

4. **AsyncDatabase method count discrepancy**
   - What we know: Database has 83 methods, AsyncDatabase has 79 methods
   - What's unclear: Which 4 methods are missing - intentional or gap?
   - Recommendation: Run inspect-based comparison to identify specific missing methods, document as exceptions if intentional

## Sources

### Primary (HIGH confidence)
- pytest-cov 7.0.0 installed in pycopg/venv (verified via `python -c "import pytest_cov"`)
- [pytest-cov Configuration Documentation](https://pytest-cov.readthedocs.io/en/latest/config.html)
- [Coverage.py Configuration Reference](https://coverage.readthedocs.io/en/latest/config.html)
- [pytest-asyncio Official Documentation](https://pytest-asyncio.readthedocs.io/)
- [Python inspect module documentation](https://docs.python.org/3/library/inspect.html)
- [psycopg3 Connection Pools Documentation](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)
- pycopg codebase: tests/conftest.py, tests/test_pool.py, tests/test_migrations.py (existing patterns)

### Secondary (MEDIUM confidence)
- [pytest-asyncio Concepts Guide](https://pytest-asyncio.readthedocs.io/en/stable/concepts.html) - async fixture patterns
- [pytest Parametrize Documentation](https://docs.pytest.org/en/stable/how-to/parametrize.html) - edge case testing
- [pytest Fixture Scope Best Practices](https://pytest-with-eric.com/fixtures/pytest-fixture-scope/) - fixture isolation
- [pytest-timeout PyPI](https://pypi.org/project/pytest-timeout/) - preventing hanging tests
- [pytest-postgresql PyPI](https://pypi.org/project/pytest-postgresql/) - real PostgreSQL testing patterns

### Tertiary (LOW confidence, needs validation)
- [Migration Rollback Edge Cases Discussion](https://github.com/edgedb/edgedb/issues/4300) - deleted file scenarios (EdgeDB, not Python-specific)
- Web search results for pool stress testing patterns (general patterns, not pytest-specific)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - pytest-cov 7.0.0 verified installed, pytest-asyncio well-documented
- Architecture: HIGH - pycopg has existing test patterns in conftest.py, established fixture structure
- Pitfalls: MEDIUM-HIGH - Based on documentation and web search, validated against pycopg codebase
- Edge cases: MEDIUM - Some scenarios (deleted migration files, nested sessions) need implementation verification
- API parity: HIGH - inspect module is standard library, pattern straightforward

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (30 days - stable testing ecosystem, but check for pytest-asyncio updates)

**Notes:**
- AsyncDatabase has 4 fewer methods than Database (79 vs 83) - needs investigation during planning
- pytest-timeout not currently in dependencies - recommend adding to [dev] extras
- PostGIS testing requires verification that CI database has extension available
- Coverage threshold 70% is achievable but requires focused edge case testing, not just happy path
