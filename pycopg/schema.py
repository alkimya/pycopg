"""Schema accessor classes for db.schema.* / async_db.schema.*.

This module provides :class:`SchemaAccessor` and
:class:`AsyncSchemaAccessor` — the real implementation of the 32
DDL + introspection helper methods, moved verbatim from
``Database`` / ``AsyncDatabase`` as part of the v0.6.0 accessor
reorganisation (D-06) and extended with 5 introspection helpers in
v0.9.0 (``primary_key``, ``foreign_keys``, ``sequences``, ``views``,
``describe``).

Both classes are exposed on the parent database via a lazy-cached
``schema`` property.  The flat ``db.*`` DDL names were removed in v0.7.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, overload

import pandas as pd
import psycopg

from pycopg import queries
from pycopg.exceptions import TableNotFoundError
from pycopg.utils import (
    validate_extension_name,
    validate_identifier,
    validate_identifiers,
    validate_index_method,
)

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database


@dataclass(frozen=True)
class TableDescription:
    """Typed wrapper around :meth:`SchemaAccessor.describe`'s flat dict (D-12).

    Returned when ``describe(into="dataclass")`` is requested. Fields mirror
    the four ``describe`` dict keys 1:1 — each sub-value is the exact,
    unreshaped output of its standalone helper (:meth:`SchemaAccessor.table_info`,
    :meth:`SchemaAccessor.primary_key`, :meth:`SchemaAccessor.foreign_keys`,
    :meth:`SchemaAccessor.list_indexes`), preserving the D-04 "shapes can
    never drift" invariant — this is a typed wrapper only, never a reshape.

    Parameters
    ----------
    columns : list of dict
        Exact output of :meth:`SchemaAccessor.table_info`.
    primary_key : dict or None
        Exact output of :meth:`SchemaAccessor.primary_key`.
    foreign_keys : list of dict
        Exact output of :meth:`SchemaAccessor.foreign_keys`.
    indexes : list of dict
        Exact output of :meth:`SchemaAccessor.list_indexes`.
    """

    columns: list[dict[str, Any]]
    primary_key: dict[str, Any] | None
    foreign_keys: list[dict[str, Any]]
    indexes: list[dict[str, Any]]


class SchemaAccessor:
    """Schema helper namespace exposed as ``db.schema``.

    Methods are moved verbatim from ``Database``.  DDL and introspection
    operations (databases, extensions, schemas, tables, columns,
    constraints, indexes) are accessible via this accessor.
    """

    def __init__(self, db: Database) -> None:
        """Store the parent database reference.

        Parameters
        ----------
        db : Database
            Parent database instance.  Stored as ``self._db``; no
            connection check is performed at construction time.
        """
        self._db = db

    # =========================================================================
    # DATABASES
    # =========================================================================

    def create_database(
        self, name: str, *, owner: str | None = None, template: str = "template1"
    ) -> None:
        """Create a new database.

        Parameters
        ----------
        name : str
            Database name.
        owner : str, optional
            Owner role.
        template : str, optional
            Template database, by default "template1".
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        validate_identifier(template)
        owner_clause = f" OWNER {owner}" if owner else ""
        # Connect to postgres for database creation
        admin_config = self._db.config.with_database("postgres")
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")

    def drop_database(self, name: str, *, if_exists: bool = True) -> None:
        """Drop a database.

        Parameters
        ----------
        name : str
            Database name.
        if_exists : bool, optional
            Don't error if database doesn't exist, by default True.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        admin_config = self._db.config.with_database("postgres")
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            with conn.cursor() as cur:
                # Terminate existing connections
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """,
                    [name],
                )
                cur.execute(f"DROP DATABASE {if_clause}{name}")

    def database_exists(self, name: str) -> bool:
        """Check if a database exists.

        Parameters
        ----------
        name : str
            Database name.

        Returns
        -------
        bool
            True if database exists.
        """
        admin_config = self._db.config.with_database("postgres")
        with psycopg.connect(**admin_config.connect_params()) as conn:
            with conn.cursor() as cur:
                cur.execute(queries.DATABASE_EXISTS, [name])
                return cur.fetchone() is not None

    def list_databases(self) -> list[str]:
        """List all databases.

        Returns
        -------
        list of str
            List of database names.
        """
        result = self._db.execute(queries.LIST_DATABASES)
        return [r["datname"] for r in result]

    # =========================================================================
    # EXTENSIONS
    # =========================================================================

    def create_extension(
        self, name: str, *, schema: str | None = None, if_not_exists: bool = True
    ) -> None:
        """Create a PostgreSQL extension.

        Parameters
        ----------
        name : str
            Extension name (e.g., 'postgis', 'timescaledb', 'uuid-ossp').
        schema : str, optional
            Schema to install extension in.
        if_not_exists : bool, optional
            Don't error if extension exists, by default True.
        """
        validate_extension_name(name)
        if schema:
            validate_identifier(schema)
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        schema_clause = f" SCHEMA {schema}" if schema else ""
        self._db.execute(
            f'CREATE EXTENSION {if_clause}"{name}"{schema_clause}', autocommit=True
        )

    def drop_extension(
        self, name: str, *, if_exists: bool = True, cascade: bool = False
    ) -> None:
        """Drop a PostgreSQL extension.

        Parameters
        ----------
        name : str
            Extension name.
        if_exists : bool, optional
            Don't error if extension doesn't exist, by default True.
        cascade : bool, optional
            Drop dependent objects, by default False.
        """
        validate_extension_name(name)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        self._db.execute(
            f'DROP EXTENSION {if_clause}"{name}"{cascade_clause}', autocommit=True
        )

    def list_extensions(self) -> list[dict[str, Any]]:
        """List installed extensions.

        Returns
        -------
        list of dict
            List of dicts with extname, extversion, nspname (schema).
        """
        return self._db.execute(queries.LIST_EXTENSIONS)

    def has_extension(self, name: str) -> bool:
        """Check if an extension is installed.

        Parameters
        ----------
        name : str
            Extension name.

        Returns
        -------
        bool
            True if extension is installed.
        """
        result = self._db.execute(queries.EXTENSION_EXISTS, [name])
        return len(result) > 0

    # =========================================================================
    # SCHEMAS
    # =========================================================================

    def create_schema(
        self, name: str, *, if_not_exists: bool = True, owner: str | None = None
    ) -> None:
        """Create a schema.

        Parameters
        ----------
        name : str
            Schema name.
        if_not_exists : bool, optional
            Don't error if schema exists, by default True.
        owner : str, optional
            Owner role.
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        owner_clause = f" AUTHORIZATION {owner}" if owner else ""
        self._db.execute(f"CREATE SCHEMA {if_clause}{name}{owner_clause}")

    def drop_schema(
        self, name: str, *, if_exists: bool = True, cascade: bool = False
    ) -> None:
        """Drop a schema.

        Parameters
        ----------
        name : str
            Schema name.
        if_exists : bool, optional
            Don't error if schema doesn't exist, by default True.
        cascade : bool, optional
            Drop all objects in schema, by default False.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        self._db.execute(f"DROP SCHEMA {if_clause}{name}{cascade_clause}")

    def list_schemas(self) -> list[str]:
        """List all schemas.

        Returns
        -------
        list of str
            List of schema names.
        """
        result = self._db.execute(queries.LIST_SCHEMAS)
        return [r["schema_name"] for r in result]

    def schema_exists(self, name: str) -> bool:
        """Check if a schema exists.

        Parameters
        ----------
        name : str
            Schema name.

        Returns
        -------
        bool
            True if schema exists.
        """
        result = self._db.execute(queries.SCHEMA_EXISTS, [name])
        return len(result) > 0

    # =========================================================================
    # TABLES
    # =========================================================================

    def list_tables(self, *, schema: str = "public") -> list[str]:
        """List tables in a schema.

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            List of table names.
        """
        result = self._db.execute(queries.LIST_TABLES, [schema])
        return [r["table_name"] for r in result]

    def table_exists(self, name: str, *, schema: str = "public") -> bool:
        """Check if a table exists.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        bool
            True if table exists.
        """
        result = self._db.execute(queries.TABLE_EXISTS, [schema, name])
        return len(result) > 0

    def column_exists(self, table: str, column: str, *, schema: str = "public") -> bool:
        """Check if a column exists on a table.

        Parameters
        ----------
        table : str
            Table name.
        column : str
            Column name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        bool
            True if the column exists on the table.
        """
        result = self._db.execute(queries.COLUMN_EXISTS, [schema, table, column])
        return len(result) > 0

    def list_columns(self, table: str, *, schema: str = "public") -> list[str]:
        """Get list of column names for a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            List of column names in ordinal order.
        """
        result = self._db.execute(queries.GET_COLUMNS, [schema, table])
        return [row["column_name"] for row in result]

    def columns_with_types(
        self, table: str, *, schema: str = "public"
    ) -> list[tuple[str, str]]:
        """Get list of (column_name, data_type) tuples for a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of tuple of (str, str)
            List of (name, type) tuples in ordinal order.
        """
        result = self._db.execute(queries.GET_COLUMNS, [schema, table])
        return [(row["column_name"], row["data_type"]) for row in result]

    def drop_table(
        self,
        name: str,
        *,
        schema: str = "public",
        if_exists: bool = True,
        cascade: bool = False,
    ) -> None:
        """Drop a table.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        if_exists : bool, optional
            Don't error if table doesn't exist, by default True.
        cascade : bool, optional
            Drop dependent objects, by default False.
        """
        validate_identifiers(name, schema)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        self._db.execute(f"DROP TABLE {if_clause}{schema}.{name}{cascade_clause}")

    def truncate_table(
        self, name: str, *, schema: str = "public", cascade: bool = False
    ) -> None:
        """Truncate a table (delete all rows).

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        cascade : bool, optional
            Truncate dependent tables, by default False.

        Raises
        ------
        TableNotFoundError
            If the table does not exist in the given schema.
        """
        validate_identifiers(name, schema)
        if not self.table_exists(name, schema=schema):
            raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")
        cascade_clause = " CASCADE" if cascade else ""
        self._db.execute(f"TRUNCATE TABLE {schema}.{name}{cascade_clause}")

    def table_info(self, name: str, *, schema: str = "public") -> list[dict[str, Any]]:
        """Get column information for a table.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of column info dicts with column_name, data_type, is_nullable,
            column_default, ordinal_position.
        """
        return self._db.execute(queries.TABLE_INFO, [schema, name])

    def row_count(self, name: str, *, schema: str = "public") -> int:
        """Get approximate row count for a table.

        Uses pg_stat for speed. For exact count, use execute("SELECT COUNT(*)...").

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Approximate row count.
        """
        result = self._db.execute(queries.ROW_COUNT, [schema, name])
        return result[0]["count"] if result else 0

    def table_size(self, name: str, *, schema: str = "public") -> int:
        """Get the total on-disk size of a table, in bytes.

        Uses ``pg_total_relation_size``, which includes the table's indexes
        and TOAST data in addition to the base heap size. Returns the raw
        byte count with no pretty formatting.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Total table size in bytes (heap + indexes + TOAST).

        Raises
        ------
        TableNotFoundError
            If the table does not exist in the given schema.

        See Also
        --------
        db.maint.table_size : human-readable/pretty size alternative
            (``pretty=True`` by default), a different accessor with
            different semantics and no existence guard.
        """
        validate_identifiers(name, schema)
        if not self.table_exists(name, schema=schema):
            raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")
        result = self._db.execute(queries.TABLE_SIZE, [f"{schema}.{name}"])
        return int(result[0]["size"])

    # =========================================================================
    # CONSTRAINTS & INDEXES
    # =========================================================================

    def add_primary_key(
        self,
        table: str,
        columns: str | list[str],
        *,
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Add primary key constraint to a table.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column name or list of column names.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Constraint name.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)

        cols_str = ", ".join(columns)
        constraint_name = name or f"{table}_pkey"
        self._db.execute(
            f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} PRIMARY KEY ({cols_str})"
        )

    def add_foreign_key(
        self,
        table: str,
        columns: str | list[str],
        ref_table: str,
        ref_columns: str | list[str],
        *,
        schema: str = "public",
        ref_schema: str = "public",
        name: str | None = None,
        on_delete: str = "NO ACTION",
        on_update: str = "NO ACTION",
    ) -> None:
        """Add foreign key constraint.

        Parameters
        ----------
        table : str
            Source table name.
        columns : str or list of str
            Source column(s).
        ref_table : str
            Referenced table name.
        ref_columns : str or list of str
            Referenced column(s).
        schema : str, optional
            Source table schema, by default "public".
        ref_schema : str, optional
            Referenced table schema, by default "public".
        name : str, optional
            Constraint name.
        on_delete : str, optional
            ON DELETE action (CASCADE, SET NULL, NO ACTION, etc.), by default "NO ACTION".
        on_update : str, optional
            ON UPDATE action, by default "NO ACTION".
        """
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(ref_columns, str):
            ref_columns = [ref_columns]

        # Validate all identifiers
        validate_identifiers(
            table, schema, ref_table, ref_schema, *columns, *ref_columns
        )
        if name:
            validate_identifier(name)

        # Validate ON DELETE/UPDATE actions
        valid_actions = {"NO ACTION", "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT"}
        if on_delete.upper() not in valid_actions:
            raise ValueError(
                f"Invalid ON DELETE action: {on_delete}. Must be one of: {valid_actions}"
            )
        if on_update.upper() not in valid_actions:
            raise ValueError(
                f"Invalid ON UPDATE action: {on_update}. Must be one of: {valid_actions}"
            )

        cols_str = ", ".join(columns)
        ref_cols_str = ", ".join(ref_columns)
        constraint_name = name or f"{table}_{columns[0]}_fkey"

        self._db.execute(f"""
            ALTER TABLE {schema}.{table}
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY ({cols_str})
            REFERENCES {ref_schema}.{ref_table} ({ref_cols_str})
            ON DELETE {on_delete}
            ON UPDATE {on_update}
        """)

    def add_unique_constraint(
        self,
        table: str,
        columns: str | list[str],
        *,
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Add unique constraint.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column(s) to make unique.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Constraint name.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)
        cols_str = ", ".join(columns)
        constraint_name = name or f"{table}_{'_'.join(columns)}_key"
        self._db.execute(
            f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} UNIQUE ({cols_str})"
        )

    def create_index(
        self,
        table: str,
        columns: str | list[str],
        *,
        schema: str = "public",
        name: str | None = None,
        unique: bool = False,
        method: str = "btree",
        if_not_exists: bool = True,
    ) -> None:
        """Create an index.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column(s) to index.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Index name (auto-generated if not provided).
        unique : bool, optional
            Create unique index, by default False.
        method : str, optional
            Index method (btree, hash, gist, gin, etc.), by default "btree".
        if_not_exists : bool, optional
            Don't error if index exists, by default True.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)
        validate_index_method(method)

        cols_str = ", ".join(columns)
        index_name = name or f"idx_{table}_{'_'.join(columns)}"
        unique_clause = "UNIQUE " if unique else ""
        if_clause = "IF NOT EXISTS " if if_not_exists else ""

        self._db.execute(f"""
            CREATE {unique_clause}INDEX {if_clause}{index_name}
            ON {schema}.{table} USING {method} ({cols_str})
        """)

    def drop_index(
        self, name: str, *, schema: str = "public", if_exists: bool = True
    ) -> None:
        """Drop an index.

        Parameters
        ----------
        name : str
            Index name.
        schema : str, optional
            Schema name, by default "public".
        if_exists : bool, optional
            Don't error if index doesn't exist, by default True.
        """
        validate_identifiers(schema, name)
        if_clause = "IF EXISTS " if if_exists else ""
        self._db.execute(f"DROP INDEX {if_clause}{schema}.{name}")

    def list_indexes(
        self, table: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """List indexes on a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of index info dicts.
        """
        return self._db.execute(queries.LIST_INDEXES, [schema, table])

    def list_constraints(
        self, table: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """List constraints on a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of constraint info dicts.
        """
        return self._db.execute(queries.LIST_CONSTRAINTS, [schema, table])

    def primary_key(
        self, table: str, *, schema: str = "public"
    ) -> dict[str, Any] | None:
        """Return the primary key constraint for a table, or None if absent.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        dict or None
            Dict with keys ``constraint_name`` and ``columns`` (in key order),
            or ``None`` when the table has no primary key (or does not exist).
        """
        validate_identifiers(table, schema)
        rows = self._db.execute(queries.PRIMARY_KEY, [schema, table])
        if not rows:
            return None
        return {
            "constraint_name": rows[0]["constraint_name"],
            "columns": [r["column_name"] for r in rows],
        }

    def foreign_keys(
        self, table: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """Return all foreign key constraints on a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            Each entry has keys ``constraint_name``, ``columns``,
            ``referenced_table``, and ``referenced_columns`` (columns in key
            order).  Returns ``[]`` when the table has no foreign keys or does
            not exist.
        """
        validate_identifiers(table, schema)
        rows = self._db.execute(queries.FOREIGN_KEYS, [schema, table])
        if not rows:
            return []
        # Group flat rows by constraint_name preserving row order.
        result: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = row["constraint_name"]
            if name not in seen:
                entry: dict[str, Any] = {
                    "constraint_name": name,
                    "columns": [],
                    "referenced_table": row["referenced_table"],
                    "referenced_columns": [],
                }
                seen[name] = entry
                result.append(entry)
            seen[name]["columns"].append(row["column_name"])
            seen[name]["referenced_columns"].append(row["referenced_column"])
        return result

    def sequences(self, *, schema: str = "public") -> list[str]:
        """Return the names of all sequences in a schema.

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            Sequence names in alphabetical order, including SERIAL/identity-backed
            sequences.  Returns ``[]`` when the schema has no sequences.
        """
        validate_identifiers(schema)
        result = self._db.execute(queries.SEQUENCES, [schema])
        return [r["sequence_name"] for r in result]

    def views(self, *, schema: str = "public") -> list[str]:
        """Return the names of regular views in a schema (materialized views excluded).

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            Regular view names in alphabetical order.  Materialized views are
            excluded.  Returns ``[]`` when the schema has no regular views.
        """
        validate_identifiers(schema)
        result = self._db.execute(queries.VIEWS, [schema])
        return [r["table_name"] for r in result]

    def materialized_views(self, *, schema: str = "public") -> list[str]:
        """Return the names of materialized views in a schema.

        ``information_schema.views`` excludes materialized views per the SQL
        standard, so :meth:`views` can never see them — this method queries
        ``pg_catalog.pg_matviews`` directly (D-14).

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            Materialized view names in alphabetical order.  Returns ``[]``
            when the schema has no materialized views.
        """
        validate_identifiers(schema)
        result = self._db.execute(queries.MATERIALIZED_VIEWS, [schema])
        return [r["table_name"] for r in result]

    def materialized_view_columns(
        self, name: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """Get column information for a materialized view.

        Returns the same 8-key shape as :meth:`table_info`
        (``column_name``, ``data_type``, ``is_nullable``, ``column_default``,
        ``ordinal_position``, ``character_maximum_length``,
        ``numeric_precision``, ``numeric_scale``), sourced from
        ``pg_catalog.pg_attribute`` since ``information_schema.columns``
        excludes materialized views (D-14).

        Parameters
        ----------
        name : str
            Materialized view name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of column info dicts in the same shape as
            :meth:`table_info`.  Materialized views never carry NOT NULL
            constraints or column defaults, so ``is_nullable`` is always
            ``'YES'`` and ``column_default`` is always ``None`` — this is
            faithful to what a materialized view actually is, not a bug.
            Returns ``[]`` when the materialized view does not exist.
        """
        validate_identifiers(name, schema)
        return self._db.execute(queries.MATERIALIZED_VIEW_COLUMNS, [schema, name])

    @overload
    def describe(
        self, table: str, *, schema: str = "public", into: Literal["dict"] = "dict"
    ) -> dict[str, Any]: ...
    @overload
    def describe(
        self, table: str, *, schema: str = "public", into: Literal["dataclass"]
    ) -> TableDescription: ...
    @overload
    def describe(
        self, table: str, *, schema: str = "public", into: Literal["dataframe"]
    ) -> pd.DataFrame: ...
    @overload
    def describe(
        self, table: str, *, schema: str = "public", into: str
    ) -> dict[str, Any] | TableDescription | pd.DataFrame: ...
    def describe(
        self, table: str, *, schema: str = "public", into: str = "dict"
    ) -> dict[str, Any] | TableDescription | pd.DataFrame:
        """Return a consolidated introspection snapshot for a table.

        Composes the four standalone helpers into one flat dict.  No new SQL
        is executed — each sub-value is the exact output of its helper, so the
        shapes can never drift from the standalone methods (D-04).

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        into : {"dict", "dataclass", "dataframe"}, optional
            Output shape selector, by default "dict" (D-11). ``"dict"``
            returns the frozen flat dict, byte-identical to the v0.9.0
            default (C-03). ``"dataclass"`` wraps the same sub-values in a
            :class:`TableDescription` (D-12, no reshape). ``"dataframe"``
            returns the ``columns`` section as a one-row-per-column
            :class:`pandas.DataFrame` (D-12) — nullable integer columns are
            promoted to ``float64`` with ``NaN`` for ``None``, a pandas
            dtype-inference artifact, not a data-loss bug.

        Returns
        -------
        dict or TableDescription or pandas.DataFrame
            ``into="dict"`` (default): flat dict with exactly the keys
            ``columns``, ``primary_key``, ``foreign_keys``, and ``indexes``.
            Each value is the output of the corresponding standalone helper.
            For a nonexistent table all sub-values are their empty/None
            defaults: ``columns=[]``, ``primary_key=None``,
            ``foreign_keys=[]``, ``indexes=[]``. ``into="dataclass"``: the
            same four sub-values wrapped in a :class:`TableDescription`.
            ``into="dataframe"``: the ``columns`` sub-value as a
            :class:`pandas.DataFrame`.

        Raises
        ------
        ValueError
            If ``into`` is not one of ``"dict"``, ``"dataclass"``, or
            ``"dataframe"``.
        """
        flat: dict[str, Any] = {
            "columns": self.table_info(table, schema=schema),
            "primary_key": self.primary_key(table, schema=schema),
            "foreign_keys": self.foreign_keys(table, schema=schema),
            "indexes": self.list_indexes(table, schema=schema),
        }
        if into == "dict":
            return flat
        if into == "dataclass":
            return TableDescription(**flat)
        if into == "dataframe":
            return pd.DataFrame(flat["columns"])
        raise ValueError(
            f"into must be 'dict', 'dataclass', or 'dataframe', got {into!r}"
        )


class AsyncSchemaAccessor:
    """Async schema helper namespace exposed as ``async_db.schema``.

    Mirrors :class:`SchemaAccessor` exactly with ``await`` calls.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        """Store the parent async database reference.

        Parameters
        ----------
        db : AsyncDatabase
            Parent async database instance.  Stored as ``self._db``; no
            connection check is performed at construction time.
        """
        self._db = db

    # =========================================================================
    # DATABASES
    # =========================================================================

    async def create_database(
        self, name: str, *, owner: str | None = None, template: str = "template1"
    ) -> None:
        """Create a new database.

        Parameters
        ----------
        name : str
            Database name.
        owner : str, optional
            Owner role.
        template : str, optional
            Template database, by default "template1".
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        validate_identifier(template)
        owner_clause = f" OWNER {owner}" if owner else ""
        # Connect to postgres for database creation
        admin_config = self._db.config.with_database("postgres")
        async with await psycopg.AsyncConnection.connect(
            **admin_config.connect_params(), autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}"
                )

    async def drop_database(self, name: str, *, if_exists: bool = True) -> None:
        """Drop a database.

        Parameters
        ----------
        name : str
            Database name.
        if_exists : bool, optional
            Don't error if database doesn't exist, by default True.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        admin_config = self._db.config.with_database("postgres")
        async with await psycopg.AsyncConnection.connect(
            **admin_config.connect_params(), autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Terminate existing connections
                await cur.execute(
                    """
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """,
                    [name],
                )
                await cur.execute(f"DROP DATABASE {if_clause}{name}")

    async def database_exists(self, name: str) -> bool:
        """Check if a database exists.

        Parameters
        ----------
        name : str
            Database name.

        Returns
        -------
        bool
            True if database exists.
        """
        admin_config = self._db.config.with_database("postgres")
        async with await psycopg.AsyncConnection.connect(
            **admin_config.connect_params()
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(queries.DATABASE_EXISTS, [name])
                return await cur.fetchone() is not None

    async def list_databases(self) -> list[str]:
        """List all databases.

        Returns
        -------
        list of str
            List of database names.
        """
        result = await self._db.execute(queries.LIST_DATABASES)
        return [r["datname"] for r in result]

    # =========================================================================
    # EXTENSIONS
    # =========================================================================

    async def create_extension(
        self, name: str, *, schema: str | None = None, if_not_exists: bool = True
    ) -> None:
        """Create a PostgreSQL extension.

        Parameters
        ----------
        name : str
            Extension name (e.g., 'postgis', 'timescaledb', 'uuid-ossp').
        schema : str, optional
            Schema to install extension in.
        if_not_exists : bool, optional
            Don't error if extension exists, by default True.
        """
        validate_extension_name(name)
        if schema:
            validate_identifier(schema)
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        schema_clause = f" SCHEMA {schema}" if schema else ""
        await self._db.execute(
            f'CREATE EXTENSION {if_clause}"{name}"{schema_clause}', autocommit=True
        )

    async def drop_extension(
        self, name: str, *, if_exists: bool = True, cascade: bool = False
    ) -> None:
        """Drop a PostgreSQL extension.

        Parameters
        ----------
        name : str
            Extension name.
        if_exists : bool, optional
            Don't error if extension doesn't exist, by default True.
        cascade : bool, optional
            Drop dependent objects, by default False.
        """
        validate_extension_name(name)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        await self._db.execute(
            f'DROP EXTENSION {if_clause}"{name}"{cascade_clause}', autocommit=True
        )

    async def list_extensions(self) -> list[dict[str, Any]]:
        """List installed extensions.

        Returns
        -------
        list of dict
            List of dicts with extname, extversion, nspname (schema).
        """
        return await self._db.execute(queries.LIST_EXTENSIONS)

    async def has_extension(self, name: str) -> bool:
        """Check if an extension is installed.

        Parameters
        ----------
        name : str
            Extension name.

        Returns
        -------
        bool
            True if extension is installed.
        """
        result = await self._db.execute(queries.EXTENSION_EXISTS, [name])
        return len(result) > 0

    # =========================================================================
    # SCHEMAS
    # =========================================================================

    async def list_schemas(self) -> list[str]:
        """List all schemas.

        Returns
        -------
        list of str
            List of schema names.
        """
        result = await self._db.execute(queries.LIST_SCHEMAS)
        return [r["schema_name"] for r in result]

    async def schema_exists(self, name: str) -> bool:
        """Check if a schema exists.

        Parameters
        ----------
        name : str
            Schema name.

        Returns
        -------
        bool
            True if schema exists.
        """
        result = await self._db.execute(queries.SCHEMA_EXISTS, [name])
        return len(result) > 0

    async def create_schema(
        self, name: str, *, if_not_exists: bool = True, owner: str | None = None
    ) -> None:
        """Create a schema.

        Parameters
        ----------
        name : str
            Schema name.
        if_not_exists : bool, optional
            Don't error if schema exists, by default True.
        owner : str, optional
            Owner role.
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        owner_clause = f" AUTHORIZATION {owner}" if owner else ""
        await self._db.execute(f"CREATE SCHEMA {if_clause}{name}{owner_clause}")

    async def drop_schema(
        self, name: str, *, if_exists: bool = True, cascade: bool = False
    ) -> None:
        """Drop a schema.

        Parameters
        ----------
        name : str
            Schema name.
        if_exists : bool, optional
            Don't error if schema doesn't exist, by default True.
        cascade : bool, optional
            Drop all objects in schema, by default False.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        await self._db.execute(f"DROP SCHEMA {if_clause}{name}{cascade_clause}")

    # =========================================================================
    # TABLES
    # =========================================================================

    async def list_tables(self, *, schema: str = "public") -> list[str]:
        """List tables in a schema.

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            List of table names.
        """
        result = await self._db.execute(queries.LIST_TABLES, [schema])
        return [r["table_name"] for r in result]

    async def table_exists(self, name: str, *, schema: str = "public") -> bool:
        """Check if a table exists.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        bool
            True if table exists.
        """
        result = await self._db.execute(queries.TABLE_EXISTS, [schema, name])
        return len(result) > 0

    async def column_exists(
        self, table: str, column: str, *, schema: str = "public"
    ) -> bool:
        """Check if a column exists on a table.

        Parameters
        ----------
        table : str
            Table name.
        column : str
            Column name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        bool
            True if the column exists on the table.
        """
        result = await self._db.execute(queries.COLUMN_EXISTS, [schema, table, column])
        return len(result) > 0

    async def list_columns(self, table: str, *, schema: str = "public") -> list[str]:
        """Get list of column names for a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            List of column names in ordinal order.
        """
        result = await self._db.execute(queries.GET_COLUMNS, [schema, table])
        return [row["column_name"] for row in result]

    async def columns_with_types(
        self, table: str, *, schema: str = "public"
    ) -> list[tuple[str, str]]:
        """Get list of (column_name, data_type) tuples for a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of tuple of (str, str)
            List of (name, type) tuples in ordinal order.
        """
        result = await self._db.execute(queries.GET_COLUMNS, [schema, table])
        return [(row["column_name"], row["data_type"]) for row in result]

    async def table_info(
        self, name: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """Get column information for a table.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of column info dicts with column_name, data_type, is_nullable,
            column_default, ordinal_position.
        """
        return await self._db.execute(queries.TABLE_INFO, [schema, name])

    async def row_count(self, name: str, *, schema: str = "public") -> int:
        """Get approximate row count for a table.

        Uses pg_stat for speed. For exact count, use execute("SELECT COUNT(*)...").

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Approximate row count.
        """
        result = await self._db.execute(queries.ROW_COUNT, [schema, name])
        return result[0]["count"] if result else 0

    async def table_size(self, name: str, *, schema: str = "public") -> int:
        """Get the total on-disk size of a table, in bytes.

        Uses ``pg_total_relation_size``, which includes the table's indexes
        and TOAST data in addition to the base heap size. Returns the raw
        byte count with no pretty formatting.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Total table size in bytes (heap + indexes + TOAST).

        Raises
        ------
        TableNotFoundError
            If the table does not exist in the given schema.

        See Also
        --------
        db.maint.table_size : human-readable/pretty size alternative
            (``pretty=True`` by default), a different accessor with
            different semantics and no existence guard.
        """
        validate_identifiers(name, schema)
        if not await self.table_exists(name, schema=schema):
            raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")
        result = await self._db.execute(queries.TABLE_SIZE, [f"{schema}.{name}"])
        return int(result[0]["size"])

    async def drop_table(
        self,
        name: str,
        *,
        schema: str = "public",
        if_exists: bool = True,
        cascade: bool = False,
    ) -> None:
        """Drop a table.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        if_exists : bool, optional
            Don't error if table doesn't exist, by default True.
        cascade : bool, optional
            Drop dependent objects, by default False.
        """
        validate_identifiers(name, schema)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        await self._db.execute(f"DROP TABLE {if_clause}{schema}.{name}{cascade_clause}")

    async def truncate_table(
        self, name: str, *, schema: str = "public", cascade: bool = False
    ) -> None:
        """Truncate a table (delete all rows).

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        cascade : bool, optional
            Truncate dependent tables, by default False.

        Raises
        ------
        TableNotFoundError
            If the table does not exist in the given schema.
        """
        validate_identifiers(name, schema)
        if not await self.table_exists(name, schema=schema):
            raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")
        cascade_clause = " CASCADE" if cascade else ""
        await self._db.execute(f"TRUNCATE TABLE {schema}.{name}{cascade_clause}")

    # =========================================================================
    # CONSTRAINTS & INDEXES
    # =========================================================================

    async def add_primary_key(
        self,
        table: str,
        columns: str | list[str],
        *,
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Add primary key constraint to a table.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column name or list of column names.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Constraint name.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)

        cols_str = ", ".join(columns)
        constraint_name = name or f"{table}_pkey"
        await self._db.execute(
            f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} PRIMARY KEY ({cols_str})"
        )

    async def add_foreign_key(
        self,
        table: str,
        columns: str | list[str],
        ref_table: str,
        ref_columns: str | list[str],
        *,
        schema: str = "public",
        ref_schema: str = "public",
        name: str | None = None,
        on_delete: str = "NO ACTION",
        on_update: str = "NO ACTION",
    ) -> None:
        """Add foreign key constraint.

        Parameters
        ----------
        table : str
            Source table name.
        columns : str or list of str
            Source column(s).
        ref_table : str
            Referenced table name.
        ref_columns : str or list of str
            Referenced column(s).
        schema : str, optional
            Source table schema, by default "public".
        ref_schema : str, optional
            Referenced table schema, by default "public".
        name : str, optional
            Constraint name.
        on_delete : str, optional
            ON DELETE action (CASCADE, SET NULL, NO ACTION, etc.), by default "NO ACTION".
        on_update : str, optional
            ON UPDATE action, by default "NO ACTION".
        """
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(ref_columns, str):
            ref_columns = [ref_columns]

        # Validate all identifiers
        validate_identifiers(
            table, schema, ref_table, ref_schema, *columns, *ref_columns
        )
        if name:
            validate_identifier(name)

        # Validate ON DELETE/UPDATE actions
        valid_actions = {"NO ACTION", "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT"}
        if on_delete.upper() not in valid_actions:
            raise ValueError(
                f"Invalid ON DELETE action: {on_delete}. Must be one of: {valid_actions}"
            )
        if on_update.upper() not in valid_actions:
            raise ValueError(
                f"Invalid ON UPDATE action: {on_update}. Must be one of: {valid_actions}"
            )

        cols_str = ", ".join(columns)
        ref_cols_str = ", ".join(ref_columns)
        constraint_name = name or f"{table}_{columns[0]}_fkey"

        await self._db.execute(f"""
            ALTER TABLE {schema}.{table}
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY ({cols_str})
            REFERENCES {ref_schema}.{ref_table} ({ref_cols_str})
            ON DELETE {on_delete}
            ON UPDATE {on_update}
        """)

    async def add_unique_constraint(
        self,
        table: str,
        columns: str | list[str],
        *,
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Add unique constraint.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column(s) to make unique.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Constraint name.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)
        cols_str = ", ".join(columns)
        constraint_name = name or f"{table}_{'_'.join(columns)}_key"
        await self._db.execute(
            f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} UNIQUE ({cols_str})"
        )

    async def create_index(
        self,
        table: str,
        columns: str | list[str],
        *,
        schema: str = "public",
        name: str | None = None,
        unique: bool = False,
        method: str = "btree",
        if_not_exists: bool = True,
    ) -> None:
        """Create an index.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column(s) to index.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Index name (auto-generated if not provided).
        unique : bool, optional
            Create unique index, by default False.
        method : str, optional
            Index method (btree, hash, gist, gin, etc.), by default "btree".
        if_not_exists : bool, optional
            Don't error if index exists, by default True.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)
        validate_index_method(method)

        cols_str = ", ".join(columns)
        index_name = name or f"idx_{table}_{'_'.join(columns)}"
        unique_clause = "UNIQUE " if unique else ""
        if_clause = "IF NOT EXISTS " if if_not_exists else ""

        await self._db.execute(f"""
            CREATE {unique_clause}INDEX {if_clause}{index_name}
            ON {schema}.{table} USING {method} ({cols_str})
        """)

    async def drop_index(
        self, name: str, *, schema: str = "public", if_exists: bool = True
    ) -> None:
        """Drop an index.

        Parameters
        ----------
        name : str
            Index name.
        schema : str, optional
            Schema name, by default "public".
        if_exists : bool, optional
            Don't error if index doesn't exist, by default True.
        """
        validate_identifiers(schema, name)
        if_clause = "IF EXISTS " if if_exists else ""
        await self._db.execute(f"DROP INDEX {if_clause}{schema}.{name}")

    async def list_indexes(
        self, table: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """List indexes on a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of index info dicts.
        """
        return await self._db.execute(queries.LIST_INDEXES, [schema, table])

    async def list_constraints(
        self, table: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """List constraints on a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of constraint info dicts.
        """
        return await self._db.execute(queries.LIST_CONSTRAINTS, [schema, table])

    async def primary_key(
        self, table: str, *, schema: str = "public"
    ) -> dict[str, Any] | None:
        """Return the primary key constraint for a table, or None if absent.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        dict or None
            Dict with keys ``constraint_name`` and ``columns`` (in key order),
            or ``None`` when the table has no primary key (or does not exist).
        """
        validate_identifiers(table, schema)
        rows = await self._db.execute(queries.PRIMARY_KEY, [schema, table])
        if not rows:
            return None
        return {
            "constraint_name": rows[0]["constraint_name"],
            "columns": [r["column_name"] for r in rows],
        }

    async def foreign_keys(
        self, table: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """Return all foreign key constraints on a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            Each entry has keys ``constraint_name``, ``columns``,
            ``referenced_table``, and ``referenced_columns`` (columns in key
            order).  Returns ``[]`` when the table has no foreign keys or does
            not exist.
        """
        validate_identifiers(table, schema)
        rows = await self._db.execute(queries.FOREIGN_KEYS, [schema, table])
        if not rows:
            return []
        # Group flat rows by constraint_name preserving row order.
        result: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = row["constraint_name"]
            if name not in seen:
                entry: dict[str, Any] = {
                    "constraint_name": name,
                    "columns": [],
                    "referenced_table": row["referenced_table"],
                    "referenced_columns": [],
                }
                seen[name] = entry
                result.append(entry)
            seen[name]["columns"].append(row["column_name"])
            seen[name]["referenced_columns"].append(row["referenced_column"])
        return result

    async def sequences(self, *, schema: str = "public") -> list[str]:
        """Return the names of all sequences in a schema.

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            Sequence names in alphabetical order, including SERIAL/identity-backed
            sequences.  Returns ``[]`` when the schema has no sequences.
        """
        validate_identifiers(schema)
        result = await self._db.execute(queries.SEQUENCES, [schema])
        return [r["sequence_name"] for r in result]

    async def views(self, *, schema: str = "public") -> list[str]:
        """Return the names of regular views in a schema (materialized views excluded).

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            Regular view names in alphabetical order.  Materialized views are
            excluded.  Returns ``[]`` when the schema has no regular views.
        """
        validate_identifiers(schema)
        result = await self._db.execute(queries.VIEWS, [schema])
        return [r["table_name"] for r in result]

    async def materialized_views(self, *, schema: str = "public") -> list[str]:
        """Return the names of materialized views in a schema.

        ``information_schema.views`` excludes materialized views per the SQL
        standard, so :meth:`views` can never see them — this method queries
        ``pg_catalog.pg_matviews`` directly (D-14).

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            Materialized view names in alphabetical order.  Returns ``[]``
            when the schema has no materialized views.
        """
        validate_identifiers(schema)
        result = await self._db.execute(queries.MATERIALIZED_VIEWS, [schema])
        return [r["table_name"] for r in result]

    async def materialized_view_columns(
        self, name: str, *, schema: str = "public"
    ) -> list[dict[str, Any]]:
        """Get column information for a materialized view.

        Returns the same 8-key shape as :meth:`table_info`
        (``column_name``, ``data_type``, ``is_nullable``, ``column_default``,
        ``ordinal_position``, ``character_maximum_length``,
        ``numeric_precision``, ``numeric_scale``), sourced from
        ``pg_catalog.pg_attribute`` since ``information_schema.columns``
        excludes materialized views (D-14).

        Parameters
        ----------
        name : str
            Materialized view name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of column info dicts in the same shape as
            :meth:`table_info`.  Materialized views never carry NOT NULL
            constraints or column defaults, so ``is_nullable`` is always
            ``'YES'`` and ``column_default`` is always ``None`` — this is
            faithful to what a materialized view actually is, not a bug.
            Returns ``[]`` when the materialized view does not exist.
        """
        validate_identifiers(name, schema)
        return await self._db.execute(
            queries.MATERIALIZED_VIEW_COLUMNS, [schema, name]
        )

    @overload
    async def describe(
        self, table: str, *, schema: str = "public", into: Literal["dict"] = "dict"
    ) -> dict[str, Any]: ...
    @overload
    async def describe(
        self, table: str, *, schema: str = "public", into: Literal["dataclass"]
    ) -> TableDescription: ...
    @overload
    async def describe(
        self, table: str, *, schema: str = "public", into: Literal["dataframe"]
    ) -> pd.DataFrame: ...
    @overload
    async def describe(
        self, table: str, *, schema: str = "public", into: str
    ) -> dict[str, Any] | TableDescription | pd.DataFrame: ...
    async def describe(
        self, table: str, *, schema: str = "public", into: str = "dict"
    ) -> dict[str, Any] | TableDescription | pd.DataFrame:
        """Return a consolidated introspection snapshot for a table.

        Composes the four standalone helpers into one flat dict.  No new SQL
        is executed — each sub-value is the exact output of its helper, so the
        shapes can never drift from the standalone methods (D-04).

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        into : {"dict", "dataclass", "dataframe"}, optional
            Output shape selector, by default "dict" (D-11). ``"dict"``
            returns the frozen flat dict, byte-identical to the v0.9.0
            default (C-03). ``"dataclass"`` wraps the same sub-values in a
            :class:`TableDescription` (D-12, no reshape). ``"dataframe"``
            returns the ``columns`` section as a one-row-per-column
            :class:`pandas.DataFrame` (D-12) — nullable integer columns are
            promoted to ``float64`` with ``NaN`` for ``None``, a pandas
            dtype-inference artifact, not a data-loss bug.

        Returns
        -------
        dict or TableDescription or pandas.DataFrame
            ``into="dict"`` (default): flat dict with exactly the keys
            ``columns``, ``primary_key``, ``foreign_keys``, and ``indexes``.
            Each value is the output of the corresponding standalone helper.
            For a nonexistent table all sub-values are their empty/None
            defaults: ``columns=[]``, ``primary_key=None``,
            ``foreign_keys=[]``, ``indexes=[]``. ``into="dataclass"``: the
            same four sub-values wrapped in a :class:`TableDescription`.
            ``into="dataframe"``: the ``columns`` sub-value as a
            :class:`pandas.DataFrame`.

        Raises
        ------
        ValueError
            If ``into`` is not one of ``"dict"``, ``"dataclass"``, or
            ``"dataframe"``.
        """
        flat: dict[str, Any] = {
            "columns": await self.table_info(table, schema=schema),
            "primary_key": await self.primary_key(table, schema=schema),
            "foreign_keys": await self.foreign_keys(table, schema=schema),
            "indexes": await self.list_indexes(table, schema=schema),
        }
        if into == "dict":
            return flat
        if into == "dataclass":
            return TableDescription(**flat)
        if into == "dataframe":
            return pd.DataFrame(flat["columns"])
        raise ValueError(
            f"into must be 'dict', 'dataclass', or 'dataframe', got {into!r}"
        )
