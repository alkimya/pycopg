"""
pycopg - High-level Python API for PostgreSQL/PostGIS/TimescaleDB.

Simple, powerful, pythonic database operations.

Example:
    # Sync usage
    from pycopg import Database

    db = Database.from_env()
    db.list_schemas()
    db.list_tables("public")

    # Async usage
    from pycopg import AsyncDatabase

    db = AsyncDatabase.from_env()
    schemas = await db.list_schemas()

    # Connection pooling
    from pycopg import PooledDatabase, AsyncPooledDatabase

    db = PooledDatabase.from_env(min_size=5, max_size=20)
    with db.connection() as conn:
        conn.execute("SELECT * FROM users")

    # Migrations
    from pycopg import Migrator

    migrator = Migrator(db, "migrations/")
    migrator.migrate()

    # Roles & Permissions
    db.create_role("appuser", password="secret", login=True)
    db.grant("SELECT", "users", "appuser")

    # Backup & Restore
    db.pg_dump("backup.dump")
    db.pg_restore("backup.dump")
"""

from pycopg.database import Database
from pycopg.async_database import AsyncDatabase
from pycopg.config import Config
from pycopg.pool import PooledDatabase, AsyncPooledDatabase
from pycopg.migrations import Migrator
from pycopg.exceptions import (
    PycopgError,
    ConnectionError,
    ConfigurationError,
    ExtensionNotAvailable,
    TableNotFound,
    InvalidIdentifier,
    MigrationError,
)
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_interval,
    validate_index_method,
)

__version__ = "0.1.0"
__all__ = [
    # Core
    "Database",
    "AsyncDatabase",
    "Config",
    # Pooling
    "PooledDatabase",
    "AsyncPooledDatabase",
    # Migrations
    "Migrator",
    # Exceptions
    "PycopgError",
    "ConnectionError",
    "ConfigurationError",
    "ExtensionNotAvailable",
    "TableNotFound",
    "InvalidIdentifier",
    "MigrationError",
    # Utilities
    "validate_identifier",
    "validate_identifiers",
    "validate_interval",
    "validate_index_method",
    # Metadata
    "__version__",
]
