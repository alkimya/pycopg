"""Integration tests for Database core methods against real PostgreSQL.

These tests use the real pycopg_test database to verify Database methods work correctly.
They cover the core operations that make up the bulk of uncovered lines.
"""

import uuid

import pytest

from pycopg import Database
from pycopg.exceptions import DatabaseExists, ExtensionNotAvailable


@pytest.fixture
def db(db_config):
    """Create a Database instance connected to pycopg_test."""
    database = Database(db_config)
    database.connect()
    yield database
    # Cleanup: disconnect
    if hasattr(database, "_conn") and database._conn:
        database._conn.close()


@pytest.fixture
def temp_table_name():
    """Generate a unique table name for tests."""
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_table(db):
    """Fixture that cleans up tables after test."""
    tables_to_cleanup = []

    def register_table(table_name):
        tables_to_cleanup.append(table_name)

    yield register_table

    # Cleanup registered tables
    for table_name in tables_to_cleanup:
        try:
            db.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
        except Exception:
            pass


class TestDatabaseCoreOperations:
    """Test core Database operations (execute, insert_batch, select, cursor)."""

    def test_connect_and_execute(self, db):
        """Test basic connection and query execution."""
        result = db.execute("SELECT 1 AS num")
        assert len(result) == 1
        assert result[0]["num"] == 1

    def test_execute_with_params(self, db):
        """Test parameterized query execution."""
        result = db.execute("SELECT %s::text AS value", ("test_value",))
        assert len(result) == 1
        assert result[0]["value"] == "test_value"

    def test_execute_autocommit(self, db, temp_table_name, cleanup_table):
        """Test execute with autocommit=True."""
        cleanup_table(temp_table_name)
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, name TEXT)',
            autocommit=True,
        )
        # Verify table exists
        assert db.table_exists(temp_table_name)

    def test_cursor_context(self, db):
        """Test using cursor() context manager."""
        with db.cursor() as cur:
            cur.execute("SELECT 42 AS answer")
            result = cur.fetchone()
            assert result["answer"] == 42

    def test_insert_batch_and_select(self, db, temp_table_name, cleanup_table):
        """Test creating table, inserting rows with insert_batch, and selecting them back."""
        cleanup_table(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, name TEXT, value INTEGER)',
            autocommit=True,
        )

        # Insert batch
        rows = [{"name": f"test{i}", "value": i * 10} for i in range(5)]
        db.insert_batch(temp_table_name, rows)

        # Select them back
        results = db.execute(f'SELECT * FROM "{temp_table_name}" ORDER BY value')
        assert len(results) == 5
        assert results[0]["name"] == "test0"
        assert results[0]["value"] == 0
        assert results[4]["name"] == "test4"
        assert results[4]["value"] == 40

    def test_select_where(self, db, temp_table_name, cleanup_table):
        """Test select with WHERE clause."""
        cleanup_table(temp_table_name)

        # Create and populate table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, status TEXT)',
            autocommit=True,
        )
        db.insert_batch(
            temp_table_name,
            [{"status": "active"}, {"status": "inactive"}, {"status": "active"}],
        )

        # Select with WHERE
        results = db.execute(
            f'SELECT * FROM "{temp_table_name}" WHERE status = %s', ("active",)
        )
        assert len(results) == 2
        assert all(r["status"] == "active" for r in results)

    def test_execute_returning_no_rows(self, db, temp_table_name, cleanup_table):
        """Test execute INSERT without RETURNING clause returns empty list."""
        cleanup_table(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY)',
            autocommit=True,
        )

        # Insert without RETURNING
        result = db.execute(f'INSERT INTO "{temp_table_name}" DEFAULT VALUES')
        assert result == []

    def test_execute_with_returning(self, db, temp_table_name, cleanup_table):
        """Test execute INSERT with RETURNING clause."""
        cleanup_table(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, name TEXT)',
            autocommit=True,
        )

        # Insert with RETURNING
        result = db.execute(
            f'INSERT INTO "{temp_table_name}" (name) VALUES (%s) RETURNING id, name',
            ("testname",),
        )
        assert len(result) == 1
        assert "id" in result[0]
        assert result[0]["name"] == "testname"


class TestDatabaseSchema:
    """Test schema introspection methods."""

    def test_list_schemas(self, db):
        """Test listing database schemas."""
        schemas = db.list_schemas()
        assert "public" in schemas

    def test_list_tables(self, db, temp_table_name, cleanup_table):
        """Test listing tables in a schema."""
        cleanup_table(temp_table_name)

        # Create temp table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY)',
            autocommit=True,
        )

        # List tables
        tables = db.list_tables("public")
        assert temp_table_name in tables

    def test_table_exists(self, db, temp_table_name, cleanup_table):
        """Test table_exists returns correct boolean."""
        cleanup_table(temp_table_name)

        # Should not exist initially
        assert not db.table_exists(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY)',
            autocommit=True,
        )

        # Should exist now
        assert db.table_exists(temp_table_name)

    def test_table_info(self, db, temp_table_name, cleanup_table):
        """Test getting table information."""
        cleanup_table(temp_table_name)

        # Create table with columns
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, name TEXT, created_at TIMESTAMP)',
            autocommit=True,
        )

        # Get table info
        info = db.table_info(temp_table_name)

        # Verify columns are present
        column_names = [col["column_name"] for col in info]
        assert "id" in column_names
        assert "name" in column_names
        assert "created_at" in column_names

    def test_schema_exists(self, db):
        """Test schema_exists for known and unknown schemas."""
        assert db.schema_exists("public")
        assert not db.schema_exists("nonexistent_schema_xyz")


class TestDatabaseSession:
    """Test session management."""

    def test_session_basic(self, db, temp_table_name, cleanup_table):
        """Test basic session usage."""
        cleanup_table(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, value INTEGER)',
            autocommit=True,
        )

        # Use session
        with db.session() as session:
            session.execute(
                f'INSERT INTO "{temp_table_name}" (value) VALUES (%s)', (42,)
            )
            # Query within session
            result = session.execute(f'SELECT value FROM "{temp_table_name}"')
            assert len(result) == 1
            assert result[0]["value"] == 42

    def test_session_in_session_property(self, db):
        """Test in_session property is True inside session, False outside."""
        assert not db.in_session

        with db.session():
            assert db.in_session

        assert not db.in_session

    def test_session_connection_reuse(self, db):
        """Test queries in session use same connection."""
        with db.session() as session:
            # Get backend PID
            result1 = session.execute("SELECT pg_backend_pid()")
            pid1 = result1[0]["pg_backend_pid"]

            result2 = session.execute("SELECT pg_backend_pid()")
            pid2 = result2[0]["pg_backend_pid"]

            # Should be same connection (same PID)
            assert pid1 == pid2

    def test_session_autocommit(self, db, temp_table_name, cleanup_table):
        """Test session with autocommit=True."""
        cleanup_table(temp_table_name)

        # Create table in autocommit session
        with db.session(autocommit=True) as session:
            session.execute(f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY)')

        # Verify table exists outside session
        assert db.table_exists(temp_table_name)


class TestDatabaseEngine:
    """Test SQLAlchemy engine integration."""

    def test_engine_returns_sqlalchemy_engine(self, db):
        """Test engine() returns SQLAlchemy Engine instance."""
        engine = db.engine
        # Check it's an Engine (has basic engine attributes)
        assert hasattr(engine, "connect")
        assert hasattr(engine, "dispose")

    def test_to_dataframe(self, db, temp_table_name, cleanup_table):
        """Test converting table to DataFrame."""
        pd = pytest.importorskip("pandas")
        cleanup_table(temp_table_name)

        # Create and populate table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, name TEXT, value INTEGER)',
            autocommit=True,
        )
        db.insert_batch(
            temp_table_name,
            [
                {"name": "a", "value": 1},
                {"name": "b", "value": 2},
                {"name": "c", "value": 3},
            ],
        )

        # Convert to DataFrame
        df = db.to_dataframe(temp_table_name)

        # Verify shape and content
        assert df.shape[0] == 3
        assert "name" in df.columns
        assert "value" in df.columns
        assert sorted(df["value"].tolist()) == [1, 2, 3]

    def test_from_dataframe(self, db, temp_table_name, cleanup_table):
        """Test creating table from DataFrame."""
        pd = pytest.importorskip("pandas")
        cleanup_table(temp_table_name)

        # Create DataFrame
        df = pd.DataFrame({"name": ["x", "y", "z"], "value": [10, 20, 30]})

        # Write to database
        db.from_dataframe(df, temp_table_name)

        # Verify data in DB
        results = db.execute(f'SELECT * FROM "{temp_table_name}" ORDER BY name')
        assert len(results) == 3
        assert results[0]["name"] == "x"
        assert results[0]["value"] == 10
        assert results[2]["name"] == "z"
        assert results[2]["value"] == 30


class TestDatabaseDDL:
    """Test DDL operations (DROP TABLE, CREATE/DROP INDEX, CREATE/DROP SCHEMA)."""

    def test_drop_table(self, db, temp_table_name, cleanup_table):
        """Test dropping a table."""
        cleanup_table(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY)',
            autocommit=True,
        )
        assert db.table_exists(temp_table_name)

        # Drop table
        db.drop_table(temp_table_name)

        # Verify gone
        assert not db.table_exists(temp_table_name)

    def test_create_index(self, db, temp_table_name, cleanup_table):
        """Test creating an index."""
        cleanup_table(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, email TEXT)',
            autocommit=True,
        )

        # Create index (signature: table, columns, schema, name...)
        index_name = f"{temp_table_name}_email_idx"
        db.create_index(temp_table_name, "email", name=index_name)

        # Verify index exists
        indexes = db.list_indexes(temp_table_name)
        index_names = [idx["index_name"] for idx in indexes]
        assert index_name in index_names

    def test_drop_index(self, db, temp_table_name, cleanup_table):
        """Test dropping an index."""
        cleanup_table(temp_table_name)

        # Create table and index
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, value INTEGER)',
            autocommit=True,
        )
        index_name = f"{temp_table_name}_idx"
        db.create_index(temp_table_name, "value", name=index_name)

        indexes = db.list_indexes(temp_table_name)
        index_names = [idx["index_name"] for idx in indexes]
        assert index_name in index_names

        # Drop index
        db.drop_index(index_name)

        # Verify gone
        indexes_after = db.list_indexes(temp_table_name)
        index_names_after = [idx["index_name"] for idx in indexes_after]
        assert index_name not in index_names_after

    def test_create_schema(self, db):
        """Test creating a schema."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        try:
            # Create schema
            db.create_schema(schema_name, if_not_exists=True)

            # Verify exists
            assert db.schema_exists(schema_name)

        finally:
            # Cleanup
            try:
                db.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            except Exception:
                pass

    def test_drop_schema(self, db):
        """Test dropping a schema."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        try:
            # Create schema
            db.execute(f'CREATE SCHEMA "{schema_name}"')
            assert db.schema_exists(schema_name)

            # Drop schema
            db.drop_schema(schema_name)

            # Verify gone
            assert not db.schema_exists(schema_name)

        finally:
            # Cleanup (in case drop failed)
            try:
                db.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            except Exception:
                pass


class TestDatabaseAdmin:
    """Test database administration methods."""

    def test_size(self, db):
        """Test getting database size."""
        size = db.size()
        # Should return a string like "8 MB" or "123 kB"
        assert isinstance(size, str)
        assert any(unit in size for unit in ["bytes", "kB", "MB", "GB"])

    def test_table_sizes(self, db, temp_table_name, cleanup_table):
        """Test getting table sizes."""
        cleanup_table(temp_table_name)

        # Create table with some data
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY, data TEXT)',
            autocommit=True,
        )
        db.insert_batch(temp_table_name, [{"data": "x" * 1000} for _ in range(10)])

        # Get table sizes
        sizes = db.table_sizes()

        # Should return a list of dicts
        assert isinstance(sizes, list)
        assert len(sizes) > 0
        # Check structure of first result
        if sizes:
            assert "table_name" in sizes[0]
            assert "total_size" in sizes[0] or "size" in sizes[0]

    def test_vacuum(self, db, temp_table_name, cleanup_table):
        """Test running VACUUM on a table."""
        cleanup_table(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY)',
            autocommit=True,
        )

        # Run vacuum (just verify no error)
        db.vacuum(temp_table_name)

    def test_analyze(self, db, temp_table_name, cleanup_table):
        """Test running ANALYZE on a table."""
        cleanup_table(temp_table_name)

        # Create table
        db.execute(
            f'CREATE TABLE "{temp_table_name}" (id SERIAL PRIMARY KEY)',
            autocommit=True,
        )

        # Run analyze (just verify no error)
        db.analyze(temp_table_name)

    def test_create_raises_when_exists_and_not_if_not_exists(self, db_config):
        """create(if_not_exists=False) on an existing DB raises DatabaseExists."""
        with pytest.raises(DatabaseExists, match="already exists"):
            Database.create(
                "pycopg_test",
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                if_not_exists=False,
            )


class TestDatabaseConnection:
    """Test connection management methods."""

    def test_connect_establishes_connection(self, db_config):
        """Test that connect() establishes a connection."""
        db = Database(db_config)

        # Connect
        db.connect()

        # Verify connection works
        result = db.execute("SELECT 1")
        assert len(result) == 1

        # Cleanup
        if hasattr(db, "_conn") and db._conn:
            db._conn.close()

    def test_list_extensions(self, db):
        """Test listing installed extensions."""
        extensions = db.list_extensions()

        # Should return a list
        assert isinstance(extensions, list)
        # plpgsql is typically installed by default
        # Just verify the structure
        if extensions:
            assert isinstance(extensions[0], (str, dict))

    def test_create_extension(self, db):
        """Test creating an extension (if not exists)."""
        # Try to create a commonly available extension
        # Use if_not_exists to avoid errors if already installed
        db.create_extension("pg_trgm", if_not_exists=True)

        # Verify it's listed (should not error)
        extensions = db.list_extensions()
        assert isinstance(extensions, list)


class TestDatabaseBatchStreamNotify:
    """PAR-03: sync mirrors of async insert_many/upsert_many/stream/notify."""

    def _make_kv_table(self, db, table):
        db.execute(
            f'CREATE TABLE "{table}" ' "(id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
        )

    def test_insert_many_empty_returns_zero(self, db):
        """insert_many of an empty list returns 0 and makes no DB call."""
        assert db.insert_many("nonexistent_table", []) == 0

    def test_insert_many_inserts_and_returns_count(
        self, db, temp_table_name, cleanup_table
    ):
        """insert_many of N rows returns N and the rows are readable."""
        cleanup_table(temp_table_name)
        self._make_kv_table(db, temp_table_name)

        count = db.insert_many(
            temp_table_name,
            [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"},
            ],
        )
        assert count == 2

        rows = db.execute(f'SELECT id, name FROM "{temp_table_name}" ORDER BY id')
        assert [r["name"] for r in rows] == ["Alice", "Bob"]

    def test_insert_many_on_conflict_do_nothing(
        self, db, temp_table_name, cleanup_table
    ):
        """insert_many with ON CONFLICT DO NOTHING skips conflicting rows."""
        cleanup_table(temp_table_name)
        self._make_kv_table(db, temp_table_name)

        db.insert_many(
            temp_table_name, [{"id": 1, "name": "Alice", "email": "a@x.com"}]
        )
        # Re-insert same PK with DO NOTHING — should not raise, row unchanged
        db.insert_many(
            temp_table_name,
            [{"id": 1, "name": "Changed", "email": "c@x.com"}],
            on_conflict="(id) DO NOTHING",
        )
        rows = db.execute(f'SELECT name FROM "{temp_table_name}" WHERE id = 1')
        assert rows[0]["name"] == "Alice"

    def test_upsert_many_updates_on_conflict(self, db, temp_table_name, cleanup_table):
        """upsert_many updates non-conflict columns on conflict and returns count."""
        cleanup_table(temp_table_name)
        self._make_kv_table(db, temp_table_name)

        db.insert_many(
            temp_table_name, [{"id": 1, "name": "Alice", "email": "old@x.com"}]
        )
        affected = db.upsert_many(
            temp_table_name,
            [{"id": 1, "name": "Alice", "email": "new@x.com"}],
            conflict_columns=["id"],
        )
        assert affected >= 1
        rows = db.execute(f'SELECT email FROM "{temp_table_name}" WHERE id = 1')
        assert rows[0]["email"] == "new@x.com"

    def test_stream_yields_all_rows_in_batches(
        self, db, temp_table_name, cleanup_table
    ):
        """stream over a 3-row table with batch_size=2 yields exactly 3 dict rows in order."""
        cleanup_table(temp_table_name)
        self._make_kv_table(db, temp_table_name)
        db.insert_many(
            temp_table_name,
            [
                {"id": 1, "name": "a", "email": "a@x"},
                {"id": 2, "name": "b", "email": "b@x"},
                {"id": 3, "name": "c", "email": "c@x"},
            ],
        )

        result = list(
            db.stream(
                f'SELECT id, name FROM "{temp_table_name}" ORDER BY id', batch_size=2
            )
        )
        assert len(result) == 3
        assert all(isinstance(r, dict) for r in result)
        assert [r["id"] for r in result] == [1, 2, 3]

    def test_stream_is_lazy_generator(self, db, temp_table_name, cleanup_table):
        """stream returns a generator, not a materialized list."""
        cleanup_table(temp_table_name)
        self._make_kv_table(db, temp_table_name)
        db.insert_many(temp_table_name, [{"id": 1, "name": "a", "email": "a@x"}])

        import types

        gen = db.stream(f'SELECT * FROM "{temp_table_name}"')
        assert isinstance(gen, types.GeneratorType)
        list(gen)  # drain so the cursor/connection is released

    def test_notify_on_valid_channel(self, db):
        """notify issues NOTIFY on a validated channel without raising."""
        db.notify("events", "hello")

    def test_notify_rejects_invalid_channel(self, db):
        """notify on an invalid channel name raises via validate_identifier."""
        with pytest.raises(Exception):
            db.notify("bad channel; DROP TABLE x", "payload")

    def test_no_sync_listen_method(self, db):
        """D-06: listen stays async-only — Database must NOT have a listen method."""
        assert not hasattr(db, "listen")


class TestDatabaseConstraintsAdminCoverage:
    """PAR-09 coverage: sync constraint/admin methods against the real DB."""

    def test_add_foreign_key_cascade(self, db, cleanup_table):
        """add_foreign_key creates an FK that cascades deletes."""
        parent = f"test_fk_p_{uuid.uuid4().hex[:8]}"
        child = f"test_fk_c_{uuid.uuid4().hex[:8]}"
        cleanup_table(parent)
        cleanup_table(child)
        db.execute(f'CREATE TABLE "{parent}" (id INTEGER PRIMARY KEY)', autocommit=True)
        db.execute(
            f'CREATE TABLE "{child}" (id INTEGER PRIMARY KEY, parent_id INTEGER)',
            autocommit=True,
        )
        db.add_foreign_key(child, "parent_id", parent, "id", on_delete="CASCADE")
        db.execute(f'INSERT INTO "{parent}" VALUES (1)', autocommit=True)
        db.execute(f'INSERT INTO "{child}" VALUES (10, 1)', autocommit=True)
        db.execute(f'DELETE FROM "{parent}" WHERE id = 1', autocommit=True)
        assert db.execute(f'SELECT * FROM "{child}"') == []

    def test_add_foreign_key_invalid_action_raises(self, db):
        """add_foreign_key with a bad on_delete raises ValueError before SQL."""
        with pytest.raises(ValueError, match="Invalid ON DELETE"):
            db.add_foreign_key("a", "x", "b", "y", on_delete="BOGUS")
        with pytest.raises(ValueError, match="Invalid ON UPDATE"):
            db.add_foreign_key("a", "x", "b", "y", on_update="BOGUS")

    def test_add_unique_constraint_rejects_duplicate(self, db, cleanup_table):
        """add_unique_constraint enforces uniqueness."""
        t = f"test_uq_{uuid.uuid4().hex[:8]}"
        cleanup_table(t)
        db.execute(f'CREATE TABLE "{t}" (id INTEGER, email TEXT)', autocommit=True)
        db.add_unique_constraint(t, "email")
        db.execute(f'INSERT INTO "{t}" VALUES (1, %s)', ["a@x"], autocommit=True)
        with pytest.raises(Exception):
            db.execute(f'INSERT INTO "{t}" VALUES (2, %s)', ["a@x"], autocommit=True)

    def test_truncate_table_cascade(self, db, cleanup_table):
        """truncate_table with cascade=True empties a referenced table."""
        parent = f"test_tr_p_{uuid.uuid4().hex[:8]}"
        child = f"test_tr_c_{uuid.uuid4().hex[:8]}"
        cleanup_table(parent)
        cleanup_table(child)
        db.execute(f'CREATE TABLE "{parent}" (id INTEGER PRIMARY KEY)', autocommit=True)
        db.execute(
            f'CREATE TABLE "{child}" (id INTEGER, p INTEGER REFERENCES "{parent}"(id))',
            autocommit=True,
        )
        db.execute(f'INSERT INTO "{parent}" VALUES (1)', autocommit=True)
        db.execute(f'INSERT INTO "{child}" VALUES (1, 1)', autocommit=True)
        db.truncate_table(parent, cascade=True)
        assert db.execute(f'SELECT COUNT(*) AS n FROM "{parent}"')[0]["n"] == 0
        assert db.execute(f'SELECT COUNT(*) AS n FROM "{child}"')[0]["n"] == 0

    def test_database_exists_and_list(self, db):
        """database_exists / list_databases against the real instance."""
        assert db.database_exists("pycopg_test") is True
        assert db.database_exists("definitely_absent_xyz") is False
        names = db.list_databases()
        assert "pycopg_test" in names

    def test_drop_extension_if_exists(self, db):
        """drop_extension(if_exists=True) is idempotent."""
        db.create_extension("pg_trgm", if_not_exists=True)
        db.drop_extension("pg_trgm", if_exists=True)
        db.drop_extension("pg_trgm", if_exists=True)  # no error second time
        db.create_extension("pg_trgm", if_not_exists=True)  # restore

    def test_drop_table_if_exists_and_cascade(self, db, cleanup_table):
        """drop_table covers if_exists and cascade branches."""
        t = f"test_dt_{uuid.uuid4().hex[:8]}"
        cleanup_table(t)
        db.execute(f'CREATE TABLE "{t}" (id INTEGER)', autocommit=True)
        db.drop_table(t, cascade=True)
        assert not db.table_exists(t)
        # if_exists=True when already gone must not raise
        db.drop_table(t, if_exists=True)

    def test_drop_schema_cascade(self, db):
        """create_schema then drop_schema(cascade=True) round-trip."""
        s = f"test_sc_{uuid.uuid4().hex[:8]}"
        db.create_schema(s)
        assert db.schema_exists(s)
        db.execute(f'CREATE TABLE "{s}".t (id INTEGER)', autocommit=True)
        db.drop_schema(s, cascade=True)
        assert not db.schema_exists(s)


class TestDatabaseCsvCoverage:
    """PAR-09 coverage: copy_to_csv / copy_from_csv round-trip."""

    def test_copy_to_and_from_csv_round_trip(self, db, cleanup_table, tmp_path):
        """copy_to_csv exports rows; copy_from_csv re-imports them."""
        src = f"test_csv_src_{uuid.uuid4().hex[:8]}"
        dst = f"test_csv_dst_{uuid.uuid4().hex[:8]}"
        cleanup_table(src)
        cleanup_table(dst)
        db.execute(f'CREATE TABLE "{src}" (id INTEGER, name TEXT)', autocommit=True)
        db.insert_many(src, [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])

        csv_path = tmp_path / "out.csv"
        exported = db.copy_to_csv(src, str(csv_path))
        assert exported == 2
        assert csv_path.exists()

        db.execute(f'CREATE TABLE "{dst}" (id INTEGER, name TEXT)', autocommit=True)
        db.copy_from_csv(dst, str(csv_path))
        rows = db.execute(f'SELECT id, name FROM "{dst}" ORDER BY id')
        assert rows == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]


class TestDatabaseBulkAndSizeCoverage:
    """PAR-09 coverage: copy_insert + size/table_size/row_count."""

    def test_copy_insert(self, db, cleanup_table):
        """copy_insert bulk-loads rows via the COPY protocol."""
        t = f"test_ci_{uuid.uuid4().hex[:8]}"
        cleanup_table(t)
        db.execute(f'CREATE TABLE "{t}" (id INTEGER, name TEXT)', autocommit=True)
        count = db.copy_insert(
            t, [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]
        )
        assert count == 3
        assert db.execute(f'SELECT COUNT(*) AS n FROM "{t}"')[0]["n"] == 3

    def test_size_pretty_and_raw(self, db):
        """size returns a human string when pretty, an int otherwise."""
        pretty = db.size(pretty=True)
        raw = db.size(pretty=False)
        assert isinstance(pretty, str)
        assert isinstance(raw, int)

    def test_table_size_and_row_count(self, db, cleanup_table):
        """table_size returns size info; row_count returns an int."""
        t = f"test_sz_{uuid.uuid4().hex[:8]}"
        cleanup_table(t)
        db.execute(f'CREATE TABLE "{t}" (id INTEGER)', autocommit=True)
        db.insert_many(t, [{"id": i} for i in range(5)])
        size = db.table_size(t)
        assert size is not None
        assert isinstance(db.row_count(t), int)


class TestDatabaseGeoCoverage:
    """PAR-09 coverage: GeoDataFrame round-trip (requires PostGIS + geopandas)."""

    def test_from_and_to_geodataframe(self, db, cleanup_table):
        """from_geodataframe writes geometry; to_geodataframe reads it back."""
        gpd = pytest.importorskip("geopandas")
        from shapely.geometry import Point

        if not db.has_extension("postgis"):
            pytest.skip("PostGIS not installed")

        t = f"test_geo_{uuid.uuid4().hex[:8]}"
        cleanup_table(t)
        gdf = gpd.GeoDataFrame(
            {"name": ["a", "b"]},
            geometry=[Point(1, 1), Point(2, 2)],
            crs="EPSG:4326",
        )
        db.from_geodataframe(gdf, t, primary_key=None, spatial_index=True)
        back = db.to_geodataframe(table=t)
        assert len(back) == 2
        assert "geometry" in back.columns


class TestDatabaseTimescaleCoverage:
    """PAR-09 coverage: TimescaleDB hypertable lifecycle (requires timescaledb)."""

    @pytest.fixture
    def ts_db(self, db):
        if not db.has_extension("timescaledb"):
            try:
                db.create_extension("timescaledb", if_not_exists=True)
            except Exception:
                pytest.skip("TimescaleDB extension not available")
        if not db.has_extension("timescaledb"):
            pytest.skip("TimescaleDB extension not available")
        return db

    def test_hypertable_lifecycle(self, ts_db, cleanup_table):
        """create_hypertable -> enable_compression -> policies -> info -> list."""
        t = f"test_ht_{uuid.uuid4().hex[:8]}"
        cleanup_table(t)
        ts_db.execute(
            f'CREATE TABLE "{t}" (ts TIMESTAMPTZ NOT NULL, device TEXT, val DOUBLE PRECISION)',
            autocommit=True,
        )
        ts_db.timescale.create_hypertable(t, "ts", chunk_time_interval="1 day")

        info = ts_db.timescale.hypertable_info(t)
        assert "total_size" in info

        hypertables = ts_db.timescale.list_hypertables()
        assert any(h["table_name"] == t for h in hypertables)

        # Compression/retention are TimescaleDB-licensed features. On the Apache
        # (community) build they raise FeatureNotSupported — exercise the code
        # paths but tolerate the license limitation in CI/local environments.
        from psycopg.errors import FeatureNotSupported

        try:
            ts_db.timescale.enable_compression(
                t, segment_by="device", order_by="ts DESC"
            )
            ts_db.timescale.add_compression_policy(t, compress_after="7 days")
            ts_db.timescale.add_retention_policy(t, drop_after="365 days")
        except FeatureNotSupported:
            pass

    def test_create_hypertable_requires_extension(self, db, cleanup_table, monkeypatch):
        """create_hypertable raises RuntimeError when timescaledb is absent."""
        t = f"test_ht_err_{uuid.uuid4().hex[:8]}"
        monkeypatch.setattr(db, "has_extension", lambda name: False)
        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            db.timescale.create_hypertable(t, "ts")
