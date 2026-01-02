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
