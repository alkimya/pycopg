# Codebase Structure

**Analysis Date:** 2026-02-11

## Directory Layout

```
/home/loc/workspace/pycopg/
├── pycopg/                          # Main library source code
│   ├── __init__.py                  # Public API exports
│   ├── database.py                  # Sync database class (2299 lines)
│   ├── async_database.py            # Async database class (768 lines)
│   ├── config.py                    # Connection configuration (244 lines)
│   ├── pool.py                      # Connection pooling (416 lines)
│   ├── migrations.py                # SQL migration system (392 lines)
│   ├── base.py                      # Shared base classes & mixins (194 lines)
│   ├── queries.py                   # Centralized SQL query constants (269 lines)
│   ├── utils.py                     # Validation & helper functions (133 lines)
│   └── exceptions.py                # Custom exception hierarchy (38 lines)
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── conftest.py                  # Pytest fixtures for all tests
│   ├── setup_test_db.py             # Test database setup
│   ├── test_database.py             # Database class tests
│   ├── test_async_database.py       # AsyncDatabase tests
│   ├── test_config.py               # Config class tests
│   ├── test_pool.py                 # PooledDatabase tests
│   ├── test_migrations.py           # Migrator tests
│   ├── test_base.py                 # Base class tests
│   ├── test_utils.py                # Utility function tests
│   ├── test_exceptions.py           # Exception tests
│   └── test_integration.py          # Integration tests with real DB
├── docs/                            # Sphinx documentation
│   ├── source/                      # RST source files
│   ├── build/                       # Generated HTML/PDF
│   └── Makefile                     # Build documentation
├── .github/                         # GitHub Actions workflows
│   └── workflows/
├── .planning/                       # GSD planning documents
│   └── codebase/                    # Architecture/structure analysis
├── pyproject.toml                   # Project metadata & dependencies
├── README.md                        # User documentation
├── LICENSE                          # MIT license
├── .gitignore                       # Git ignore rules
└── .readthedocs.yaml                # ReadTheDocs configuration
```

## Directory Purposes

**pycopg/ (Main Library):**
- Purpose: High-level PostgreSQL API implementation
- Contains: Core classes for sync/async database access, configuration, pooling, migrations
- Key files: `database.py` (primary sync API), `async_database.py` (async equivalent)
- No external dependencies in files except psycopg, sqlalchemy, optional python-dotenv

**tests/ (Test Suite):**
- Purpose: Unit, integration, and functional testing
- Contains: Test modules for each public class, fixtures, test database setup
- Key files: `conftest.py` (shared fixtures), integration tests
- Uses pytest, unittest.mock, and optional pytest-asyncio

**docs/ (Documentation):**
- Purpose: API documentation and user guides
- Contains: Sphinx-based RST documentation, generated HTML/PDF
- Built via ReadTheDocs on each push

**.planning/ (GSD Planning):**
- Purpose: Codebase analysis documents for AI-assisted development
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md

## Key File Locations

**Entry Points:**
- `pycopg/__init__.py`: Public API exports (Database, AsyncDatabase, Config, Migrator, exceptions, utils)
- `pycopg/database.py`: Sync Database class, primary entry point for most operations
- `pycopg/async_database.py`: Async Database class for async/await applications

**Configuration:**
- `pycopg/config.py`: Config dataclass for connection parameters
- `pyproject.toml`: Package metadata, dependencies, test configuration, build settings
- `.readthedocs.yaml`: ReadTheDocs build configuration

**Core Logic:**
- `pycopg/database.py`: Execute queries, manage transactions, DataFrame operations, schema introspection (2299 lines - largest file)
- `pycopg/async_database.py`: Async equivalent of Database (768 lines)
- `pycopg/pool.py`: Connection pooling wrapper around psycopg_pool (416 lines)
- `pycopg/migrations.py`: SQL migration file parsing and execution (392 lines)
- `pycopg/queries.py`: SQL query constants for all database operations (269 lines)
- `pycopg/base.py`: DatabaseBase, QueryMixin, SessionMixin shared abstractions (194 lines)

**Utilities:**
- `pycopg/utils.py`: validate_identifier, validate_identifiers, validate_interval, validate_index_method (133 lines)
- `pycopg/exceptions.py`: Custom exception hierarchy (38 lines)

**Testing:**
- `tests/conftest.py`: Pytest fixtures (db_config, config, mock_connection, temp_migrations_dir, sample_migrations, env_vars, database_url_env)
- `tests/test_database.py`: Database class tests with mocks
- `tests/test_integration.py`: Tests against real PostgreSQL database
- `tests/test_async_database.py`: AsyncDatabase tests with pytest-asyncio

## Naming Conventions

**Files:**
- Class files match class name: `database.py` contains Database class, `config.py` contains Config
- Test files: `test_*.py` (pytest convention)
- Module files use lowercase: `queries.py`, `utils.py`, `exceptions.py`

**Directories:**
- `pycopg/`: library package (lowercase, no underscores)
- `tests/`: test package (lowercase)
- `docs/`: documentation (lowercase)
- `.github/`: GitHub-specific (dot-prefix for hidden directories)
- `.planning/`: GSD planning (dot-prefix)

**Functions/Methods:**
- Sync methods: lowercase_with_underscores (e.g., `execute()`, `list_tables()`, `to_dataframe()`)
- Async methods: same naming as sync equivalents (e.g., `async def execute()`)
- Private methods: underscore prefix (e.g., `_get_session_connection()`, `_build_insert_sql()`)
- Factory methods: lowercase_with_underscores (e.g., `from_env()`, `from_url()`)
- Context managers: lowercase_with_underscores (e.g., `connection()`, `cursor()`, `session()`, `transaction()`)

**Classes:**
- PascalCase: Database, AsyncDatabase, PooledDatabase, AsyncPooledDatabase, Config, Migration, Migrator
- Exception classes: PascalCase ending in "Error" (e.g., PycopgError, ConnectionError, ConfigurationError)
- Mixin classes: PascalCase ending in "Mixin" (e.g., QueryMixin, SessionMixin)
- Dataclass: Config (also PascalCase)

**Variables/Constants:**
- Instance variables: lowercase_with_underscores (e.g., `self.config`, `self._engine`, `self._session_conn`)
- Query constants: UPPERCASE_WITH_UNDERSCORES (e.g., `LIST_SCHEMAS`, `TABLE_EXISTS`)
- Module-level regex patterns: _LOWERCASE_WITH_LEADING_UNDERSCORE (e.g., `_IDENTIFIER_PATTERN`)

## Where to Add New Code

**New Feature (Database Operation):**
- Sync implementation: Add method to `pycopg/database.py`
- Async equivalent: Add method to `pycopg/async_database.py`
- SQL constant: Add to `pycopg/queries.py` if reusable query
- Tests: Add test class/methods to `tests/test_database.py` and `tests/test_async_database.py`
- Helper logic: Extract shared query building to QueryMixin in `pycopg/base.py`

**New Component/Module:**
- Main class: Create new file `pycopg/module_name.py`
- If shared by sync/async: Use mixin pattern in `pycopg/base.py`
- Exceptions: Add to `pycopg/exceptions.py`
- Tests: Create `tests/test_module_name.py`
- Export: Add to `__all__` in `pycopg/__init__.py`

**Utilities:**
- Validation functions: `pycopg/utils.py` (lines 21-134)
- Shared helpers: `pycopg/base.py` for mixins, `pycopg/queries.py` for SQL
- Query constants: Always add to `pycopg/queries.py` for consistency and reuse

**Tests:**
- Unit tests (mocked): `tests/test_*.py` using unittest.mock
- Integration tests (real DB): `tests/test_integration.py` using db_config fixture
- Async tests: Use `@pytest.mark.asyncio` decorator, `async def test_*()`
- Fixtures: Add to `tests/conftest.py` if used by multiple test files

## Special Directories

**dist/:**
- Purpose: Built distributions (wheels, source distributions)
- Generated: Yes (by `python -m build`)
- Committed: No (.gitignore excludes dist/)

**.git/:**
- Purpose: Git repository metadata
- Generated: Yes (created by git init)
- Committed: No (not part of working tree)

**venv/:**
- Purpose: Python virtual environment for development
- Generated: Yes (by `python -m venv venv`)
- Committed: No (.gitignore excludes venv/)

**.pytest_cache/:**
- Purpose: Pytest cache directory
- Generated: Yes (by pytest runs)
- Committed: No (.gitignore excludes .pytest_cache/)

**.coverage:**
- Purpose: Coverage.py data file for test coverage tracking
- Generated: Yes (by pytest with --cov flag)
- Committed: No (.gitignore should exclude, currently doesn't)

**docs/build/:**
- Purpose: Generated Sphinx documentation (HTML, PDF)
- Generated: Yes (by `make html` in docs/)
- Committed: No (.gitignore excludes docs/build/)

**__pycache__/:**
- Purpose: Python bytecode cache
- Generated: Yes (by Python interpreter)
- Committed: No (.gitignore excludes __pycache__/)

## File Organization Patterns

**Large Files (>1000 lines):**
- `database.py` (2299 lines): Contains all Database methods; consider refactoring into:
  - Core query execution (execute, execute_many)
  - DDL operations (create_table, alter_table, drop_table)
  - Schema introspection (list_schemas, list_tables, table_info)
  - DataFrame operations (to_dataframe, from_dataframe)
  - Admin operations (roles, grants, backup/restore)
  - PostGIS operations
  - TimescaleDB operations

**Medium Files (400-800 lines):**
- `async_database.py` (768 lines): Parallel to Database for async operations
- `pool.py` (416 lines): PooledDatabase and AsyncPooledDatabase wrappers
- `migrations.py` (392 lines): Migration and Migrator classes

**Small Files (<300 lines):**
- `config.py` (244 lines): Configuration only
- `queries.py` (269 lines): SQL query strings
- `base.py` (194 lines): Abstract base classes and mixins
- `utils.py` (133 lines): Validation functions
- `exceptions.py` (38 lines): Exception definitions
- `__init__.py` (89 lines): Public API exports

## Import Organization

**Canonical Import Pattern** (from Database/AsyncDatabase):
```python
from __future__ import annotations

from contextlib import contextmanager  # or asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Sequence

import psycopg  # or psycopg.AsyncConnection
from psycopg.rows import dict_row
from sqlalchemy import create_engine, text

from pycopg.config import Config
from pycopg.utils import validate_identifier, validate_identifiers
from pycopg import queries

if TYPE_CHECKING:
    import pandas as pd
    import geopandas as gpd
```

**Import Groups:**
1. `from __future__` annotations
2. Standard library (contextlib, pathlib, typing, etc.)
3. External libraries (psycopg, sqlalchemy, pandas-like)
4. Internal pycopg imports (config, utils, queries)
5. TYPE_CHECKING imports (optional dependencies)

## Code Patterns to Maintain

**Class Initialization:**
```python
def __init__(self, config: Config):
    """Initialize with docstring."""
    self.config = config
    self._optional_cache: Optional[Type] = None
```

**Factory Methods:**
```python
@classmethod
def from_env(cls, dotenv_path: Optional[str | Path] = None) -> "ClassName":
    """Create from environment variables."""
    return cls(Config.from_env(dotenv_path))

@classmethod
def from_url(cls, url: str) -> "ClassName":
    """Create from connection URL."""
    return cls(Config.from_url(url))
```

**Context Managers (Sync):**
```python
@contextmanager
def connection(self, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """Context manager for connection."""
    conn = psycopg.connect(**self.config.connect_params(), autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()
```

**Context Managers (Async):**
```python
@asynccontextmanager
async def connection(self, autocommit: bool = False) -> AsyncIterator[AsyncConnection]:
    """Async context manager for connection."""
    conn = await psycopg.AsyncConnection.connect(
        **self.config.connect_params(), autocommit=autocommit
    )
    try:
        yield conn
    finally:
        await conn.close()
```

**Query Building:**
```python
@staticmethod
def _build_insert_sql(
    table: str,
    columns: list[str],
    schema: str = "public",
    on_conflict: Optional[str] = None,
) -> tuple[str, str]:
    """Build INSERT SQL template."""
    validate_identifiers(table, schema, *columns)
    # ... construction with %s placeholders
    return sql, cols_str
```

**Method Documentation:**
```python
def method_name(self, param1: str, param2: Optional[int] = None) -> SomeType:
    """One-line summary.

    Longer description if needed.

    Args:
        param1: What this parameter means.
        param2: Optional parameter description.

    Returns:
        Description of return value.

    Example:
        >>> result = db.method_name("value")
    """
```
