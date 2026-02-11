# Stack Research: Python Database Library Testing & Consolidation

**Domain:** Python database library (PostgreSQL)
**Researched:** 2026-02-11
**Confidence:** MEDIUM (training data from Jan 2025, no web verification available)

## Research Context

This research focuses on **incremental stack additions** for pycopg v0.3.0 consolidation. Existing core dependencies (psycopg 3, SQLAlchemy 2, pandas 2, pytest) are already in place and not re-evaluated here.

**Scope:**
- Testing infrastructure for real PostgreSQL databases
- Retry/backoff patterns for database operations
- Async/sync parity testing patterns
- Release and quality tooling

## Recommended Stack

### Testing Infrastructure

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| testcontainers[postgres] | ~4.8.2 | Isolated PostgreSQL instances per test suite | Industry standard for database integration tests. Manages Docker PostgreSQL containers with automatic cleanup. Better than pytest-postgresql for complex scenarios. |
| pytest-asyncio | ~0.24.0 | Async test support | Required for testing AsyncDatabase. Provides async fixtures and event loop management. Version 0.23+ has auto mode that reduces boilerplate. |
| pytest-xdist | ~3.6.1 | Parallel test execution | Runs tests in parallel to catch connection pool issues and improve CI speed. Critical for database libraries to verify thread safety. |
| coverage[toml] | ~7.6.9 | Code coverage with pyproject.toml config | Standard coverage tool. [toml] extra allows configuration in pyproject.toml instead of separate .coveragerc. |

### Retry/Backoff Patterns

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| tenacity | ~9.0.0 | Declarative retry with backoff | De facto standard for retry logic in Python. Cleaner than custom implementations. Supports exponential backoff, jitter, custom stop conditions. Used by major projects (OpenStack, etc). |

**Alternative:** Custom retry implementation with `time.sleep()` and exponential backoff. Only use if tenacity adds unacceptable dependency weight, but for a library already depending on psycopg/SQLAlchemy, tenacity is negligible.

### Release & Quality Tooling

| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| hatch | ~1.12.0 | Build backend & version management | Already in pyproject.toml. Modern replacement for setuptools. Handles versioning, builds, and environment management. |
| ruff | ~0.8.4 | Linting & formatting | Already in dev deps. Replaces black + flake8 + isort. 10-100x faster than alternatives. |
| mypy | ~1.13.0 | Static type checking | Missing from current stack. Critical for library code to catch type errors. Async code especially benefits from type checking. |
| pre-commit | ~4.0.1 | Git hooks for quality checks | Automates ruff, mypy, tests before commits. Prevents broken commits. |
| pytest-benchmark | ~5.1.0 | Performance regression testing | Optional but valuable for database library. Detects performance regressions in connection pooling, batch operations. |

### Documentation (Already in place)

| Tool | Current | Notes |
|------|---------|-------|
| Sphinx | ~8.1.3 | Already configured. Keep current version. |
| sphinx-rtd-theme | ~3.0.2 | Already configured for Read the Docs. |

## Supporting Libraries

### Async/Sync Parity Patterns

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| anyio | ~4.7.0 | Async abstraction layer | AVOID for pycopg. Adds complexity when psycopg 3 already provides sync/async. Better to maintain parallel implementations. |
| trio | ~0.27.0 | Alternative async runtime | AVOID. Stick with asyncio. psycopg 3 is asyncio-native. |

**Pattern Recommendation:** Maintain **parallel sync/async implementations** rather than runtime abstraction layers. This is what psycopg 3 does, and it's the right pattern for database libraries where performance and control matter.

### Database Testing Utilities

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Faker | ~33.1.0 | Generate test data | Useful for generating realistic test datasets. Better than hand-crafted test data for edge cases. |
| pytest-postgresql | ~6.1.1 | PostgreSQL fixtures | AVOID if using testcontainers. pytest-postgresql manages system PostgreSQL, less isolated than containers. Use testcontainers instead. |
| docker-py | (implicit) | Docker control | Required by testcontainers. Don't add explicitly; testcontainers brings it. |

## Installation

```bash
# Testing infrastructure (add to [dev])
pip install testcontainers[postgres]~=4.8.2
pip install pytest-asyncio~=0.24.0
pip install pytest-xdist~=3.6.1
pip install coverage[toml]~=7.6.9

# Retry/backoff (add to core dependencies)
pip install tenacity~=9.0.0

# Quality tooling (add to [dev])
pip install mypy~=1.13.0
pip install pre-commit~=4.0.1
pip install pytest-benchmark~=5.1.0  # Optional

# Test data generation (add to [dev], optional)
pip install Faker~=33.1.0
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| testcontainers | pytest-postgresql | Never for pycopg. testcontainers provides better isolation and matches real deployment environments. |
| testcontainers | Manual Docker management | Only if testcontainers has incompatibility issues. Managing containers manually is error-prone. |
| tenacity | backoff library | If you need simpler API. backoff uses decorators, tenacity has more features. For database ops, tenacity is better. |
| tenacity | Custom retry logic | Never for library code. Custom implementations miss edge cases (jitter, logging, max time limits). |
| mypy | pyright | If using VS Code with Pylance. Pyright is faster but mypy has better ecosystem support. Stick with mypy for library code. |
| pytest-asyncio auto mode | strict mode | If you have complex event loop requirements. Auto mode (default in 0.23+) is simpler for standard async tests. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| pytest-postgresql | Less isolated than containers. Requires system PostgreSQL installation. | testcontainers[postgres] |
| asyncio-compat wrappers | Adds runtime overhead and complexity. Database libraries need direct control. | Parallel sync/async implementations |
| unittest instead of pytest | pytest fixtures are superior for database testing. | pytest with fixtures |
| Coverage without TOML support | Requires separate .coveragerc file. | coverage[toml] |
| green/nose2 | Deprecated or unmaintained. pytest is the standard. | pytest |
| freezegun for time mocking | Can break asyncio event loops. Use with caution in async tests. | Manual time control or asyncio-aware mocking |

## Stack Patterns for v0.3.0 Consolidation

### Pattern 1: Isolated Test Database per Test Suite

**Implementation:**
```python
# conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres

@pytest.fixture(scope="session")
def db_config(postgres_container):
    return Config(
        host=postgres_container.get_container_host_ip(),
        port=postgres_container.get_exposed_port(5432),
        database=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
```

**Why:** Each test run gets clean PostgreSQL. Prevents test pollution. Matches CI environment.

### Pattern 2: Retry with Tenacity

**Implementation:**
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import psycopg

@retry(
    retry=retry_if_exception_type((psycopg.OperationalError, psycopg.DatabaseError)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
)
def connect_with_retry(config: Config):
    return psycopg.connect(**config.to_psycopg())
```

**Why:** Handles transient connection failures. Exponential backoff prevents overwhelming database. Configurable stop conditions.

**Advanced pattern with jitter:**
```python
from tenacity import wait_exponential_jitter

@retry(
    retry=retry_if_exception_type((psycopg.OperationalError,)),
    wait=wait_exponential_jitter(initial=1, max=10),
    stop=stop_after_attempt(5),
)
```

**Why jitter:** Prevents thundering herd when many clients retry simultaneously.

### Pattern 3: Async/Sync Test Parity

**Implementation:**
```python
# test_database.py (sync)
def test_execute_select(db):
    result = db.execute("SELECT 1 AS value")
    assert result[0]["value"] == 1

# test_async_database.py (async)
@pytest.mark.asyncio
async def test_execute_select(async_db):
    result = await async_db.execute("SELECT 1 AS value")
    assert result[0]["value"] == 1
```

**Structure:**
- Separate test files: `test_database.py` (sync) and `test_async_database.py` (async)
- Parallel test implementations, not shared
- Use `pytest.mark.asyncio` for async tests
- Separate fixtures: `db` vs `async_db`

**Why:** Clearer than parameterized tests. Catches async-specific issues. Easier to debug failures.

**Anti-pattern to avoid:**
```python
# DON'T DO THIS - parameterized sync/async in same test
@pytest.mark.parametrize("db_class", [Database, AsyncDatabase])
def test_execute(db_class):
    # This gets messy with async/await conditional logic
```

### Pattern 4: Connection Pool Testing with pytest-xdist

**Configuration:**
```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "-v --cov=pycopg --cov-report=term-missing -n auto"
```

**Why:** `-n auto` runs tests in parallel (one process per CPU). This stress-tests connection pools and catches thread safety issues that sequential tests miss.

**Caution:** Database fixtures must be `scope="session"` or tests will interfere. testcontainers handles this correctly.

### Pattern 5: Type Checking Async Code

**Configuration:**
```toml
# pyproject.toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

# Async-specific
warn_unused_ignores = true
check_untyped_defs = true

[[tool.mypy.overrides]]
module = "psycopg.*"
ignore_missing_imports = true
```

**Why:** Async code has more type complexity (Awaitable, Coroutine, AsyncIterator). mypy catches `await` on non-awaitable, missing `async`, etc.

**Critical for library code:** Users depend on type hints for IDE autocomplete and type safety.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| pytest-asyncio 0.24.x | Python 3.11-3.13 | Auto mode works with pytest 7.0+. |
| testcontainers 4.8.x | Docker 20.10+ | Requires Docker daemon. Won't work in environments without Docker. |
| tenacity 9.0.x | Python 3.8+ | No breaking changes from 8.x. Async support built-in. |
| pytest-xdist 3.6.x | pytest 7.0+ | Works with pytest-asyncio. Use `scope="session"` fixtures. |
| mypy 1.13.x | Python 3.11+ | Use `--python-version 3.11` flag. Supports Python 3.13. |

**PostgreSQL Version Compatibility:**
- testcontainers supports PostgreSQL 12-16
- Recommend testing against PostgreSQL 14 (stable) and 16 (latest)
- Use `PostgresContainer("postgres:14-alpine")` for faster CI

## Configuration Recommendations

### pytest-asyncio Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
```

**Why:**
- `auto` mode: Automatically detects async tests without `@pytest.mark.asyncio` on every test
- `session` scope: Reuses event loop across tests for performance

**Caution:** If you need strict event loop isolation per test, use `asyncio_mode = "strict"` and explicit marks.

### Coverage Configuration

```toml
# pyproject.toml
[tool.coverage.run]
source = ["pycopg"]
omit = ["*/tests/*", "*/venv/*"]
concurrency = ["thread", "greenlet"]  # If using gevent/eventlet

[tool.coverage.report]
precision = 2
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]

[tool.coverage.html]
directory = "htmlcov"
```

### pre-commit Configuration

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]

  - repo: local
    hooks:
      - id: pytest-quick
        name: pytest-quick
        entry: pytest tests/ -x --lf
        language: system
        pass_filenames: false
        always_run: true
```

**Why:** Catches issues before commit. `-x --lf` runs only previously failed tests for speed.

## Async/Sync Parity Best Practices

### 1. Maintain Parallel Implementations

**DO:**
```python
# pycopg/database.py
class Database:
    def execute(self, sql: str, params=None):
        with self._connect() as conn:
            return conn.execute(sql, params)

# pycopg/async_database.py
class AsyncDatabase:
    async def execute(self, sql: str, params=None):
        async with self._connect() as conn:
            return await conn.execute(sql, params)
```

**DON'T:**
```python
# Avoid runtime abstraction
class Database:
    def execute(self, sql, params=None):
        if self._is_async:
            return asyncio.run(self._async_execute(sql, params))
        return self._sync_execute(sql, params)
```

**Why:** Runtime abstraction adds overhead and complexity. Separate classes are clearer and faster.

### 2. Test Async Code with Async Assertions

**DO:**
```python
@pytest.mark.asyncio
async def test_async_transaction():
    async with db.transaction() as conn:
        await conn.execute("INSERT INTO users (name) VALUES ('test')")
        # Verify inside transaction
        result = await conn.execute("SELECT name FROM users WHERE name = 'test'")
        assert result[0]["name"] == "test"
```

**DON'T:**
```python
def test_async_transaction():
    # Don't use asyncio.run in tests - breaks pytest-asyncio event loop
    asyncio.run(async_transaction())
```

### 3. Use Separate Fixtures for Sync/Async

**DO:**
```python
# conftest.py
@pytest.fixture
def db(db_config):
    return Database(db_config)

@pytest.fixture
async def async_db(db_config):
    db = AsyncDatabase(db_config)
    yield db
    await db.close()
```

**DON'T:**
```python
# Don't parameterize sync/async - gets messy
@pytest.fixture(params=[Database, AsyncDatabase])
def db(request, db_config):
    return request.param(db_config)
```

### 4. Verify API Parity with Linting

**Pattern:**
```python
# tests/test_parity.py
import inspect
from pycopg import Database, AsyncDatabase

def test_api_parity():
    """Verify sync and async have matching methods."""
    sync_methods = {name for name, _ in inspect.getmembers(Database, inspect.isfunction)}
    async_methods = {name for name, _ in inspect.getmembers(AsyncDatabase, inspect.isfunction)}

    # Allow async-only methods (listen, notify, stream)
    async_only = {"listen", "notify", "stream"}

    assert sync_methods == async_methods - async_only, "API mismatch between sync/async"
```

**Why:** Catches when you add a method to one class but forget the other.

## Retry/Backoff Pattern Details

### Connection Retry Pattern

```python
from tenacity import (
    retry,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

logger = logging.getLogger(__name__)

@retry(
    retry=retry_if_exception_type((
        psycopg.OperationalError,
        psycopg.DatabaseError,
    )),
    wait=wait_exponential_jitter(initial=1, max=30),
    stop=stop_after_attempt(5) | stop_after_delay(60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def connect_with_retry(config: Config):
    return psycopg.connect(**config.to_psycopg())
```

**Features:**
- **Jittered exponential backoff:** 1s, 2s, 4s, 8s, 16s with random jitter
- **Max wait:** 30 seconds between attempts
- **Combined stop:** Stop after 5 attempts OR 60 seconds total
- **Logging:** Logs before each retry at WARNING level

### Query Retry Pattern (More Conservative)

```python
@retry(
    retry=retry_if_exception_type(psycopg.OperationalError),  # Only transient errors
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    stop=stop_after_attempt(3),
)
def execute_with_retry(conn, sql: str, params=None):
    return conn.execute(sql, params)
```

**Why more conservative:** Queries might have side effects. Only retry operational errors (connection lost), not data errors.

### Pool Checkout Retry Pattern

```python
from psycopg_pool import PoolTimeout

@retry(
    retry=retry_if_exception_type(PoolTimeout),
    wait=wait_exponential(multiplier=0.1, max=2),
    stop=stop_after_attempt(10),
)
def get_connection_from_pool(pool):
    return pool.connection(timeout=5)
```

**Why:** Pool exhaustion is transient. Retry quickly (0.1s multiplier) since pool might free up soon.

### Async Retry Pattern

```python
from tenacity import AsyncRetrying

async def async_connect_with_retry(config: Config):
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(psycopg.OperationalError),
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_attempt(5),
    ):
        with attempt:
            return await psycopg.AsyncConnection.connect(**config.to_psycopg())
```

**Note:** Use `AsyncRetrying` for async code, not `@retry` decorator. Allows proper async/await.

## Release Tooling Recommendations

### Versioning Strategy

Use **hatch** for version management:

```toml
# pyproject.toml
[tool.hatch.version]
path = "pycopg/__init__.py"
```

```python
# pycopg/__init__.py
__version__ = "0.3.0"
```

**Commands:**
```bash
# Bump version
hatch version minor  # 0.2.0 -> 0.3.0
hatch version patch  # 0.3.0 -> 0.3.1

# Build
hatch build

# Publish (after testing on test.pypi.org)
hatch publish
```

### CI/CD Pattern

**GitHub Actions pattern for database libraries:**

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
        postgres-version: ["14", "16"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[all,dev]"

      - name: Run tests with coverage
        run: |
          pytest -v --cov=pycopg --cov-report=xml
        env:
          POSTGRES_VERSION: ${{ matrix.postgres-version }}

      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

**Why testcontainers in CI:** GitHub Actions has Docker, so testcontainers works. No need for service containers.

### Documentation Build Verification

```bash
# Add to pre-commit or CI
cd docs/
make clean html
# Fails if documentation has errors
```

## Confidence Levels by Recommendation

| Recommendation | Confidence | Notes |
|----------------|------------|-------|
| testcontainers | HIGH | Standard for Python database testing. Well-maintained. |
| pytest-asyncio 0.24.x | MEDIUM | Version number from training data. Verify current version. |
| tenacity | HIGH | De facto standard for retry logic. Stable API. |
| Avoid pytest-postgresql | HIGH | testcontainers is superior for modern projects. |
| mypy for library code | HIGH | Critical for Python libraries with type hints. |
| Parallel sync/async implementations | HIGH | This is how psycopg 3 does it. Proven pattern. |
| pytest-xdist for pool testing | HIGH | Standard practice for concurrent code testing. |
| Version numbers | LOW | All versions from Jan 2025 training data. VERIFY before using. |

## Sources

**Note:** This research was completed without access to web search, WebFetch, or Context7 due to tool restrictions. All information is from training data (January 2025) and should be verified with official sources before implementation.

**Recommended verification:**
1. Check current versions: `pip index versions [package]`
2. Verify testcontainers-python docs: https://testcontainers-python.readthedocs.io/
3. Verify pytest-asyncio docs: https://pytest-asyncio.readthedocs.io/
4. Verify tenacity docs: https://tenacity.readthedocs.io/
5. Check psycopg 3 testing patterns: https://www.psycopg.org/psycopg3/docs/

---
*Stack research for: Python database library consolidation*
*Researched: 2026-02-11*
*Confidence: MEDIUM (training data only, web verification unavailable)*
