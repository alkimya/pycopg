"""Proof that removed v0.6.0 flat aliases raise AttributeError (ALIAS-RM-02).

This test file verifies that:
- All 56 flat names removed in v0.7.0 raise AttributeError on Database instances.
- All 56 flat names removed in v0.7.0 raise AttributeError on AsyncDatabase instances.
- No public method on Database or AsyncDatabase retains ``*args``/``**kwargs``
  signatures (WR-01: IDE autocomplete/type-checking restored).
"""

import inspect

import pytest

from pycopg import AsyncDatabase, Database

# The 56 removed flat names — hardcoded for clarity and stability post-v0.7.0.
# Source of truth: RESEARCH.md §1 and MIGRATION.md v0.6→v0.7 table.
REMOVED_FLAT_NAMES = [
    "add_compression_policy",
    "add_foreign_key",
    "add_primary_key",
    "add_retention_policy",
    "add_unique_constraint",
    "alter_role",
    "analyze",
    "columns_with_types",
    "copy_from_csv",
    "copy_to_csv",
    "create_database",
    "create_extension",
    "create_hypertable",
    "create_index",
    "create_role",
    "create_schema",
    "create_spatial_index",
    "database_exists",
    "drop_database",
    "drop_extension",
    "drop_index",
    "drop_role",
    "drop_schema",
    "drop_table",
    "enable_compression",
    "explain",
    "grant",
    "grant_role",
    "has_extension",
    "hypertable_info",
    "list_columns",
    "list_constraints",
    "list_databases",
    "list_extensions",
    "list_geometry_columns",
    "list_hypertables",
    "list_indexes",
    "list_role_grants",
    "list_role_members",
    "list_roles",
    "list_schemas",
    "list_tables",
    "pg_dump",
    "pg_restore",
    "revoke",
    "revoke_role",
    "role_exists",
    "row_count",
    "schema_exists",
    "size",
    "table_exists",
    "table_info",
    "table_size",
    "table_sizes",
    "truncate_table",
    "vacuum",
]


@pytest.mark.parametrize("name", REMOVED_FLAT_NAMES)
def test_removed_flat_name_raises_attribute_error_sync(name, config):
    """Each removed flat name raises AttributeError on a Database instance.

    Parameters
    ----------
    name : str
        One of the 56 flat names removed in v0.7.0.
    config : Config
        Bare test config fixture — no live DB connection needed.
    """
    db = Database(config)
    with pytest.raises(AttributeError):
        getattr(db, name)


@pytest.mark.parametrize("name", REMOVED_FLAT_NAMES)
def test_removed_flat_name_raises_attribute_error_async(name, config):
    """Each removed flat name raises AttributeError on an AsyncDatabase instance.

    Parameters
    ----------
    name : str
        One of the 56 flat names removed in v0.7.0.
    config : Config
        Bare test config fixture — no live DB connection needed.
    """
    db = AsyncDatabase(config)
    with pytest.raises(AttributeError):
        getattr(db, name)


def test_no_varargs_on_database_public_surface():
    """WR-01: No ``*args``/``**kwargs`` stubs remain on Database.

    Verifies that the public surface of Database now exposes only
    accessor-namespaced methods with real signatures, restoring IDE
    autocomplete and type-checking on this ``py.typed`` package.
    """
    for name, member in inspect.getmembers(Database, predicate=callable):
        if name.startswith("_"):
            continue
        try:
            params = inspect.signature(member).parameters.values()
            for p in params:
                assert p.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ), f"Database.{name} still has *args/**kwargs"
        except (ValueError, TypeError):
            pass


def test_no_varargs_on_async_database_public_surface():
    """WR-01: No ``*args``/``**kwargs`` stubs remain on AsyncDatabase.

    Verifies that the public surface of AsyncDatabase now exposes only
    accessor-namespaced methods with real signatures, restoring IDE
    autocomplete and type-checking on this ``py.typed`` package.
    """
    for name, member in inspect.getmembers(AsyncDatabase, predicate=callable):
        if name.startswith("_"):
            continue
        try:
            params = inspect.signature(member).parameters.values()
            for p in params:
                assert p.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ), f"AsyncDatabase.{name} still has *args/**kwargs"
        except (ValueError, TypeError):
            pass
