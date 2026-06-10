"""
pycopg - High-level Python API for PostgreSQL/PostGIS/TimescaleDB.

Simple, powerful, pythonic database operations.
"""

from pycopg.async_database import AsyncDatabase
from pycopg.config import Config
from pycopg.database import Database
from pycopg.exceptions import (
    ConfigurationError,
    ConnectionError,
    DatabaseExists,
    ExtensionNotAvailable,
    InvalidIdentifier,
    MigrationError,
    PycopgError,
    TableNotFound,
)
from pycopg.migrations import Migrator
from pycopg.pool import AsyncPooledDatabase, PooledDatabase
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_index_method,
    validate_interval,
)

try:
    from importlib.metadata import PackageNotFoundError, version
    __version__ = version("pycopg")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
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
    "DatabaseExists",
    # Utilities
    "validate_identifier",
    "validate_identifiers",
    "validate_interval",
    "validate_index_method",
    # Metadata
    "__version__",
]
