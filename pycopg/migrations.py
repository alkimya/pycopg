"""
Simple SQL migrations for pycopg.

Provides a straightforward migration system using numbered SQL files.

Example:
    migrations/
    ├── 001_create_users.sql
    ├── 002_add_email_index.sql
    └── 003_create_orders.sql

    from pycopg import Database, Migrator

    db = Database.from_env()
    migrator = Migrator(db, "migrations/")
    migrator.migrate()
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

        Args:
            path: Path to SQL migration file.
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

        Returns:
            Tuple of (version, name).

        Raises:
            MigrationError: If filename format is invalid.
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
        return f"Migration({self.version:03d}_{self.name})"


class Migrator:
    """Simple SQL migration manager.

    Uses numbered SQL files and tracks applied migrations in a database table.

    Example:
        # Directory structure:
        # migrations/
        # ├── 001_create_users.sql
        # ├── 002_add_email_column.sql
        # └── 003_create_orders.sql

        from pycopg import Database, Migrator

        db = Database.from_env()
        migrator = Migrator(db, "migrations/")

        # Run all pending migrations
        migrator.migrate()

        # Check status
        migrator.status()

        # Rollback (if DOWN section exists)
        migrator.rollback()
    """

    MIGRATIONS_TABLE = "schema_migrations"

    def __init__(
        self,
        db: "Database",
        migrations_dir: Union[str, Path],
        table: str = "schema_migrations",
    ):
        """Initialize migrator.

        Args:
            db: Database instance.
            migrations_dir: Path to directory containing SQL migration files.
            table: Name of migrations tracking table.
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

        Returns:
            List of Migration objects that haven't been applied.
        """
        applied = self._get_applied()
        return [m for m in self._get_migrations() if m.version not in applied]

    def applied(self) -> list[dict]:
        """Get list of applied migrations from database.

        Returns:
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

        Args:
            target: Optional target version. If specified, only migrations
                   up to and including this version are applied.

        Returns:
            List of applied migrations.

        Raises:
            MigrationError: If a migration fails.

        Example:
            # Run all pending
            migrator.migrate()

            # Run up to version 5
            migrator.migrate(target=5)
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

        Args:
            migration: Migration to apply.
        """
        sql = migration.sql

        # Extract UP section if migration has UP/DOWN sections
        up_sql = self._extract_section(sql, "UP") or sql

        # Execute migration
        with self.db.cursor() as cur:
            cur.execute(up_sql)
            cur.execute(
                f"INSERT INTO {self.table} (version, name) VALUES (%s, %s)",
                [migration.version, migration.name]
            )

    def rollback(self, steps: int = 1) -> list[dict]:
        """Rollback the last N migrations.

        Only works if migrations contain a -- DOWN section.

        Args:
            steps: Number of migrations to rollback.

        Returns:
            List of rolled back migration info.

        Raises:
            MigrationError: If rollback fails or DOWN section not found.

        Example:
            # Rollback last migration
            migrator.rollback()

            # Rollback last 3 migrations
            migrator.rollback(steps=3)
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
                with self.db.cursor() as cur:
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

        Args:
            sql: Full migration SQL.
            section: Section to extract ("UP" or "DOWN").

        Returns:
            Section SQL or None if not found.
        """
        pattern = rf'--\s*{section}\s*\n(.*?)(?=--\s*(?:UP|DOWN)\s*\n|$)'
        match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def status(self) -> dict:
        """Get migration status.

        Returns:
            Dict with applied count, pending count, and lists.

        Example:
            status = migrator.status()
            print(f"Applied: {status['applied_count']}")
            print(f"Pending: {status['pending_count']}")
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

        Args:
            name: Migration name (will be sanitized).

        Returns:
            Path to created migration file.

        Example:
            path = migrator.create("add_email_to_users")
            # Creates: migrations/004_add_email_to_users.sql
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
        status = self.status()
        return (
            f"Migrator({self.migrations_dir}, "
            f"applied={status['applied_count']}, "
            f"pending={status['pending_count']})"
        )
