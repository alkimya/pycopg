"""SQL injection regression tests for pycopg (hotfix v0.3.1).

Each test feeds a malicious identifier / interval / timestamp / option to a
public method and asserts it is rejected with ``InvalidIdentifier`` *before*
any SQL reaches the database. The database driver is mocked, so if validation
were missing the call would silently "succeed" against the mock instead of
raising — making these true regression guards for the patched methods.

No real database is required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.etl import _build_insert_sql, _build_upsert_sql
from pycopg.exceptions import InvalidIdentifier

# A representative set of injection payloads for identifier-typed arguments.
EVIL_IDENTIFIERS = [
    "users; DROP TABLE users; --",
    'x"; DROP TABLE y; --',
    "a' OR '1'='1",
    "schema.table",  # dotted -> not a bare identifier
    "tab le",
]


@pytest.fixture
def sync_db(config):
    """A sync Database with a mocked psycopg layer."""
    with patch("pycopg.database.psycopg") as mock_psycopg:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn
        yield Database(config)


@pytest.fixture
def async_db(config):
    """An async Database with DB-touching helpers stubbed.

    Some methods run a pre-check (e.g. ``role_exists``, ``has_extension``)
    before reaching the argument being tested. We stub those so the test
    exercises the validation guard rather than a live connection.
    """
    db = AsyncDatabase(config)
    db.role_exists = AsyncMock(return_value=False)
    db.has_extension = AsyncMock(return_value=True)
    db.execute = AsyncMock(return_value=[])
    db.execute_many = AsyncMock(return_value=0)
    return db


class TestSyncIdentifierInjection:
    """Sync methods must reject malicious identifiers."""

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_drop_index(self, sync_db, evil):
        with pytest.raises(InvalidIdentifier):
            sync_db.drop_index(evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_create_spatial_index_table(self, sync_db, evil):
        with pytest.raises(InvalidIdentifier):
            sync_db.create_spatial_index(evil, "geom")

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_create_spatial_index_column(self, sync_db, evil):
        with pytest.raises(InvalidIdentifier):
            sync_db.create_spatial_index("parcels", evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_vacuum_table(self, sync_db, evil):
        with pytest.raises(InvalidIdentifier):
            sync_db.maint.vacuum(evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_analyze_table(self, sync_db, evil):
        with pytest.raises(InvalidIdentifier):
            sync_db.maint.analyze(evil)

    def test_create_extension_injection(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.create_extension('postgis"; DROP DATABASE x; --')

    def test_create_extension_schema_injection(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.create_extension("postgis", schema="public; DROP SCHEMA public")

    def test_create_extension_hyphen_ok(self, sync_db):
        """Legitimate hyphenated extension must NOT be rejected."""
        # Reaches execute() (mocked) without raising InvalidIdentifier.
        sync_db.create_extension("uuid-ossp")

    def test_drop_extension_injection(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.drop_extension('postgis"; DROP DATABASE x; --')

    def test_drop_extension_hyphen_ok(self, sync_db):
        """Legitimate hyphenated extension must NOT be rejected on drop."""
        sync_db.drop_extension("uuid-ossp")


class TestSyncValueInjection:
    """Sync methods must reject malicious non-identifier values."""

    def test_valid_until_create_role(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.admin.create_role(
                "appuser", valid_until="2025-01-01'; DROP TABLE x; --"
            )

    def test_valid_until_alter_role(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.admin.alter_role("appuser", valid_until="bad'; DROP")

    def test_compression_interval(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.timescale.add_compression_policy(
                "events", compress_after="1 day'); DROP TABLE x; --"
            )

    def test_retention_interval(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.timescale.add_retention_policy("logs", drop_after="evil")

    def test_grant_privileges(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.admin.grant("SELECT; DROP TABLE users; --", "users", "readonly")

    def test_grant_object_type(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.admin.grant(
                "SELECT", "users", "readonly", object_type="TABLE; DROP"
            )

    def test_revoke_privileges(self, sync_db):
        with pytest.raises(InvalidIdentifier):
            sync_db.admin.revoke("ALL; GRANT SUPERUSER", "users", "readonly")

    def test_csv_delimiter(self, sync_db, tmp_path):
        with pytest.raises(InvalidIdentifier):
            sync_db.backup.copy_to_csv(
                "users", tmp_path / "u.csv", delimiter="','; DROP TABLE x; --"
            )


class TestAsyncIdentifierInjection:
    """Async methods must reject the same payloads (parity)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_drop_index(self, async_db, evil):
        with pytest.raises(InvalidIdentifier):
            await async_db.drop_index(evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_create_spatial_index(self, async_db, evil):
        with pytest.raises(InvalidIdentifier):
            await async_db.create_spatial_index(evil, "geom")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_vacuum(self, async_db, evil):
        with pytest.raises(InvalidIdentifier):
            await async_db.maint.vacuum(evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_analyze(self, async_db, evil):
        with pytest.raises(InvalidIdentifier):
            await async_db.maint.analyze(evil)

    @pytest.mark.asyncio
    async def test_create_extension(self, async_db):
        with pytest.raises(InvalidIdentifier):
            await async_db.create_extension('postgis"; DROP DATABASE x; --')

    @pytest.mark.asyncio
    async def test_drop_extension(self, async_db):
        with pytest.raises(InvalidIdentifier):
            await async_db.drop_extension('postgis"; DROP DATABASE x; --')


class TestAsyncValueInjection:
    """Async value-injection parity."""

    @pytest.mark.asyncio
    async def test_valid_until_create_role(self, async_db):
        with pytest.raises(InvalidIdentifier):
            await async_db.admin.create_role("u", valid_until="2025'; DROP")

    @pytest.mark.asyncio
    async def test_compression_interval(self, async_db):
        with pytest.raises(InvalidIdentifier):
            await async_db.timescale.add_compression_policy(
                "events", compress_after="evil"
            )

    @pytest.mark.asyncio
    async def test_retention_interval(self, async_db):
        with pytest.raises(InvalidIdentifier):
            await async_db.timescale.add_retention_policy("logs", drop_after="evil")

    @pytest.mark.asyncio
    async def test_grant_privileges(self, async_db):
        with pytest.raises(InvalidIdentifier):
            await async_db.admin.grant("SELECT; DROP", "users", "readonly")

    @pytest.mark.asyncio
    async def test_revoke_object_type(self, async_db):
        with pytest.raises(InvalidIdentifier):
            await async_db.admin.revoke(
                "SELECT", "users", "readonly", object_type="X; DROP"
            )

    @pytest.mark.asyncio
    async def test_insert_many_column_injection(self, async_db):
        rows = [{"id; DROP TABLE x; --": 1}]
        with pytest.raises(InvalidIdentifier):
            await async_db.insert_many("t", rows)

    @pytest.mark.asyncio
    async def test_upsert_many_conflict_column_injection(self, async_db):
        rows = [{"id": 1, "v": 2}]
        with pytest.raises(InvalidIdentifier):
            await async_db.upsert_many("t", rows, conflict_columns=["id; DROP TABLE x"])


class TestEtlIdentifierInjection:
    """ETL pure builders must reject every EVIL_IDENTIFIERS payload (ETL-16 / SC-6).

    These tests call the builders directly — no DB, no mock needed.  A
    builder that passes ``evil`` to an f-string without ``validate_identifiers``
    would silently return a string; the fact that ``InvalidIdentifier`` is
    raised before any SQL is returned is the regression guard.
    """

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_sql_evil_table(self, evil):
        """_build_insert_sql with a malicious table name raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            _build_insert_sql(evil, ["a"], [{"a": 1}])

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_sql_evil_schema(self, evil):
        """_build_insert_sql with a malicious schema name raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            _build_insert_sql("t", ["a"], [{"a": 1}], schema=evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_sql_evil_column(self, evil):
        """_build_insert_sql with a malicious column name raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            _build_insert_sql("t", [evil], [{evil: 1}])

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_upsert_sql_evil_conflict_column(self, evil):
        """_build_upsert_sql with a malicious conflict_column raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            _build_upsert_sql("t", [{"id": 1, "v": 2}], conflict_columns=[evil])

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_upsert_sql_evil_table(self, evil):
        """_build_upsert_sql with a malicious table name raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            _build_upsert_sql(evil, [{"id": 1, "v": 2}], conflict_columns=["id"])
