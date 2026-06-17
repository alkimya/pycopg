"""Tests that deprecated flat maint aliases warn and delegate (REORG-04, D-09).

Asserts that each of the 6 flat ``db.*`` maint aliases:

1. Emits exactly one :class:`DeprecationWarning` with the correct message.
2. Points the warning at the *caller's* file (``stacklevel=2`` proof).
3. Delegates to the corresponding ``db.maint.*`` accessor method with
   identical arguments.

All tests are DB-free: the ``maint`` accessor is replaced by a
:class:`unittest.mock.MagicMock` so no live PostgreSQL connection is needed.
"""

from __future__ import annotations

import os
import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.maint import AsyncMaintAccessor, MaintAccessor

# ---------------------------------------------------------------------------
# Sample arguments for each method (minimal valid inputs)
# ---------------------------------------------------------------------------

_SYNC_ALIAS_ARGS: dict[str, tuple] = {
    "size": (),
    "table_size": ("users",),
    "table_sizes": (),
    "vacuum": (),
    "analyze": (),
    "explain": ("SELECT 1",),
}

_ASYNC_ALIAS_ARGS: dict[str, tuple] = {
    "size": (),
    "table_size": ("users",),
    "table_sizes": (),
    "vacuum": (),
    "analyze": (),
    "explain": ("SELECT 1",),
}


class TestMaintAliases:
    """Each flat db.* maint alias must warn AND delegate to db.maint.*."""

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
        mock_accessor = MagicMock(spec=MaintAccessor)
        # Inject the mock so the lazy property returns it immediately.
        db._maint = mock_accessor

        args = _SYNC_ALIAS_ARGS[name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            getattr(db, name)(*args)

        # Isolate the alias's own DeprecationWarning. Under the combined
        # ``-W error::DeprecationWarning`` gate, unrelated DeprecationWarnings
        # (asyncio/connection-pool internals) can leak into this record buffer
        # across test boundaries, so assert on the alias-specific warning rather
        # than the raw recorded count.
        alias_warnings = [
            rec
            for rec in w
            if rec.category is DeprecationWarning
            and f"db.maint.{name}" in str(rec.message)
        ]
        # Exactly one alias warning.
        assert (
            len(alias_warnings) == 1
        ), f"Expected 1 alias warning for {name}, got {len(alias_warnings)}: {[str(r.message) for r in w]}"
        rec = alias_warnings[0]

        msg_str = str(rec.message)
        # Message names the new accessor path.
        assert (
            f"db.maint.{name}" in msg_str
        ), f"Expected 'db.maint.{name}' in warning message: {msg_str!r}"
        # Message mentions the deprecation timeline.
        assert "v0.7.0" in msg_str, f"Expected 'v0.7.0' in warning message: {msg_str!r}"

        # stacklevel=2 proof: warning must point at THIS test file, not aliases.py.
        basename = os.path.basename(rec.filename)
        assert (
            "test_" in basename
        ), f"Warning filename should start with 'test_', got: {rec.filename!r}"
        assert (
            basename != "aliases.py"
        ), f"Warning must not point at aliases.py (stacklevel wrong): {rec.filename!r}"
        assert (
            basename != "database.py"
        ), f"Warning must not point at database.py (stacklevel wrong): {rec.filename!r}"

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
        mock_accessor = MagicMock(spec=AsyncMaintAccessor)
        # Each accessor method must be an AsyncMock so ``await`` works.
        for method_name in _ASYNC_ALIAS_ARGS:
            setattr(mock_accessor, method_name, AsyncMock())
        # Inject the mock.
        db._maint = mock_accessor

        args = _ASYNC_ALIAS_ARGS[name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await getattr(db, name)(*args)

        # Isolate the alias's own DeprecationWarning. Under the combined
        # ``-W error::DeprecationWarning`` gate, unrelated DeprecationWarnings
        # (asyncio/connection-pool internals) can leak into this record buffer
        # across test boundaries, so assert on the alias-specific warning rather
        # than the raw recorded count.
        alias_warnings = [
            rec
            for rec in w
            if rec.category is DeprecationWarning
            and f"db.maint.{name}" in str(rec.message)
        ]
        # Exactly one alias warning.
        assert (
            len(alias_warnings) == 1
        ), f"Expected 1 alias warning for {name}, got {len(alias_warnings)}: {[str(r.message) for r in w]}"
        rec = alias_warnings[0]

        msg_str = str(rec.message)
        # Message names the new accessor path.
        assert (
            f"db.maint.{name}" in msg_str
        ), f"Expected 'db.maint.{name}' in warning message: {msg_str!r}"
        # Message mentions the deprecation timeline.
        assert "v0.7.0" in msg_str, f"Expected 'v0.7.0' in warning message: {msg_str!r}"

        # stacklevel=2 proof: warning must point at THIS test file.
        async_basename = os.path.basename(rec.filename)
        assert (
            "test_" in async_basename
        ), f"Warning filename should start with 'test_', got: {rec.filename!r}"
        assert (
            async_basename != "aliases.py"
        ), f"Warning must not point at aliases.py (stacklevel wrong): {rec.filename!r}"
        assert (
            async_basename != "async_database.py"
        ), f"Warning must not point at async_database.py (stacklevel wrong): {rec.filename!r}"

        # Delegation: the accessor method was called with the original args.
        getattr(mock_accessor, name).assert_called_once_with(*args)
