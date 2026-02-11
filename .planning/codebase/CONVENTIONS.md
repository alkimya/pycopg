# Coding Conventions

**Analysis Date:** 2026-02-11

## Naming Patterns

**Files:**
- Lowercase with underscores: `database.py`, `async_database.py`, `config.py`, `migrations.py`
- Test files: `test_*.py` (e.g., `test_database.py`, `test_async_database.py`)
- Module docstring at file top explaining purpose

**Functions:**
- snake_case: `validate_identifier()`, `from_env()`, `insert_batch()`, `copy_insert()`
- Predicate functions start with `has_`, `is_`, or `exists_`: `has_extension()`, `table_exists()`, `schema_exists()`, `role_exists()`
- Private methods prefix with single underscore: `_build_insert_sql()`, `_psql_restore()`, `_session_conn`
- Factory methods as `@classmethod`: `from_env()`, `from_url()`, `create()` (e.g., `Database.from_env()`)

**Variables:**
- snake_case throughout: `db_config`, `mock_connection`, `schema_name`, `chunk_time_interval`
- Constants in UPPER_SNAKE_CASE: `_IDENTIFIER_PATTERN`, `_INTERVAL_PATTERN`
- Regex patterns prefixed with underscore: `_IDENTIFIER_PATTERN`, `_INTERVAL_PATTERN`
- Temporary/loop variables kept descriptive: `cur` for cursor, `conn` for connection (short but clear in context)

**Types:**
- Use PEP 484 type hints throughout: `def execute(self, sql: str, params: Optional[Sequence] = None) -> list[dict]:`
- Use modern Python 3.11+ union syntax `str | Path` instead of `Union[str, Path]`
- Use `Optional[T]` for nullable types: `Optional[str]`, `Optional[list[str]]`
- Sequence types use generic brackets: `list[dict]`, `list[str]`, `tuple[str, str]`
- Context managers return type with `Iterator`: `Iterator[psycopg.Connection]`
- Async contexts return `AsyncIterator`: `AsyncIterator[AsyncConnection]`

**Classes:**
- PascalCase: `Database`, `AsyncDatabase`, `Config`, `Migrator`
- Base/Abstract classes with `Base` suffix: `DatabaseBase`
- Mixin classes with `Mixin` suffix: `QueryMixin`
- Exception classes inherit from `PycopgError`: `ConnectionError(PycopgError)`, `ConfigurationError(PycopgError)`

## Code Style

**Formatting:**
- Tool: ruff (linter and formatter)
- Line length: 100 characters
- Target version: Python 3.11+
- Ruff selected rules: `["E", "F", "W", "I", "N", "UP"]` (style, logical errors, warnings, imports, naming, upgrading syntax)
- Ruff ignore: `["E501"]` (ignore line-too-long, handled separately)

**Linting:**
- Rules selected: E (PEP 8), F (PyFlakes), W (warnings), I (imports), N (naming), UP (upgrade syntax)
- Enforced naming convention: Functions/variables snake_case, Classes PascalCase
- No F401 (unused imports) - all imports are used
- No E302 violations - proper spacing around class definitions

**Import Organization:**
- Order:
  1. `from __future__ import annotations` (at top for forward references)
  2. Standard library imports (sorted): `import re`, `from contextlib import contextmanager`, `from pathlib import Path`, `from typing import ...`
  3. Third-party imports (sorted): `import psycopg`, `from sqlalchemy import ...`
  4. Local/relative imports: `from pycopg import ...`
  5. Conditional imports in try/except: `try: from dotenv import load_dotenv`

**Path Aliases:**
- No alias imports detected - uses absolute imports from package root: `from pycopg import Database`, `from pycopg.config import Config`

## Error Handling

**Patterns:**
- Custom exception hierarchy rooted in `PycopgError` defined in `pycopg/exceptions.py`
- Specific exceptions for different error types: `ConnectionError`, `ConfigurationError`, `InvalidIdentifier`, `TableNotFound`, `ExtensionNotAvailable`, `MigrationError`
- Validation functions raise `InvalidIdentifier` with descriptive messages: `raise InvalidIdentifier(f"Invalid identifier: {name!r}. Must start with...")`
- SQL injection prevention through identifier validation before building queries: `validate_identifier(name)`, `validate_identifiers(table, schema, *columns)`
- Resource cleanup in finally blocks (context managers handle this):
  ```python
  try:
      yield conn
  finally:
      conn.close()
  ```
- Subprocess errors caught and re-raised with context: `if result.returncode != 0: raise RuntimeError(f"pg_dump failed: {result.stderr}")`

## Logging

**Framework:** Standard Python `print()` - no logging library detected

**Patterns:**
- No logging configured
- Errors propagated as exceptions, not logged
- Tracebacks rely on exception raising for visibility

## Comments

**When to Comment:**
- Module docstrings required explaining purpose and usage
- Class docstrings with description and attributes (e.g., "Attributes: config, engine")
- Complex SQL queries or validation logic documented with comments explaining the "why"
- Section headers as comments separating major functionality areas:
  ```python
  # =========================================================================
  # DATABASE ADMINISTRATION
  # =========================================================================
  ```

**JSDoc/TSDoc:**
- Uses Google-style docstrings (not Sphinx/RST)
- Format:
  ```python
  """Short description.

  Longer description if needed.

  Args:
      param1: Description.
      param2: Description.

  Returns:
      Description of return value.

  Example:
      code_example()
  """
  ```
- All public methods documented with Args, Returns, Example sections
- Raises documented when exceptions are raised: `Raises: InvalidIdentifier: If...`

## Function Design

**Size:** Generally 10-50 lines for public methods
- Longer methods (100+ lines) are administrative/bulk operations: `pg_dump()`, `pg_restore()`, `from_geodataframe()` are acceptable due to parameter handling and subprocess management
- Database class is large (~2300 lines) with logical groupings by functionality sections

**Parameters:**
- Keep positional parameters minimal - use keyword arguments with defaults
- Common patterns: `table: str`, `schema: str = "public"`, `if_exists: bool = True`
- Optional parameters are `Optional[Type]` with default `None`
- Literal types for constrained choices: `Literal["fail", "replace", "append"]`, `Literal["plain", "custom", "directory", "tar"]`
- SQL keywords and clauses built as keyword args: `on_delete: str = "NO ACTION"`, `on_update: str = "NO ACTION"`

**Return Values:**
- Consistent return types: functions return `list[dict]` for query results, `int` for row counts, `None` for mutations
- Dict rows always use lowercase keys matching database column names
- Empty results return `[]` not `None`
- Single row fetching returns `Optional[dict]` (None if not found)
- Batch methods return count of affected rows: `-> int`

## Module Design

**Exports:**
- Central `__init__.py` exports main API in `__all__`:
  ```python
  __all__ = [
      "Database", "AsyncDatabase", "Config",
      "PooledDatabase", "AsyncPooledDatabase",
      "Migrator",
      "PycopgError", "ConnectionError", ...
      "validate_identifier", ...
      "__version__",
  ]
  ```
- Version in `__init__.py`: `__version__ = "0.2.0"`

**Barrel Files:**
- `pycopg/__init__.py` is the primary barrel file, importing and re-exporting all public classes
- Module-specific exports handled in `__init__.py` with explicit `__all__`
- No internal barrel files within subdirectories

---

*Convention analysis: 2026-02-11*
