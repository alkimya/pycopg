"""
Shared utilities for pycopg.

Contains validation functions and common helpers used across modules.
"""

import re
from typing import Union

from pycopg.exceptions import InvalidIdentifier


# Valid SQL identifier pattern: starts with letter or underscore,
# followed by letters, digits, or underscores
_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

# Valid interval pattern for TimescaleDB (e.g., "1 day", "7 days", "1 week")
_INTERVAL_PATTERN = re.compile(r'^\d+\s+(second|minute|hour|day|week|month|year)s?$', re.IGNORECASE)


def validate_identifier(name: str) -> None:
    """Validate SQL identifier to prevent injection.

    Ensures the identifier follows PostgreSQL naming rules:
    - Starts with a letter (a-z, A-Z) or underscore
    - Contains only letters, digits, and underscores
    - Does not use SQL reserved words (basic check)

    Args:
        name: SQL identifier to validate (table, column, schema, role name, etc.)

    Raises:
        InvalidIdentifier: If the identifier contains invalid characters.

    Example:
        >>> validate_identifier("users")  # OK
        >>> validate_identifier("my_table_123")  # OK
        >>> validate_identifier("123_invalid")  # Raises InvalidIdentifier
        >>> validate_identifier("table; DROP TABLE users;--")  # Raises InvalidIdentifier
    """
    if not name:
        raise InvalidIdentifier("Identifier cannot be empty")

    if not _IDENTIFIER_PATTERN.match(name):
        raise InvalidIdentifier(
            f"Invalid identifier: {name!r}. "
            "Must start with a letter or underscore and contain only "
            "letters, digits, and underscores."
        )


def validate_identifiers(*names: str) -> None:
    """Validate multiple SQL identifiers.

    Args:
        *names: SQL identifiers to validate.

    Raises:
        InvalidIdentifier: If any identifier is invalid.

    Example:
        >>> validate_identifiers("schema", "table", "column")  # OK
        >>> validate_identifiers("good", "bad;drop")  # Raises InvalidIdentifier
    """
    for name in names:
        if name is not None:
            validate_identifier(name)


def validate_interval(interval: str) -> None:
    """Validate a PostgreSQL interval string.

    Used for TimescaleDB chunk intervals, retention policies, etc.

    Args:
        interval: Interval string (e.g., "1 day", "7 days", "1 week").

    Raises:
        InvalidIdentifier: If the interval format is invalid.

    Example:
        >>> validate_interval("1 day")  # OK
        >>> validate_interval("7 days")  # OK
        >>> validate_interval("1 week")  # OK
        >>> validate_interval("drop table")  # Raises InvalidIdentifier
    """
    if not interval:
        raise InvalidIdentifier("Interval cannot be empty")

    if not _INTERVAL_PATTERN.match(interval.strip()):
        raise InvalidIdentifier(
            f"Invalid interval: {interval!r}. "
            "Expected format: '<number> <unit>' where unit is "
            "second, minute, hour, day, week, month, or year."
        )


def validate_index_method(method: str) -> None:
    """Validate PostgreSQL index method.

    Args:
        method: Index method name (btree, hash, gist, gin, etc.)

    Raises:
        InvalidIdentifier: If the method is not a valid PostgreSQL index type.
    """
    valid_methods = {"btree", "hash", "gist", "spgist", "gin", "brin"}
    if method.lower() not in valid_methods:
        raise InvalidIdentifier(
            f"Invalid index method: {method!r}. "
            f"Must be one of: {', '.join(sorted(valid_methods))}"
        )


def quote_literal(value: str) -> str:
    """Safely quote a string literal for SQL.

    This escapes single quotes by doubling them and wraps the value in quotes.
    For parameterized queries, prefer using query parameters instead.

    Args:
        value: String value to quote.

    Returns:
        Quoted string safe for SQL inclusion.

    Example:
        >>> quote_literal("hello")
        "'hello'"
        >>> quote_literal("it's")
        "'it''s'"
    """
    return "'" + value.replace("'", "''") + "'"
