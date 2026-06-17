"""Tests that deprecated flat aliases warn and delegate (REORG-04, D-09).

Asserts that each of the 6 flat ``db.*`` TimescaleDB aliases:

1. Emits exactly one :class:`DeprecationWarning` with the correct message.
2. Points the warning at the *caller's* file (``stacklevel=2`` proof — Footgun 2).
3. Delegates to the corresponding ``db.timescale.*`` accessor method with
   identical arguments.

All tests are DB-free: the ``timescale`` accessor is replaced by a
:class:`unittest.mock.MagicMock` so no live PostgreSQL connection is needed.
"""

from __future__ import annotations

import os
import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor

# ---------------------------------------------------------------------------
# Sample arguments for each method (minimal valid inputs)
# ---------------------------------------------------------------------------

_SYNC_ALIAS_ARGS: dict[str, tuple] = {
    "create_hypertable": ("events", "ts"),
    "enable_compression": ("events",),
    "add_compression_policy": ("events", "7 days"),
    "add_retention_policy": ("events", "365 days"),
    "list_hypertables": (),
    "hypertable_info": ("events",),
}

_ASYNC_ALIAS_ARGS: dict[str, tuple] = {
    "create_hypertable": ("events", "ts"),
    "enable_compression": ("events",),
    "add_compression_policy": ("events", "7 days"),
    "add_retention_policy": ("events", "365 days"),
    "list_hypertables": (),
    "hypertable_info": ("events",),
}


class TestTimescaleAliases:
    """Each flat db.* alias must warn AND delegate to db.timescale.*."""

    # ------------------------------------------------------------------
    # Sync aliases
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("name", list(_SYNC_ALIAS_ARGS.keys()))
    def test_sync_alias_warns_and_delegates(self, name, config):
        """Flat sync alias emits DeprecationWarning and delegates (D-09).

        Parameters
        ----------
        name : str
            Name of the flat alias method under test.
        config : Config
            Test configuration fixture (no live DB needed — accessor is mocked).
        """
        db = Database(config)
        mock_accessor = MagicMock(spec=TimescaleAccessor)
        # Inject the mock so the lazy property returns it immediately.
        db._timescale = mock_accessor

        args = _SYNC_ALIAS_ARGS[name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            getattr(db, name)(*args)

        # Exactly one warning.
        assert len(w) == 1, f"Expected 1 warning, got {len(w)}"
        assert w[0].category is DeprecationWarning

        msg_str = str(w[0].message)
        # Message names the new accessor path.
        assert (
            f"db.timescale.{name}" in msg_str
        ), f"Expected 'db.timescale.{name}' in warning message: {msg_str!r}"
        # Message mentions the deprecation timeline.
        assert "v0.7.0" in msg_str, f"Expected 'v0.7.0' in warning message: {msg_str!r}"

        # stacklevel=2 proof: warning must point at THIS test file, not aliases.py.
        basename = os.path.basename(w[0].filename)
        assert "test_" in basename, (
            f"Warning filename should start with 'test_', got: {w[0].filename!r}"
        )
        assert basename != "aliases.py", (
            f"Warning must not point at aliases.py (stacklevel wrong): {w[0].filename!r}"
        )
        assert basename != "database.py", (
            f"Warning must not point at database.py (stacklevel wrong): {w[0].filename!r}"
        )

        # Delegation: the accessor method was called with the original args.
        getattr(mock_accessor, name).assert_called_once_with(*args)

    # ------------------------------------------------------------------
    # Async aliases
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("name", list(_ASYNC_ALIAS_ARGS.keys()))
    @pytest.mark.asyncio
    async def test_async_alias_warns_and_delegates(self, name, config):
        """Flat async alias emits DeprecationWarning and delegates (D-09).

        Parameters
        ----------
        name : str
            Name of the flat async alias method under test.
        config : Config
            Test configuration fixture (no live DB needed — accessor is mocked).
        """
        db = AsyncDatabase(config)
        mock_accessor = MagicMock(spec=AsyncTimescaleAccessor)
        # Each accessor method must be an AsyncMock so ``await`` works.
        for method_name in _ASYNC_ALIAS_ARGS:
            setattr(mock_accessor, method_name, AsyncMock())
        # Inject the mock.
        db._timescale = mock_accessor

        args = _ASYNC_ALIAS_ARGS[name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await getattr(db, name)(*args)

        # Exactly one warning.
        assert len(w) == 1, f"Expected 1 warning, got {len(w)}"
        assert w[0].category is DeprecationWarning

        msg_str = str(w[0].message)
        # Message names the new accessor path.
        assert (
            f"db.timescale.{name}" in msg_str
        ), f"Expected 'db.timescale.{name}' in warning message: {msg_str!r}"
        # Message mentions the deprecation timeline.
        assert "v0.7.0" in msg_str, f"Expected 'v0.7.0' in warning message: {msg_str!r}"

        # stacklevel=2 proof: warning must point at THIS test file.
        async_basename = os.path.basename(w[0].filename)
        assert "test_" in async_basename, (
            f"Warning filename should start with 'test_', got: {w[0].filename!r}"
        )
        assert async_basename != "aliases.py", (
            f"Warning must not point at aliases.py (stacklevel wrong): {w[0].filename!r}"
        )
        assert async_basename != "async_database.py", (
            f"Warning must not point at async_database.py (stacklevel wrong): {w[0].filename!r}"
        )

        # Delegation: the accessor method was called with the original args.
        getattr(mock_accessor, name).assert_called_once_with(*args)
