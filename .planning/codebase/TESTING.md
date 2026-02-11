# Testing Patterns

**Analysis Date:** 2026-02-11

## Test Framework

**Runner:**
- pytest 7.0.0+
- Config: `pyproject.toml` with `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest's built-in assertions (no separate library)
- Pattern: `assert condition` or `assert value == expected`
- Exception testing: `pytest.raises(ExceptionType)`

**Run Commands:**
```bash
pytest tests/ -v                           # Run all tests with verbose output
pytest tests/ -v --cov=pycopg              # Run with coverage report
pytest tests/ -v --cov=pycopg --cov-report=term-missing  # Coverage with missing lines
pytest tests/ -k test_name                 # Run specific test by name
pytest tests/test_database.py::TestDatabaseInit::test_init_with_config  # Run specific test class/method
pytest -m asyncio tests/test_async_database.py  # Run async tests
```

## Test File Organization

**Location:**
- Separate directory: `/home/loc/workspace/pycopg/tests/` (not co-located with source)
- Test database setup: `tests/setup_test_db.py`
- Fixtures and configuration: `tests/conftest.py`

**Naming:**
- Test files: `test_*.py` (e.g., `test_database.py`, `test_async_database.py`, `test_config.py`)
- Test classes: `Test*` (e.g., `TestDatabaseInit`, `TestDatabaseConnection`, `TestAsyncDatabaseInit`)
- Test methods: `test_*` (e.g., `test_init_with_config`, `test_connect_context`, `test_valid_identifier_simple`)
- Descriptive names explaining what is tested: `test_cursor_with_autocommit_no_commit` (not just `test_cursor`)

**Structure:**
```
tests/
├── conftest.py                    # pytest fixtures
├── setup_test_db.py              # Test database initialization
├── test_base.py                  # Base class tests
├── test_config.py                # Config class tests
├── test_database.py              # Sync Database tests
├── test_async_database.py        # Async Database tests
├── test_pool.py                  # Connection pool tests
├── test_migrations.py            # Migrations tests
├── test_utils.py                 # Utility function tests
├── test_exceptions.py            # Exception tests
├── test_integration.py           # Integration tests (real DB)
└── __init__.py                   # Empty, marks as package
```

## Test Structure

**Suite Organization:**
```python
class TestDatabaseInit:
    """Tests for Database initialization."""

    @patch("pycopg.database.psycopg")
    def test_init_with_config(self, mock_psycopg, config):
        """Test initialization with Config object."""
        db = Database(config)
        assert db.config == config

    @patch("pycopg.database.Config.from_env")
    def test_from_env(self, mock_from_env, mock_psycopg):
        """Test creating from environment."""
        mock_from_env.return_value = Config()
        db = Database.from_env()
        mock_from_env.assert_called_once()
        assert db.config is not None
```

**Patterns:**
- Setup: Use pytest fixtures from `conftest.py` for test data, mocks, and configs
- Teardown: Context managers and fixtures handle cleanup automatically
- Assertion: Multiple assertions per test (grouped by functionality), descriptive error messages

## Mocking

**Framework:** `unittest.mock` from Python standard library

**Patterns:**
```python
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

# Patch at module level where used
@patch("pycopg.database.psycopg")
def test_method(self, mock_psycopg, config):
    mock_conn = MagicMock()
    mock_psycopg.connect.return_value = mock_conn

    # Test code
    assert mock_conn.close.assert_called_once()

# Async mocking
mock_cursor = MagicMock()
mock_cursor.execute = AsyncMock()
mock_cursor.fetchall = AsyncMock(return_value=[])
```

**Helper Functions:**
- `create_async_cursor_mock(description=None, fetchall_result=None, fetchone_result=None, rowcount=1)` - creates properly mocked async cursor
- `create_async_conn_mock(cursor_mock)` - creates properly mocked async connection with context manager support
- Both helpers in `test_async_database.py` for reuse across async tests

**What to Mock:**
- External dependencies: `psycopg` module, database connections, subprocess calls
- SQLAlchemy engine when testing initialization (not needed when testing execute)
- Environment variables with `monkeypatch` fixture
- File I/O when testing backup/restore logic

**What NOT to Mock:**
- Custom exceptions (test the real exception class)
- Validation logic (test with real inputs/outputs)
- Helper functions from same module (test integration)
- Internal methods unless testing specifically for their interaction with mocks

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def config():
    """Create a test config."""
    return Config(
        host="localhost",
        port=5432,
        database="testdb",
        user="testuser",
        password="testpass",
    )

@pytest.fixture
def sample_migrations(temp_migrations_dir):
    """Create sample migration files."""
    migrations = [
        ("001_create_users.sql", """-- UP
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

-- DOWN
DROP TABLE users;
"""),
    ]
    for filename, content in migrations:
        (temp_migrations_dir / filename).write_text(content)
    return temp_migrations_dir
```

**Location:**
- Centralized in `tests/conftest.py` for shared fixtures
- Module-specific fixtures inline in test files when needed
- Fixtures defined with `@pytest.fixture` decorator
- Return values injected as test method parameters

**Built-in Fixtures Used:**
- `monkeypatch`: Modify environment variables, patch modules temporarily
- `tmp_path`, `tmpdir`, `tempfile`: Temporary file/directory creation

## Coverage

**Requirements:** Not explicitly enforced but coverage reports generated

**View Coverage:**
```bash
# Terminal report with missing lines
pytest tests/ -v --cov=pycopg --cov-report=term-missing

# HTML report (creates htmlcov/index.html)
pytest tests/ --cov=pycopg --cov-report=html

# XML report for CI/CD
pytest tests/ --cov=pycopg --cov-report=xml
```

**Coverage File:** `.coverage` file exists in root after running tests

## Test Types

**Unit Tests:**
- Scope: Individual functions and classes in isolation
- Approach: Mock external dependencies (database, files, subprocess)
- Examples: `test_init_with_config`, `test_validate_identifier_valid`, `test_valid_interval_day`
- Location: Most tests in `test_database.py`, `test_async_database.py`, `test_utils.py`, etc.
- ~230+ unit tests total covering validation, initialization, and API surface

**Integration Tests:**
- Scope: End-to-end functionality with real PostgreSQL database
- Approach: Mark with `@pytest.mark.integration` or `pytestmark = pytest.mark.integration`
- Requires: Real test database setup via `setup_test_db.py`
- Uses: `db_config` fixture pointing to `pycopg_test` database
- Examples: `TestIntegration.test_connection()`, `TestIntegration.test_authors_table()` in `test_integration.py`
- Run with: `pytest -m integration tests/test_integration.py`

**E2E Tests:**
- Not present - integration tests serve this purpose
- Would require Docker/PostgreSQL instance

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
class TestAsyncDatabaseConnection:
    """Tests for AsyncDatabase connection methods."""

    async def test_connect_context(self, config):
        """Test async connect context manager."""
        # Async test code using await
        async with db.connect() as conn:
            result = await db.execute("SELECT 1")
```

**Error Testing:**
```python
def test_invalid_identifier_sql_injection(self):
    """Test SQL injection attempts are rejected."""
    with pytest.raises(InvalidIdentifier):
        validate_identifier("users; DELETE FROM users;--")

    with pytest.raises(InvalidIdentifier):
        validate_identifier("users'--")

def test_missing_parameter(self):
    """Test missing required parameter raises error."""
    with pytest.raises(ValueError) as exc:
        Database.from_url(None)  # or missing required param
    assert "parameter" in str(exc.value).lower()
```

**Exception Inheritance Testing:**
```python
def test_exception_catching(self):
    """Test catching PycopgError catches all subclasses."""
    errors = [
        ConnectionError("conn"),
        ConfigurationError("config"),
        ExtensionNotAvailable("ext"),
    ]

    for error in errors:
        try:
            raise error
        except PycopgError as e:
            assert e is error  # Correctly caught
```

**Fixture Usage:**
```python
def test_from_env(self, mock_from_env, mock_psycopg):
    """Parameters are pytest fixtures or mocked patches."""
    mock_from_env.return_value = Config()
    db = Database.from_env()
    mock_from_env.assert_called_once()
```

---

*Testing analysis: 2026-02-11*
