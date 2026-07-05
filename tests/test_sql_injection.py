"""SQL injection regression tests for pycopg (hotfix v0.3.1).

Each test feeds a malicious identifier / interval / timestamp / option to a
public method and asserts it is rejected with ``InvalidIdentifierError`` *before*
any SQL reaches the database. The database driver is mocked, so if validation
were missing the call would silently "succeed" against the mock instead of
raising — making these true regression guards for the patched methods.

No real database is required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.base import QueryMixin
from pycopg.etl import _build_insert_sql, _build_upsert_sql
from pycopg.exceptions import InvalidIdentifierError
from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor

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
    """A sync Database with a mocked psycopg layer.

    The schema accessor's ``has_extension`` is patched to return True so that
    SpatialAccessor.__init__ passes without a real PostGIS connection. All other
    schema methods retain real validation behaviour.
    This is necessary because SpatialAccessor.__init__ performs a PostGIS guard
    check (via has_extension), so the fixture patches it to return True.
    """
    with patch("pycopg.database.psycopg") as mock_psycopg:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn
        db = Database(config)
        # Create a real schema accessor (no DB connection needed — __init__ only stores _db).
        real_schema = SchemaAccessor(db)
        # Patch only has_extension so SpatialAccessor.__init__ passes without PostGIS.
        real_schema.has_extension = MagicMock(return_value=True)
        db._schema = real_schema
        yield db


@pytest.fixture
def async_db(config):
    """An async Database with DB-touching helpers stubbed.

    Some methods run a pre-check (e.g. ``role_exists``, ``has_extension``)
    before reaching the argument being tested. We stub those so the test
    exercises the validation guard rather than a live connection.

    The schema accessor's ``has_extension`` is patched to return True so that
    AsyncSpatialAccessor._check_postgis() passes without a real connection.
    All other schema methods retain real validation behaviour.
    """
    db = AsyncDatabase(config)
    db.execute = AsyncMock(return_value=[])
    db.execute_many = AsyncMock(return_value=0)
    # Create a real schema accessor (no DB connection needed — __init__ only stores _db).
    real_schema = AsyncSchemaAccessor(db)
    # Patch only has_extension so _check_postgis passes without executing SQL.
    real_schema.has_extension = AsyncMock(return_value=True)
    db._schema = real_schema
    return db


class TestSyncIdentifierInjection:
    """Sync methods must reject malicious identifiers."""

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_drop_index(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.schema.drop_index(evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_create_spatial_index_table(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.spatial.create_spatial_index(evil, column="geom")

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_create_spatial_index_column(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.spatial.create_spatial_index("parcels", column=evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_vacuum_table(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.maint.vacuum(table=evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_analyze_table(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.maint.analyze(table=evil)

    def test_create_extension_injection(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.schema.create_extension('postgis"; DROP DATABASE x; --')

    def test_create_extension_schema_injection(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.schema.create_extension(
                "postgis", schema="public; DROP SCHEMA public"
            )

    def test_create_extension_hyphen_ok(self, sync_db):
        """Legitimate hyphenated extension must NOT be rejected."""
        # Reaches execute() (mocked) without raising InvalidIdentifierError.
        sync_db.schema.create_extension("uuid-ossp")

    def test_drop_extension_injection(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.schema.drop_extension('postgis"; DROP DATABASE x; --')

    def test_drop_extension_hyphen_ok(self, sync_db):
        """Legitimate hyphenated extension must NOT be rejected on drop."""
        sync_db.schema.drop_extension("uuid-ossp")


class TestSyncValueInjection:
    """Sync methods must reject malicious non-identifier values."""

    def test_valid_until_create_role(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.admin.create_role(
                "appuser", valid_until="2025-01-01'; DROP TABLE x; --"
            )

    def test_valid_until_alter_role(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.admin.alter_role("appuser", valid_until="bad'; DROP")

    def test_compression_interval(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.timescale.add_compression_policy(
                "events", compress_after="1 day'); DROP TABLE x; --"
            )

    def test_retention_interval(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.timescale.add_retention_policy("logs", drop_after="evil")

    def test_grant_privileges(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.admin.grant("SELECT; DROP TABLE users; --", "users", "readonly")

    def test_grant_object_type(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.admin.grant(
                "SELECT", "users", "readonly", object_type="TABLE; DROP"
            )

    def test_revoke_privileges(self, sync_db):
        with pytest.raises(InvalidIdentifierError):
            sync_db.admin.revoke("ALL; GRANT SUPERUSER", "users", "readonly")

    def test_csv_delimiter(self, sync_db, tmp_path):
        with pytest.raises(InvalidIdentifierError):
            sync_db.backup.copy_to_csv(
                "users", tmp_path / "u.csv", delimiter="','; DROP TABLE x; --"
            )


class TestAsyncIdentifierInjection:
    """Async methods must reject the same payloads (parity)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_drop_index(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.schema.drop_index(evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_create_spatial_index(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.spatial.create_spatial_index(evil, column="geom")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_vacuum(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.maint.vacuum(table=evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_analyze(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.maint.analyze(table=evil)

    @pytest.mark.asyncio
    async def test_create_extension(self, async_db):
        with pytest.raises(InvalidIdentifierError):
            await async_db.schema.create_extension('postgis"; DROP DATABASE x; --')

    @pytest.mark.asyncio
    async def test_drop_extension(self, async_db):
        with pytest.raises(InvalidIdentifierError):
            await async_db.schema.drop_extension('postgis"; DROP DATABASE x; --')


class TestAsyncValueInjection:
    """Async value-injection parity."""

    @pytest.mark.asyncio
    async def test_valid_until_create_role(self, async_db):
        with pytest.raises(InvalidIdentifierError):
            await async_db.admin.create_role("u", valid_until="2025'; DROP")

    @pytest.mark.asyncio
    async def test_compression_interval(self, async_db):
        with pytest.raises(InvalidIdentifierError):
            await async_db.timescale.add_compression_policy(
                "events", compress_after="evil"
            )

    @pytest.mark.asyncio
    async def test_retention_interval(self, async_db):
        with pytest.raises(InvalidIdentifierError):
            await async_db.timescale.add_retention_policy("logs", drop_after="evil")

    @pytest.mark.asyncio
    async def test_grant_privileges(self, async_db):
        with pytest.raises(InvalidIdentifierError):
            await async_db.admin.grant("SELECT; DROP", "users", "readonly")

    @pytest.mark.asyncio
    async def test_revoke_object_type(self, async_db):
        with pytest.raises(InvalidIdentifierError):
            await async_db.admin.revoke(
                "SELECT", "users", "readonly", object_type="X; DROP"
            )

    @pytest.mark.asyncio
    async def test_insert_many_column_injection(self, async_db):
        rows = [{"id; DROP TABLE x; --": 1}]
        with pytest.raises(InvalidIdentifierError):
            await async_db.insert_many("t", rows)

    @pytest.mark.asyncio
    async def test_upsert_many_conflict_column_injection(self, async_db):
        rows = [{"id": 1, "v": 2}]
        with pytest.raises(InvalidIdentifierError):
            await async_db.upsert_many("t", rows, conflict_columns=["id; DROP TABLE x"])


class TestSelectWhereFindIdentifierInjection:
    """CRUD-F04 (T-53-01): select_where/find must reject malicious
    table/schema/columns identifiers via validate_identifiers, which runs
    inside _build_select_sql before any SQL executes.
    """

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_select_where_table_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.select_where(evil, {"a": 1})

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_select_where_schema_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.select_where("t", {"a": 1}, schema=evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_select_where_columns_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.select_where("t", {"a": 1}, columns=[evil])

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_find_table_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.find(evil, {"a": 1})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_select_where_table_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.select_where(evil, {"a": 1})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_select_where_schema_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.select_where("t", {"a": 1}, schema=evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_select_where_columns_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.select_where("t", {"a": 1}, columns=[evil])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_find_table_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.find(evil, {"a": 1})


class TestGetFindOneIdentifierInjection:
    """CRUD-F05 (T-53-01): get/find_one must reject malicious table/schema/
    columns identifiers via validate_identifiers, which runs inside
    _build_select_sql before any SQL executes.
    """

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_get_table_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.get(evil, {"a": 1})

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_get_schema_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.get("t", {"a": 1}, schema=evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_get_columns_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.get("t", {"a": 1}, columns=[evil])

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_find_one_table_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.find_one(evil, {"a": 1})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_get_table_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.get(evil, {"a": 1})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_get_schema_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.get("t", {"a": 1}, schema=evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_get_columns_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.get("t", {"a": 1}, columns=[evil])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_find_one_table_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.find_one(evil, {"a": 1})


class TestInsertIdentifierInjection:
    """CRUD-F06 (T-53-01): single-row insert must reject malicious
    table/schema/row-key identifiers via validate_identifiers, which runs
    inside _build_insert_sql before any SQL executes.
    """

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_table_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.insert(evil, {"a": 1})

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_schema_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.insert("t", {"a": 1}, schema=evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_row_key_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.insert("t", {evil: 1})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_insert_table_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.insert(evil, {"a": 1})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_insert_schema_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.insert("t", {"a": 1}, schema=evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_insert_row_key_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.insert("t", {evil: 1})


class TestWhereSqlValueInjection:
    """CRUD-F01 (T-50-02): where_sql fragment passthrough + where_params
    binding. The raw ``where_sql`` fragment is a documented escape hatch
    (C-02) and is never run through ``validate_identifiers`` — only
    ``where_params`` are treated as untrusted values, bound ``%s`` and never
    interpolated into the SQL string. These tests assert an
    ``EVIL_IDENTIFIERS`` payload reaches the cursor/fetch_val call as a bound
    parameter (not string-interpolated) while the fragment stays byte-exact.
    """

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_where_sql_params_bound_sync(self, config, evil):
        """Sync: an EVIL_IDENTIFIERS payload via where_params binds as %s."""
        with patch("pycopg.database.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = None
            mock_cursor.fetchone.return_value = {"count": 0}
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_psycopg.connect.return_value = mock_conn

            db = Database(config)
            result = db.count("t", where_sql="name = %s", where_params=[evil])

            assert result == 0
            sql, params = mock_cursor.execute.call_args[0]
            # The fragment passes through verbatim — untouched by validation.
            assert sql == "SELECT COUNT(*) FROM public.t WHERE name = %s"
            # The evil payload reached the cursor as a bound param, never
            # interpolated into the SQL text.
            assert params == [evil]
            assert evil not in sql

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_where_sql_params_bound_async(self, config, evil):
        """Async mirror: an EVIL_IDENTIFIERS payload via where_params binds as %s."""
        db = AsyncDatabase(config)
        db.fetch_val = AsyncMock(return_value=0)

        result = await db.count("t", where_sql="name = %s", where_params=[evil])

        assert result == 0
        sql, params = db.fetch_val.call_args[0]
        assert sql == "SELECT COUNT(*) FROM public.t WHERE name = %s"
        assert params == [evil]
        assert evil not in sql

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_select_where_where_sql_params_bound_sync(self, config, evil):
        """Sync: select_where(where_sql=...) binds an evil payload as %s."""
        with patch("pycopg.database.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",)]
            mock_cursor.fetchall.return_value = []
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_psycopg.connect.return_value = mock_conn

            db = Database(config)
            result = db.select_where("t", where_sql="name = %s", where_params=[evil])

            assert result == []
            sql, params = mock_cursor.execute.call_args[0]
            assert sql == "SELECT * FROM public.t WHERE name = %s"
            assert params == [evil]
            assert evil not in sql

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_select_where_where_sql_params_bound_async(self, config, evil):
        """Async mirror: select_where(where_sql=...) binds an evil payload as %s."""
        db = AsyncDatabase(config)
        db.fetch_all = AsyncMock(return_value=[])

        result = await db.select_where("t", where_sql="name = %s", where_params=[evil])

        assert result == []
        sql, params = db.fetch_all.call_args[0]
        assert sql == "SELECT * FROM public.t WHERE name = %s"
        assert params == [evil]
        assert evil not in sql

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_get_where_sql_params_bound_sync(self, config, evil):
        """Sync: get(where_sql=...) binds an evil payload as %s."""
        with patch("pycopg.database.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",)]
            mock_cursor.fetchone.return_value = None
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_psycopg.connect.return_value = mock_conn

            db = Database(config)
            result = db.get("t", where_sql="name = %s", where_params=[evil])

            assert result is None
            sql, params = mock_cursor.execute.call_args[0]
            assert sql == "SELECT * FROM public.t WHERE name = %s LIMIT 1"
            assert params == [evil]
            assert evil not in sql

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_get_where_sql_params_bound_async(self, config, evil):
        """Async mirror: get(where_sql=...) binds an evil payload as %s."""
        db = AsyncDatabase(config)
        db.fetch_one = AsyncMock(return_value=None)

        result = await db.get("t", where_sql="name = %s", where_params=[evil])

        assert result is None
        sql, params = db.fetch_one.call_args[0]
        assert sql == "SELECT * FROM public.t WHERE name = %s LIMIT 1"
        assert params == [evil]
        assert evil not in sql


class TestOrderByEscapeHatch:
    """CRUD-F04 (T-53-03): order_by is a documented, intentional escape
    hatch on select_where/find — it is appended verbatim and is NOT run
    through validate_identifiers. This is not a validation bypass: it proves
    typical multi-column ORDER BY syntax (which validate_identifiers would
    reject as a bare identifier) passes through by design.
    """

    def test_select_where_multi_column_order_by_not_rejected_sync(self, config):
        """A multi-column order_by string is accepted, not rejected, on select_where."""
        with patch("pycopg.database.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",)]
            mock_cursor.fetchall.return_value = []
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_psycopg.connect.return_value = mock_conn

            db = Database(config)
            # Not raising InvalidIdentifierError proves the escape hatch.
            result = db.select_where("t", order_by="a DESC, b ASC")

            assert result == []
            sql, _ = mock_cursor.execute.call_args[0]
            assert sql == "SELECT * FROM public.t ORDER BY a DESC, b ASC"

    @pytest.mark.asyncio
    async def test_select_where_multi_column_order_by_not_rejected_async(self, config):
        """Async mirror: a multi-column order_by string is accepted on select_where."""
        db = AsyncDatabase(config)
        db.fetch_all = AsyncMock(return_value=[])

        result = await db.select_where("t", order_by="a DESC, b ASC")

        assert result == []
        sql, _ = db.fetch_all.call_args[0]
        assert sql == "SELECT * FROM public.t ORDER BY a DESC, b ASC"

    def test_get_multi_column_order_by_not_rejected_sync(self, config):
        """A multi-column order_by string is accepted, not rejected, on get."""
        with patch("pycopg.database.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",)]
            mock_cursor.fetchone.return_value = None
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_psycopg.connect.return_value = mock_conn

            db = Database(config)
            result = db.get("t", order_by="a DESC, b ASC")

            assert result is None
            sql, _ = mock_cursor.execute.call_args[0]
            assert sql == "SELECT * FROM public.t ORDER BY a DESC, b ASC LIMIT 1"


class TestKeysetInjection:
    """CRUD-F02 (T-50-04/T-50-05): QueryMixin._build_keyset_where must reject
    a malicious ``order_by`` identifier via ``validate_identifiers`` (C-02
    line 1) and must bind every ``after`` cursor value as ``%s`` — never
    interpolated into the returned fragment.
    """

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_keyset_order_by_validated(self, evil):
        """An EVIL_IDENTIFIERS order_by column raises before any SQL build."""
        with pytest.raises(InvalidIdentifierError):
            QueryMixin._build_keyset_where([evil], (1,), False)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_keyset_after_values_bound_not_interpolated(self, evil):
        """An EVIL_IDENTIFIERS after value is returned as a bound param, never
        interpolated into the row-value fragment."""
        frag, params = QueryMixin._build_keyset_where(["id"], (evil,), False)
        assert frag == "(id) > (%s)"
        assert params == [evil]
        assert evil not in frag


class TestMaterializedViewIdentifierInjection:
    """INTRO-F02 (T-50-06/T-50-07): materialized_view_columns/materialized_views
    must reject a malicious ``name``/``schema`` via ``validate_identifiers``
    (C-02 line 1) before any SQL executes — defense-in-depth, since name/schema
    are also only ever bound ``%s`` params to the pg_catalog query, never
    interpolated (T-50-07).
    """

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_materialized_views_schema_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.schema.materialized_views(schema=evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_materialized_view_columns_name_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.schema.materialized_view_columns(evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_materialized_view_columns_schema_sync(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.schema.materialized_view_columns("mv", schema=evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_materialized_views_schema_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.schema.materialized_views(schema=evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_materialized_view_columns_name_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.schema.materialized_view_columns(evil)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    async def test_materialized_view_columns_schema_async(self, async_db, evil):
        with pytest.raises(InvalidIdentifierError):
            await async_db.schema.materialized_view_columns("mv", schema=evil)


class TestEtlIdentifierInjection:
    """ETL pure builders must reject every EVIL_IDENTIFIERS payload (ETL-16 / SC-6).

    These tests call the builders directly — no DB, no mock needed.  A
    builder that passes ``evil`` to an f-string without ``validate_identifiers``
    would silently return a string; the fact that ``InvalidIdentifierError`` is
    raised before any SQL is returned is the regression guard.
    """

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_sql_evil_table(self, evil):
        """_build_insert_sql with a malicious table name raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
            _build_insert_sql(evil, ["a"], [{"a": 1}])

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_sql_evil_schema(self, evil):
        """_build_insert_sql with a malicious schema name raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
            _build_insert_sql("t", ["a"], [{"a": 1}], schema=evil)

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_insert_sql_evil_column(self, evil):
        """_build_insert_sql with a malicious column name raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
            _build_insert_sql("t", [evil], [{evil: 1}])

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_upsert_sql_evil_conflict_column(self, evil):
        """_build_upsert_sql with a malicious conflict_column raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
            _build_upsert_sql("t", [{"id": 1, "v": 2}], conflict_columns=[evil])

    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_upsert_sql_evil_table(self, evil):
        """_build_upsert_sql with a malicious table name raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
            _build_upsert_sql(evil, [{"id": 1, "v": 2}], conflict_columns=["id"])
