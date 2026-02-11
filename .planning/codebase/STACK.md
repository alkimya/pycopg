# Technology Stack

**Analysis Date:** 2026-02-11

## Languages

**Primary:**
- Python 3.11+ - Core language for the library
- SQL - PostgreSQL/PostGIS queries

## Runtime

**Environment:**
- Python 3.11, 3.12, 3.13 (officially supported)
- OS independent (runs on Linux, macOS, Windows)

**Package Manager:**
- pip - Primary package manager
- Lockfile: Not used (project uses pyproject.toml pinned versions)

## Frameworks & Core Libraries

**Database:**
- psycopg 3.1.0+ - PostgreSQL driver (native async support, COPY protocol)
- psycopg_pool 3.2.0+ - Connection pooling for sync and async

**ORM & Data:**
- SQLAlchemy 2.0.0+ - SQL generation and DataFrame operations
- pandas 2.0.0+ - Tabular data processing and DataFrame support

**Optional Geospatial:**
- geopandas 0.14.0+ - Geospatial DataFrame operations
- geoalchemy2 0.14.0+ - SQLAlchemy spatial types
- shapely 2.0.0+ - Geometric objects

**Configuration:**
- python-dotenv 1.0.0+ - .env file support (optional)

## Build System

**Build Tool:**
- hatchling - Build backend for wheel/sdist packaging

**Configuration File:**
- `pyproject.toml` - Single source of truth for build, dependencies, metadata

## Development Tools

**Testing:**
- pytest 7.0.0+ - Test runner
- pytest-cov 4.0.0+ - Coverage reporting
- pytest-asyncio 0.23.0+ - Async test support

**Code Quality:**
- black 23.0.0+ - Code formatter
- ruff 0.1.0+ - Fast linter and import sorter
  - Line length: 100 characters
  - Target version: Python 3.11+
  - Checks: E, F, W, I, N, UP

**Documentation:**
- Sphinx 7.0.0+ - Documentation generator
- myst-parser 2.0.0+ - Markdown support in Sphinx
- furo 2024.0.0+ - Modern Sphinx theme
- sphinx-autobuild 2024.0.0+ - Live documentation reloading
- sphinx-copybutton 0.5.0+ - Copy-to-clipboard for code blocks
- sphinx-intl 2.1.0+ - Internationalization support

## Configuration Files

**Location:** `/home/loc/workspace/pycopg/`

**Core Configuration:**
- `pyproject.toml` - Package metadata, dependencies, build config, tool settings
- `.readthedocs.yaml` - ReadTheDocs build configuration (Python 3.12, Sphinx docs)

**Development:**
- `docs/requirements.txt` - Documentation build dependencies (Sphinx ecosystem)

**CI/CD:**
- `.github/workflows/publish.yml` - GitHub Actions workflow for PyPI publishing

## Platform Requirements

**Development:**
- Python 3.11+ with pip
- PostgreSQL 10+ (for testing and connection)
- Virtual environment (venv at `pycopg/venv/`)

**Production:**
- Python 3.11, 3.12, or 3.13
- PostgreSQL 10+ (any version)
- psycopg and psycopg_pool packages

**Optional (PostGIS):**
- PostgreSQL PostGIS extension
- geopandas, geoalchemy2, shapely packages

**Optional (TimescaleDB):**
- PostgreSQL TimescaleDB extension (no additional Python deps)

## Testing Configuration

**Test Runner Setup:** `pytest.ini_options` in `pyproject.toml`
- Test paths: `tests/`
- Coverage reporting: terminal + missing lines
- Coverage module: `pycopg/`
- CLI: `pytest tests/ -v`

**Run Commands:**
```bash
# All tests with coverage
pytest tests/ -v

# Watch mode with pytest-watch (requires watchdog)
pytest-watch tests/

# Coverage report only
pytest tests/ --cov=pycopg --cov-report=html
```

## Version Information

**Current:** pycopg v0.2.0 (released January 2026)

**Python Support:**
- Minimum: 3.11
- Recommended: 3.12+
- Maximum tested: 3.13

---

*Stack analysis: 2026-02-11*
