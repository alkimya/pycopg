"""Tests that deprecated flat spatial aliases warn and delegate (REORG-04, D-09).

Asserts that each of the 2 flat ``db.*`` spatial aliases:

1. Emits exactly one :class:`DeprecationWarning` with the correct message.
2. Points the warning at the *caller's* file (``stacklevel=2`` proof — Footgun 2).
3. Delegates to the corresponding ``db.spatial.*`` accessor method with
   identical arguments.

All tests are DB-free: the ``spatial`` accessor is replaced by a
:class:`unittest.mock.MagicMock` so no live PostgreSQL connection is needed.
The mock is injected into ``db._spatial`` to bypass the PostGIS constructor guard
(SpatialAccessor raises at construction if PostGIS is absent).
"""

from __future__ import annotations

import os
import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.spatial import AsyncSpatialAccessor, SpatialAccessor

# ---------------------------------------------------------------------------
# Sample arguments for each method (minimal valid inputs)
# ---------------------------------------------------------------------------

_SYNC_ALIAS_ARGS: dict[str, tuple] = {
    "create_spatial_index": ("my_table",),
    "list_geometry_columns": (),
}

_ASYNC_ALIAS_ARGS = _SYNC_ALIAS_ARGS.copy()


class TestSpatialAliases:
    """Each flat db.* spatial alias must warn AND delegate to db.spatial.*."""

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
        # Inject the mock into the cache field to bypass the PostGIS constructor guard.
        db._spatial = MagicMock(spec=SpatialAccessor)

        args = _SYNC_ALIAS_ARGS[name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            getattr(db, name)(*args)

        # Isolate the alias's own DeprecationWarning.
        alias_warnings = [
            rec
            for rec in w
            if rec.category is DeprecationWarning
            and f"db.spatial.{name}" in str(rec.message)
        ]
        # Exactly one alias warning.
        assert (
            len(alias_warnings) == 1
        ), f"Expected 1 alias warning for {name}, got {len(alias_warnings)}: {[str(r.message) for r in w]}"
        rec = alias_warnings[0]

        msg_str = str(rec.message)
        # Message names the new accessor path.
        assert (
            f"db.spatial.{name}" in msg_str
        ), f"Expected 'db.spatial.{name}' in warning message: {msg_str!r}"
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
        getattr(db._spatial, name).assert_called_once_with(*args)

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
        mock = MagicMock(spec=AsyncSpatialAccessor)
        # Each accessor method must be an AsyncMock so ``await`` works.
        for method_name in _ASYNC_ALIAS_ARGS:
            setattr(mock, method_name, AsyncMock())
        # Inject the mock into the cache field to bypass the deferred PostGIS guard.
        db._spatial = mock

        args = _ASYNC_ALIAS_ARGS[name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await getattr(db, name)(*args)

        # Isolate the alias's own DeprecationWarning.
        alias_warnings = [
            rec
            for rec in w
            if rec.category is DeprecationWarning
            and f"db.spatial.{name}" in str(rec.message)
        ]
        # Exactly one alias warning.
        assert (
            len(alias_warnings) == 1
        ), f"Expected 1 alias warning for {name}, got {len(alias_warnings)}: {[str(r.message) for r in w]}"
        rec = alias_warnings[0]

        msg_str = str(rec.message)
        # Message names the new accessor path.
        assert (
            f"db.spatial.{name}" in msg_str
        ), f"Expected 'db.spatial.{name}' in warning message: {msg_str!r}"
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
        getattr(mock, name).assert_called_once_with(*args)
