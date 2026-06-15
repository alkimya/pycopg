"""
pycopg - High-level Python API for PostgreSQL/PostGIS/TimescaleDB.

Simple, powerful, pythonic database operations.
"""

from pycopg.async_database import AsyncDatabase
from pycopg.config import Config
from pycopg.database import Database
from pycopg.etl import AsyncETLAccessor, ETLAccessor, Pipeline, RunResult
from pycopg.exceptions import (
    ConfigurationError,
    ConnectionError,
    DatabaseExists,
    ETLError,
    ETLTargetNotFoundError,
    ETLTransformError,
    ExtensionNotAvailable,
    InvalidIdentifier,
    MigrationError,
    PycopgError,
    TableNotFound,
)
from pycopg.migrations import Migrator
from pycopg.pool import AsyncPooledDatabase, PooledDatabase
from pycopg.spatial import AsyncSpatialAccessor, SpatialAccessor
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
    # Spatial
    "SpatialAccessor",
    "AsyncSpatialAccessor",
    # ETL
    "ETLAccessor",
    "AsyncETLAccessor",
    "RunResult",
    "Pipeline",
    # Exceptions
    "PycopgError",
    "ConnectionError",
    "ConfigurationError",
    "DatabaseExists",
    "ETLError",
    "ETLTargetNotFoundError",
    "ETLTransformError",
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
