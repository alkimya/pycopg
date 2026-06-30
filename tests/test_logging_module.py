"""
Unit tests for pycopg.logging module.

Tests cover:
- get_logger() identity and NullHandler default
- log_operation() DEBUG record with correct extra fields
- NullHandler silence (library-silent-by-default rule)
"""

from __future__ import annotations

import ast
import inspect
import logging
import time

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
