"""Tests for pycopg.utils module."""

import pytest

from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_interval,
    validate_index_method,
    quote_literal,
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
