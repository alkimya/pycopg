"""
Structured logging helpers for pycopg.

Provides ``get_logger()`` and the ``log_operation`` context manager.

Library rule (D-08): a ``NullHandler`` is attached to the ``pycopg`` logger
at import time so the library is silent unless the application opts in by
configuring its own handler stack.  This module never calls
``logging.basicConfig()``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

__all__ = ["get_logger", "log_operation"]

_logger = logging.getLogger("pycopg")
_logger.addHandler(logging.NullHandler())


def get_logger() -> logging.Logger:
    """Return the pycopg library logger.

    The logger is named ``"pycopg"`` and has a ``NullHandler`` attached by
    default so that library code is silent unless the application configures
    its own handler.

    Returns
    -------
    logging.Logger
        The ``logging.getLogger("pycopg")`` singleton.

    Examples
    --------
    >>> from pycopg.logging import get_logger
    >>> logger = get_logger()
    >>> logger.name
    'pycopg'
    """
    return _logger


@contextmanager
def log_operation(
    operation: str,
    *,
    rows: int | None = None,
) -> Generator[None, None, None]:
    """Context manager that emits a single DEBUG record after the wrapped block.

    The record is emitted via the ``pycopg`` library logger with
    ``extra`` fields containing the operation name, elapsed time (in
    milliseconds), and — only when provided — a row count.  No
    ``logging.basicConfig()`` call is ever made.

    Parameters
    ----------
    operation : str
        Short descriptor of the operation being timed (e.g.
        ``"database.from_dataframe"``).  This becomes the ``operation``
        field in the log record's ``extra`` dict.  Callers should use
        constant strings — never SQL text, DSNs, or credential values
        (T-45-01).
    rows : int or None, optional
        Number of rows affected by the operation.  When provided, the
        value is added to the log record's ``extra`` dict as ``rows``.
        Keyword-only.

    Yields
    ------
    None

    Examples
    --------
    >>> from pycopg.logging import log_operation
    >>> with log_operation("etl.run", rows=42):
    ...     pass  # timed block
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        extra: dict[str, Any] = {
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
        }
        if rows is not None:
            extra["rows"] = rows
        _logger.debug("pycopg: %s completed", operation, extra=extra)
