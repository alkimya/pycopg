# External Integrations

**Analysis Date:** 2026-02-11

## Database Connections

**PostgreSQL:**
- Service: PostgreSQL 10+ (self-hosted or cloud)
- Client: psycopg 3.1.0+ (native Python driver)
- Connection: DSN string or individual parameters
- Auth: Username/password, SSL mode support
- Pooling: psycopg_pool for connection management

**Environment Variables:**
- `DATABASE_URL` - Full PostgreSQL connection URL (highest priority)
- `DB_HOST` / `PGHOST` - Database hostname (default: localhost)
- `DB_PORT` / `PGPORT` - Database port (default: 5432)
- `DB_NAME` / `PGDATABASE` - Database name (default: postgres)
- `DB_USER` / `PGUSER` - Database user (default: postgres)
- `DB_PASSWORD` / `PGPASSWORD` - Database password (empty by default)
- `DB_SSLMODE` / `PGSSLMODE` - SSL connection mode (optional)

## Configuration Management

**Environment Files:**
- `.env` support via python-dotenv (optional dependency)
- Configuration: `pycopg/config.py` (`Config` class)
- Methods:
  - `Config.from_env()` - Load from environment or .env file
  - `Config.from_url()` - Parse PostgreSQL connection URL
  - `Config()` - Direct instantiation with parameters

**Config Class Methods:**
- `.dsn` property - Generate psycopg DSN format
- `.url` property - Generate SQLAlchemy PostgreSQL URL (with psycopg driver)
- `.connect_params()` - Get dict for psycopg.connect()
- `.with_database()` - Clone config with different database name

## Data Processing Integrations

**pandas Integration:**
- Library: pandas 2.0.0+
- Location: `pycopg/database.py`, `pycopg/async_database.py`
- Methods:
  - `Database.from_dataframe()` - Create table from DataFrame
  - `Database.to_dataframe()` - Read table/query into DataFrame
  - AsyncDatabase equivalents with `async with`

**geopandas Integration (Optional):**
- Library: geopandas 0.14.0+
- Additional deps: geoalchemy2 0.14.0+, shapely 2.0.0+
- Location: `pycopg/database.py` (geo methods)
- Methods:
  - `Database.from_geodataframe()` - Create spatial table from GeoDataFrame
  - `Database.to_geodataframe()` - Read table into GeoDataFrame with spatial geometry

## PostgreSQL Extensions

**PostGIS Support:**
- Extension: CREATE EXTENSION postgis
- Integration: `Database.create_extension("postgis")`
- Spatial operations: ST_Within, ST_MakeEnvelope, ST_Intersects, etc.
- Data type: geometry/geography columns
- Dependencies: geopandas, geoalchemy2, shapely

**TimescaleDB Support:**
- Extension: CREATE EXTENSION timescaledb
- Integration: `Database.create_extension("timescaledb")`
- Hypertable methods:
  - `Database.create_hypertable()`
  - `Database.enable_compression()`
  - `Database.add_compression_policy()`
  - `Database.add_retention_policy()`
- No additional Python dependencies required

## Documentation & Hosting

**Documentation Platform:**
- ReadTheDocs (RTD)
- URL: https://pycopg.readthedocs.io
- Config file: `.readthedocs.yaml`
- Build environment: Ubuntu 24.04, Python 3.12
- Theme: Furo (modern, dark mode compatible)

**Internationalization:**
- Tool: sphinx-intl
- Supported languages: French (fr) with English (en) fallback
- Configuration: Sphinx multi-language setup

## Package Distribution

**PyPI (Python Package Index):**
- Package name: pycopg
- Repository: https://github.com/alkimya/pycopg
- Release trigger: GitHub release published
- Build system: GitHub Actions + python-build
- Upload: PyPI trusted publisher (OIDC)
- CI workflow: `.github/workflows/publish.yml`

**Publishing Process:**
1. GitHub release triggers `publish.yml`
2. Build wheel and source distribution
3. Upload to PyPI via `pypa/gh-action-pypi-publish`

## Version Control & Collaboration

**Repository:**
- Platform: GitHub
- URL: https://github.com/alkimya/pycopg
- Issues: GitHub Issues
- Releases: GitHub Releases

**License:**
- MIT License
- Author: Loc Cosnier (loc.cosnier@pm.me)

## Backup & Restore Integration

**pg_dump/pg_restore:**
- Binary integration: Requires PostgreSQL tools installed
- Methods in `Database`:
  - `pg_dump()` - Export to .dump or .sql (custom, plain, directory formats)
  - `pg_restore()` - Import from backup files

**CSV Export/Import:**
- Methods: `copy_to_csv()`, `copy_from_csv()`
- Uses PostgreSQL COPY protocol for high performance

## LISTEN/NOTIFY (Pub/Sub)

**PostgreSQL Native Pub/Sub:**
- Async only: `AsyncDatabase.listen()`, `AsyncDatabase.notify()`
- No external message broker required
- Uses PostgreSQL as lightweight event bus

## Migration Framework

**SQL-Based Migrations:**
- Framework: Custom `Migrator` class in `pycopg/migrations.py`
- Tracking: `schema_migrations` table
- Format: Numbered SQL files with UP/DOWN sections
- Methods:
  - `Migrator.migrate()` - Apply pending migrations
  - `Migrator.rollback()` - Revert migrations
  - `Migrator.status()` - Check migration state

## No Direct External API Integrations

**Notable Absent:**
- No Stripe, AWS, or third-party APIs
- No authentication providers (auth handled by PostgreSQL roles)
- No external caching (optional future: Redis integration)
- No monitoring/observability platforms (no APM)
- No webhook system (built-in PostgreSQL LISTEN/NOTIFY available)

---

*Integration audit: 2026-02-11*
