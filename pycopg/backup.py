"""Backup & restore accessor classes for db.backup.* / async_db.backup.*.

This module provides :class:`BackupAccessor` and
:class:`AsyncBackupAccessor` — the real implementation of the 4 public
backup/restore/CSV methods (plus the private ``_psql_restore`` companion),
moved verbatim from ``Database`` / ``AsyncDatabase`` as part of the v0.6.0
accessor reorganisation (D-06).

Both classes are exposed on the parent database via a lazy-cached
``backup`` property added in plan 02.  The flat ``db.*`` names remain
as thin deprecated aliases (see :mod:`pycopg.aliases`) until v0.7.0.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pycopg.base import build_pg_dump_cmd, build_pg_restore_cmd
from pycopg.utils import validate_csv_option, validate_identifiers

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database


class BackupAccessor:
    """Backup helper namespace exposed as ``db.backup``.

    Methods are moved verbatim from ``Database``.  Database dump/restore
    and CSV import/export operations are accessible via this accessor.
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

    def pg_dump(
        self,
        output_file: str | Path,
        format: Literal["plain", "custom", "directory", "tar"] = "custom",
        schema_only: bool = False,
        data_only: bool = False,
        tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
        schemas: list[str] | None = None,
        compress: int = 6,
        jobs: int = 1,
    ) -> None:
        """Backup database using pg_dump.

        Parameters
        ----------
        output_file : str or Path
            Output file path.
        format : {'plain', 'custom', 'directory', 'tar'}, optional
            Dump format (plain=SQL, custom=compressed, directory=parallel, tar),
            by default "custom".
        schema_only : bool, optional
            Dump only schema, no data, by default False.
        data_only : bool, optional
            Dump only data, no schema, by default False.
        tables : list of str, optional
            Only dump these tables.
        exclude_tables : list of str, optional
            Exclude these tables.
        schemas : list of str, optional
            Only dump these schemas.
        compress : int, optional
            Compression level (0-9, for custom format), by default 6.
        jobs : int, optional
            Parallel jobs (for directory format), by default 1.
        """
        import subprocess

        cmd = build_pg_dump_cmd(
            host=self._db.config.host,
            port=self._db.config.port,
            user=self._db.config.user,
            database=self._db.config.database,
            output_file=output_file,
            format=format,
            schema_only=schema_only,
            data_only=data_only,
            tables=tables,
            exclude_tables=exclude_tables,
            schemas=schemas,
            compress=compress,
            jobs=jobs,
        )

        # Run with password in environment
        env = {"PGPASSWORD": self._db.config.password} if self._db.config.password else {}
        result = subprocess.run(
            cmd, env={**os.environ, **env}, capture_output=True, text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr}")

    def pg_restore(
        self,
        input_file: str | Path,
        clean: bool = False,
        if_exists: bool = True,
        create: bool = False,
        data_only: bool = False,
        schema_only: bool = False,
        tables: list[str] | None = None,
        schemas: list[str] | None = None,
        jobs: int = 1,
        no_owner: bool = False,
        no_privileges: bool = False,
    ) -> None:
        """Restore database from pg_dump backup.

        Parameters
        ----------
        input_file : str or Path
            Backup file path.
        clean : bool, optional
            Drop objects before recreating, by default False.
        if_exists : bool, optional
            Use IF EXISTS with clean (prevents errors), by default True.
        create : bool, optional
            Create database before restoring, by default False.
        data_only : bool, optional
            Restore only data, by default False.
        schema_only : bool, optional
            Restore only schema, by default False.
        tables : list of str, optional
            Only restore these tables.
        schemas : list of str, optional
            Only restore these schemas.
        jobs : int, optional
            Parallel jobs, by default 1.
        no_owner : bool, optional
            Don't restore ownership, by default False.
        no_privileges : bool, optional
            Don't restore privileges, by default False.
        """
        import subprocess

        input_file = Path(input_file)

        # Check if it's a plain SQL file
        if input_file.suffix == ".sql" or not input_file.exists():
            # Use psql for plain format
            self._psql_restore(input_file)
            return

        cmd = build_pg_restore_cmd(
            host=self._db.config.host,
            port=self._db.config.port,
            user=self._db.config.user,
            database=self._db.config.database,
            input_file=input_file,
            clean=clean,
            if_exists=if_exists,
            create=create,
            data_only=data_only,
            schema_only=schema_only,
            tables=tables,
            schemas=schemas,
            jobs=jobs,
            no_owner=no_owner,
            no_privileges=no_privileges,
        )

        # Run with password in environment
        env = {"PGPASSWORD": self._db.config.password} if self._db.config.password else {}
        result = subprocess.run(
            cmd, env={**os.environ, **env}, capture_output=True, text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {result.stderr}")

    def _psql_restore(self, sql_file: Path) -> None:
        """Restore from plain SQL file using psql."""
        import subprocess

        cmd = [
            "psql",
            "-h",
            self._db.config.host,
            "-p",
            str(self._db.config.port),
            "-U",
            self._db.config.user,
            "-d",
            self._db.config.database,
            "-f",
            str(sql_file),
        ]

        env = {"PGPASSWORD": self._db.config.password} if self._db.config.password else {}
        result = subprocess.run(
            cmd, env={**os.environ, **env}, capture_output=True, text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"psql restore failed: {result.stderr}")

    def copy_to_csv(
        self,
        table: str,
        output_file: str | Path,
        schema: str = "public",
        columns: list[str] | None = None,
        delimiter: str = ",",
        header: bool = True,
        null_string: str = "",
        encoding: str = "UTF8",
    ) -> int:
        """Export table to CSV file.

        Parameters
        ----------
        table : str
            Table name.
        output_file : str or Path
            Output CSV file path.
        schema : str, optional
            Schema name, by default "public".
        columns : list of str, optional
            Specific columns to export.
        delimiter : str, optional
            Field delimiter, by default ",".
        header : bool, optional
            Include header row, by default True.
        null_string : str, optional
            String for NULL values, by default "".
        encoding : str, optional
            File encoding, by default "UTF8".

        Returns
        -------
        int
            Number of rows exported.
        """
        output_file = Path(output_file)
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)

        validate_csv_option(delimiter, "delimiter")
        validate_csv_option(null_string, "null_string")
        validate_csv_option(encoding, "encoding")

        cols = f"({', '.join(columns)})" if columns else ""

        options = [
            "FORMAT CSV",
            f"DELIMITER '{delimiter}'",
            f"NULL '{null_string}'",
            f"ENCODING '{encoding}'",
        ]
        if header:
            options.append("HEADER")

        with self._db.cursor() as cur:
            with open(output_file, "w", encoding=encoding) as f:
                with cur.copy(
                    f"COPY {schema}.{table}{cols} TO STDOUT WITH ({', '.join(options)})"
                ) as copy:
                    for data in copy:
                        # psycopg yields memoryview chunks; bytes(...) handles
                        # both memoryview and bytes before decoding to text.
                        if isinstance(data, str):
                            f.write(data)
                        else:
                            f.write(bytes(data).decode(encoding))

            # Get row count
            cur.execute(f"SELECT COUNT(*) AS count FROM {schema}.{table}")
            return cur.fetchone()["count"]

    def copy_from_csv(
        self,
        table: str,
        input_file: str | Path,
        schema: str = "public",
        columns: list[str] | None = None,
        delimiter: str = ",",
        header: bool = True,
        null_string: str = "",
        encoding: str = "UTF8",
    ) -> int:
        """Import CSV file into table.

        Parameters
        ----------
        table : str
            Table name.
        input_file : str or Path
            Input CSV file path.
        schema : str, optional
            Schema name, by default "public".
        columns : list of str, optional
            Specific columns to import.
        delimiter : str, optional
            Field delimiter, by default ",".
        header : bool, optional
            First row is header, by default True.
        null_string : str, optional
            String representing NULL, by default "".
        encoding : str, optional
            File encoding, by default "UTF8".

        Returns
        -------
        int
            Number of rows imported.
        """
        input_file = Path(input_file)
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)

        validate_csv_option(delimiter, "delimiter")
        validate_csv_option(null_string, "null_string")
        validate_csv_option(encoding, "encoding")

        cols = f"({', '.join(columns)})" if columns else ""

        options = [
            "FORMAT CSV",
            f"DELIMITER '{delimiter}'",
            f"NULL '{null_string}'",
            f"ENCODING '{encoding}'",
        ]
        if header:
            options.append("HEADER")

        with self._db.cursor() as cur:
            with open(input_file, encoding=encoding) as f:
                with cur.copy(
                    f"COPY {schema}.{table}{cols} FROM STDIN WITH ({', '.join(options)})"
                ) as copy:
                    while data := f.read(8192):
                        copy.write(data.encode(encoding))

            return cur.rowcount


class AsyncBackupAccessor:
    """Async backup helper namespace exposed as ``async_db.backup``.

    Mirrors :class:`BackupAccessor` exactly with ``await`` calls.
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

    async def pg_dump(
        self,
        output_file: str | Path,
        format: Literal["plain", "custom", "directory", "tar"] = "custom",
        schema_only: bool = False,
        data_only: bool = False,
        tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
        schemas: list[str] | None = None,
        compress: int = 6,
        jobs: int = 1,
    ) -> None:
        """Backup database using pg_dump.

        Parameters
        ----------
        output_file : str or Path
            Output file path.
        format : {'plain', 'custom', 'directory', 'tar'}, optional
            Dump format (plain=SQL, custom=compressed, directory=parallel, tar),
            by default "custom".
        schema_only : bool, optional
            Dump only schema, no data, by default False.
        data_only : bool, optional
            Dump only data, no schema, by default False.
        tables : list of str, optional
            Only dump these tables.
        exclude_tables : list of str, optional
            Exclude these tables.
        schemas : list of str, optional
            Only dump these schemas.
        compress : int, optional
            Compression level (0-9, for custom format), by default 6.
        jobs : int, optional
            Parallel jobs (for directory format), by default 1.
        """
        cmd = build_pg_dump_cmd(
            host=self._db.config.host,
            port=self._db.config.port,
            user=self._db.config.user,
            database=self._db.config.database,
            output_file=output_file,
            format=format,
            schema_only=schema_only,
            data_only=data_only,
            tables=tables,
            exclude_tables=exclude_tables,
            schemas=schemas,
            compress=compress,
            jobs=jobs,
        )

        # Run with password in environment
        env = {**os.environ}
        if self._db.config.password:
            env["PGPASSWORD"] = self._db.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr.decode()}")

    async def pg_restore(
        self,
        input_file: str | Path,
        clean: bool = False,
        if_exists: bool = True,
        create: bool = False,
        data_only: bool = False,
        schema_only: bool = False,
        tables: list[str] | None = None,
        schemas: list[str] | None = None,
        jobs: int = 1,
        no_owner: bool = False,
        no_privileges: bool = False,
    ) -> None:
        """Restore database from pg_dump backup.

        Parameters
        ----------
        input_file : str or Path
            Backup file path.
        clean : bool, optional
            Drop objects before recreating, by default False.
        if_exists : bool, optional
            Use IF EXISTS with clean (prevents errors), by default True.
        create : bool, optional
            Create database before restoring, by default False.
        data_only : bool, optional
            Restore only data, by default False.
        schema_only : bool, optional
            Restore only schema, by default False.
        tables : list of str, optional
            Only restore these tables.
        schemas : list of str, optional
            Only restore these schemas.
        jobs : int, optional
            Parallel jobs, by default 1.
        no_owner : bool, optional
            Don't restore ownership, by default False.
        no_privileges : bool, optional
            Don't restore privileges, by default False.
        """
        input_file = Path(input_file)

        # Check if it's a plain SQL file
        if input_file.suffix == ".sql" or not input_file.exists():
            # Use psql for plain format
            await self._psql_restore(input_file)
            return

        cmd = build_pg_restore_cmd(
            host=self._db.config.host,
            port=self._db.config.port,
            user=self._db.config.user,
            database=self._db.config.database,
            input_file=input_file,
            clean=clean,
            if_exists=if_exists,
            create=create,
            data_only=data_only,
            schema_only=schema_only,
            tables=tables,
            schemas=schemas,
            jobs=jobs,
            no_owner=no_owner,
            no_privileges=no_privileges,
        )

        # Run with password in environment
        env = {**os.environ}
        if self._db.config.password:
            env["PGPASSWORD"] = self._db.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {stderr.decode()}")

    async def _psql_restore(self, sql_file: Path) -> None:
        """Restore from plain SQL file using psql."""
        cmd = [
            "psql",
            "-h",
            self._db.config.host,
            "-p",
            str(self._db.config.port),
            "-U",
            self._db.config.user,
            "-d",
            self._db.config.database,
            "-f",
            str(sql_file),
        ]

        env = {**os.environ}
        if self._db.config.password:
            env["PGPASSWORD"] = self._db.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"psql restore failed: {stderr.decode()}")

    async def copy_to_csv(
        self,
        table: str,
        output_file: str | Path,
        schema: str = "public",
        columns: list[str] | None = None,
        delimiter: str = ",",
        header: bool = True,
        null_string: str = "",
        encoding: str = "UTF8",
    ) -> int:
        """Export table to CSV file.

        Parameters
        ----------
        table : str
            Table name.
        output_file : str or Path
            Output CSV file path.
        schema : str, optional
            Schema name, by default "public".
        columns : list of str, optional
            Specific columns to export.
        delimiter : str, optional
            Field delimiter, by default ",".
        header : bool, optional
            Include header row, by default True.
        null_string : str, optional
            String for NULL values, by default "".
        encoding : str, optional
            File encoding, by default "UTF8".

        Returns
        -------
        int
            Number of rows exported.
        """
        output_file = Path(output_file)
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)
        validate_csv_option(delimiter, "delimiter")
        validate_csv_option(null_string, "null_string")
        validate_csv_option(encoding, "encoding")

        cols = f"({', '.join(columns)})" if columns else ""

        options = [
            "FORMAT CSV",
            f"DELIMITER '{delimiter}'",
            f"NULL '{null_string}'",
            f"ENCODING '{encoding}'",
        ]
        if header:
            options.append("HEADER")

        # Create parent directory if needed
        await asyncio.to_thread(output_file.parent.mkdir, parents=True, exist_ok=True)

        async with self._db.cursor() as cur:
            # Open file and write data
            file_handle = await asyncio.to_thread(
                open, output_file, "w", encoding=encoding
            )
            try:
                async with cur.copy(
                    f"COPY {schema}.{table}{cols} TO STDOUT WITH ({', '.join(options)})"
                ) as copy:
                    async for data in copy:
                        # psycopg yields memoryview chunks; bytes(...) handles
                        # both memoryview and bytes before decoding to text.
                        decoded = (
                            data
                            if isinstance(data, str)
                            else bytes(data).decode(encoding)
                        )
                        await asyncio.to_thread(file_handle.write, decoded)
            finally:
                await asyncio.to_thread(file_handle.close)

            # Get row count
            result = await self._db.execute(
                f"SELECT COUNT(*) AS count FROM {schema}.{table}"
            )
            return result[0]["count"]

    async def copy_from_csv(
        self,
        table: str,
        input_file: str | Path,
        schema: str = "public",
        columns: list[str] | None = None,
        delimiter: str = ",",
        header: bool = True,
        null_string: str = "",
        encoding: str = "UTF8",
    ) -> int:
        """Import CSV file into table.

        Parameters
        ----------
        table : str
            Table name.
        input_file : str or Path
            Input CSV file path.
        schema : str, optional
            Schema name, by default "public".
        columns : list of str, optional
            Specific columns to import.
        delimiter : str, optional
            Field delimiter, by default ",".
        header : bool, optional
            First row is header, by default True.
        null_string : str, optional
            String representing NULL, by default "".
        encoding : str, optional
            File encoding, by default "UTF8".

        Returns
        -------
        int
            Number of rows imported.
        """
        input_file = Path(input_file)
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)
        validate_csv_option(delimiter, "delimiter")
        validate_csv_option(null_string, "null_string")
        validate_csv_option(encoding, "encoding")

        cols = f"({', '.join(columns)})" if columns else ""

        options = [
            "FORMAT CSV",
            f"DELIMITER '{delimiter}'",
            f"NULL '{null_string}'",
            f"ENCODING '{encoding}'",
        ]
        if header:
            options.append("HEADER")

        async with self._db.cursor() as cur:
            # Open file and read data
            file_handle = await asyncio.to_thread(
                open, input_file, "r", encoding=encoding
            )
            try:
                async with cur.copy(
                    f"COPY {schema}.{table}{cols} FROM STDIN WITH ({', '.join(options)})"
                ) as copy:
                    while True:
                        data = await asyncio.to_thread(file_handle.read, 8192)
                        if not data:
                            break
                        await copy.write(data.encode(encoding))
            finally:
                await asyncio.to_thread(file_handle.close)

            return cur.rowcount
