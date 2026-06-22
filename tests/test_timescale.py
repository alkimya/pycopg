"""Tests for TimescaleDB advanced chunk/partition management methods (v0.8.0).

Home for all advanced TSDB tests introduced in Phase 30 and extended in Phases
31-32.  Basic TSDB tests (create_hypertable, list_hypertables, etc.) remain in
tests/test_database_integration.py and tests/test_async_database.py.

Two test layers (D-11):
  - Live-DB integration tests: gated by the ts_db / async_ts_db skip-fixture
    (create-extension-or-skip, ported from TestDatabaseTimescaleCoverage).
  - Mock SQL-shape unit tests: use MagicMock / AsyncMock to assert generated
    SQL without a live DB (authoritative for add_reorder_policy under Apache
    license, per D-12).

asyncio_mode = "auto" is set in pyproject.toml so async tests need no per-test
marker.
"""

# FeatureNotSupported is used by the live reorder-policy integration test (D-12,
# Apache-license tolerance).  Import here so it is available when Plan 03 fills
# in the stub bodies, and to satisfy the Wave 0 acceptance criterion.
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from psycopg.errors import FeatureNotSupported  # noqa: F401

from pycopg import AsyncDatabase, Database
from pycopg.exceptions import ExtensionNotAvailable, TimescaleError  # noqa: F401

# =============================================================================
# Fixtures — live-DB integration layer (D-10, D-11)
# =============================================================================


@pytest.fixture
def db(db_config):
    """Return a Database connected to pycopg_test."""
    database = Database(db_config)
    yield database
    if hasattr(database, "_session_conn") and database._session_conn:
        database._session_conn.close()


@pytest.fixture
def ts_db(db):
    """Return a Database with TimescaleDB enabled, or skip if not available.

    Ported from tests/test_database_integration.py::TestDatabaseTimescaleCoverage
    (create-extension-or-skip pattern).
    """
    if not db.schema.has_extension("timescaledb"):
        try:
            db.schema.create_extension("timescaledb", if_not_exists=True)
        except Exception:
            pytest.skip("TimescaleDB extension not available")
    if not db.schema.has_extension("timescaledb"):
        pytest.skip("TimescaleDB extension not available")
    return db


@pytest.fixture
async def async_ts_db(db_config):
    """Return an AsyncDatabase with TimescaleDB enabled, or skip if not available.

    Async equivalent of ts_db, using asyncio_mode = "auto" (no per-test marker
    required).
    """
    database = AsyncDatabase(db_config)
    if not await database.schema.has_extension("timescaledb"):
        try:
            await database.schema.create_extension("timescaledb", if_not_exists=True)
        except Exception:
            pytest.skip("TimescaleDB extension not available")
    if not await database.schema.has_extension("timescaledb"):
        pytest.skip("TimescaleDB extension not available")
    yield database


# =============================================================================
# Helpers for live-DB tests
# =============================================================================


def _make_hypertable(db, table_name, days=5):
    """Create a small hypertable with data spanning multiple chunk intervals.

    Creates a table with ``days`` rows, one per day, which results in
    ``days`` chunks with a 1-day chunk interval.  Returns the table name.
    """
    db.execute(f"DROP TABLE IF EXISTS {table_name}")
    db.execute(f"""
        CREATE TABLE {table_name} (
            ts TIMESTAMPTZ NOT NULL,
            val DOUBLE PRECISION
        )
        """)
    db.timescale.create_hypertable(
        table_name, "ts", chunk_time_interval="1 day", if_not_exists=True
    )
    # Insert one row per day for `days` days — creates `days` chunks.
    for i in range(days):
        db.execute(
            f"INSERT INTO {table_name} (ts, val) "
            f"VALUES (now() - INTERVAL '{days - 1 - i} days', {i})"
        )
    return table_name


# =============================================================================
# show_chunks — mock SQL-shape unit tests (Layer 2, no live DB)
# =============================================================================


class TestShowChunksMock:
    """Mock SQL-shape unit tests for show_chunks (sync + async, no live DB)."""

    def test_show_chunks_sql_shape_no_bounds(self, config):
        """show_chunks() with no bounds executes TSDB_SHOW_CHUNKS with no args."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(
            return_value=[{"chunk_name": "_timescaledb_internal._hyper_1_1_chunk"}]
        )

        result = db.timescale.show_chunks("events")

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        sql, params = db.execute.call_args[0]
        assert "show_chunks(" in sql
        assert "ORDER BY c.range_start ASC" in sql
        # No bound fragments
        assert "older_than" not in sql
        assert "newer_than" not in sql
        assert params == []
        assert result == ["_timescaledb_internal._hyper_1_1_chunk"]

    def test_show_chunks_sql_shape_str_older_than(self, config):
        """show_chunks with str older_than emits %s::interval fragment."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        db.timescale.show_chunks("events", older_than="30 days")

        sql, params = db.execute.call_args[0]
        assert ", older_than => %s::interval" in sql
        assert "newer_than" not in sql
        assert params == ["30 days"]

    def test_show_chunks_sql_shape_datetime_older_than(self, config):
        """show_chunks with datetime older_than emits bare %s fragment."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        cutoff = datetime(2024, 1, 15)
        db.timescale.show_chunks("events", older_than=cutoff)

        sql, params = db.execute.call_args[0]
        assert ", older_than => %s" in sql
        assert "::interval" not in sql
        assert params == [cutoff]

    def test_show_chunks_params_order_older_then_newer(self, config):
        """show_chunks params are [older_than, newer_than] — not swapped (D-02 footgun)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        older = "60 days"
        newer = "10 days"
        db.timescale.show_chunks("events", older_than=older, newer_than=newer)

        sql, params = db.execute.call_args[0]
        assert ", older_than => %s::interval" in sql
        assert ", newer_than => %s::interval" in sql
        assert params == [older, newer]

    def test_show_chunks_no_extension_raises(self, config):
        """show_chunks raises ExtensionNotAvailable when TimescaleDB is absent."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=False)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            db.timescale.show_chunks("events")

        db.execute.assert_not_called()

    async def test_show_chunks_async_sql_shape(self, config):
        """Async show_chunks awaits has_extension and execute; correct SQL shape."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(
            return_value=[{"chunk_name": "_timescaledb_internal._hyper_1_1_chunk"}]
        )

        result = await db.timescale.show_chunks("events")

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        sql, params = db.execute.call_args[0]
        assert "show_chunks(" in sql
        assert "ORDER BY c.range_start ASC" in sql
        assert result == ["_timescaledb_internal._hyper_1_1_chunk"]

    async def test_show_chunks_async_params_order(self, config):
        """Async show_chunks params are [older_than, newer_than] in that order."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[])

        older = "30 days"
        newer = "5 days"
        await db.timescale.show_chunks("events", older_than=older, newer_than=newer)

        sql, params = db.execute.call_args[0]
        assert params == [older, newer]

    async def test_show_chunks_async_no_extension_raises(self, config):
        """Async show_chunks raises ExtensionNotAvailable when extension absent."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema
        db.execute = AsyncMock()

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.show_chunks("events")

        db.execute.assert_not_called()


# =============================================================================
# drop_chunks — mock SQL-shape unit tests (Layer 2, no live DB)
# =============================================================================


class TestDropChunksMock:
    """Mock SQL-shape unit tests for drop_chunks (sync + async, no live DB)."""

    @pytest.mark.parametrize("bad", [123, 1.5, date(2020, 1, 1)])
    def test_build_chunk_bound_fragments_rejects_unsupported_type(self, bad):
        """WR-04: non-str/non-datetime bounds raise TypeError, not a silent bind.

        ``drop_chunks`` is destructive, so an int/date/Decimal must not fall
        through to a bare ``%s`` bind where the DB could match an unexpected
        chunk set.  ``date`` is excluded too (datetime is a subclass of date).
        """
        from pycopg.timescale import _build_chunk_bound_fragments

        with pytest.raises(TypeError, match="older_than must be str"):
            _build_chunk_bound_fragments(bad, None)

        with pytest.raises(TypeError, match="newer_than must be str"):
            _build_chunk_bound_fragments(None, bad)

    def test_drop_chunks_both_none_raises_before_execute(self, config):
        """drop_chunks(both None) raises ValueError and never calls execute (D-03)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(ValueError, match="drop_chunks requires at least one"):
            db.timescale.drop_chunks("events")

        # Guard fires BEFORE DB round-trip — execute must never be called.
        db.execute.assert_not_called()

    def test_drop_chunks_dry_run_no_drop_sql(self, config):
        """drop_chunks dry_run=True does not issue SELECT drop_chunks(...)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        captured = [
            {"chunk_name": "_timescaledb_internal._hyper_1_1_chunk"},
            {"chunk_name": "_timescaledb_internal._hyper_1_2_chunk"},
        ]
        db.execute = MagicMock(return_value=captured)

        result = db.timescale.drop_chunks("events", older_than="30 days", dry_run=True)

        # Only one execute call (the show_chunks capture); no drop call.
        assert db.execute.call_count == 1
        sql_called = db.execute.call_args[0][0]
        assert "drop_chunks(" not in sql_called
        assert "show_chunks(" in sql_called
        assert result == [
            "_timescaledb_internal._hyper_1_1_chunk",
            "_timescaledb_internal._hyper_1_2_chunk",
        ]

    def test_drop_chunks_real_drop_issues_drop_sql(self, config):
        """drop_chunks dry_run=False issues both capture and drop SQL."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema

        captured = [{"chunk_name": "_timescaledb_internal._hyper_1_1_chunk"}]
        # First call is the capture (show_chunks), second is the drop.
        db.execute = MagicMock(side_effect=[captured, []])

        result = db.timescale.drop_chunks("events", older_than="30 days", dry_run=False)

        assert db.execute.call_count == 2
        first_sql = db.execute.call_args_list[0][0][0]
        second_sql = db.execute.call_args_list[1][0][0]
        assert "show_chunks(" in first_sql
        assert "drop_chunks(" in second_sql
        assert result == ["_timescaledb_internal._hyper_1_1_chunk"]

    def test_drop_chunks_both_none_raises_no_extension_check(self, config):
        """drop_chunks(both None) raises BEFORE the extension guard (pure Python)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(ValueError):
            db.timescale.drop_chunks("events", older_than=None, newer_than=None)

        # has_extension must NOT be called — guard fires before any DB touch.
        mock_schema.has_extension.assert_not_called()

    async def test_drop_chunks_async_both_none_raises(self, config):
        """Async drop_chunks(both None) raises ValueError before any await."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        with pytest.raises(ValueError, match="drop_chunks requires at least one"):
            await db.timescale.drop_chunks("events")

        # execute never reached — ValueError is pre-guard.
        db.execute.assert_not_called()

    async def test_drop_chunks_async_dry_run_no_drop(self, config):
        """Async drop_chunks dry_run=True does not emit drop SQL."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        captured = [{"chunk_name": "_timescaledb_internal._hyper_1_1_chunk"}]
        db.execute = AsyncMock(return_value=captured)

        result = await db.timescale.drop_chunks(
            "events", older_than="30 days", dry_run=True
        )

        assert db.execute.call_count == 1
        sql_called = db.execute.call_args[0][0]
        assert "drop_chunks(" not in sql_called
        assert result == ["_timescaledb_internal._hyper_1_1_chunk"]

    async def test_drop_chunks_async_real_drop(self, config):
        """Async drop_chunks dry_run=False issues capture + drop SQL."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema

        captured = [{"chunk_name": "_timescaledb_internal._hyper_1_1_chunk"}]
        db.execute = AsyncMock(side_effect=[captured, []])

        result = await db.timescale.drop_chunks(
            "events", older_than="30 days", dry_run=False
        )

        assert db.execute.call_count == 2
        first_sql = db.execute.call_args_list[0][0][0]
        second_sql = db.execute.call_args_list[1][0][0]
        assert "show_chunks(" in first_sql
        assert "drop_chunks(" in second_sql
        assert result == ["_timescaledb_internal._hyper_1_1_chunk"]


# =============================================================================
# show_chunks — live-DB integration tests (Layer 1, gated by ts_db)
# =============================================================================


class TestShowChunksLive:
    """Live-DB integration tests for show_chunks (TS-ADV-04)."""

    def test_show_chunks_returns_list(self, ts_db):
        """show_chunks returns a non-empty list[str] of fully-qualified chunk names."""
        table = f"_test_show_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=3)
            chunks = ts_db.timescale.show_chunks(table)
            assert isinstance(chunks, list)
            assert len(chunks) >= 1
            # Fully-qualified: schema.name form.
            for name in chunks:
                assert "." in name
                assert "_hyper_" in name
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    def test_show_chunks_oldest_first(self, ts_db):
        """show_chunks list is ordered oldest-first by range_start (not lexicographically).

        Verifies that chunk N+1 appears AFTER chunk N in the returned list (range
        order), so that e.g. _hyper_X_10_chunk comes AFTER _hyper_X_9_chunk.
        """
        table = f"_test_order_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=12)
            chunks = ts_db.timescale.show_chunks(table)
            assert len(chunks) >= 2, "Need at least 2 chunks to verify ordering"

            # Extract the numeric chunk suffix (N in _hyper_X_N_chunk).
            def chunk_seq(name):
                # name = "_timescaledb_internal._hyper_X_N_chunk"
                parts = name.split("_")
                # Find the numeric part before "chunk" at the end.
                return int(parts[-2])

            seqs = [chunk_seq(c) for c in chunks]
            # The sequence of chunk IDs must be strictly ascending
            # (oldest chunk was created first, so has the smallest ID).
            assert seqs == sorted(
                seqs
            ), f"Chunks not in ascending-ID order (oldest-first): {seqs}"
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    def test_show_chunks_older_than_filter(self, ts_db):
        """show_chunks older_than filters to chunks before the cutoff."""
        table = f"_test_ot_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=5)
            all_chunks = ts_db.timescale.show_chunks(table)
            assert len(all_chunks) >= 2, "Need >=2 chunks to test filter"

            # older_than="1 day" should return chunks older than 1 day.
            filtered = ts_db.timescale.show_chunks(table, older_than="1 day")
            # The filtered list must be a subset of the full list.
            assert set(filtered).issubset(set(all_chunks))
            # We inserted rows spanning the last 5 days so at least some
            # chunks are older than 1 day.
            assert len(filtered) >= 1
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_show_chunks_async(self, async_ts_db):
        """Async show_chunks returns identical shape to sync."""
        table = f"_test_async_show_{uuid.uuid4().hex[:8]}"
        try:
            # Create the hypertable via the sync path to reuse the helper.
            from pycopg import Database

            sync_db = Database(async_ts_db.config)
            _make_hypertable(sync_db, table, days=3)

            chunks = await async_ts_db.timescale.show_chunks(table)
            assert isinstance(chunks, list)
            assert len(chunks) >= 1
            for name in chunks:
                assert "." in name
                assert "_hyper_" in name
        finally:
            await async_ts_db.execute(f"DROP TABLE IF EXISTS {table}")


# =============================================================================
# drop_chunks — live-DB integration tests (Layer 1, gated by ts_db)
# =============================================================================


class TestDropChunksLive:
    """Live-DB integration tests for drop_chunks (TS-ADV-05)."""

    def test_drop_chunks_both_none_raises(self, ts_db):
        """drop_chunks raises ValueError when both bounds are None (D-03)."""
        with pytest.raises(ValueError, match="drop_chunks requires at least one"):
            ts_db.timescale.drop_chunks("any_table")

    def test_drop_chunks_dry_run(self, ts_db):
        """drop_chunks dry_run=True returns chunk list without deleting anything."""
        table = f"_test_dry_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=5)
            before_count = len(ts_db.timescale.show_chunks(table))
            assert before_count >= 1

            dry_result = ts_db.timescale.drop_chunks(
                table, older_than="1 day", dry_run=True
            )

            after_count = len(ts_db.timescale.show_chunks(table))
            # Dry run must not change the chunk count.
            assert after_count == before_count
            # dry_result is a list of strings.
            assert isinstance(dry_result, list)
            for name in dry_result:
                assert "." in name
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    def test_drop_chunks_real_drop(self, ts_db):
        """drop_chunks real drop removes chunks and returns the dropped names."""
        table = f"_test_drop_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=5)
            all_chunks = ts_db.timescale.show_chunks(table)
            assert len(all_chunks) >= 2, "Need >=2 chunks to test real drop"

            # Drop chunks older than 1 day.
            dropped = ts_db.timescale.drop_chunks(table, older_than="1 day")

            # Returned list must be a subset of the original full list.
            assert set(dropped).issubset(set(all_chunks))
            # After the drop, show_chunks count must have decreased.
            remaining = ts_db.timescale.show_chunks(table)
            assert len(remaining) < len(all_chunks)
            # Dropped names must not appear in remaining.
            assert set(dropped).isdisjoint(set(remaining))
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    def test_drop_chunks_returned_list_oldest_first(self, ts_db):
        """drop_chunks returned list is oldest-first (same ordering as show_chunks)."""
        table = f"_test_order_drop_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=5)

            dry_result = ts_db.timescale.drop_chunks(
                table, older_than="1 day", dry_run=True
            )

            if len(dry_result) >= 2:

                def chunk_seq(name):
                    parts = name.split("_")
                    return int(parts[-2])

                seqs = [chunk_seq(c) for c in dry_result]
                assert seqs == sorted(
                    seqs
                ), f"drop_chunks returned list not oldest-first: {seqs}"
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_drop_chunks_async(self, async_ts_db):
        """Async drop_chunks mirrors sync behavior."""
        table = f"_test_async_drop_{uuid.uuid4().hex[:8]}"
        try:
            from pycopg import Database

            sync_db = Database(async_ts_db.config)
            _make_hypertable(sync_db, table, days=5)

            # Dry run via async.
            dry_result = await async_ts_db.timescale.drop_chunks(
                table, older_than="1 day", dry_run=True
            )
            assert isinstance(dry_result, list)

            # Real drop via async.
            all_chunks_before = await async_ts_db.timescale.show_chunks(table)
            dropped = await async_ts_db.timescale.drop_chunks(table, older_than="1 day")
            all_chunks_after = await async_ts_db.timescale.show_chunks(table)

            assert set(dropped).issubset(set(all_chunks_before))
            assert len(all_chunks_after) <= len(all_chunks_before)
        finally:
            await async_ts_db.execute(f"DROP TABLE IF EXISTS {table}")


# =============================================================================
# add_dimension — mock SQL-shape unit tests (Layer 2, authoritative, no live DB)
# =============================================================================


class TestAddDimensionMock:
    """Mock SQL-shape unit tests for add_dimension (sync + async, no live DB)."""

    def test_add_dimension_hash_sql_shape(self, config):
        """add_dimension hash form generates by_hash('device_id', 4) SQL."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        db.timescale.add_dimension(
            "events", "device_id", partition_type="hash", number_partitions=4
        )

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        sql = db.execute.call_args[0][0]
        assert "by_hash('device_id', 4)" in sql
        assert "if_not_exists => true" in sql
        assert "add_dimension('public.events'" in sql

    def test_add_dimension_range_sql_shape(self, config):
        """add_dimension range form generates by_range('ts2', INTERVAL '7 days') SQL."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        db.timescale.add_dimension(
            "events", "ts2", partition_type="range", chunk_interval="7 days"
        )

        sql = db.execute.call_args[0][0]
        assert "by_range('ts2', INTERVAL '7 days')" in sql
        assert "if_not_exists => true" in sql

    def test_add_dimension_hash_without_number_partitions_raises(self, config):
        """add_dimension hash without number_partitions raises ValueError (no DB call)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(ValueError, match="number_partitions"):
            db.timescale.add_dimension("events", "device_id", partition_type="hash")

        db.execute.assert_not_called()

    def test_add_dimension_hash_with_chunk_interval_raises(self, config):
        """add_dimension hash with chunk_interval raises ValueError (no DB call)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(ValueError, match="chunk_interval"):
            db.timescale.add_dimension(
                "events",
                "device_id",
                partition_type="hash",
                number_partitions=4,
                chunk_interval="7 days",
            )

        db.execute.assert_not_called()

    def test_add_dimension_range_without_chunk_interval_raises(self, config):
        """add_dimension range without chunk_interval raises ValueError (no DB call)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(ValueError, match="chunk_interval"):
            db.timescale.add_dimension("events", "ts2", partition_type="range")

        db.execute.assert_not_called()

    def test_add_dimension_range_with_number_partitions_raises(self, config):
        """add_dimension range with number_partitions raises ValueError (no DB call)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(ValueError, match="number_partitions"):
            db.timescale.add_dimension(
                "events",
                "ts2",
                partition_type="range",
                chunk_interval="7 days",
                number_partitions=4,
            )

        db.execute.assert_not_called()

    def test_add_dimension_db_error_reraises_as_timescale_error(self, config):
        """add_dimension re-raises a DB error as TimescaleError (if_not_exists=False)."""
        from psycopg import DatabaseError

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        # Simulate TS160 duplicate-dimension error (surfaces as DatabaseError subclass).
        db.execute = MagicMock(
            side_effect=DatabaseError('column "device_id" is already a dimension')
        )

        with pytest.raises(TimescaleError, match="add_dimension failed"):
            db.timescale.add_dimension(
                "events",
                "device_id",
                partition_type="hash",
                number_partitions=4,
                if_not_exists=False,
            )

    def test_add_dimension_non_db_error_propagates_unwrapped(self, config):
        """WR-01: a non-DatabaseError from execute propagates, not wrapped."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(side_effect=RuntimeError("not a db error"))

        # Must surface as the original RuntimeError, never flattened to
        # TimescaleError (the catch is narrowed to DatabaseError).
        with pytest.raises(RuntimeError, match="not a db error"):
            db.timescale.add_dimension(
                "events",
                "device_id",
                partition_type="hash",
                number_partitions=4,
                if_not_exists=False,
            )

    @pytest.mark.parametrize("bad", [True, 3.9, 0, -1])
    def test_add_dimension_invalid_number_partitions_raises(self, config, bad):
        """WR-03: bool/float/non-positive number_partitions raise ValueError, no DB call."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(ValueError, match="number_partitions"):
            db.timescale.add_dimension(
                "events",
                "device_id",
                partition_type="hash",
                number_partitions=bad,
            )

        db.execute.assert_not_called()

    async def test_add_dimension_async_non_db_error_propagates_unwrapped(self, config):
        """WR-01 async: a non-DatabaseError from execute propagates, not wrapped."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(side_effect=RuntimeError("not a db error"))

        with pytest.raises(RuntimeError, match="not a db error"):
            await db.timescale.add_dimension(
                "events",
                "device_id",
                partition_type="hash",
                number_partitions=4,
                if_not_exists=False,
            )

    @pytest.mark.parametrize("bad", [True, 3.9, 0, -1])
    async def test_add_dimension_async_invalid_number_partitions_raises(
        self, config, bad
    ):
        """WR-03 async: invalid number_partitions raises ValueError before any await."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        with pytest.raises(ValueError, match="number_partitions"):
            await db.timescale.add_dimension(
                "events",
                "device_id",
                partition_type="hash",
                number_partitions=bad,
            )

        db.execute.assert_not_called()

    async def test_add_dimension_async_hash_sql_shape(self, config):
        """Async add_dimension hash form awaits guard + execute; correct SQL shape."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[])

        await db.timescale.add_dimension(
            "events", "device_id", partition_type="hash", number_partitions=4
        )

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        sql = db.execute.call_args[0][0]
        assert "by_hash('device_id', 4)" in sql
        assert "if_not_exists => true" in sql

    async def test_add_dimension_async_range_sql_shape(self, config):
        """Async add_dimension range form generates by_range SQL."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[])

        await db.timescale.add_dimension(
            "events", "ts2", partition_type="range", chunk_interval="7 days"
        )

        sql = db.execute.call_args[0][0]
        assert "by_range('ts2', INTERVAL '7 days')" in sql

    async def test_add_dimension_async_mutual_exclusivity_raises(self, config):
        """Async add_dimension ValueError fires before any await (D-07)."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        with pytest.raises(ValueError, match="number_partitions"):
            await db.timescale.add_dimension(
                "events", "device_id", partition_type="hash"
            )

        db.execute.assert_not_called()

    async def test_add_dimension_async_db_error_reraises_as_timescale_error(
        self, config
    ):
        """Async add_dimension re-raises a DB error as TimescaleError."""
        from psycopg import DatabaseError

        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(
            side_effect=DatabaseError('column "device_id" is already a dimension')
        )

        with pytest.raises(TimescaleError, match="add_dimension failed"):
            await db.timescale.add_dimension(
                "events",
                "device_id",
                partition_type="hash",
                number_partitions=4,
                if_not_exists=False,
            )


# =============================================================================
# add_reorder_policy — mock SQL-shape unit tests (authoritative per D-12)
# =============================================================================


class TestAddReorderPolicyMock:
    """Mock SQL-shape unit tests for add_reorder_policy (sync + async, no live DB).

    These are the AUTHORITATIVE assertions for TS-ADV-09 per D-12 because the
    Apache-licensed local/CI build raises FeatureNotSupported on live calls.
    """

    def test_add_reorder_policy_sql_shape(self, config):
        """add_reorder_policy generates correct SQL with if_not_exists flag."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        db.timescale.add_reorder_policy("events", "idx_events_ts")

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        sql = db.execute.call_args[0][0]
        assert "add_reorder_policy(" in sql
        assert "idx_events_ts" in sql
        assert "if_not_exists => true" in sql
        assert "public.events" in sql

    def test_add_reorder_policy_no_extension_raises(self, config):
        """add_reorder_policy raises ExtensionNotAvailable when extension absent."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=False)
        db._schema = mock_schema
        db.execute = MagicMock()

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            db.timescale.add_reorder_policy("events", "idx_events_ts")

        db.execute.assert_not_called()

    async def test_add_reorder_policy_async_sql_shape(self, config):
        """Async add_reorder_policy awaits guard + execute; correct SQL shape."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[])

        await db.timescale.add_reorder_policy("events", "idx_events_ts")

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        sql = db.execute.call_args[0][0]
        assert "add_reorder_policy(" in sql
        assert "idx_events_ts" in sql
        assert "if_not_exists => true" in sql

    async def test_add_reorder_policy_async_no_extension_raises(self, config):
        """Async add_reorder_policy raises ExtensionNotAvailable when extension absent."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema
        db.execute = AsyncMock()

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.add_reorder_policy("events", "idx_events_ts")

        db.execute.assert_not_called()


# =============================================================================
# add_dimension — live-DB integration tests (Layer 1, gated by ts_db)
# =============================================================================


class TestAddDimensionLive:
    """Live-DB integration tests for add_dimension (TS-ADV-08)."""

    def test_add_dimension_by_hash_succeeds(self, ts_db):
        """add_dimension by_hash registers a hash dimension on a populated hypertable."""
        table = f"_test_addhash_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=2)
            # Add a hash dimension — should succeed on non-empty hypertable (D-08 reshape).
            ts_db.timescale.add_dimension(
                table, "val", partition_type="hash", number_partitions=2
            )
            # Verify the dimension appears in the info view.
            rows = ts_db.execute(
                "SELECT column_name, dimension_type "
                "FROM timescaledb_information.dimensions "
                f"WHERE hypertable_name = '{table}'"
            )
            col_names = [r["column_name"] for r in rows]
            assert "val" in col_names
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    def test_add_dimension_by_range_succeeds(self, ts_db):
        """add_dimension by_range registers a range dimension on a populated hypertable."""
        table = f"_test_addrange_{uuid.uuid4().hex[:8]}"
        try:
            # Create a table with an extra timestamp column to partition by range.
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")
            ts_db.execute(f"""
                CREATE TABLE {table} (
                    ts TIMESTAMPTZ NOT NULL,
                    ts2 TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """)
            ts_db.timescale.create_hypertable(
                table, "ts", chunk_time_interval="1 day", if_not_exists=True
            )
            ts_db.execute(f"INSERT INTO {table} (ts, ts2) VALUES (now(), now())")
            ts_db.timescale.add_dimension(
                table, "ts2", partition_type="range", chunk_interval="7 days"
            )
            rows = ts_db.execute(
                "SELECT column_name "
                "FROM timescaledb_information.dimensions "
                f"WHERE hypertable_name = '{table}'"
            )
            col_names = [r["column_name"] for r in rows]
            assert "ts2" in col_names
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    def test_add_dimension_duplicate_if_not_exists_false_raises_timescale_error(
        self, ts_db
    ):
        """add_dimension with if_not_exists=False raises TimescaleError on duplicate (D-08)."""
        table = f"_test_dupedim_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=2)
            # Add the dimension once.
            ts_db.timescale.add_dimension(
                table,
                "val",
                partition_type="hash",
                number_partitions=2,
                if_not_exists=True,
            )
            # A second call with if_not_exists=False should raise TimescaleError.
            with pytest.raises(TimescaleError):
                ts_db.timescale.add_dimension(
                    table,
                    "val",
                    partition_type="hash",
                    number_partitions=2,
                    if_not_exists=False,
                )
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    def test_add_dimension_mutual_exclusivity_raises(self, ts_db):
        """add_dimension ValueError fires before DB (pure Python, no connection needed)."""
        with pytest.raises(ValueError, match="number_partitions"):
            ts_db.timescale.add_dimension("any_table", "col", partition_type="hash")

    async def test_add_dimension_async_hash_succeeds(self, async_ts_db):
        """Async add_dimension by_hash registers dimension on a populated hypertable."""
        table = f"_test_async_addhash_{uuid.uuid4().hex[:8]}"
        try:
            from pycopg import Database

            sync_db = Database(async_ts_db.config)
            _make_hypertable(sync_db, table, days=2)

            await async_ts_db.timescale.add_dimension(
                table, "val", partition_type="hash", number_partitions=2
            )
            rows = await async_ts_db.execute(
                "SELECT column_name "
                "FROM timescaledb_information.dimensions "
                f"WHERE hypertable_name = '{table}'"
            )
            col_names = [r["column_name"] for r in rows]
            assert "val" in col_names
        finally:
            await async_ts_db.execute(f"DROP TABLE IF EXISTS {table}")


# =============================================================================
# add_reorder_policy — live-DB integration tests (Layer 1, license-tolerant)
# =============================================================================


class TestAddReorderPolicyLive:
    """Live-DB integration tests for add_reorder_policy (TS-ADV-09, D-12).

    The local/CI TSDB runs under the Apache license, so add_reorder_policy
    raises FeatureNotSupported.  The live call is wrapped in try/except to
    tolerate that.  The authoritative SQL assertion lives in TestAddReorderPolicyMock.
    """

    def test_add_reorder_policy_live(self, ts_db):
        """add_reorder_policy live: tolerates FeatureNotSupported on Apache builds (D-12)."""
        table = f"_test_reorder_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=2)
            # Create an index to reorder by.
            index_name = f"idx_{table}_ts"
            ts_db.execute(f"CREATE INDEX {index_name} ON {table} (ts)")

            try:
                ts_db.timescale.add_reorder_policy(table, index_name)
                # On Community builds: verify the job was registered.
                rows = ts_db.execute(
                    "SELECT job_id, proc_name "
                    "FROM timescaledb_information.jobs "
                    "WHERE hypertable_name = %s AND proc_name = 'policy_reorder'",
                    [table],
                )
                assert len(rows) >= 1
            except FeatureNotSupported:
                # Apache license — expected on local/CI.
                pass
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_add_reorder_policy_async_live(self, async_ts_db):
        """Async add_reorder_policy live: tolerates FeatureNotSupported on Apache builds."""
        table = f"_test_async_reorder_{uuid.uuid4().hex[:8]}"
        try:
            from pycopg import Database

            sync_db = Database(async_ts_db.config)
            _make_hypertable(sync_db, table, days=2)
            index_name = f"idx_{table}_ts"
            sync_db.execute(f"CREATE INDEX {index_name} ON {table} (ts)")

            try:
                await async_ts_db.timescale.add_reorder_policy(table, index_name)
                # On Community builds: verify the job was registered.
                rows = await async_ts_db.execute(
                    "SELECT job_id "
                    "FROM timescaledb_information.jobs "
                    "WHERE hypertable_name = %s AND proc_name = 'policy_reorder'",
                    [table],
                )
                assert len(rows) >= 1
            except FeatureNotSupported:
                pass
        finally:
            await async_ts_db.execute(f"DROP TABLE IF EXISTS {table}")
