"""
pycopg - High-level Python API for PostgreSQL/PostGIS/TimescaleDB.

Simple, powerful, pythonic database operations.
"""

from typing import cast

from psycopg import IsolationLevel  # direct re-export — D-01 thin alias

from pycopg import exceptions
from pycopg.admin import AdminAccessor, AsyncAdminAccessor
from pycopg.async_database import AsyncDatabase
from pycopg.backup import AsyncBackupAccessor, BackupAccessor
from pycopg.base import Params
from pycopg.config import Config
from pycopg.database import Database, Page
from pycopg.etl import AsyncETLAccessor, ETLAccessor, Pipeline, RunResult
from pycopg.exceptions import (
    ConfigurationError,
    ConnectionError,
    DatabaseExistsError,
    ETLError,
    ETLTargetNotFoundError,
    ETLTransformError,
    ExtensionNotAvailableError,
    InvalidIdentifierError,
    MigrationError,
    PycopgError,
    TableNotFoundError,
    TimescaleError,
)
from pycopg.maint import AsyncMaintAccessor, MaintAccessor
from pycopg.migrations import Migrator
from pycopg.pool import AsyncPooledDatabase, PooledDatabase
from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor, TableDescription
from pycopg.spatial import AsyncSpatialAccessor, SpatialAccessor
from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_index_method,
    validate_interval,
)

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("pycopg")
except (
    PackageNotFoundError
):  # pragma: no cover — PackageNotFoundError only fires when package is not installed; never hit in test env
    __version__ = "0.0.0+unknown"

from pycopg.exceptions import _DEPRECATED_NAMES as _DEPRECATED_PACKAGE_ALIASES


def __getattr__(name: str) -> type:
    """Resolve deprecated exception names at the package level (PEP 562).

    Parameters
    ----------
    name : str
        Attribute name being accessed on the ``pycopg`` package.

    Returns
    -------
    type
        The canonical ``*Error`` class object from ``pycopg.exceptions``.

    Raises
    ------
    AttributeError
        If the name is not a known deprecated alias.
    """
    if name in _DEPRECATED_PACKAGE_ALIASES:
        import warnings

        new_name = _DEPRECATED_PACKAGE_ALIASES[name]
        warnings.warn(
            f"{name} is deprecated and will be removed in pycopg 2.0. "
            f"Use {new_name} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # getattr() with a dynamic string name is statically Any; every value in
        # _DEPRECATED_PACKAGE_ALIASES is a *Error class name defined in
        # pycopg.exceptions (D-01 genuinely-dynamic attribute lookup).
        return cast("type", getattr(exceptions, new_name))
    raise AttributeError(f"module 'pycopg' has no attribute {name!r}")


__all__ = [
    # Core
    "Database",
    "AsyncDatabase",
    "Config",
    "Page",
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
    # TimescaleDB
    "TimescaleAccessor",
    "AsyncTimescaleAccessor",
    # Admin
    "AdminAccessor",
    "AsyncAdminAccessor",
    # Maint
    "MaintAccessor",
    "AsyncMaintAccessor",
    # Backup
    "BackupAccessor",
    "AsyncBackupAccessor",
    # Schema
    "SchemaAccessor",
    "AsyncSchemaAccessor",
    "TableDescription",
    # Exceptions — canonical *Error names
    "PycopgError",
    "ConnectionError",
    "ConfigurationError",
    "DatabaseExistsError",
    "ETLError",
    "ETLTargetNotFoundError",
    "ETLTransformError",
    "ExtensionNotAvailableError",
    "TableNotFoundError",
    "TimescaleError",
    "InvalidIdentifierError",
    "MigrationError",
    # Deprecated aliases (resolved via __getattr__, removed in 2.0):
    "DatabaseExists",
    "ExtensionNotAvailable",
    "TableNotFound",
    "InvalidIdentifier",
    # Utilities
    "validate_identifier",
    "validate_identifiers",
    "validate_interval",
    "validate_index_method",
    # Types
    "IsolationLevel",
    "Params",
    # Metadata
    "__version__",
]
