"""
pycopg - High-level Python API for PostgreSQL/PostGIS/TimescaleDB.

Simple, powerful, pythonic database operations.
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
    DatabaseExists,
)
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_interval,
    validate_index_method,
)

try:
    from importlib.metadata import version, PackageNotFoundError
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
