"""
Custom exceptions for pycopg.
"""

import warnings as _warnings


class PycopgError(Exception):
    """Base exception for pycopg errors."""

    pass


class ConnectionError(PycopgError):
    """Error connecting to the database."""

    pass


class ConfigurationError(PycopgError):
    """Error in configuration (missing env vars, invalid URL, etc.)."""

    pass


class ExtensionNotAvailableError(PycopgError):
    """Required extension is not installed."""

    pass


class TableNotFoundError(PycopgError):
    """Table does not exist."""

    pass


class InvalidIdentifierError(PycopgError):
    """Invalid SQL identifier (potential injection attempt)."""

    pass


class MigrationError(PycopgError):
    """Error during database migration."""

    pass


class DatabaseExistsError(PycopgError):
    """Database already exists."""

    pass


class TimescaleError(PycopgError):
    """Error raised by TimescaleDB management operations."""

    pass


class ETLError(PycopgError):
    """Base exception for ETL pipeline errors."""

    pass


class ETLTransformError(ETLError):
    """Error raised when a pipeline transform function fails."""

    pass


class ETLTargetNotFoundError(ETLError):
    """Error raised when an append-mode load target table is missing."""

    pass


_DEPRECATED_NAMES: dict[str, str] = {
    "ExtensionNotAvailable": "ExtensionNotAvailableError",
    "TableNotFound": "TableNotFoundError",
    "InvalidIdentifier": "InvalidIdentifierError",
    "DatabaseExists": "DatabaseExistsError",
}


def __getattr__(name: str) -> type:
    """Resolve deprecated exception names with a DeprecationWarning (PEP 562).

    Parameters
    ----------
    name : str
        Attribute name being accessed.

    Returns
    -------
    type
        The canonical ``*Error`` class object.

    Raises
    ------
    AttributeError
        If the name is not a known deprecated alias.
    """
    if name in _DEPRECATED_NAMES:
        new = _DEPRECATED_NAMES[name]
        _warnings.warn(
            f"pycopg.exceptions.{name} is deprecated and will be removed in "
            f"pycopg 2.0. Use {new} instead.",
            DeprecationWarning,
            stacklevel=2,  # points to caller's import line, not exceptions.py
        )
        return globals()[new]
    raise AttributeError(f"module 'pycopg.exceptions' has no attribute {name!r}")
