"""Tests that deprecated flat aliases warn and delegate (REORG-04, D-09).

Asserts that each of the 27 flat ``db.*`` schema aliases:

1. Emits exactly one :class:`DeprecationWarning` with the correct message.
2. Points the warning at the *caller's* file (``stacklevel=2`` proof — Footgun 2).
3. Delegates to the corresponding ``db.schema.*`` accessor method with
   identical arguments.

All tests are DB-free: the ``schema`` accessor is replaced by a
:class:`unittest.mock.MagicMock` so no live PostgreSQL connection is needed.
"""

from __future__ import annotations

import os
import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor

# ---------------------------------------------------------------------------
# Sample arguments for each method (minimal valid inputs)
# D-01: all 27 schema method names must be enumerated here.
# ---------------------------------------------------------------------------

_SYNC_ALIAS_ARGS: dict[str, tuple] = {
    "create_database": ("mydb",),
    "drop_database": ("mydb",),
    "database_exists": ("mydb",),
    "list_databases": (),
    "create_extension": ("postgis",),
    "drop_extension": ("postgis",),
    "list_extensions": (),
    "has_extension": ("postgis",),
    "create_schema": ("myschema",),
    "drop_schema": ("myschema",),
    "list_schemas": (),
    "schema_exists": ("myschema",),
    "list_tables": (),
    "table_exists": ("users",),
    "list_columns": ("users",),
    "columns_with_types": ("users",),
    "drop_table": ("users",),
    "truncate_table": ("users",),
    "table_info": ("users",),
    "row_count": ("users",),
    "add_primary_key": ("users", "id"),
    "add_foreign_key": ("orders", "user_id", "users", "id"),
    "add_unique_constraint": ("users", ["email"]),
    "create_index": ("users", ["email"]),
    "drop_index": ("idx_users_email",),
    "list_indexes": ("users",),
    "list_constraints": ("users",),
}

# Async args are identical to sync args (same method signatures).
_ASYNC_ALIAS_ARGS: dict[str, tuple] = _SYNC_ALIAS_ARGS.copy()

assert len(_SYNC_ALIAS_ARGS) == 27, (
    f"D-01 violation: expected 27 schema methods, got {len(_SYNC_ALIAS_ARGS)}"
)


class TestSchemaAliases:
    """Each flat db.* schema alias must warn AND delegate to db.schema.*."""

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
        mock_accessor = MagicMock(spec=SchemaAccessor)
        # Inject the mock so the lazy property returns it immediately.
        db._schema = mock_accessor

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
            and f"db.schema.{name}" in str(rec.message)
        ]
        # Exactly one alias warning.
        assert (
            len(alias_warnings) == 1
        ), f"Expected 1 alias warning for {name}, got {len(alias_warnings)}: {[str(r.message) for r in w]}"
        rec = alias_warnings[0]

        msg_str = str(rec.message)
        # Message names the new accessor path.
        assert (
            f"db.schema.{name}" in msg_str
        ), f"Expected 'db.schema.{name}' in warning message: {msg_str!r}"
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
        mock_accessor = MagicMock(spec=AsyncSchemaAccessor)
        # Each accessor method must be an AsyncMock so ``await`` works.
        for method_name in _ASYNC_ALIAS_ARGS:
            setattr(mock_accessor, method_name, AsyncMock())
        # Inject the mock.
        db._schema = mock_accessor

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
            and f"db.schema.{name}" in str(rec.message)
        ]
        # Exactly one alias warning.
        assert (
            len(alias_warnings) == 1
        ), f"Expected 1 alias warning for {name}, got {len(alias_warnings)}: {[str(r.message) for r in w]}"
        rec = alias_warnings[0]

        msg_str = str(rec.message)
        # Message names the new accessor path.
        assert (
            f"db.schema.{name}" in msg_str
        ), f"Expected 'db.schema.{name}' in warning message: {msg_str!r}"
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
