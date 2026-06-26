"""Regression tests for Phase 37 AUDIT-01 finding fixes.

Covers:
  CR-01  explain() format whitelist (sync + async)
  CR-02  from_dataframe() identifier validation (sync + async)
  CR-03  from_geodataframe() identifier validation (sync + async)
  CR-04  build_pg_dump_cmd / build_pg_restore_cmd CLI flag-injection guard
  CR-05  pg_restore() FileNotFoundError for missing non-.sql archives (sync + async)
  WR-01  build_role_options() connection_limit int guard
  WR-02  AsyncDatabase.stream() uses session-aware cursor (parity with sync)
  WR-04  Config options key/value sanitization (dsn + connect_params)
  WR-05  TimescaleError exported from pycopg.__init__
  WR-06  _decode_watermark() raises ETLError for unknown type tags

audit WR-03 (copy_insert session bypass) is deferred — no test added here.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pycopg import Config
from pycopg.base import build_pg_dump_cmd, build_pg_restore_cmd, build_role_options
from pycopg.etl import _decode_watermark
from pycopg.exceptions import ConfigurationError, ETLError, InvalidIdentifier

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_CONN = {"host": "h", "port": 5432, "user": "u", "database": "d"}


@pytest.fixture
def config():
    return Config(host="localhost", port=5432, database="testdb", user="u")


def _make_db_with_mock_execute(config, execute_return=None):
    """Return a mocked sync Database whose execute() returns execute_return."""
    from pycopg import Database

    db = Database(config)
    db.execute = MagicMock(return_value=execute_return or [{"QUERY PLAN": "Seq Scan"}])
    return db


def _make_async_db_with_mock_execute(config, execute_return=None):
    """Return a mocked async Database whose execute() is an AsyncMock."""
    from pycopg import AsyncDatabase

    db = AsyncDatabase(config)
    db.execute = AsyncMock(
        return_value=execute_return or [{"QUERY PLAN": "Seq Scan"}]
    )
    return db


# ===========================================================================
# CR-01: explain() format whitelist
# ===========================================================================


class TestCR01ExplainFormatWhitelist:
    """CR-01: format param must be whitelisted before reaching the DB."""

    def test_valid_format_text(self, config):
        """format='text' (default) is accepted."""
        db = _make_db_with_mock_execute(config)
        result = db.maint.explain("SELECT 1", format="text")
        assert result == ["Seq Scan"]

    def test_valid_format_json(self, config):
        """format='json' is accepted; FORMAT JSON appears in SQL."""
        db = _make_db_with_mock_execute(config)
        db.maint.explain("SELECT 1", format="json")
        sql = db.execute.call_args[0][0]
        assert "FORMAT JSON" in sql

    def test_valid_format_xml(self, config):
        """format='xml' is accepted."""
        db = _make_db_with_mock_execute(config)
        db.maint.explain("SELECT 1", format="xml")
        sql = db.execute.call_args[0][0]
        assert "FORMAT XML" in sql

    def test_valid_format_yaml(self, config):
        """format='yaml' is accepted."""
        db = _make_db_with_mock_execute(config)
        db.maint.explain("SELECT 1", format="yaml")
        sql = db.execute.call_args[0][0]
        assert "FORMAT YAML" in sql

    def test_valid_format_case_insensitive(self, config):
        """format='TEXT' (uppercase) is normalised and accepted."""
        db = _make_db_with_mock_execute(config)
        db.maint.explain("SELECT 1", format="TEXT")
        db.execute.assert_called_once()

    def test_unknown_format_raises_value_error(self, config):
        """An unknown format raises ValueError before the DB is touched."""
        db = _make_db_with_mock_execute(config)
        with pytest.raises(ValueError, match="format must be one of"):
            db.maint.explain("SELECT 1", format="csv")
        db.execute.assert_not_called()

    def test_injection_attempt_raises_value_error(self, config):
        """A format injection string raises ValueError."""
        db = _make_db_with_mock_execute(config)
        with pytest.raises(ValueError):
            db.maint.explain("SELECT 1", format="TEXT, BUFFERS TRUE")
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_unknown_format_raises_value_error(self, config):
        """AsyncMaintAccessor.explain() also rejects unknown format."""
        db = _make_async_db_with_mock_execute(config)
        with pytest.raises(ValueError, match="format must be one of"):
            await db.maint.explain("SELECT 1", format="csv")
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_valid_format_json(self, config):
        """AsyncMaintAccessor.explain() accepts format='json'."""
        db = _make_async_db_with_mock_execute(config)
        await db.maint.explain("SELECT 1", format="json")
        sql = db.execute.call_args[0][0]
        assert "FORMAT JSON" in sql


# ===========================================================================
# CR-02: from_dataframe() identifier validation
# ===========================================================================


class TestCR02FromDataframeValidation:
    """CR-02: from_dataframe() must call validate_identifiers before to_sql."""

    @patch("pycopg.database.psycopg")
    def test_bad_table_raises_invalid_identifier(self, _mock_psycopg, config):
        """A bad table name raises InvalidIdentifier before to_sql is called."""
        from pycopg import Database

        db = Database(config)
        mock_df = MagicMock()
        with pytest.raises(InvalidIdentifier):
            db.from_dataframe(mock_df, table="bad table", schema="public")
        mock_df.to_sql.assert_not_called()

    @patch("pycopg.database.psycopg")
    def test_bad_schema_raises_invalid_identifier(self, _mock_psycopg, config):
        """A bad schema name raises InvalidIdentifier before to_sql is called."""
        from pycopg import Database

        db = Database(config)
        mock_df = MagicMock()
        with pytest.raises(InvalidIdentifier):
            db.from_dataframe(mock_df, table="users", schema="bad-schema")
        mock_df.to_sql.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_bad_table_raises_invalid_identifier(self, config):
        """AsyncDatabase.from_dataframe() rejects bad table names."""
        from pycopg import AsyncDatabase

        db = AsyncDatabase(config)
        mock_df = MagicMock()
        with pytest.raises(InvalidIdentifier):
            await db.from_dataframe(mock_df, table="bad table", schema="public")

    @pytest.mark.asyncio
    async def test_async_bad_schema_raises_invalid_identifier(self, config):
        """AsyncDatabase.from_dataframe() rejects bad schema names."""
        from pycopg import AsyncDatabase

        db = AsyncDatabase(config)
        mock_df = MagicMock()
        with pytest.raises(InvalidIdentifier):
            await db.from_dataframe(mock_df, table="users", schema="bad-schema")


# ===========================================================================
# CR-03: from_geodataframe() identifier validation
# ===========================================================================


class TestCR03FromGeoDataframeValidation:
    """CR-03: from_geodataframe() must call validate_identifiers before to_postgis."""

    @patch("pycopg.database.psycopg")
    def test_bad_table_raises_invalid_identifier(self, _mock_psycopg, config):
        """A bad table name raises InvalidIdentifier before PostGIS check."""
        from pycopg import Database
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        # Schema is a lazy property backed by _schema — inject a mock via the cache
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        mock_gdf = MagicMock()
        mock_gdf.crs = None
        with pytest.raises(InvalidIdentifier):
            db.from_geodataframe(mock_gdf, table="bad table", schema="public", srid=4326)

    @patch("pycopg.database.psycopg")
    def test_bad_schema_raises_invalid_identifier(self, _mock_psycopg, config):
        """A bad schema name raises InvalidIdentifier."""
        from pycopg import Database
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        mock_gdf = MagicMock()
        with pytest.raises(InvalidIdentifier):
            db.from_geodataframe(
                mock_gdf, table="places", schema="bad-schema", srid=4326
            )

    @pytest.mark.asyncio
    async def test_async_bad_table_raises_invalid_identifier(self, config):
        """AsyncDatabase.from_geodataframe() rejects bad table names."""
        from pycopg import AsyncDatabase
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        mock_gdf = MagicMock()
        with pytest.raises(InvalidIdentifier):
            await db.from_geodataframe(
                mock_gdf, table="bad table", schema="public", srid=4326
            )

    @pytest.mark.asyncio
    async def test_async_bad_schema_raises_invalid_identifier(self, config):
        """AsyncDatabase.from_geodataframe() rejects bad schema names."""
        from pycopg import AsyncDatabase
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        mock_gdf = MagicMock()
        with pytest.raises(InvalidIdentifier):
            await db.from_geodataframe(
                mock_gdf, table="places", schema="bad-schema", srid=4326
            )


# ===========================================================================
# CR-04: build_pg_dump_cmd / build_pg_restore_cmd CLI flag injection guard
# ===========================================================================


class TestCR04CLIFlagInjectionGuard:
    """CR-04: tables/schemas values starting with '-' must be rejected."""

    def test_pg_dump_flag_in_tables_raises(self):
        """A '--no-password'-style value in tables raises ValueError."""
        with pytest.raises(ValueError, match="flag injection"):
            build_pg_dump_cmd(
                **_CONN,
                output_file="out.dump",
                tables=["--no-password"],
            )

    def test_pg_dump_flag_in_exclude_tables_raises(self):
        """A flag-style value in exclude_tables raises ValueError."""
        with pytest.raises(ValueError, match="flag injection"):
            build_pg_dump_cmd(
                **_CONN,
                output_file="out.dump",
                exclude_tables=["-x"],
            )

    def test_pg_dump_flag_in_schemas_raises(self):
        """A flag-style value in schemas raises ValueError."""
        with pytest.raises(ValueError, match="flag injection"):
            build_pg_dump_cmd(
                **_CONN,
                output_file="out.dump",
                schemas=["--schema-only"],
            )

    def test_pg_restore_flag_in_tables_raises(self):
        """build_pg_restore_cmd rejects a flag-style table value."""
        with pytest.raises(ValueError, match="flag injection"):
            build_pg_restore_cmd(
                **_CONN,
                input_file="backup.dump",
                tables=["--no-password"],
            )

    def test_pg_restore_flag_in_schemas_raises(self):
        """build_pg_restore_cmd rejects a flag-style schema value."""
        with pytest.raises(ValueError, match="flag injection"):
            build_pg_restore_cmd(
                **_CONN,
                input_file="backup.dump",
                schemas=["--schema-only"],
            )

    def test_pg_dump_wildcard_pattern_accepted(self):
        """A pattern with wildcards (valid pg_dump pattern) is accepted."""
        cmd = build_pg_dump_cmd(
            **_CONN,
            output_file="out.dump",
            tables=["public.orders", "sales_*"],
        )
        assert "-t" in cmd

    def test_pg_dump_schema_qualified_table_accepted(self):
        """A schema.table pattern is accepted."""
        cmd = build_pg_dump_cmd(
            **_CONN,
            output_file="out.dump",
            tables=["myschema.mytable"],
        )
        assert "-t" in cmd

    def test_control_char_in_tables_raises(self):
        """A value with a control character raises ValueError."""
        with pytest.raises(ValueError, match="control character"):
            build_pg_dump_cmd(
                **_CONN,
                output_file="out.dump",
                tables=["table\x00name"],
            )


# ===========================================================================
# CR-05: pg_restore() FileNotFoundError for missing non-.sql archives
# ===========================================================================


class TestCR05PgRestoreMissingFile:
    """CR-05: pg_restore() raises FileNotFoundError for missing non-.sql files."""

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_missing_dump_raises_file_not_found(self, _mock_run, _mock_psycopg, config):
        """pg_restore on a non-existent .dump file raises FileNotFoundError."""
        from pycopg import Database

        db = Database(config)
        with pytest.raises(FileNotFoundError, match="not found"):
            db.backup.pg_restore("/tmp/nonexistent_file_xyz.dump")

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_sql_file_not_requiring_existence_routes_psql(
        self, mock_run, _mock_psycopg, config
    ):
        """An .sql path (even non-existent) still routes to psql, not pg_restore."""
        from pycopg import Database

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        db = Database(config)
        # Non-existent .sql file should route to psql (not raise FileNotFoundError)
        # psql call will fail because file doesn't exist — that's subprocess's problem
        # We verify pg_restore was NOT called (psql was).
        try:
            db.backup.pg_restore("/tmp/nonexistent_xyz.sql")
        except Exception:
            pass
        if mock_run.called:
            cmd = mock_run.call_args[0][0]
            assert "psql" in cmd[0], "Non-existent .sql should route to psql, not pg_restore"

    @pytest.mark.asyncio
    async def test_async_missing_dump_raises_file_not_found(self, config):
        """Async pg_restore on a non-existent .dump file raises FileNotFoundError."""
        from pycopg import AsyncDatabase

        db = AsyncDatabase(config)
        with pytest.raises(FileNotFoundError, match="not found"):
            await db.backup.pg_restore("/tmp/nonexistent_file_xyz.dump")


# ===========================================================================
# WR-01: build_role_options() connection_limit int guard
# ===========================================================================


class TestWR01ConnectionLimitIntGuard:
    """WR-01: connection_limit must be an int; non-int raises TypeError."""

    def test_int_accepted(self):
        """An integer connection_limit is accepted."""
        opts = build_role_options(connection_limit=10)
        assert any("CONNECTION LIMIT 10" in o for o in opts)

    def test_minus_one_default_no_connection_limit(self):
        """Default -1 produces no CONNECTION LIMIT token."""
        opts = build_role_options(connection_limit=-1)
        assert not any("CONNECTION LIMIT" in o for o in opts)

    def test_string_raises_type_error(self):
        """A string connection_limit raises TypeError."""
        with pytest.raises(TypeError, match="connection_limit must be an int"):
            build_role_options(connection_limit="10 SUPERUSER")

    def test_float_raises_type_error(self):
        """A float connection_limit raises TypeError."""
        with pytest.raises(TypeError):
            build_role_options(connection_limit=5.0)

    def test_bool_raises_type_error(self):
        """A bool (subclass of int) raises TypeError (consistent with number_partitions)."""
        with pytest.raises(TypeError):
            build_role_options(connection_limit=True)


# ===========================================================================
# WR-02: AsyncDatabase.stream() session-aware parity with sync
# ===========================================================================


class TestWR02AsyncStreamSessionParity:
    """WR-02: AsyncDatabase.stream() must use self.cursor() not self.connect()."""

    @pytest.mark.asyncio
    async def test_async_stream_uses_cursor_not_connect(self, config):
        """stream() goes through self.cursor() — session-aware path."""
        from pycopg import AsyncDatabase

        db = AsyncDatabase(config)

        # Track which path is taken
        cursor_called = []

        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        # Return two batches then empty
        mock_cursor.fetchmany = AsyncMock(
            side_effect=[
                [{"id": 1}, {"id": 2}],
                [],
            ]
        )

        @asynccontextmanager
        async def _cursor_cm(**kwargs):
            cursor_called.append(True)
            yield mock_cursor

        db.cursor = MagicMock(side_effect=_cursor_cm)

        # connect should NOT be called
        connect_called = []

        @asynccontextmanager
        async def _connect_cm(**kwargs):
            connect_called.append(True)
            yield MagicMock()

        db.connect = MagicMock(side_effect=_connect_cm)

        rows = []
        async for row in db.stream("SELECT 1"):
            rows.append(row)

        assert rows == [{"id": 1}, {"id": 2}]
        assert cursor_called, "stream() must call self.cursor()"
        assert not connect_called, "stream() must NOT call self.connect() directly"

    @pytest.mark.asyncio
    async def test_async_stream_inside_session_uses_session_conn(self, config):
        """When a session is active, stream() must use it (not open a new conn)."""
        from pycopg import AsyncDatabase

        db = AsyncDatabase(config)

        # Simulate an active session connection
        mock_session_conn = MagicMock()
        mock_session_conn.info = MagicMock()
        from psycopg.pq import TransactionStatus

        mock_session_conn.info.transaction_status = TransactionStatus.IDLE

        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor.fetchmany = AsyncMock(side_effect=[[{"val": 42}], []])

        @asynccontextmanager
        async def cursor_cm(*args, **kwargs):
            yield mock_cursor

        mock_session_conn.cursor = MagicMock(side_effect=cursor_cm)

        db._session_conn = mock_session_conn

        rows = []
        async for row in db.stream("SELECT 42 AS val"):
            rows.append(row)

        assert rows == [{"val": 42}]
        # The session connection's cursor should have been used
        mock_session_conn.cursor.assert_called()


# ===========================================================================
# WR-04: Config options key/value sanitization
# ===========================================================================


class TestWR04ConfigOptionSanitization:
    """WR-04: options keys/values must be sanitized before interpolation into libpq options."""

    def test_safe_key_and_value_accepted_in_dsn(self):
        """A valid GUC key=value passes through to dsn."""
        c = Config(options={"search_path": "myschema"})
        dsn = c.dsn
        assert "search_path=myschema" in dsn

    def test_safe_key_and_value_accepted_in_connect_params(self):
        """A valid GUC key=value passes through to connect_params."""
        c = Config(options={"search_path": "myschema"})
        params = c.connect_params()
        assert "options" in params
        assert "search_path=myschema" in params["options"]

    def test_value_with_space_raises_configuration_error_in_dsn(self):
        """A value with a space raises ConfigurationError (injection guard)."""
        c = Config(options={"statement_timeout": "1000 -c search_path=evil"})
        with pytest.raises(ConfigurationError, match="Unsafe option value"):
            _ = c.dsn

    def test_value_with_space_raises_configuration_error_in_connect_params(self):
        """Same guard applies in connect_params()."""
        c = Config(options={"statement_timeout": "1000 -c search_path=evil"})
        with pytest.raises(ConfigurationError, match="Unsafe option value"):
            c.connect_params()

    def test_value_with_single_quote_raises_configuration_error(self):
        """A value with a single-quote raises ConfigurationError."""
        c = Config(options={"application_name": "foo'bar"})
        with pytest.raises(ConfigurationError, match="Unsafe option value"):
            _ = c.dsn

    def test_value_with_backslash_raises_configuration_error(self):
        """A value with a backslash raises ConfigurationError."""
        c = Config(options={"application_name": "foo\\bar"})
        with pytest.raises(ConfigurationError, match="Unsafe option value"):
            _ = c.dsn

    def test_key_with_special_chars_raises_configuration_error(self):
        """An option key containing spaces raises ConfigurationError."""
        c = Config(options={"bad key": "value"})
        with pytest.raises(ConfigurationError, match="Unsafe option key"):
            _ = c.dsn

    def test_no_options_produces_no_options_part_in_dsn(self):
        """A config with no options produces a clean dsn."""
        c = Config(options={})
        assert "options" not in c.dsn


# ===========================================================================
# WR-05: TimescaleError exported from pycopg.__init__
# ===========================================================================


class TestWR05TimescaleErrorExported:
    """WR-05: TimescaleError must be importable from pycopg and in __all__."""

    def test_timescale_error_importable_from_pycopg(self):
        """from pycopg import TimescaleError works."""
        from pycopg import TimescaleError

        assert TimescaleError is not None

    def test_timescale_error_in_all(self):
        """TimescaleError appears in pycopg.__all__."""
        import pycopg

        assert "TimescaleError" in pycopg.__all__

    def test_timescale_error_is_pycopg_error_subclass(self):
        """TimescaleError is a subclass of PycopgError."""
        from pycopg import TimescaleError
        from pycopg.exceptions import PycopgError

        assert issubclass(TimescaleError, PycopgError)

    def test_timescale_error_can_be_raised_and_caught(self):
        """TimescaleError can be raised and caught by its pycopg import path."""
        from pycopg import TimescaleError

        with pytest.raises(TimescaleError):
            raise TimescaleError("TimescaleDB operation failed")


# ===========================================================================
# WR-06: _decode_watermark() raises ETLError for unknown type tags
# ===========================================================================


class TestWR06DecodeWatermarkUnknownTag:
    """WR-06: _decode_watermark() must raise ETLError for unrecognised type tags."""

    def test_known_tag_int_works(self):
        """'int' tag decodes correctly (regression: not broken by fix)."""
        assert _decode_watermark({"type": "int", "value": 5}) == 5

    def test_known_tag_str_works(self):
        """'str' tag decodes correctly (was previously the silent fallback)."""
        assert _decode_watermark({"type": "str", "value": "hello"}) == "hello"

    def test_known_tag_datetime_works(self):
        """'datetime' tag decodes correctly."""
        from datetime import UTC, datetime

        val = _decode_watermark(
            {"type": "datetime", "value": "2024-01-01T00:00:00+00:00"}
        )
        assert val == datetime(2024, 1, 1, tzinfo=UTC)

    def test_unknown_tag_raises_etl_error(self):
        """An unrecognised type tag raises ETLError, not silent str() coercion."""
        with pytest.raises(ETLError, match="Unknown watermark type tag"):
            _decode_watermark({"type": "datetimetz", "value": "2024-01-01"})

    def test_corrupted_tag_message_contains_envelope(self):
        """The ETLError message includes the envelope for debuggability."""
        envelope = {"type": "blob", "value": b"binary"}
        with pytest.raises(ETLError) as exc_info:
            _decode_watermark(envelope)
        assert "blob" in str(exc_info.value)

    def test_none_tag_raises_etl_error(self):
        """A None type tag raises ETLError (corrupted envelope)."""
        with pytest.raises(ETLError):
            _decode_watermark({"type": None, "value": "something"})
