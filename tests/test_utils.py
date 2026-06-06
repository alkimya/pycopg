"""Tests for pycopg.utils module."""

import pytest

from pycopg.utils import (
    quote_literal,
    validate_csv_option,
    validate_extension_name,
    validate_identifier,
    validate_identifiers,
    validate_index_method,
    validate_interval,
    validate_object_type,
    validate_privileges,
    validate_timestamp,
)
from pycopg.exceptions import InvalidIdentifier


class TestValidateIdentifier:
    """Tests for validate_identifier function."""

    def test_valid_identifier_simple(self):
        """Test simple valid identifiers."""
        validate_identifier("users")
        validate_identifier("table_name")
        validate_identifier("MyTable")

    def test_valid_identifier_with_underscore_prefix(self):
        """Test identifiers starting with underscore."""
        validate_identifier("_private")
        validate_identifier("_internal_table")

    def test_valid_identifier_with_numbers(self):
        """Test identifiers with numbers."""
        validate_identifier("users123")
        validate_identifier("table_2024")
        validate_identifier("v2_schema")

    def test_invalid_identifier_empty(self):
        """Test empty identifier raises error."""
        with pytest.raises(InvalidIdentifier) as exc:
            validate_identifier("")
        assert "cannot be empty" in str(exc.value)

    def test_invalid_identifier_starts_with_number(self):
        """Test identifier starting with number raises error."""
        with pytest.raises(InvalidIdentifier):
            validate_identifier("123users")

    def test_invalid_identifier_with_hyphen(self):
        """Test identifier with hyphen raises error."""
        with pytest.raises(InvalidIdentifier):
            validate_identifier("user-table")

    def test_invalid_identifier_with_space(self):
        """Test identifier with space raises error."""
        with pytest.raises(InvalidIdentifier):
            validate_identifier("DROP TABLE")

    def test_invalid_identifier_sql_injection(self):
        """Test SQL injection attempts are rejected."""
        with pytest.raises(InvalidIdentifier):
            validate_identifier("users; DELETE FROM users;--")

        with pytest.raises(InvalidIdentifier):
            validate_identifier("users'--")


class TestValidateIdentifiers:
    """Tests for validate_identifiers function."""

    def test_valid_identifiers_multiple(self):
        """Test multiple valid identifiers pass."""
        validate_identifiers("schema", "table", "column")

    def test_valid_identifiers_with_none(self):
        """Test that None values are skipped."""
        validate_identifiers("schema", None, "column")

    def test_invalid_identifiers_one_invalid(self):
        """Test that one invalid identifier raises error."""
        with pytest.raises(InvalidIdentifier):
            validate_identifiers("good", "bad;drop", "also_good")

    def test_empty_call(self):
        """Test empty call is valid."""
        validate_identifiers()


class TestValidateInterval:
    """Tests for validate_interval function."""

    def test_valid_interval_day(self):
        """Test valid day intervals."""
        validate_interval("1 day")
        validate_interval("7 days")
        validate_interval("30 days")

    def test_valid_interval_various_units(self):
        """Test valid intervals with various time units."""
        validate_interval("1 second")
        validate_interval("60 seconds")
        validate_interval("1 minute")
        validate_interval("60 minutes")
        validate_interval("1 hour")
        validate_interval("24 hours")
        validate_interval("1 week")
        validate_interval("4 weeks")
        validate_interval("1 month")
        validate_interval("12 months")
        validate_interval("1 year")
        validate_interval("5 years")

    def test_valid_interval_case_insensitive(self):
        """Test interval validation is case insensitive."""
        validate_interval("1 DAY")
        validate_interval("7 Days")
        validate_interval("1 WEEK")

    def test_invalid_interval_empty(self):
        """Test empty interval raises error."""
        with pytest.raises(InvalidIdentifier) as exc:
            validate_interval("")
        assert "cannot be empty" in str(exc.value)

    def test_invalid_interval_bad_format(self):
        """Test invalid interval format raises error."""
        with pytest.raises(InvalidIdentifier):
            validate_interval("invalid")

        with pytest.raises(InvalidIdentifier):
            validate_interval("days 7")

        with pytest.raises(InvalidIdentifier):
            validate_interval("drop table")


class TestValidateIndexMethod:
    """Tests for validate_index_method function."""

    def test_valid_index_methods(self):
        """Test all valid index methods pass."""
        validate_index_method("btree")
        validate_index_method("hash")
        validate_index_method("gist")
        validate_index_method("spgist")
        validate_index_method("gin")
        validate_index_method("brin")

    def test_valid_index_method_case_insensitive(self):
        """Test index method validation is case insensitive."""
        validate_index_method("BTREE")
        validate_index_method("Hash")
        validate_index_method("GIN")

    def test_invalid_index_method(self):
        """Test invalid index method raises error."""
        with pytest.raises(InvalidIdentifier) as exc:
            validate_index_method("invalid")
        assert "Invalid index method" in str(exc.value)
        assert "btree" in str(exc.value)

        with pytest.raises(InvalidIdentifier):
            validate_index_method("fulltext")


class TestValidateExtensionName:
    """Tests for validate_extension_name function."""

    def test_valid_extension_names(self):
        """Test common extension names pass, including hyphenated ones."""
        validate_extension_name("postgis")
        validate_extension_name("timescaledb")
        validate_extension_name("uuid-ossp")
        validate_extension_name("pgcrypto")
        validate_extension_name("_custom")

    def test_invalid_extension_empty(self):
        """Test empty extension name raises error."""
        with pytest.raises(InvalidIdentifier) as exc:
            validate_extension_name("")
        assert "cannot be empty" in str(exc.value)

    def test_invalid_extension_injection(self):
        """Test injection attempts via extension name are rejected."""
        with pytest.raises(InvalidIdentifier):
            validate_extension_name('postgis"; DROP DATABASE x; --')
        with pytest.raises(InvalidIdentifier):
            validate_extension_name("ext name with space")


class TestValidateTimestamp:
    """Tests for validate_timestamp function."""

    def test_valid_dates(self):
        """Test valid date and timestamp forms pass."""
        validate_timestamp("2025-12-31")
        validate_timestamp("2025-12-31 23:59:59")
        validate_timestamp("2025-12-31T23:59:59")
        validate_timestamp("2025-12-31 23:59:59+02:00")
        validate_timestamp("2025-12-31 23:59:59.123")
        validate_timestamp("infinity")

    def test_invalid_timestamp_empty(self):
        """Test empty timestamp raises error."""
        with pytest.raises(InvalidIdentifier) as exc:
            validate_timestamp("")
        assert "cannot be empty" in str(exc.value)

    def test_invalid_timestamp_injection(self):
        """Test injection attempts via VALID UNTIL value are rejected."""
        with pytest.raises(InvalidIdentifier):
            validate_timestamp("2025-01-01'; DROP TABLE users; --")
        with pytest.raises(InvalidIdentifier):
            validate_timestamp("not a date")


class TestValidatePrivileges:
    """Tests for validate_privileges function."""

    def test_valid_single_and_multiple(self):
        """Test single and comma-joined privileges pass."""
        validate_privileges("SELECT")
        validate_privileges("ALL")
        validate_privileges("SELECT, INSERT, UPDATE")
        validate_privileges("select, delete")  # case-insensitive

    def test_invalid_privileges_empty(self):
        """Test empty privileges raises error."""
        with pytest.raises(InvalidIdentifier):
            validate_privileges("")

    def test_invalid_privileges_injection(self):
        """Test injection attempts via privileges are rejected."""
        with pytest.raises(InvalidIdentifier):
            validate_privileges("SELECT; DROP TABLE users; --")
        with pytest.raises(InvalidIdentifier):
            validate_privileges("ALL; GRANT SUPERUSER")


class TestValidateObjectType:
    """Tests for validate_object_type function."""

    def test_valid_object_types(self):
        """Test recognized object types pass."""
        validate_object_type("TABLE")
        validate_object_type("schema")  # case-insensitive
        validate_object_type("DATABASE")
        validate_object_type("SEQUENCE")

    def test_invalid_object_type_injection(self):
        """Test injection attempts via object_type are rejected."""
        with pytest.raises(InvalidIdentifier):
            validate_object_type("TABLE; DROP TABLE x; --")
        with pytest.raises(InvalidIdentifier):
            validate_object_type("")


class TestValidateCsvOption:
    """Tests for validate_csv_option function."""

    def test_valid_csv_options(self):
        """Test typical CSV option values pass."""
        validate_csv_option(",", "delimiter")
        validate_csv_option(";", "delimiter")
        validate_csv_option("", "null_string")
        validate_csv_option("UTF8", "encoding")

    def test_invalid_csv_option_quote(self):
        """Test values with quotes are rejected (would break the literal)."""
        with pytest.raises(InvalidIdentifier):
            validate_csv_option("','; DROP TABLE x; --", "delimiter")

    def test_invalid_csv_option_backslash(self):
        """Test values with backslash are rejected."""
        with pytest.raises(InvalidIdentifier):
            validate_csv_option("\\", "delimiter")

    def test_invalid_csv_option_too_long(self):
        """Test over-long values are rejected."""
        with pytest.raises(InvalidIdentifier):
            validate_csv_option("x" * 100, "encoding")


class TestQuoteLiteral:
    """Tests for quote_literal function."""

    def test_quote_simple_string(self):
        """Test simple string is quoted."""
        assert quote_literal("hello") == "'hello'"

    def test_quote_string_with_single_quote(self):
        """Test string with single quote is escaped."""
        assert quote_literal("it's") == "'it''s'"

    def test_quote_string_with_multiple_quotes(self):
        """Test string with multiple quotes is escaped."""
        assert quote_literal("it's a 'test'") == "'it''s a ''test'''"

    def test_quote_empty_string(self):
        """Test empty string is quoted."""
        assert quote_literal("") == "''"
