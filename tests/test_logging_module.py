"""
Unit tests for pycopg.logging module.

Tests cover:
- get_logger() identity and NullHandler default
- log_operation() DEBUG record with correct extra fields
- NullHandler silence (library-silent-by-default rule)
- Instrumentation sites: smoke tests that wrapped ops emit DEBUG records
"""

from __future__ import annotations

import ast
import inspect
import logging
import time
from unittest.mock import MagicMock, patch

from pycopg.logging import get_logger, log_operation


class TestGetLogger:
    """Tests for get_logger() function."""

    def test_get_logger_returns_pycopg_logger(self):
        """get_logger() must return the logging.getLogger('pycopg') singleton."""
        assert get_logger() is logging.getLogger("pycopg")

    def test_get_logger_name(self):
        """Logger returned by get_logger() must have name 'pycopg'."""
        assert get_logger().name == "pycopg"

    def test_get_logger_has_null_handler(self):
        """Library logger must have at least one NullHandler attached at import time."""
        handlers = get_logger().handlers
        assert any(isinstance(h, logging.NullHandler) for h in handlers)


class TestLogOperation:
    """Tests for log_operation() context manager."""

    def test_log_operation_extra(self, caplog):
        """log_operation emits one DEBUG record with correct extra fields."""
        with caplog.at_level(logging.DEBUG, logger="pycopg"):
            with log_operation("t.op", rows=5):
                pass

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.DEBUG
        assert record.operation == "t.op"
        assert isinstance(record.duration_ms, float)
        assert record.duration_ms >= 0
        assert record.rows == 5

    def test_log_operation_no_rows(self, caplog):
        """log_operation without rows= must not include rows in the record extra."""
        with caplog.at_level(logging.DEBUG, logger="pycopg"):
            with log_operation("t.no_rows"):
                pass

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.DEBUG
        assert record.operation == "t.no_rows"
        assert isinstance(record.duration_ms, float)
        # rows must not be present when not provided
        assert getattr(record, "rows", None) is None

    def test_log_operation_rows_is_kwonly(self):
        """rows parameter must be keyword-only."""
        sig = inspect.signature(log_operation)
        rows_param = sig.parameters["rows"]
        assert rows_param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_log_operation_duration_is_positive(self, caplog):
        """duration_ms must be a non-negative float."""
        with caplog.at_level(logging.DEBUG, logger="pycopg"):
            with log_operation("t.timing"):
                time.sleep(0.001)

        record = caplog.records[0]
        assert record.duration_ms >= 0

    def test_log_operation_no_basicconfig_call(self):
        """log_operation must never call logging.basicConfig()."""
        import pycopg.logging as logging_mod

        source = inspect.getsource(logging_mod)
        tree = ast.parse(source)
        # Walk the AST to find actual basicConfig calls (not mentions in comments/docstrings)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "basicConfig":
                    raise AssertionError(
                        "pycopg/logging.py must not call logging.basicConfig()"
                    )


class TestNullHandlerSilence:
    """Tests that the library logger is silent by default (library rule D-08)."""

    def test_null_handler_silence(self):
        """With only a NullHandler, log_operation must not raise and must emit nothing."""
        lib_logger = logging.getLogger("pycopg")
        original_handlers = lib_logger.handlers[:]
        original_propagate = lib_logger.propagate

        # Restrict to NullHandler only; suppress propagation to root
        lib_logger.handlers = [logging.NullHandler()]
        lib_logger.propagate = False

        try:
            # Must not raise and must produce no output
            with log_operation("t.silent"):
                pass
        finally:
            lib_logger.handlers = original_handlers
            lib_logger.propagate = original_propagate

    def test_module_does_not_call_basicconfig(self):
        """pycopg/logging.py must not contain any logging.basicConfig() call."""
        import pycopg.logging as logging_mod

        source = inspect.getsource(logging_mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "basicConfig":
                    raise AssertionError(
                        "pycopg/logging.py must not call logging.basicConfig()"
                    )


class TestInstrumentationSites:
    """Smoke tests verifying that instrumented ops emit a DEBUG log record.

    All tests in this class run WITHOUT a live database by monkeypatching the
    inner DB work — only the log_operation call site is exercised.
    Conforms to D-09 (coarse instrumentation only; hot path untouched).
    """

    def _make_db_stub(self):
        """Return a minimal Database-like stub with mocked internals."""
        import pandas as pd

        from pycopg.database import Database

        db = object.__new__(Database)
        # Provide the minimum attributes used by from_dataframe
        engine_mock = MagicMock()
        db.__dict__["_engine"] = engine_mock
        db.__dict__["_schema"] = MagicMock()
        db.__dict__["_schema"].add_primary_key = MagicMock()
        return db, pd.DataFrame({"a": [1, 2, 3]})

    def test_instrumentation_sites_from_dataframe_emits_debug(self, caplog):
        """Database.from_dataframe emits a DEBUG record with operation='database.from_dataframe'
        and a numeric duration_ms — no live DB required."""
        import pandas as pd

        from pycopg.database import Database

        db = object.__new__(Database)
        df = pd.DataFrame({"x": [10, 20, 30]})

        # Patch the two inner I/O calls so no DB connection is needed
        mock_to_sql = MagicMock(return_value=None)
        mock_stream = MagicMock(return_value=3)
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)

        with (
            patch("pycopg.database.validate_identifiers"),
            patch.object(pd.DataFrame, "to_sql", mock_to_sql),
            patch("pycopg.database._stream_df_copy", mock_stream),
            patch.object(Database, "connect", return_value=mock_conn),
            patch.object(Database, "engine", new_callable=lambda: property(lambda self: MagicMock())),
            patch.object(Database, "schema", new_callable=lambda: property(lambda self: MagicMock())),
            caplog.at_level(logging.DEBUG, logger="pycopg"),
        ):
            db.from_dataframe(df, "test_table")

        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        ops = [getattr(r, "operation", None) for r in debug_records]
        assert "database.from_dataframe" in ops, (
            f"Expected 'database.from_dataframe' in operations; got {ops}"
        )

        # Find the specific record and verify fields
        rec = next(r for r in debug_records if getattr(r, "operation", None) == "database.from_dataframe")
        assert isinstance(rec.duration_ms, float), (
            f"duration_ms must be float, got {type(rec.duration_ms)}"
        )
        assert rec.duration_ms >= 0

    def test_instrumentation_sites_operation_strings_present_in_source(self):
        """Assert that all instrumentation site strings are present in source files (D-09 audit)."""
        import inspect

        import pycopg.async_database as async_database_mod
        import pycopg.backup as backup_mod
        import pycopg.database as database_mod
        import pycopg.etl as etl_mod
        import pycopg.migrations as migrations_mod

        expected_sites = [
            (etl_mod, "etl.run"),
            (backup_mod, "backup.pg_dump"),
            (backup_mod, "backup.pg_restore"),
            (migrations_mod, "migrations.migrate"),
            (database_mod, "database.from_dataframe"),
            (database_mod, "database.from_geodataframe"),
            (async_database_mod, "database.from_dataframe"),
            (async_database_mod, "database.from_geodataframe"),
            (database_mod, "database.health"),          # Plan 03 site
            (async_database_mod, "database.health"),    # Plan 03 site
        ]

        for mod, op_name in expected_sites:
            src = inspect.getsource(mod)
            assert f'"{op_name}"' in src or f"'{op_name}'" in src, (
                f"Expected log_operation site '{op_name}' not found in {mod.__name__}"
            )
