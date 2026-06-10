"""
Simple SQL migrations for pycopg.

Provides a straightforward migration system using numbered SQL files.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

from pycopg.exceptions import MigrationError
from pycopg.utils import validate_identifier

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pycopg.database import Database


class Migration:
    """Represents a single migration file."""

    def __init__(self, path: Path):
        """Initialize migration from file path.

        Parameters
        ----------
        path : Path
            Path to SQL migration file.
        """
        self.path = path
        self.filename = path.name
        self.version, self.name = self._parse_filename()

    def _parse_filename(self) -> tuple[int, str]:
        """Parse version number and name from filename.

        Expected formats:
            - 001_create_users.sql
            - 0001_create_users.sql
            - 1_create_users.sql

        Returns
        -------
        tuple of (int, str)
            Tuple of (version, name).

        Raises
        ------
        MigrationError
            If filename format is invalid.
        """
        match = re.match(r'^(\d+)_(.+)\.sql$', self.filename)
        if not match:
            raise MigrationError(
                f"Invalid migration filename: {self.filename}. "
                "Expected format: NNN_description.sql"
            )
        return int(match.group(1)), match.group(2)

    @property
    def sql(self) -> str:
        """Read and return SQL content."""
        return self.path.read_text(encoding='utf-8')

    def __repr__(self) -> str:
        """Return string representation of the Migration instance."""
        return f"Migration({self.version:03d}_{self.name})"


class Migrator:
    """Simple SQL migration manager.

    Uses numbered SQL files and tracks applied migrations in a database table.
    """

    MIGRATIONS_TABLE = "schema_migrations"

    def __init__(
        self,
        db: "Database",
        migrations_dir: Union[str, Path],
        table: str = "schema_migrations",
    ):
        """Initialize migrator.

        Parameters
        ----------
        db : Database
            Database instance.
        migrations_dir : str or Path
            Path to directory containing SQL migration files.
        table : str, optional
            Name of migrations tracking table, by default "schema_migrations".
        """
        self.db = db
        self.migrations_dir = Path(migrations_dir)
        
        # Validate table name to prevent SQL injection
        validate_identifier(table)
        self.table = table

        if not self.migrations_dir.exists():
            raise MigrationError(f"Migrations directory not found: {self.migrations_dir}")

    def _ensure_table(self) -> None:
        """Create migrations tracking table if it doesn't exist."""
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    def _get_applied(self) -> set[int]:
        """Get set of applied migration versions."""
        self._ensure_table()
        result = self.db.execute(f"SELECT version FROM {self.table}")
        return {row["version"] for row in result}

    def _get_migrations(self) -> list[Migration]:
        """Get all migration files sorted by version."""
        files = sorted(self.migrations_dir.glob("*.sql"))
        migrations = []
        for f in files:
            try:
                migrations.append(Migration(f))
            except MigrationError as e:
                logger.warning("Skipping invalid migration file '%s': %s", f.name, e)
                continue
        return sorted(migrations, key=lambda m: m.version)

    def pending(self) -> list[Migration]:
        """Get list of pending (unapplied) migrations.

        Returns
        -------
        list of Migration
            Migration objects that haven't been applied.
        """
        applied = self._get_applied()
        return [m for m in self._get_migrations() if m.version not in applied]

    def applied(self) -> list[dict]:
        """Get list of applied migrations from database.

        Returns
        -------
        list of dict
            List of dicts with version, name, applied_at.
        """
        self._ensure_table()
        return self.db.execute(f"""
            SELECT version, name, applied_at
            FROM {self.table}
            ORDER BY version
        """)

    def migrate(self, target: Optional[int] = None) -> list[Migration]:
        """Run pending migrations.

        Parameters
        ----------
        target : int, optional
            Target version. If specified, only migrations up to and
            including this version are applied.

        Returns
        -------
        list of Migration
            List of applied migrations.

        Raises
        ------
        MigrationError
            If a migration fails.
        """
        self._ensure_table()
        pending = self.pending()

        if target is not None:
            pending = [m for m in pending if m.version <= target]

        applied = []
        for migration in pending:
            try:
                self._apply(migration)
                applied.append(migration)
            except Exception as e:
                raise MigrationError(
                    f"Migration {migration.version:03d}_{migration.name} failed: {e}"
                ) from e

        return applied

    def _apply(self, migration: Migration) -> None:
        """Apply a single migration.

        Parameters
        ----------
        migration : Migration
            Migration to apply.
        """
        sql = migration.sql

        # Extract UP section if migration has UP/DOWN sections
        up_sql = self._extract_section(sql, "UP") or sql

        # Execute migration atomically: UP SQL + INSERT version in one transaction
        # so a mid-course failure leaves neither a partial schema nor a version row.
        with self.db.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(up_sql)
                cur.execute(
                    f"INSERT INTO {self.table} (version, name) VALUES (%s, %s)",
                    [migration.version, migration.name]
                )

    def rollback(self, steps: int = 1) -> list[dict]:
        """Rollback the last N migrations.

        Only works if migrations contain a -- DOWN section.

        Parameters
        ----------
        steps : int, optional
            Number of migrations to rollback, by default 1.

        Returns
        -------
        list of dict
            List of rolled back migration info.

        Raises
        ------
        MigrationError
            If rollback fails or DOWN section not found.
        """
        applied = self.applied()
        if not applied:
            return []

        # Get last N applied migrations in reverse order
        to_rollback = list(reversed(applied[-steps:]))
        rolled_back = []

        for info in to_rollback:
            version = info["version"]
            name = info["name"]

            # Find migration file
            migration = self._find_migration(version)
            if not migration:
                raise MigrationError(
                    f"Migration file for version {version} not found"
                )

            # Extract DOWN section
            down_sql = self._extract_section(migration.sql, "DOWN")
            if not down_sql:
                raise MigrationError(
                    f"No DOWN section in migration {version:03d}_{name}"
                )

            try:
                # Execute rollback atomically: DOWN SQL + DELETE version in one
                # transaction so a mid-course failure leaves the version row intact
                # and the schema unchanged.
                with self.db.transaction() as conn:
                    with conn.cursor() as cur:
                        cur.execute(down_sql)
                        cur.execute(
                            f"DELETE FROM {self.table} WHERE version = %s",
                            [version]
                        )
                rolled_back.append(info)
            except Exception as e:
                raise MigrationError(
                    f"Rollback of {version:03d}_{name} failed: {e}"
                ) from e

        return rolled_back

    def _find_migration(self, version: int) -> Optional[Migration]:
        """Find migration by version number."""
        for m in self._get_migrations():
            if m.version == version:
                return m
        return None

    def _extract_section(self, sql: str, section: str) -> Optional[str]:
        """Extract UP or DOWN section from migration SQL.

        Migration format:
            -- UP
            CREATE TABLE users (...);

            -- DOWN
            DROP TABLE users;

        Parameters
        ----------
        sql : str
            Full migration SQL.
        section : str
            Section to extract ("UP" or "DOWN").

        Returns
        -------
        str or None
            Section SQL or None if not found.
        """
        pattern = rf'--\s*{section}\s*\n(.*?)(?=--\s*(?:UP|DOWN)\s*\n|$)'
        match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def status(self) -> dict:
        """Get migration status.

        Returns
        -------
        dict
            Dict with applied count, pending count, and lists.
        """
        applied = self.applied()
        pending = self.pending()

        return {
            "applied_count": len(applied),
            "pending_count": len(pending),
            "applied": applied,
            "pending": [{"version": m.version, "name": m.name} for m in pending],
        }

    def create(self, name: str) -> Path:
        """Create a new migration file.

        Parameters
        ----------
        name : str
            Migration name (will be sanitized).

        Returns
        -------
        Path
            Path to created migration file.
        """
        # Sanitize name
        safe_name = re.sub(r'[^a-z0-9_]', '_', name.lower())

        # Get next version number
        migrations = self._get_migrations()
        next_version = max((m.version for m in migrations), default=0) + 1

        # Create file
        filename = f"{next_version:03d}_{safe_name}.sql"
        path = self.migrations_dir / filename

        template = f"""-- Migration: {safe_name}
-- Created: {datetime.now().isoformat()}

-- UP
-- Write your migration SQL here


-- DOWN
-- Write your rollback SQL here (optional)

"""
        path.write_text(template, encoding='utf-8')
        return path

    def __repr__(self) -> str:
        """Return string representation of the Migrator instance."""
        status = self.status()
        return (
            f"Migrator({self.migrations_dir}, "
            f"applied={status['applied_count']}, "
            f"pending={status['pending_count']})"
        )
