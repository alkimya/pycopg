"""Tests for pycopg.exceptions module."""

import pytest

from pycopg.exceptions import (
    ConfigurationError,
    ConnectionError,
    DatabaseExistsError,
    ExtensionNotAvailableError,
    InvalidIdentifierError,
    MigrationError,
    PycopgError,
    TableNotFoundError,
)


class TestExceptions:
    """Tests for custom exceptions."""

    def test_pycopg_error_base(self):
        """Test base PycopgError."""
        error = PycopgError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_connection_error(self):
        """Test ConnectionError inherits from PycopgError."""
        error = ConnectionError("Connection failed")
        assert isinstance(error, PycopgError)
        assert str(error) == "Connection failed"

    def test_configuration_error(self):
        """Test ConfigurationError inherits from PycopgError."""
        error = ConfigurationError("Invalid config")
        assert isinstance(error, PycopgError)
        assert str(error) == "Invalid config"

    def test_extension_not_available_error(self):
        """Test ExtensionNotAvailableError inherits from PycopgError."""
        error = ExtensionNotAvailableError("PostGIS not installed")
        assert isinstance(error, PycopgError)

    def test_table_not_found_error(self):
        """Test TableNotFoundError inherits from PycopgError."""
        error = TableNotFoundError("Table 'users' not found")
        assert isinstance(error, PycopgError)

    def test_invalid_identifier_error(self):
        """Test InvalidIdentifierError inherits from PycopgError."""
        error = InvalidIdentifierError("Invalid table name: DROP TABLE")
        assert isinstance(error, PycopgError)

    def test_database_exists_error(self):
        """Test DatabaseExistsError inherits from PycopgError."""
        error = DatabaseExistsError("Database already exists")
        assert isinstance(error, PycopgError)

    def test_migration_error(self):
        """Test MigrationError inherits from PycopgError."""
        error = MigrationError("Migration 001 failed")
        assert isinstance(error, PycopgError)
        assert str(error) == "Migration 001 failed"

    def test_exception_catching(self):
        """Test catching PycopgError catches all subclasses."""
        errors = [
            ConnectionError("conn"),
            ConfigurationError("config"),
            ExtensionNotAvailableError("ext"),
            TableNotFoundError("table"),
            InvalidIdentifierError("id"),
            MigrationError("migration"),
        ]

        for error in errors:
            try:
                raise error
            except PycopgError as e:
                assert e is error  # Correctly caught

    def test_exception_not_catching_unrelated(self):
        """Test PycopgError doesn't catch unrelated exceptions."""
        with pytest.raises(ValueError):
            try:
                raise ValueError("not pycopg")
            except PycopgError:
                pytest.fail("Should not catch ValueError")
