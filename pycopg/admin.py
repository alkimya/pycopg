"""Admin accessor classes for db.admin.* / async_db.admin.*.

This module provides :class:`AdminAccessor` and
:class:`AsyncAdminAccessor` — the real implementation of the 11
admin (roles & permissions) helper methods, moved verbatim from
``Database`` / ``AsyncDatabase`` as part of the v0.6.0 accessor
reorganisation (D-06).

Both classes are exposed on the parent database via a lazy-cached
``admin`` property added in plan 02.  The flat ``db.*`` names remain
as thin deprecated aliases (see :mod:`pycopg.aliases`) until v0.7.0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pycopg import queries
from pycopg.base import build_role_options
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_object_type,
    validate_privileges,
    validate_timestamp,
)

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database


class AdminAccessor:
    """Admin helper namespace exposed as ``db.admin``.

    Methods are moved verbatim from ``Database``.  Role and permission
    management operations are accessible via this accessor.
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

    def create_role(
        self,
        name: str,
        password: str | None = None,
        login: bool = True,
        superuser: bool = False,
        createdb: bool = False,
        createrole: bool = False,
        inherit: bool = True,
        replication: bool = False,
        connection_limit: int = -1,
        valid_until: str | None = None,
        in_roles: list[str] | None = None,
        if_not_exists: bool = True,
    ) -> None:
        """Create a database role/user.

        Parameters
        ----------
        name : str
            Role name.
        password : str, optional
            Role password (for login roles).
        login : bool, optional
            Can log in (True = user, False = group role), by default True.
        superuser : bool, optional
            Is superuser, by default False.
        createdb : bool, optional
            Can create databases, by default False.
        createrole : bool, optional
            Can create other roles, by default False.
        inherit : bool, optional
            Inherits privileges from member roles, by default True.
        replication : bool, optional
            Can initiate streaming replication, by default False.
        connection_limit : int, optional
            Max concurrent connections (-1 = unlimited), by default -1.
        valid_until : str, optional
            Password expiration (e.g., '2025-12-31').
        in_roles : list of str, optional
            List of roles to be a member of.
        if_not_exists : bool, optional
            Don't error if role exists, by default True.
        """
        validate_identifier(name)

        # Check if exists
        if if_not_exists and self._db.admin.role_exists(name):
            return

        options = build_role_options(
            login=login,
            superuser=superuser,
            createdb=createdb,
            createrole=createrole,
            inherit=inherit,
            replication=replication,
            connection_limit=connection_limit,
            password=password,
            valid_until=valid_until,
        )
        options_str = " ".join(options)

        if password:
            with self._db.cursor(autocommit=True) as cur:
                cur.execute(f"CREATE ROLE {name} WITH {options_str}", [password])
        else:
            self._db.execute(f"CREATE ROLE {name} WITH {options_str}", autocommit=True)

        # Add to roles
        if in_roles:
            for role in in_roles:
                self._db.admin.grant_role(role, name)

    def drop_role(self, name: str, if_exists: bool = True) -> None:
        """Drop a role.

        Parameters
        ----------
        name : str
            Role name.
        if_exists : bool, optional
            Don't error if role doesn't exist, by default True.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        self._db.execute(f"DROP ROLE {if_clause}{name}", autocommit=True)

    def role_exists(self, name: str) -> bool:
        """Check if a role exists.

        Parameters
        ----------
        name : str
            Role name.

        Returns
        -------
        bool
            True if role exists.
        """
        result = self._db.execute(queries.ROLE_EXISTS, [name])
        return len(result) > 0

    def list_roles(self, include_system: bool = False) -> list[dict]:
        """List all roles.

        Parameters
        ----------
        include_system : bool, optional
            Include system roles (pg_*), by default False.

        Returns
        -------
        list of dict
            List of role info dicts.
        """
        where_clause = "" if include_system else "WHERE rolname NOT LIKE 'pg_%'"
        return self._db.execute(queries.LIST_ROLES.format(where_clause=where_clause))

    def alter_role(
        self,
        name: str,
        password: str | None = None,
        login: bool | None = None,
        superuser: bool | None = None,
        createdb: bool | None = None,
        createrole: bool | None = None,
        connection_limit: int | None = None,
        valid_until: str | None = None,
        rename_to: str | None = None,
    ) -> None:
        """Alter a role's attributes.

        Parameters
        ----------
        name : str
            Role name.
        password : str, optional
            New password.
        login : bool, optional
            Enable/disable login.
        superuser : bool, optional
            Enable/disable superuser.
        createdb : bool, optional
            Enable/disable createdb.
        createrole : bool, optional
            Enable/disable createrole.
        connection_limit : int, optional
            New connection limit.
        valid_until : str, optional
            New password expiration.
        rename_to : str, optional
            Rename the role.
        """
        validate_identifier(name)

        if rename_to:
            validate_identifier(rename_to)
            self._db.execute(
                f"ALTER ROLE {name} RENAME TO {rename_to}", autocommit=True
            )
            return

        options = []
        params = []

        if password is not None:
            options.append("PASSWORD %s")
            params.append(password)
        if login is not None:
            options.append("LOGIN" if login else "NOLOGIN")
        if superuser is not None:
            options.append("SUPERUSER" if superuser else "NOSUPERUSER")
        if createdb is not None:
            options.append("CREATEDB" if createdb else "NOCREATEDB")
        if createrole is not None:
            options.append("CREATEROLE" if createrole else "NOCREATEROLE")
        if connection_limit is not None:
            options.append(f"CONNECTION LIMIT {connection_limit}")
        if valid_until is not None:
            validate_timestamp(valid_until)
            options.append(f"VALID UNTIL '{valid_until}'")

        if options:
            options_str = " ".join(options)
            with self._db.cursor(autocommit=True) as cur:
                cur.execute(
                    f"ALTER ROLE {name} WITH {options_str}", params if params else None
                )

    def grant_role(self, role: str, member: str, with_admin: bool = False) -> None:
        """Grant role membership to another role.

        Parameters
        ----------
        role : str
            Role to grant.
        member : str
            Role receiving membership.
        with_admin : bool, optional
            Allow member to grant role to others, by default False.
        """
        validate_identifiers(role, member)
        admin_clause = " WITH ADMIN OPTION" if with_admin else ""
        self._db.execute(f"GRANT {role} TO {member}{admin_clause}", autocommit=True)

    def revoke_role(self, role: str, member: str) -> None:
        """Revoke role membership from a role.

        Parameters
        ----------
        role : str
            Role to revoke.
        member : str
            Role losing membership.
        """
        validate_identifiers(role, member)
        self._db.execute(f"REVOKE {role} FROM {member}", autocommit=True)

    def grant(
        self,
        privileges: str | list[str],
        on: str,
        to: str,
        object_type: str = "TABLE",
        schema: str = "public",
        with_grant_option: bool = False,
    ) -> None:
        """Grant privileges on database objects.

        Parameters
        ----------
        privileges : str or list of str
            Privilege(s) to grant (SELECT, INSERT, UPDATE, DELETE, ALL, etc.).
        on : str
            Object name or ALL TABLES/SEQUENCES/FUNCTIONS.
        to : str
            Role receiving privileges.
        object_type : str, optional
            Type of object (TABLE, SEQUENCE, FUNCTION, SCHEMA, DATABASE),
            by default "TABLE".
        schema : str, optional
            Schema name (for tables/sequences), by default "public".
        with_grant_option : bool, optional
            Allow grantee to grant to others, by default False.
        """
        validate_identifier(to)
        validate_object_type(object_type)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)
        validate_privileges(privileges)

        grant_clause = " WITH GRANT OPTION" if with_grant_option else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            self._db.execute(
                f"GRANT {privileges} ON SCHEMA {on} TO {to}{grant_clause}",
                autocommit=True,
            )
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            self._db.execute(
                f"GRANT {privileges} ON DATABASE {on} TO {to}{grant_clause}",
                autocommit=True,
            )
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            self._db.execute(
                f"GRANT {privileges} ON {on} IN SCHEMA {schema} TO {to}{grant_clause}",
                autocommit=True,
            )
        else:
            validate_identifiers(on, schema)
            self._db.execute(
                f"GRANT {privileges} ON {object_type} {schema}.{on} TO {to}{grant_clause}",
                autocommit=True,
            )

    def revoke(
        self,
        privileges: str | list[str],
        on: str,
        from_role: str,
        object_type: str = "TABLE",
        schema: str = "public",
        cascade: bool = False,
    ) -> None:
        """Revoke privileges on database objects.

        Parameters
        ----------
        privileges : str or list of str
            Privilege(s) to revoke.
        on : str
            Object name or ALL TABLES/SEQUENCES/FUNCTIONS.
        from_role : str
            Role losing privileges.
        object_type : str, optional
            Type of object, by default "TABLE".
        schema : str, optional
            Schema name, by default "public".
        cascade : bool, optional
            Revoke from dependent privileges, by default False.
        """
        validate_identifier(from_role)
        validate_object_type(object_type)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)
        validate_privileges(privileges)

        cascade_clause = " CASCADE" if cascade else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            self._db.execute(
                f"REVOKE {privileges} ON SCHEMA {on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            self._db.execute(
                f"REVOKE {privileges} ON DATABASE {on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            self._db.execute(
                f"REVOKE {privileges} ON {on} IN SCHEMA {schema} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        else:
            validate_identifiers(on, schema)
            self._db.execute(
                f"REVOKE {privileges} ON {object_type} {schema}.{on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )

    def list_role_members(self, role: str) -> list[str]:
        """List members of a role.

        Parameters
        ----------
        role : str
            Role name.

        Returns
        -------
        list of str
            List of member role names.
        """
        result = self._db.execute(queries.LIST_ROLE_MEMBERS, [role])
        return [r["member"] for r in result]

    def list_role_grants(self, role: str) -> list[dict]:
        """List privileges granted to a role.

        Parameters
        ----------
        role : str
            Role name.

        Returns
        -------
        list of dict
            List of privilege info dicts.
        """
        return self._db.execute(queries.LIST_ROLE_GRANTS, [role])


class AsyncAdminAccessor:
    """Async admin helper namespace exposed as ``async_db.admin``.

    Mirrors :class:`AdminAccessor` exactly with ``await`` calls.
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

    async def create_role(
        self,
        name: str,
        password: str | None = None,
        login: bool = True,
        superuser: bool = False,
        createdb: bool = False,
        createrole: bool = False,
        inherit: bool = True,
        replication: bool = False,
        connection_limit: int = -1,
        valid_until: str | None = None,
        in_roles: list[str] | None = None,
        if_not_exists: bool = True,
    ) -> None:
        """Create a database role/user.

        Parameters
        ----------
        name : str
            Role name.
        password : str, optional
            Role password (for login roles).
        login : bool, optional
            Can log in (True = user, False = group role), by default True.
        superuser : bool, optional
            Is superuser, by default False.
        createdb : bool, optional
            Can create databases, by default False.
        createrole : bool, optional
            Can create other roles, by default False.
        inherit : bool, optional
            Inherits privileges from member roles, by default True.
        replication : bool, optional
            Can initiate streaming replication, by default False.
        connection_limit : int, optional
            Max concurrent connections (-1 = unlimited), by default -1.
        valid_until : str, optional
            Password expiration (e.g., '2025-12-31').
        in_roles : list of str, optional
            List of roles to be a member of.
        if_not_exists : bool, optional
            Don't error if role exists, by default True.
        """
        validate_identifier(name)

        # Check if exists
        if if_not_exists and await self._db.admin.role_exists(name):
            return

        options = build_role_options(
            login=login,
            superuser=superuser,
            createdb=createdb,
            createrole=createrole,
            inherit=inherit,
            replication=replication,
            connection_limit=connection_limit,
            password=password,
            valid_until=valid_until,
        )
        options_str = " ".join(options)

        if password:
            async with self._db.cursor(autocommit=True) as cur:
                await cur.execute(f"CREATE ROLE {name} WITH {options_str}", [password])
        else:
            await self._db.execute(
                f"CREATE ROLE {name} WITH {options_str}", autocommit=True
            )

        # Add to roles
        if in_roles:
            for role in in_roles:
                await self._db.admin.grant_role(role, name)

    async def drop_role(self, name: str, if_exists: bool = True) -> None:
        """Drop a role.

        Parameters
        ----------
        name : str
            Role name.
        if_exists : bool, optional
            Don't error if role doesn't exist, by default True.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        await self._db.execute(f"DROP ROLE {if_clause}{name}", autocommit=True)

    async def role_exists(self, name: str) -> bool:
        """Check if a role exists.

        Parameters
        ----------
        name : str
            Role name.

        Returns
        -------
        bool
            True if role exists.
        """
        result = await self._db.execute(queries.ROLE_EXISTS, [name])
        return len(result) > 0

    async def list_roles(self, include_system: bool = False) -> list[dict]:
        """List all roles.

        Parameters
        ----------
        include_system : bool, optional
            Include system roles (pg_*), by default False.

        Returns
        -------
        list of dict
            List of role info dicts.
        """
        where_clause = "" if include_system else "WHERE rolname NOT LIKE 'pg_%'"
        return await self._db.execute(
            queries.LIST_ROLES.format(where_clause=where_clause)
        )

    async def alter_role(
        self,
        name: str,
        password: str | None = None,
        login: bool | None = None,
        superuser: bool | None = None,
        createdb: bool | None = None,
        createrole: bool | None = None,
        connection_limit: int | None = None,
        valid_until: str | None = None,
        rename_to: str | None = None,
    ) -> None:
        """Alter a role's attributes.

        Parameters
        ----------
        name : str
            Role name.
        password : str, optional
            New password.
        login : bool, optional
            Enable/disable login.
        superuser : bool, optional
            Enable/disable superuser.
        createdb : bool, optional
            Enable/disable createdb.
        createrole : bool, optional
            Enable/disable createrole.
        connection_limit : int, optional
            New connection limit.
        valid_until : str, optional
            New password expiration.
        rename_to : str, optional
            Rename the role.
        """
        validate_identifier(name)

        if rename_to:
            validate_identifier(rename_to)
            await self._db.execute(
                f"ALTER ROLE {name} RENAME TO {rename_to}", autocommit=True
            )
            return

        options = []
        params = []

        if password is not None:
            options.append("PASSWORD %s")
            params.append(password)
        if login is not None:
            options.append("LOGIN" if login else "NOLOGIN")
        if superuser is not None:
            options.append("SUPERUSER" if superuser else "NOSUPERUSER")
        if createdb is not None:
            options.append("CREATEDB" if createdb else "NOCREATEDB")
        if createrole is not None:
            options.append("CREATEROLE" if createrole else "NOCREATEROLE")
        if connection_limit is not None:
            options.append(f"CONNECTION LIMIT {connection_limit}")
        if valid_until is not None:
            validate_timestamp(valid_until)
            options.append(f"VALID UNTIL '{valid_until}'")

        if options:
            options_str = " ".join(options)
            async with self._db.cursor(autocommit=True) as cur:
                await cur.execute(
                    f"ALTER ROLE {name} WITH {options_str}", params if params else None
                )

    async def grant_role(
        self, role: str, member: str, with_admin: bool = False
    ) -> None:
        """Grant role membership to another role.

        Parameters
        ----------
        role : str
            Role to grant.
        member : str
            Role receiving membership.
        with_admin : bool, optional
            Allow member to grant role to others, by default False.
        """
        validate_identifiers(role, member)
        admin_clause = " WITH ADMIN OPTION" if with_admin else ""
        await self._db.execute(
            f"GRANT {role} TO {member}{admin_clause}", autocommit=True
        )

    async def revoke_role(self, role: str, member: str) -> None:
        """Revoke role membership from a role.

        Parameters
        ----------
        role : str
            Role to revoke.
        member : str
            Role losing membership.
        """
        validate_identifiers(role, member)
        await self._db.execute(f"REVOKE {role} FROM {member}", autocommit=True)

    async def grant(
        self,
        privileges: str | list[str],
        on: str,
        to: str,
        object_type: str = "TABLE",
        schema: str = "public",
        with_grant_option: bool = False,
    ) -> None:
        """Grant privileges on database objects.

        Parameters
        ----------
        privileges : str or list of str
            Privilege(s) to grant (SELECT, INSERT, UPDATE, DELETE, ALL, etc.).
        on : str
            Object name or ALL TABLES/SEQUENCES/FUNCTIONS.
        to : str
            Role receiving privileges.
        object_type : str, optional
            Type of object (TABLE, SEQUENCE, FUNCTION, SCHEMA, DATABASE),
            by default "TABLE".
        schema : str, optional
            Schema name (for tables/sequences), by default "public".
        with_grant_option : bool, optional
            Allow grantee to grant to others, by default False.
        """
        validate_identifier(to)
        validate_object_type(object_type)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)
        validate_privileges(privileges)

        grant_clause = " WITH GRANT OPTION" if with_grant_option else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            await self._db.execute(
                f"GRANT {privileges} ON SCHEMA {on} TO {to}{grant_clause}",
                autocommit=True,
            )
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            await self._db.execute(
                f"GRANT {privileges} ON DATABASE {on} TO {to}{grant_clause}",
                autocommit=True,
            )
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            await self._db.execute(
                f"GRANT {privileges} ON {on} IN SCHEMA {schema} TO {to}{grant_clause}",
                autocommit=True,
            )
        else:
            validate_identifiers(on, schema)
            await self._db.execute(
                f"GRANT {privileges} ON {object_type} {schema}.{on} TO {to}{grant_clause}",
                autocommit=True,
            )

    async def revoke(
        self,
        privileges: str | list[str],
        on: str,
        from_role: str,
        object_type: str = "TABLE",
        schema: str = "public",
        cascade: bool = False,
    ) -> None:
        """Revoke privileges on database objects.

        Parameters
        ----------
        privileges : str or list of str
            Privilege(s) to revoke.
        on : str
            Object name or ALL TABLES/SEQUENCES/FUNCTIONS.
        from_role : str
            Role losing privileges.
        object_type : str, optional
            Type of object, by default "TABLE".
        schema : str, optional
            Schema name, by default "public".
        cascade : bool, optional
            Revoke from dependent privileges, by default False.
        """
        validate_identifier(from_role)
        validate_object_type(object_type)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)
        validate_privileges(privileges)

        cascade_clause = " CASCADE" if cascade else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            await self._db.execute(
                f"REVOKE {privileges} ON SCHEMA {on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            await self._db.execute(
                f"REVOKE {privileges} ON DATABASE {on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            await self._db.execute(
                f"REVOKE {privileges} ON {on} IN SCHEMA {schema} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        else:
            validate_identifiers(on, schema)
            await self._db.execute(
                f"REVOKE {privileges} ON {object_type} {schema}.{on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )

    async def list_role_members(self, role: str) -> list[str]:
        """List members of a role.

        Parameters
        ----------
        role : str
            Role name.

        Returns
        -------
        list of str
            List of member role names.
        """
        result = await self._db.execute(queries.LIST_ROLE_MEMBERS, [role])
        return [r["member"] for r in result]

    async def list_role_grants(self, role: str) -> list[dict]:
        """List privileges granted to a role.

        Parameters
        ----------
        role : str
            Role name.

        Returns
        -------
        list of dict
            List of privilege info dicts.
        """
        return await self._db.execute(queries.LIST_ROLE_GRANTS, [role])
