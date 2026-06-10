# Phase 13: Qualité documentaire (docstrings numpydoc + interrogate) - Pattern Map

**Mapped:** 2026-06-10
**Files analyzed:** 13 new/modified files
**Analogs found:** 12 / 13

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/exceptions.py` | model | — | `pycopg/exceptions.py` (self) | exact (addition only) |
| `pycopg/__init__.py` | config/entry-point | — | `pycopg/__init__.py` (self) | exact (line 63 patch) |
| `pycopg/database.py` | service | CRUD / request-response | `pycopg/async_database.py` | role-match (mirror module) |
| `pycopg/async_database.py` | service | CRUD / request-response | `pycopg/database.py` | role-match (mirror module) |
| `pycopg/base.py` | model/mixin | — | `pycopg/database.py` (parent pattern) | role-match |
| `pycopg/config.py` | config | — | `pycopg/utils.py` | role-match |
| `pycopg/utils.py` | utility | transform | `pycopg/utils.py` (self) | exact |
| `pycopg/migrations.py` | service | CRUD | `pycopg/migrations.py` (self) | exact |
| `pycopg/pool.py` | service | request-response | `pycopg/pool.py` (self) | exact |
| `pyproject.toml` | config | — | `pyproject.toml` (self, existing `[tool.*]`) | exact (append sections) |
| `.github/workflows/tests.yml` | config/CI | — | `.github/workflows/tests.yml` (self, existing steps) | exact (append steps) |
| `docs/conf.py` | config | — | `docs/conf.py` (self) | exact (append flag) |
| `tests/test_version.py` | test | — | `tests/test_exceptions.py` | role-match |

---

## Pattern Assignments

### `pycopg/exceptions.py` — add `DatabaseExists`

**Analog:** `pycopg/exceptions.py` (lines 1-38, read above)

**Existing class pattern** (lines 26-38) — copy exactly:
```python
class TableNotFound(PycopgError):
    """Table does not exist."""
    pass


class InvalidIdentifier(PycopgError):
    """Invalid SQL identifier (potential injection attempt)."""
    pass


class MigrationError(PycopgError):
    """Error during database migration."""
    pass
```

**Addition — insert after `MigrationError`:**
```python
class DatabaseExists(PycopgError):
    """Database already exists."""
    pass
```

**Rule (D-03):** Single inheritance from `PycopgError` only. No `(PycopgError, ValueError)`.

---

### `pycopg/__init__.py` — `__version__` via `importlib.metadata`

**Analog:** `pycopg/__init__.py` (line 63)

**Current line 63:**
```python
__version__ = "0.3.1"
```

**Replacement (D-09) — 3-line patch:**
```python
try:
    from importlib.metadata import version, PackageNotFoundError
    __version__ = version("pycopg")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
```

**Constraint:** `__version__` stays in `__all__` at line 88 — do not remove it.

**Export update:** Add `DatabaseExists` to the `from pycopg.exceptions import (...)` block and to `__all__` alongside the other exceptions.

---

### `pycopg/database.py` — Google→numpydoc docstring migration + exception conversion

**Analog for docstring format:** `pycopg/async_database.py` (mirror module, same pattern count)

**Google-style (current) — representative example** (`database.py` lines 194-213):
```python
def create_from_env(
    cls,
    name: str,
    ...
) -> Database:
    """Create a new database using connection params from environment.

    Uses PGHOST, PGPORT, PGUSER, PGPASSWORD from environment or .env file,
    then creates the database and returns a connection to it.

    Args:
        name: Name of the database to create.
        owner: Optional owner role for the new database.
        template: Template database (default: template1).
        if_not_exists: If True, don't error if database already exists.
        dotenv_path: Optional path to .env file.

    Returns:
        Database instance connected to the newly created database.

    Example:
        # Uses credentials from .env or environment
        db = Database.create_from_env("myapp")
```

**Numpydoc shallow target format (D-06) — same method converted:**
```python
def create_from_env(
    cls,
    name: str,
    ...
) -> Database:
    """Create a new database using connection params from environment.

    Uses PGHOST, PGPORT, PGUSER, PGPASSWORD from environment or .env file,
    then creates the database and returns a connection to it.

    Parameters
    ----------
    name : str
        Name of the database to create.
    owner : str, optional
        Owner role for the new database.
    template : str, optional
        Template database, by default "template1".
    if_not_exists : bool, optional
        If True, don't error if database already exists.
    dotenv_path : str or Path, optional
        Path to .env file.

    Returns
    -------
    Database
        Instance connected to the newly created database.
    """
```

**Migration rules:**
- `Args:` → `Parameters\n----------` (10 dashes — exact length of "Parameters")
- `Returns:` → `Returns\n-------` (7 dashes)
- `Raises:` → `Raises\n------` (6 dashes)
- `Example:` / `Examples:` section → **delete entirely** (D-06)
- Parameter format: `name : type\n    Description.` (4-space indent, period at end)
- Optional params: append `, optional` to the type
- Default values: append `, by default <value>` in the description line

**Exception conversion — `database.py` 7 sites (DOC-09 / D-01):**

Site pattern at `database.py:167`:
```python
# BEFORE:
raise ValueError(f"Database '{name}' already exists")

# AFTER:
raise DatabaseExists(f"Database '{name}' already exists")
```

Site pattern at `database.py:1369-1371` (and 6 similar TimescaleDB/PostGIS sites):
```python
# BEFORE:
raise RuntimeError(
    "PostGIS extension not installed. Run db.create_extension('postgis')"
)

# AFTER (message text preserved per D-01):
raise ExtensionNotAvailable(
    "PostGIS extension not installed. Run db.create_extension('postgis')"
)
```

**Import addition at top of `database.py`:**
```python
from pycopg.exceptions import (
    ...
    ExtensionNotAvailable,
    DatabaseExists,  # add
)
```

---

### `pycopg/async_database.py` — same as database.py + `async_engine` annotation

**Analog:** `pycopg/database.py` (mirror)

**Same docstring migration rules as database.py above. Additionally:**

**`async_engine` annotation fix (TY2 / DOC-12):**

Current (`async_database.py:90-92`):
```python
@property
def async_engine(self):
    """Get or create async SQLAlchemy engine (lazy initialization)."""
```

Target (TYPE_CHECKING guard to avoid eager import):
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

@property
def async_engine(self) -> AsyncEngine:
    """Get or create async SQLAlchemy engine (lazy initialization)."""
```

**Analog for `-> Engine` pattern:** `database.py:231` (`@property def engine(self) -> Engine:`).

**`_async_engine` attribute type** (`async_database.py:88`): update `self._async_engine = None` to `self._async_engine: AsyncEngine | None = None` (requires `from __future__ import annotations`).

---

### `pycopg/base.py` — Google→numpydoc migration

**Analog:** `pycopg/base.py` itself (5 Google-style docstrings)

**Current Google-style example** (`base.py:25-29`):
```python
def __init__(self, config: Config):
    """Initialize database with configuration.

    Args:
        config: Database configuration.
    """
```

**Numpydoc target:**
```python
def __init__(self, config: Config):
    """Initialize database with configuration.

    Parameters
    ----------
    config : Config
        Database configuration.
    """
```

**Note:** `from_env` and `from_url` classmethods have both `Args:` and `Returns:` — apply full migration.

---

### `pycopg/utils.py` — Google→numpydoc migration (10 sites)

**Analog:** `pycopg/utils.py` itself

**Current style** (`utils.py:48`+): `Args:`, `Returns:`, `Raises:` sections — apply standard migration rules.

---

### `pycopg/migrations.py` — Google→numpydoc migration (7 sites)

**Analog:** `pycopg/migrations.py` itself (`migrations.py:40-65` shows `Args:`/`Returns:`/`Raises:` pattern)

---

### `pycopg/pool.py` — Google→numpydoc migration (13 sites)

**Analog:** `pycopg/pool.py` itself

---

### `pycopg/config.py` — Google→numpydoc migration (7 sites)

**Analog:** `pycopg/utils.py` (same utility/config role)

---

### `pyproject.toml` — add `[tool.interrogate]`, `[tool.mypy]`, dev deps

**Analog:** existing `[tool.*]` sections in `pyproject.toml` (lines 80-103)

**Existing `[tool.*]` pattern** (lines 80-103):
```toml
[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "W", "I", "N", "UP"]
ignore = ["E501"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=92"
asyncio_mode = "auto"

[tool.coverage.run]
source = ["pycopg"]
omit = ["*/tests/*", "*/venv/*"]
```

**New sections to append after `[tool.coverage.report]`:**
```toml
[tool.interrogate]
ignore-init-method = true
ignore-init-module = false
ignore-magic = false
ignore-semiprivate = false
ignore-private = false
ignore-module = false
ignore-property-decorators = false
fail-under = 95
exclude = ["tests", "docs", "setup.py"]
verbose = 0
quiet = false
color = true

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = false
disallow_untyped_defs = false
check_untyped_defs = true
no_implicit_optional = true

[[tool.mypy.overrides]]
module = "sqlalchemy.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "psycopg.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "psycopg_pool.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "geopandas.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "geoalchemy2.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "shapely.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tenacity.*"
ignore_missing_imports = true
```

**Dev deps addition** (`pyproject.toml` lines 63-69):
```toml
[dependency-groups]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-asyncio>=0.23.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "interrogate>=1.7.0",   # ADD
    "mypy>=2.1.0",           # ADD
]
```

---

### `.github/workflows/tests.yml` — add interrogate, sphinx-build, mypy steps

**Analog:** existing `steps:` block in `tests.yml` (lines 32-58)

**Existing step pattern** (lines 52-58):
```yaml
      - name: Run tests
        env:
          PGHOST: localhost
          PGUSER: postgres
          PGPASSWORD: postgres
          PGPORT: "5432"
        run: uv run pytest
```

**New steps to append after "Run tests" step:**
```yaml
      - name: Check docstring coverage
        run: uv run interrogate pycopg --fail-under 95 --quiet

      - name: Build Sphinx docs (napoleon non-regression)
        run: |
          uv run pip install -r docs/requirements.txt
          uv run sphinx-build -W --keep-going -b html docs docs/_build/html

      - name: mypy type check
        continue-on-error: true
        run: uv run mypy pycopg/
```

**Note (D-05):** `continue-on-error: true` on mypy step only — interrogate and sphinx-build are blocking.

---

### `docs/conf.py` — add `napoleon_numpy_docstring`

**Analog:** `docs/conf.py` lines 20-28 (existing extensions block)

**Existing napoleon entry** (line 25):
```python
    'sphinx.ext.napoleon',   # Google/NumPy docstring support
```

**Addition after line 28 (end of extensions list), as a new block:**
```python
# Napoleon settings
napoleon_numpy_docstring = True    # Enable NumPy-style docstring parsing
# napoleon_google_docstring remains True (default) during migration;
# disable after all modules are converted.
```

---

### `tests/test_version.py` — new test for DOC-10

**Analog:** `tests/test_exceptions.py` (lines 1-14 — import pattern, class structure)

**Import pattern** from `tests/test_exceptions.py:1-13`:
```python
"""Tests for pycopg.exceptions module."""

import pytest

from pycopg.exceptions import (
    PycopgError,
    ...
)
```

**Target file:**
```python
"""Tests for pycopg.__version__ (DOC-10)."""

import pycopg


class TestVersion:
    """Tests for package version metadata."""

    def test_version_is_string(self):
        """__version__ is a non-empty string."""
        assert isinstance(pycopg.__version__, str)
        assert len(pycopg.__version__) > 0

    def test_version_format(self):
        """__version__ follows semver-like format x.y.z."""
        parts = pycopg.__version__.split(".")
        assert len(parts) >= 2

    def test_version_in_all(self):
        """__version__ is exported in __all__."""
        assert "__version__" in pycopg.__all__
```

---

### Tests — update `pytest.raises` for exception conversion (D-04)

**Analog for update pattern:** `tests/test_exceptions.py:37-40`

```python
# Current pattern in tests/test_exceptions.py (model for how assertions are written):
def test_extension_not_available(self):
    """Test ExtensionNotAvailable inherits from PycopgError."""
    error = ExtensionNotAvailable("PostGIS not installed")
    assert isinstance(error, PycopgError)
```

**Update pattern for converted sites:**

In `tests/test_database_integration.py:869`:
```python
# BEFORE:
with pytest.raises(RuntimeError, match="TimescaleDB extension not installed"):

# AFTER:
from pycopg.exceptions import ExtensionNotAvailable
with pytest.raises(ExtensionNotAvailable, match="TimescaleDB extension not installed"):
```

In `tests/test_async_database.py` (8 sites — lines 740, 2248, 2295, 2317, 2339, 2372, 2396, 2616):
```python
# Lines 740, 2248, 2295, 2317, 2339, 2372, 2396 — RuntimeError → ExtensionNotAvailable:
with pytest.raises(ExtensionNotAvailable, match="...extension not installed")

# Line 2616 — ValueError → DatabaseExists:
from pycopg.exceptions import DatabaseExists
with pytest.raises(DatabaseExists, match="already exists")
```

**Import to add at top of each updated test file:**
```python
from pycopg.exceptions import ExtensionNotAvailable, DatabaseExists
```

---

## Shared Patterns

### Numpydoc Section Headers
**Apply to:** All 187 Google-style docstrings in 7 modules

```
Parameters          Returns             Raises
----------          -------             ------
name : type         type                ExceptionType
    Description.        Description.        When it is raised.
```

Dash count = exact `len(section_name)`:
- `Parameters` → 10 dashes
- `Returns` → 7 dashes
- `Raises` → 6 dashes

Blank line required after the header-underline before first parameter.

### TYPE_CHECKING import guard
**Source:** `pycopg/migrations.py:32-34` (established project pattern)
**Apply to:** `async_database.py` for `AsyncEngine` annotation

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine
```

### `PycopgError` inheritance pattern
**Source:** `pycopg/exceptions.py:6-38`
**Apply to:** `DatabaseExists` addition

```python
class ExceptionName(PycopgError):
    """One-line summary."""
    pass
```

Single inheritance only. No `pass` body beyond the docstring for leaf exception classes.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| None | — | — | All files have close analogs in the codebase |

---

## Metadata

**Analog search scope:** `pycopg/`, `tests/`, `.github/workflows/`, `docs/`, `pyproject.toml`
**Files scanned:** 13 files read directly + 5 grep queries
**Pattern extraction date:** 2026-06-10
