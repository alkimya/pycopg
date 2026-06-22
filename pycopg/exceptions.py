"""
Custom exceptions for pycopg.
"""


class PycopgError(Exception):
    """Base exception for pycopg errors."""

    pass


class ConnectionError(PycopgError):
    """Error connecting to the database."""

    pass


class ConfigurationError(PycopgError):
    """Error in configuration (missing env vars, invalid URL, etc.)."""

    pass


class ExtensionNotAvailable(PycopgError):
    """Required extension is not installed."""

    pass


class TableNotFound(PycopgError):
    """Table does not exist."""

    pass


class InvalidIdentifier(PycopgError):
    """Invalid SQL identifier (potential injection attempt)."""

    pass


class MigrationError(PycopgError):
    """Error during database migration."""

    pass


class DatabaseExists(PycopgError):
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
