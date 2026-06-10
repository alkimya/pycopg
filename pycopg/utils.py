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

# Valid timestamp pattern for VALID UNTIL (date or date+time, optional tz offset).
# e.g. "2025-12-31", "2025-12-31 23:59:59", "2025-12-31T23:59:59+02:00", "infinity".
_TIMESTAMP_PATTERN = re.compile(
    r'^(infinity|-infinity|\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?'
    r'(\s*[+-]\d{2}(:?\d{2})?)?)?)$',
    re.IGNORECASE,
)

# Extension names may contain hyphens (e.g. "uuid-ossp"); they are emitted
# inside double quotes, so allow letters, digits, underscore and hyphen only.
_EXTENSION_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_-]*$')

# Whitelisted SQL privileges for GRANT/REVOKE.
_VALID_PRIVILEGES = frozenset({
    "SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER",
    "USAGE", "CREATE", "CONNECT", "TEMPORARY", "TEMP", "EXECUTE", "ALL",
    "ALL PRIVILEGES", "MAINTAIN", "SET", "ALTER SYSTEM",
})

# Whitelisted object types for GRANT/REVOKE.
_VALID_OBJECT_TYPES = frozenset({
    "TABLE", "SEQUENCE", "FUNCTION", "PROCEDURE", "ROUTINE", "SCHEMA",
    "DATABASE", "TABLESPACE", "TYPE", "DOMAIN", "LANGUAGE", "FOREIGN DATA WRAPPER",
    "FOREIGN SERVER", "LARGE OBJECT", "PARAMETER",
})


def validate_identifier(name: str) -> None:
    """Validate SQL identifier to prevent injection.

    Ensures the identifier follows PostgreSQL naming rules:
    - Starts with a letter (a-z, A-Z) or underscore
    - Contains only letters, digits, and underscores
    - Does not use SQL reserved words (basic check)

    Parameters
    ----------
    name : str
        SQL identifier to validate (table, column, schema, role name, etc.)

    Raises
    ------
    InvalidIdentifier
        If the identifier contains invalid characters.
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

    Parameters
    ----------
    *names : str
        SQL identifiers to validate.

    Raises
    ------
    InvalidIdentifier
        If any identifier is invalid.
    """
    for name in names:
        if name is not None:
            validate_identifier(name)


def validate_interval(interval: str) -> None:
    """Validate a PostgreSQL interval string.

    Used for TimescaleDB chunk intervals, retention policies, etc.

    Parameters
    ----------
    interval : str
        Interval string (e.g., "1 day", "7 days", "1 week").

    Raises
    ------
    InvalidIdentifier
        If the interval format is invalid.
    """
    if not interval:
        raise InvalidIdentifier("Interval cannot be empty")

    if not _INTERVAL_PATTERN.match(interval.strip()):
        raise InvalidIdentifier(
            f"Invalid interval: {interval!r}. "
            "Expected format: '<number> <unit>' where unit is "
            "second, minute, hour, day, week, month, or year."
        )


def validate_extension_name(name: str) -> None:
    """Validate a PostgreSQL extension name.

    Like :func:`validate_identifier` but also permits hyphens, since some
    extensions (e.g. ``uuid-ossp``) contain them. The name is emitted inside
    double quotes in the generated SQL.

    Parameters
    ----------
    name : str
        Extension name (e.g. ``'postgis'``, ``'uuid-ossp'``).

    Raises
    ------
    InvalidIdentifier
        If the name contains invalid characters.
    """
    if not name:
        raise InvalidIdentifier("Extension name cannot be empty")

    if not _EXTENSION_NAME_PATTERN.match(name):
        raise InvalidIdentifier(
            f"Invalid extension name: {name!r}. "
            "Must start with a letter or underscore and contain only "
            "letters, digits, underscores, and hyphens."
        )


def validate_timestamp(value: str) -> None:
    """Validate a timestamp/date string for SQL interpolation.

    Used for clauses such as ``VALID UNTIL`` where the value cannot be passed
    as a bound parameter and is interpolated into the statement.

    Parameters
    ----------
    value : str
        Date or timestamp string (e.g. ``'2025-12-31'``,
        ``'2025-12-31 23:59:59'``, ``'infinity'``).

    Raises
    ------
    InvalidIdentifier
        If the value is not a recognized date/timestamp form.
    """
    if not value:
        raise InvalidIdentifier("Timestamp cannot be empty")

    if not _TIMESTAMP_PATTERN.match(value.strip()):
        raise InvalidIdentifier(
            f"Invalid timestamp: {value!r}. "
            "Expected an ISO date/timestamp such as '2025-12-31' or "
            "'2025-12-31 23:59:59', or 'infinity'."
        )


def validate_privileges(privileges: str) -> None:
    """Validate SQL privilege keyword(s) for GRANT/REVOKE against a whitelist.

    Parameters
    ----------
    privileges : str
        A privilege keyword, or several joined by commas
        (e.g. ``'SELECT'``, ``'SELECT, INSERT'``, ``'ALL'``).

    Raises
    ------
    InvalidIdentifier
        If any privilege is not a recognized SQL privilege.
    """
    if not privileges:
        raise InvalidIdentifier("Privileges cannot be empty")

    for priv in privileges.split(","):
        token = priv.strip().upper()
        if token not in _VALID_PRIVILEGES:
            raise InvalidIdentifier(
                f"Invalid privilege: {priv.strip()!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_PRIVILEGES))}"
            )


def validate_object_type(object_type: str) -> None:
    """Validate a GRANT/REVOKE object type against a whitelist.

    Parameters
    ----------
    object_type : str
        Object type keyword (e.g. ``'TABLE'``, ``'SCHEMA'``).

    Raises
    ------
    InvalidIdentifier
        If the object type is not recognized.
    """
    if not object_type or object_type.strip().upper() not in _VALID_OBJECT_TYPES:
        raise InvalidIdentifier(
            f"Invalid object type: {object_type!r}. "
            f"Must be one of: {', '.join(sorted(_VALID_OBJECT_TYPES))}"
        )


def validate_csv_option(value: str, name: str, max_length: int = 32) -> None:
    """Validate a COPY ... CSV option value interpolated into a SQL literal.

    Rejects single quotes and backslashes (which could break out of the quoted
    literal) and over-long values. Used for ``delimiter``, ``null`` and
    ``encoding`` options that cannot be passed as bound parameters.

    Parameters
    ----------
    value : str
        The option value.
    name : str
        Option name, used in the error message.
    max_length : int, optional
        Maximum allowed length, by default 32.

    Raises
    ------
    InvalidIdentifier
        If the value contains quotes/backslashes or is too long.
    """
    if "'" in value or "\\" in value:
        raise InvalidIdentifier(
            f"Invalid {name}: {value!r} must not contain quotes or backslashes."
        )
    if len(value) > max_length:
        raise InvalidIdentifier(
            f"Invalid {name}: {value!r} exceeds maximum length of {max_length}."
        )


def validate_index_method(method: str) -> None:
    """Validate PostgreSQL index method.

    Parameters
    ----------
    method : str
        Index method name (btree, hash, gist, gin, etc.)

    Raises
    ------
    InvalidIdentifier
        If the method is not a valid PostgreSQL index type.
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

    Parameters
    ----------
    value : str
        String value to quote.

    Returns
    -------
    str
        Quoted string safe for SQL inclusion.
    """
    return "'" + value.replace("'", "''") + "'"
