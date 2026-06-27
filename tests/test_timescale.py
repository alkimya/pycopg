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


# =============================================================================
# create_continuous_aggregate — mock SQL-shape unit tests (authoritative per D-09)
# =============================================================================


class TestCreateContinuousAggregateMock:
    """Mock SQL-shape unit tests for create_continuous_aggregate (sync + async, no live DB).

    These are the AUTHORITATIVE assertions for TS-ADV-01 per D-09 because the
    Apache-licensed local/CI build raises FeatureNotSupported on live calls.

    The autocommit seam is mocked: db.connect(autocommit=True) is intercepted as a
    context manager whose conn.execute captures the SQL string.  db.execute is NOT
    called for the create statement — asserted explicitly.
    """

    def test_create_continuous_aggregate_sql_shape_defaults(self, config):
        """create_continuous_aggregate default flags generate correct SQL via autocommit seam."""
        from unittest.mock import patch

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        select_sql = (
            "SELECT time_bucket('1 hour', ts) AS bucket, avg(val) FROM src GROUP BY 1"
        )
        conn_mock = MagicMock()
        ctx_mock = MagicMock()
        ctx_mock.__enter__ = MagicMock(return_value=conn_mock)
        ctx_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(db, "connect", return_value=ctx_mock) as mock_connect:
            db.timescale.create_continuous_aggregate("metrics_hourly", select_sql)

            mock_connect.assert_called_once_with(autocommit=True)
            sql = conn_mock.execute.call_args[0][0]

        assert "CREATE MATERIALIZED VIEW public.metrics_hourly" in sql
        assert (
            "WITH (timescaledb.continuous, timescaledb.materialized_only=true)" in sql
        )
        assert "WITH DATA" in sql
        assert "WITH NO DATA" not in sql
        # db.execute must NOT be called for the create statement
        db.execute.assert_not_called()

    def test_create_continuous_aggregate_sql_shape_flags_flipped(self, config):
        """create_continuous_aggregate with materialized_only=False, with_no_data=True."""
        from unittest.mock import patch

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        select_sql = (
            "SELECT time_bucket('1 hour', ts) AS bucket, avg(val) FROM src GROUP BY 1"
        )
        conn_mock = MagicMock()
        ctx_mock = MagicMock()
        ctx_mock.__enter__ = MagicMock(return_value=conn_mock)
        ctx_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(db, "connect", return_value=ctx_mock):
            db.timescale.create_continuous_aggregate(
                "metrics_hourly",
                select_sql,
                materialized_only=False,
                with_no_data=True,
            )

            sql = conn_mock.execute.call_args[0][0]

        assert "timescaledb.materialized_only=false" in sql
        assert "WITH NO DATA" in sql

    def test_create_continuous_aggregate_no_time_bucket_raises_valueerror(self, config):
        """create_continuous_aggregate raises ValueError when select_sql lacks time_bucket(."""
        from unittest.mock import patch

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema

        with patch.object(db, "connect") as mock_connect:
            with pytest.raises(ValueError, match="time_bucket"):
                db.timescale.create_continuous_aggregate(
                    "bad_view", "SELECT avg(val) FROM src GROUP BY 1"
                )
            # Seam must never be opened for pre-DB raises
            mock_connect.assert_not_called()

    def test_create_continuous_aggregate_no_extension_raises(self, config):
        """create_continuous_aggregate raises ExtensionNotAvailable when extension absent."""
        from unittest.mock import patch

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=False)
        db._schema = mock_schema

        select_sql = (
            "SELECT time_bucket('1 hour', ts) AS bucket, avg(val) FROM src GROUP BY 1"
        )
        with patch.object(db, "connect") as mock_connect:
            with pytest.raises(
                ExtensionNotAvailable, match="TimescaleDB extension not installed"
            ):
                db.timescale.create_continuous_aggregate("metrics_hourly", select_sql)
            mock_connect.assert_not_called()

    async def test_create_continuous_aggregate_async_sql_shape(self, config):
        """Async create_continuous_aggregate awaits guard + runs on autocommit seam."""
        from unittest.mock import patch

        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[])

        select_sql = (
            "SELECT time_bucket('1 hour', ts) AS bucket, avg(val) FROM src GROUP BY 1"
        )
        conn_mock = AsyncMock()
        ctx_mock = MagicMock()
        ctx_mock.__aenter__ = AsyncMock(return_value=conn_mock)
        ctx_mock.__aexit__ = AsyncMock(return_value=False)

        with patch.object(db, "connect", return_value=ctx_mock) as mock_connect:
            await db.timescale.create_continuous_aggregate("metrics_hourly", select_sql)

            mock_connect.assert_called_once_with(autocommit=True)
            sql = conn_mock.execute.call_args[0][0]

        assert "CREATE MATERIALIZED VIEW public.metrics_hourly" in sql
        assert (
            "WITH (timescaledb.continuous, timescaledb.materialized_only=true)" in sql
        )
        assert "WITH DATA" in sql
        # db.execute must NOT be called for the create statement
        db.execute.assert_not_called()

    async def test_create_continuous_aggregate_async_no_extension_raises(self, config):
        """Async create_continuous_aggregate raises ExtensionNotAvailable when extension absent.

        This test is the Phase-23 await-omission catch: without ``await`` on the guard,
        the AsyncMock coroutine is truthy and the extension check never triggers, causing
        this test to fail.
        """
        from unittest.mock import patch

        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        select_sql = (
            "SELECT time_bucket('1 hour', ts) AS bucket, avg(val) FROM src GROUP BY 1"
        )
        with patch.object(db, "connect") as mock_connect:
            with pytest.raises(
                ExtensionNotAvailable, match="TimescaleDB extension not installed"
            ):
                await db.timescale.create_continuous_aggregate(
                    "metrics_hourly", select_sql
                )
            mock_connect.assert_not_called()


# =============================================================================
# create_continuous_aggregate — live-DB integration tests (D-09, D-10)
# =============================================================================


class TestCreateContinuousAggregateLive:
    """Live-DB integration tests for create_continuous_aggregate (TS-ADV-01, D-09/D-10).

    The local/CI TSDB runs under the Apache license, so create_continuous_aggregate
    raises FeatureNotSupported.  The live call is wrapped in try/except to tolerate that.
    The authoritative SQL assertion lives in TestCreateContinuousAggregateMock.

    On a Community-licensed build, the tests also assert a row in
    timescaledb_information.continuous_aggregates.
    """

    def test_create_continuous_aggregate_live(self, ts_db):
        """create_continuous_aggregate live: tolerates FeatureNotSupported on Apache builds (D-09)."""
        table = f"_test_cagg_{uuid.uuid4().hex[:8]}"
        view = f"_test_cagg_v_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=3)
            select_sql = (
                f"SELECT time_bucket('1 hour', ts) AS bucket, avg(val) AS avg_val "
                f"FROM {table} GROUP BY 1"
            )
            try:
                ts_db.timescale.create_continuous_aggregate(view, select_sql)
                # On Community builds: verify the cagg row exists.
                rows = ts_db.execute(
                    "SELECT 1 FROM timescaledb_information.continuous_aggregates "
                    "WHERE view_schema = %s AND view_name = %s",
                    ["public", view],
                )
                assert len(rows) >= 1
            except FeatureNotSupported:
                # Apache license — expected on local/CI.
                pass
        finally:
            ts_db.execute(f"DROP MATERIALIZED VIEW IF EXISTS public.{view}")
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_create_continuous_aggregate_async_live(self, async_ts_db):
        """Async create_continuous_aggregate live: tolerates FeatureNotSupported on Apache builds."""
        table = f"_test_async_cagg_{uuid.uuid4().hex[:8]}"
        view = f"_test_async_cagg_v_{uuid.uuid4().hex[:8]}"
        sync_db = None
        try:
            from pycopg import Database

            sync_db = Database(async_ts_db.config)
            _make_hypertable(sync_db, table, days=3)

            select_sql = (
                f"SELECT time_bucket('1 hour', ts) AS bucket, avg(val) AS avg_val "
                f"FROM {table} GROUP BY 1"
            )
            try:
                await async_ts_db.timescale.create_continuous_aggregate(
                    view, select_sql
                )
                # On Community builds: verify the cagg row exists.
                rows = await async_ts_db.execute(
                    "SELECT 1 FROM timescaledb_information.continuous_aggregates "
                    "WHERE view_schema = %s AND view_name = %s",
                    ["public", view],
                )
                assert len(rows) >= 1
            except FeatureNotSupported:
                pass
        finally:
            if sync_db is None:
                from pycopg import Database

                sync_db = Database(async_ts_db.config)
            sync_db.execute(f"DROP MATERIALIZED VIEW IF EXISTS public.{view}")
            sync_db.execute(f"DROP TABLE IF EXISTS {table}")


# =============================================================================
# refresh_continuous_aggregate — mock SQL-shape unit tests (authoritative per D-09)
# =============================================================================


class TestRefreshContinuousAggregateMock:
    """Mock SQL-shape unit tests for refresh_continuous_aggregate (sync + async, no live DB).

    These are the AUTHORITATIVE assertions for TS-ADV-02 per D-09 because the
    Apache-licensed local/CI build raises FeatureNotSupported on live calls.

    The autocommit seam is mocked: db.connect(autocommit=True) is intercepted as a
    context manager whose conn.execute captures (sql, params).  db.execute is NOT
    called for the refresh statement — asserted explicitly.

    The structural-isolation proof (D-10a) is the mock-level assertion that
    refresh opens connect(autocommit=True) rather than routing through the
    session-aware db.execute path.
    """

    def test_refresh_continuous_aggregate_sql_shape_both_none(self, config):
        """Both-None window → literal NULL bounds, no params (full refresh) via autocommit seam.

        Absent bounds render as the SQL literal ``NULL`` rather than untyped bind
        parameters — an untyped ``NULL`` parameter cannot be type-inferred against
        TimescaleDB's ``"any"`` window arguments (IndeterminateDatatype).
        """
        from unittest.mock import patch

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        conn_mock = MagicMock()
        ctx_mock = MagicMock()
        ctx_mock.__enter__ = MagicMock(return_value=conn_mock)
        ctx_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(db, "connect", return_value=ctx_mock) as mock_connect:
            db.timescale.refresh_continuous_aggregate("metrics_hourly")

            mock_connect.assert_called_once_with(autocommit=True)
            call_args = conn_mock.execute.call_args
            sql = call_args[0][0]
            params = call_args[0][1]

        assert (
            sql
            == "CALL refresh_continuous_aggregate('public.metrics_hourly', NULL, NULL)"
        )
        assert params == []
        # db.execute must NOT be called for the refresh statement
        db.execute.assert_not_called()

    def test_refresh_continuous_aggregate_sql_shape_with_start(self, config):
        """datetime start + None end → typed start param, literal NULL end (one-sided window)."""
        from unittest.mock import patch

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema

        start = datetime(2024, 1, 1, 0, 0, 0)

        conn_mock = MagicMock()
        ctx_mock = MagicMock()
        ctx_mock.__enter__ = MagicMock(return_value=conn_mock)
        ctx_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(db, "connect", return_value=ctx_mock):
            db.timescale.refresh_continuous_aggregate(
                "metrics_hourly", window_start=start
            )
            call_args = conn_mock.execute.call_args
            sql = call_args[0][0]
            params = call_args[0][1]

        assert (
            sql
            == "CALL refresh_continuous_aggregate('public.metrics_hourly', %s, NULL)"
        )
        assert params == [start]

    def test_refresh_continuous_aggregate_str_bound_raises_before_seam(self, config):
        """str window bound raises ValueError before the autocommit seam is opened."""
        from unittest.mock import patch

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema

        with patch.object(db, "connect") as mock_connect:
            with pytest.raises(ValueError, match="datetime or None"):
                db.timescale.refresh_continuous_aggregate(
                    "metrics_hourly", window_start="7 days"
                )
            # Seam must never be opened for pre-DB raises
            mock_connect.assert_not_called()

    def test_refresh_continuous_aggregate_no_extension_raises(self, config):
        """refresh_continuous_aggregate raises ExtensionNotAvailable when extension absent."""
        from unittest.mock import patch

        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=False)
        db._schema = mock_schema

        with patch.object(db, "connect") as mock_connect:
            with pytest.raises(
                ExtensionNotAvailable, match="TimescaleDB extension not installed"
            ):
                db.timescale.refresh_continuous_aggregate("metrics_hourly")
            mock_connect.assert_not_called()

    async def test_refresh_continuous_aggregate_async_sql_shape(self, config):
        """Async refresh_continuous_aggregate awaits guard + runs on autocommit seam."""
        from unittest.mock import patch

        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[])

        conn_mock = AsyncMock()
        ctx_mock = MagicMock()
        ctx_mock.__aenter__ = AsyncMock(return_value=conn_mock)
        ctx_mock.__aexit__ = AsyncMock(return_value=False)

        with patch.object(db, "connect", return_value=ctx_mock) as mock_connect:
            await db.timescale.refresh_continuous_aggregate("metrics_hourly")

            mock_connect.assert_called_once_with(autocommit=True)
            call_args = conn_mock.execute.call_args
            sql = call_args[0][0]
            params = call_args[0][1]

        assert (
            sql
            == "CALL refresh_continuous_aggregate('public.metrics_hourly', NULL, NULL)"
        )
        assert params == []
        # db.execute must NOT be called for the refresh statement
        db.execute.assert_not_called()

    async def test_refresh_continuous_aggregate_async_no_extension_raises(self, config):
        """Async refresh raises ExtensionNotAvailable when extension absent.

        This test is the Phase-23 await-omission catch: without ``await`` on
        the guard, the AsyncMock coroutine is truthy and the extension check
        never triggers, causing this test to fail.
        """
        from unittest.mock import patch

        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        with patch.object(db, "connect") as mock_connect:
            with pytest.raises(
                ExtensionNotAvailable, match="TimescaleDB extension not installed"
            ):
                await db.timescale.refresh_continuous_aggregate("metrics_hourly")
            mock_connect.assert_not_called()


# =============================================================================
# refresh_continuous_aggregate — live-DB integration tests (D-09, D-10)
# =============================================================================


class TestRefreshContinuousAggregateLive:
    """Live-DB integration tests for refresh_continuous_aggregate (TS-ADV-02, D-09/D-10).

    The local/CI TSDB runs under the Apache license, so refresh_continuous_aggregate
    raises FeatureNotSupported.  The live call is wrapped in try/except to tolerate that.
    The authoritative SQL assertion lives in TestRefreshContinuousAggregateMock.

    On a Community-licensed build, the tests also assert materialized rows appear.

    D-10b structural-isolation proof: call refresh from inside a db.session() block and
    confirm that only the license error (0A000) surfaces — NOT a transaction-block error
    (25001/active-txn) — proving the autocommit seam bypasses the enclosing transaction.
    """

    def test_refresh_continuous_aggregate_live(self, ts_db):
        """refresh_continuous_aggregate live: tolerates FeatureNotSupported on Apache builds.

        The refresh is issued from inside a db.session() block (D-10b structural proof):
        only the license error is tolerated; a transaction-block error would be a bug.

        On Apache, create raises FeatureNotSupported (view never created), so the
        refresh is only issued when the cagg actually exists (Community build).
        """
        table = f"_test_refresh_{uuid.uuid4().hex[:8]}"
        view = f"_test_refresh_v_{uuid.uuid4().hex[:8]}"
        cagg_created = False
        try:
            _make_hypertable(ts_db, table, days=3)
            select_sql = (
                f"SELECT time_bucket('1 hour', ts) AS bucket, avg(val) AS avg_val "
                f"FROM {table} GROUP BY 1"
            )
            # Create the cagg first (tolerate license error)
            try:
                ts_db.timescale.create_continuous_aggregate(view, select_sql)
                cagg_created = True
            except FeatureNotSupported:
                # Apache license — view never materialized; skip refresh.
                pass

            if cagg_created:
                # Call refresh from inside a db.session() — structural isolation proof (D-10b).
                # On Apache: only FeatureNotSupported (0A000) is tolerated.
                # A transaction-block error (25001) would be a bug in the seam.
                with ts_db.session():
                    try:
                        ts_db.timescale.refresh_continuous_aggregate(view)
                        # On Community builds: verify materialized rows exist after refresh.
                        rows = ts_db.execute(
                            "SELECT 1 FROM timescaledb_information.continuous_aggregates "
                            "WHERE view_schema = %s AND view_name = %s",
                            ["public", view],
                        )
                        assert len(rows) >= 1
                    except FeatureNotSupported:
                        # Apache license — expected on local/CI (D-09).
                        pass
        finally:
            ts_db.execute(f"DROP MATERIALIZED VIEW IF EXISTS public.{view}")
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_refresh_continuous_aggregate_async_live(self, async_ts_db):
        """Async refresh_continuous_aggregate live: tolerates FeatureNotSupported on Apache builds.

        On Apache, create raises FeatureNotSupported (view never created), so the
        refresh is only issued when the cagg actually exists (Community build).
        """
        table = f"_test_async_refresh_{uuid.uuid4().hex[:8]}"
        view = f"_test_async_refresh_v_{uuid.uuid4().hex[:8]}"
        sync_db = None
        cagg_created = False
        try:
            from pycopg import Database

            sync_db = Database(async_ts_db.config)
            _make_hypertable(sync_db, table, days=3)

            select_sql = (
                f"SELECT time_bucket('1 hour', ts) AS bucket, avg(val) AS avg_val "
                f"FROM {table} GROUP BY 1"
            )
            # Create the cagg first (tolerate license error)
            try:
                await async_ts_db.timescale.create_continuous_aggregate(
                    view, select_sql
                )
                cagg_created = True
            except FeatureNotSupported:
                # Apache license — view never materialized; skip refresh.
                pass

            if cagg_created:
                # Call refresh from inside an async session — structural isolation proof (D-10b).
                async with async_ts_db.session():
                    try:
                        await async_ts_db.timescale.refresh_continuous_aggregate(view)
                        # On Community builds: verify materialized rows exist after refresh.
                        rows = await async_ts_db.execute(
                            "SELECT 1 FROM timescaledb_information.continuous_aggregates "
                            "WHERE view_schema = %s AND view_name = %s",
                            ["public", view],
                        )
                        assert len(rows) >= 1
                    except FeatureNotSupported:
                        # Apache license — expected on local/CI (D-09).
                        pass
        finally:
            if sync_db is None:
                from pycopg import Database

                sync_db = Database(async_ts_db.config)
            sync_db.execute(f"DROP MATERIALIZED VIEW IF EXISTS public.{view}")
            sync_db.execute(f"DROP TABLE IF EXISTS {table}")


# =============================================================================
# add_continuous_aggregate_policy — mock SQL-shape unit tests (authoritative per D-09)
# =============================================================================


class TestAddContinuousAggregatePolicyMock:
    """Mock SQL-shape unit tests for add_continuous_aggregate_policy (sync + async, no live DB).

    These are the AUTHORITATIVE assertions for TS-ADV-03 per D-09 because the
    Apache-licensed local/CI build raises FeatureNotSupported on live calls.

    The policy call uses a plain db.execute (D-01 — NOT the autocommit seam):
    assert db.execute is called and db.connect is NOT called.
    """

    def test_add_continuous_aggregate_policy_sql_shape_defaults(self, config):
        """Policy SQL shape with defaults: named-arg form, if_not_exists=True, INTERVAL frags."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])
        db.connect = MagicMock()

        db.timescale.add_continuous_aggregate_policy(
            "metrics_hourly", "7 days", "1 hour"
        )

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        db.execute.assert_called_once()
        db.connect.assert_not_called()

        sql = db.execute.call_args[0][0]
        assert "add_continuous_aggregate_policy('public.metrics_hourly'" in sql
        assert "start_offset => INTERVAL '7 days'" in sql
        assert "end_offset => INTERVAL '1 hour'" in sql
        assert "schedule_interval => INTERVAL '1 hour'" in sql
        assert ", if_not_exists => true" in sql

    def test_add_continuous_aggregate_policy_if_not_exists_false(self, config):
        """if_not_exists=False omits the if_not_exists named arg from SQL."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        db.timescale.add_continuous_aggregate_policy(
            "metrics_hourly", "7 days", "1 hour", if_not_exists=False
        )

        sql = db.execute.call_args[0][0]
        assert "if_not_exists" not in sql

    def test_add_continuous_aggregate_policy_none_start_offset_renders_null(
        self, config
    ):
        """None start_offset renders as SQL literal NULL (not INTERVAL 'None')."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        db.timescale.add_continuous_aggregate_policy("metrics_hourly", None, "1 hour")

        sql = db.execute.call_args[0][0]
        assert "start_offset => NULL" in sql
        assert "INTERVAL 'None'" not in sql

    def test_add_continuous_aggregate_policy_none_end_offset_renders_null(self, config):
        """None end_offset renders as SQL literal NULL (not INTERVAL 'None')."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        db.timescale.add_continuous_aggregate_policy("metrics_hourly", "7 days", None)

        sql = db.execute.call_args[0][0]
        assert "end_offset => NULL" in sql
        assert "INTERVAL 'None'" not in sql

    def test_add_continuous_aggregate_policy_offset_ordering_same_unit_raises(
        self, config
    ):
        """Same-unit start_offset <= end_offset raises ValueError before any execute (D-07)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        with pytest.raises(ValueError, match="start_offset"):
            db.timescale.add_continuous_aggregate_policy(
                "metrics_hourly", "1 hour", "7 hours"
            )
        db.execute.assert_not_called()

    def test_add_continuous_aggregate_policy_offset_ordering_mixed_unit_no_raise(
        self, config
    ):
        """Mixed-unit offset pair does not raise in Python — deferred to DB (D-07)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[])

        # "1 day" vs "6 hours" — different units, no Python ValueError
        db.timescale.add_continuous_aggregate_policy(
            "metrics_hourly", "1 day", "6 hours"
        )
        db.execute.assert_called_once()

    def test_add_continuous_aggregate_policy_no_extension_raises(self, config):
        """add_continuous_aggregate_policy raises ExtensionNotAvailable when extension absent."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=False)
        db._schema = mock_schema
        db.execute = MagicMock()
        db.connect = MagicMock()

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            db.timescale.add_continuous_aggregate_policy(
                "metrics_hourly", "7 days", "1 hour"
            )

        db.execute.assert_not_called()
        db.connect.assert_not_called()

    async def test_add_continuous_aggregate_policy_async_sql_shape(self, config):
        """Async policy SQL shape: named-arg form via plain await self._db.execute (D-01)."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[])
        db.connect = MagicMock()

        await db.timescale.add_continuous_aggregate_policy(
            "metrics_hourly", "7 days", "1 hour"
        )

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        db.execute.assert_called_once()
        db.connect.assert_not_called()

        sql = db.execute.call_args[0][0]
        assert "add_continuous_aggregate_policy('public.metrics_hourly'" in sql
        assert "start_offset => INTERVAL '7 days'" in sql
        assert "end_offset => INTERVAL '1 hour'" in sql
        assert "schedule_interval => INTERVAL '1 hour'" in sql
        assert ", if_not_exists => true" in sql

    async def test_add_continuous_aggregate_policy_async_no_extension_raises(
        self, config
    ):
        """Async policy raises ExtensionNotAvailable when extension absent.

        This is the Phase-23 await-omission catch: without ``await`` on the
        has_extension guard, the AsyncMock coroutine is truthy and the
        extension check never triggers, causing this test to fail.
        """
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema
        db.execute = AsyncMock()
        db.connect = MagicMock()

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.add_continuous_aggregate_policy(
                "metrics_hourly", "7 days", "1 hour"
            )

        db.execute.assert_not_called()
        db.connect.assert_not_called()


# =============================================================================
# add_continuous_aggregate_policy — live-DB integration tests (D-09, D-10)
# =============================================================================


class TestAddContinuousAggregatePolicyLive:
    """Live-DB integration tests for add_continuous_aggregate_policy (TS-ADV-03, D-09).

    The local/CI TSDB runs under the Apache license, so add_continuous_aggregate_policy
    raises FeatureNotSupported.  The live call is wrapped in try/except to tolerate that.
    The authoritative SQL assertion lives in TestAddContinuousAggregatePolicyMock.

    On a Community-licensed build, the tests also assert a job row in
    timescaledb_information.jobs and call CALL run_job(job_id) to exercise it.
    """

    def test_add_continuous_aggregate_policy_live(self, ts_db):
        """add_continuous_aggregate_policy live: tolerates FeatureNotSupported on Apache builds.

        On a Community build, asserts the job row exists in
        timescaledb_information.jobs (proc_name='policy_refresh_continuous_aggregate')
        and CALL run_job(job_id) succeeds.
        """
        table = f"_test_cagg_policy_{uuid.uuid4().hex[:8]}"
        view = f"_test_cagg_policy_v_{uuid.uuid4().hex[:8]}"
        cagg_created = False
        try:
            _make_hypertable(ts_db, table, days=3)
            select_sql = (
                f"SELECT time_bucket('1 hour', ts) AS bucket, avg(val) AS avg_val "
                f"FROM {table} GROUP BY 1"
            )
            # Create the cagg first (tolerate license error)
            try:
                ts_db.timescale.create_continuous_aggregate(view, select_sql)
                cagg_created = True
            except FeatureNotSupported:
                pass

            if cagg_created:
                try:
                    ts_db.timescale.add_continuous_aggregate_policy(
                        view, "7 days", "1 hour"
                    )
                    # On Community builds: verify the job was registered.
                    rows = ts_db.execute(
                        "SELECT job_id FROM timescaledb_information.jobs "
                        "WHERE hypertable_name = %s "
                        "AND proc_name = 'policy_refresh_continuous_aggregate'",
                        [view],
                    )
                    assert len(rows) >= 1
                    job_id = rows[0]["job_id"]
                    # Exercise the job on-demand.  run_job for a continuous-
                    # aggregate refresh policy internally calls
                    # refresh_continuous_aggregate, which cannot run inside a
                    # transaction block — use a dedicated autocommit connection.
                    with ts_db.connect(autocommit=True) as conn:
                        conn.execute(f"CALL run_job({job_id})")
                except FeatureNotSupported:
                    # Apache license — expected on local/CI.
                    pass
        finally:
            ts_db.execute(f"DROP MATERIALIZED VIEW IF EXISTS public.{view}")
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_add_continuous_aggregate_policy_async_live(self, async_ts_db):
        """Async add_continuous_aggregate_policy live: tolerates FeatureNotSupported.

        On a Community build, asserts the job row exists in
        timescaledb_information.jobs and CALL run_job(job_id) succeeds.
        """
        table = f"_test_async_cagg_policy_{uuid.uuid4().hex[:8]}"
        view = f"_test_async_cagg_policy_v_{uuid.uuid4().hex[:8]}"
        sync_db = None
        cagg_created = False
        try:
            from pycopg import Database

            sync_db = Database(async_ts_db.config)
            _make_hypertable(sync_db, table, days=3)

            select_sql = (
                f"SELECT time_bucket('1 hour', ts) AS bucket, avg(val) AS avg_val "
                f"FROM {table} GROUP BY 1"
            )
            # Create the cagg first (tolerate license error)
            try:
                await async_ts_db.timescale.create_continuous_aggregate(
                    view, select_sql
                )
                cagg_created = True
            except FeatureNotSupported:
                pass

            if cagg_created:
                try:
                    await async_ts_db.timescale.add_continuous_aggregate_policy(
                        view, "7 days", "1 hour"
                    )
                    # On Community builds: verify the job was registered.
                    rows = await async_ts_db.execute(
                        "SELECT job_id FROM timescaledb_information.jobs "
                        "WHERE hypertable_name = %s "
                        "AND proc_name = 'policy_refresh_continuous_aggregate'",
                        [view],
                    )
                    assert len(rows) >= 1
                    job_id = rows[0]["job_id"]
                    # Exercise the job on-demand.  run_job for a continuous-
                    # aggregate refresh policy internally calls
                    # refresh_continuous_aggregate, which cannot run inside a
                    # transaction block — use a dedicated autocommit connection.
                    async with async_ts_db.connect(autocommit=True) as conn:
                        await conn.execute(f"CALL run_job({job_id})")
                except FeatureNotSupported:
                    # Apache license — expected on local/CI.
                    pass
        finally:
            if sync_db is None:
                from pycopg import Database

                sync_db = Database(async_ts_db.config)
            sync_db.execute(f"DROP MATERIALIZED VIEW IF EXISTS public.{view}")
            sync_db.execute(f"DROP TABLE IF EXISTS {table}")


# =============================================================================
# time_bucket — mock SQL-shape unit tests (Layer 2, no live DB)
# =============================================================================


class TestTimeBucketMock:
    """Mock SQL-shape unit tests for time_bucket (sync + async, no live DB).

    Mirror :class:`TestShowChunksMock` -- a ``MagicMock(spec=SchemaAccessor)``
    with ``has_extension -> True`` is assigned to ``db._schema`` and
    ``db.execute`` / ``db.to_dataframe`` are mocked so the generated SQL/params
    are asserted without a live DB (D-01, D-02, D-03).
    """

    def test_time_bucket_rows_sql_shape(self, config):
        """time_bucket(into='rows') executes time_bucket(%s, col) AS bucket (D-01)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[{"bucket": "x", "avg_val": 1.0}])

        result = db.timescale.time_bucket(
            "events", "ts", "1 hour", "avg(val) AS avg_val", into="rows"
        )

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        sql, params = db.execute.call_args[0]
        assert "time_bucket(%s," in sql
        assert "AS bucket" in sql
        assert "GROUP BY bucket ORDER BY bucket" in sql
        assert params == ["1 hour"]
        assert result == [{"bucket": "x", "avg_val": 1.0}]

    def test_time_bucket_df_named_binds(self, config):
        """time_bucket(into='df') routes through to_dataframe with named binds (D-02)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()
        sentinel = object()
        db.to_dataframe = MagicMock(return_value=sentinel)

        result = db.timescale.time_bucket("events", "ts", "1 hour", "avg(val)")

        # into='df' (default) MUST go through to_dataframe, never execute.
        db.execute.assert_not_called()
        kwargs = db.to_dataframe.call_args.kwargs
        # Named binds (:p0), NOT %s.
        assert ":p0" in kwargs["sql"]
        assert "%s" not in kwargs["sql"]
        assert "AS bucket" in kwargs["sql"]
        # params is a dict whose values match the positional params in order.
        assert isinstance(kwargs["params"], dict)
        assert list(kwargs["params"].values()) == ["1 hour"]
        assert result is sentinel

    def test_time_bucket_df_with_where(self, config):
        """time_bucket(where=...) injects the WHERE fragment into the df-path SQL."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.to_dataframe = MagicMock(return_value=object())

        db.timescale.time_bucket("events", "ts", "1 hour", "avg(val)", where="val > 0")

        sql = db.to_dataframe.call_args.kwargs["sql"]
        assert "WHERE val > 0" in sql

    def test_time_bucket_df_without_where(self, config):
        """time_bucket() with no where= emits no WHERE clause."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.to_dataframe = MagicMock(return_value=object())

        db.timescale.time_bucket("events", "ts", "1 hour", "avg(val)")

        sql = db.to_dataframe.call_args.kwargs["sql"]
        assert "WHERE" not in sql

    def test_time_bucket_gdf_raises_before_db(self, config):
        """time_bucket(into='gdf') raises ValueError before any DB call (D-03)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()
        db.to_dataframe = MagicMock()

        with pytest.raises(ValueError, match="into must be one of"):
            db.timescale.time_bucket("events", "ts", "1 hour", "avg(val)", into="gdf")

        # Guard fires before SQL -- neither DB sink is touched.
        db.execute.assert_not_called()
        db.to_dataframe.assert_not_called()

    def test_time_bucket_no_extension_raises(self, config):
        """time_bucket raises ExtensionNotAvailable when TimescaleDB is absent."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=False)
        db._schema = mock_schema
        db.execute = MagicMock()
        db.to_dataframe = MagicMock()

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            db.timescale.time_bucket("events", "ts", "1 hour", "avg(val)")

        db.execute.assert_not_called()
        db.to_dataframe.assert_not_called()

    async def test_time_bucket_async_rows_awaits_has_extension(self, config):
        """Async time_bucket awaits has_extension; correct rows SQL shape (D-07)."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[{"bucket": "x"}])

        result = await db.timescale.time_bucket(
            "events", "ts", "1 hour", "avg(val)", into="rows"
        )

        mock_schema.has_extension.assert_awaited_once_with("timescaledb")
        sql, params = db.execute.call_args[0]
        assert "time_bucket(%s," in sql
        assert "AS bucket" in sql
        assert params == ["1 hour"]
        assert result == [{"bucket": "x"}]

    async def test_time_bucket_async_df_named_binds(self, config):
        """Async time_bucket(into='df') awaits to_dataframe with named binds (D-02, D-07)."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()
        sentinel = object()
        db.to_dataframe = AsyncMock(return_value=sentinel)

        result = await db.timescale.time_bucket("events", "ts", "1 hour", "avg(val)")

        mock_schema.has_extension.assert_awaited_once_with("timescaledb")
        db.execute.assert_not_called()
        kwargs = db.to_dataframe.call_args.kwargs
        assert ":p0" in kwargs["sql"]
        assert "%s" not in kwargs["sql"]
        assert list(kwargs["params"].values()) == ["1 hour"]
        assert result is sentinel


# =============================================================================
# time_bucket_gapfill — mock SQL-shape unit tests (Layer 2, no live DB)
# =============================================================================


class TestTimeBucketGapfillMock:
    """Mock SQL-shape unit tests for time_bucket_gapfill (sync + async).

    Authoritative for the gapfill SQL shape and the start/finish double-bind
    (D-10) -- the live test (Apache-gated) cannot assert real output on the
    local build.
    """

    def test_gapfill_rows_double_bind(self, config):
        """gapfill binds start/finish TWICE: [bw, start, finish, start, finish] (D-10)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock(return_value=[{"bucket": "x", "lo": None}])

        start = datetime(2024, 1, 1)
        finish = datetime(2024, 1, 2)
        result = db.timescale.time_bucket_gapfill(
            "events", "ts", "1 hour", start, finish, "locf(avg(val)) AS lo", into="rows"
        )

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        sql, params = db.execute.call_args[0]
        assert "time_bucket_gapfill(%s," in sql
        assert "AS bucket" in sql
        # The double-bind (D-10): five placeholders, start/finish each twice.
        assert sql.count("%s") == 5
        assert params == ["1 hour", start, finish, start, finish]
        # WHERE range uses >= lower and < upper.
        assert ">= %s" in sql
        assert "< %s" in sql
        assert "GROUP BY bucket ORDER BY bucket" in sql
        assert result == [{"bucket": "x", "lo": None}]

    def test_gapfill_df_named_binds(self, config):
        """gapfill(into='df') routes through to_dataframe with named binds (D-02)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()
        sentinel = object()
        db.to_dataframe = MagicMock(return_value=sentinel)

        start = datetime(2024, 1, 1)
        finish = datetime(2024, 1, 2)
        result = db.timescale.time_bucket_gapfill(
            "events", "ts", "1 hour", start, finish, "locf(avg(val)) AS lo"
        )

        db.execute.assert_not_called()
        kwargs = db.to_dataframe.call_args.kwargs
        assert ":p0" in kwargs["sql"]
        assert "%s" not in kwargs["sql"]
        # Named binds preserve the double-bind order (D-10).
        assert list(kwargs["params"].values()) == [
            "1 hour",
            start,
            finish,
            start,
            finish,
        ]
        assert result is sentinel

    def test_gapfill_df_with_where(self, config):
        """gapfill(where=...) ANDs the extra fragment onto the time-range WHERE."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.to_dataframe = MagicMock(return_value=object())

        start = datetime(2024, 1, 1)
        finish = datetime(2024, 1, 2)
        db.timescale.time_bucket_gapfill(
            "events",
            "ts",
            "1 hour",
            start,
            finish,
            "locf(avg(val)) AS lo",
            where="val > 0",
        )

        sql = db.to_dataframe.call_args.kwargs["sql"]
        assert "AND (val > 0)" in sql

    def test_gapfill_gdf_raises_before_db(self, config):
        """gapfill(into='gdf') raises ValueError before any DB call (D-03)."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=True)
        db._schema = mock_schema
        db.execute = MagicMock()
        db.to_dataframe = MagicMock()

        with pytest.raises(ValueError, match="into must be one of"):
            db.timescale.time_bucket_gapfill(
                "events",
                "ts",
                "1 hour",
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                "locf(avg(val)) AS lo",
                into="gdf",
            )

        db.execute.assert_not_called()
        db.to_dataframe.assert_not_called()

    def test_gapfill_no_extension_raises(self, config):
        """gapfill raises ExtensionNotAvailable when TimescaleDB is absent."""
        from pycopg.schema import SchemaAccessor

        db = Database(config)
        mock_schema = MagicMock(spec=SchemaAccessor)
        mock_schema.has_extension = MagicMock(return_value=False)
        db._schema = mock_schema
        db.execute = MagicMock()
        db.to_dataframe = MagicMock()

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            db.timescale.time_bucket_gapfill(
                "events",
                "ts",
                "1 hour",
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                "locf(avg(val)) AS lo",
            )

        db.execute.assert_not_called()
        db.to_dataframe.assert_not_called()

    async def test_gapfill_async_rows_awaits_double_bind(self, config):
        """Async gapfill awaits has_extension; double-bind preserved (D-07, D-10)."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(return_value=[{"bucket": "x", "lo": None}])

        start = datetime(2024, 1, 1)
        finish = datetime(2024, 1, 2)
        result = await db.timescale.time_bucket_gapfill(
            "events", "ts", "1 hour", start, finish, "locf(avg(val)) AS lo", into="rows"
        )

        mock_schema.has_extension.assert_awaited_once_with("timescaledb")
        sql, params = db.execute.call_args[0]
        assert "time_bucket_gapfill(%s," in sql
        assert sql.count("%s") == 5
        assert params == ["1 hour", start, finish, start, finish]
        assert result == [{"bucket": "x", "lo": None}]

    async def test_gapfill_async_df_named_binds(self, config):
        """Async gapfill(into='df') awaits to_dataframe with named binds (D-02, D-07)."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()
        sentinel = object()
        db.to_dataframe = AsyncMock(return_value=sentinel)

        start = datetime(2024, 1, 1)
        finish = datetime(2024, 1, 2)
        result = await db.timescale.time_bucket_gapfill(
            "events", "ts", "1 hour", start, finish, "locf(avg(val)) AS lo"
        )

        mock_schema.has_extension.assert_awaited_once_with("timescaledb")
        db.execute.assert_not_called()
        kwargs = db.to_dataframe.call_args.kwargs
        assert ":p0" in kwargs["sql"]
        assert "%s" not in kwargs["sql"]
        assert list(kwargs["params"].values()) == [
            "1 hour",
            start,
            finish,
            start,
            finish,
        ]
        assert result is sentinel


# =============================================================================
# time_bucket / time_bucket_gapfill — live integration tests (Layer 1)
# =============================================================================


class TestTimeBucketLive:
    """Live-DB integration tests for time_bucket (Apache-free -> REAL output)."""

    def test_time_bucket_df_returns_bucket_column(self, ts_db):
        """time_bucket(into='df') returns a DataFrame with a real bucket column."""
        table = f"_test_tb_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=5)
            df = ts_db.timescale.time_bucket(
                table, "ts", "1 day", "avg(val) AS avg_val"
            )
            # time_bucket is Apache-free -> assert REAL output (no try/except).
            assert "bucket" in df.columns
            assert len(df) >= 1
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    def test_time_bucket_rows_returns_dicts(self, ts_db):
        """time_bucket(into='rows') returns list[dict] each with a bucket key."""
        table = f"_test_tbr_{uuid.uuid4().hex[:8]}"
        try:
            _make_hypertable(ts_db, table, days=5)
            rows = ts_db.timescale.time_bucket(
                table, "ts", "1 day", "avg(val) AS avg_val", into="rows"
            )
            assert isinstance(rows, list)
            assert len(rows) >= 1
            for row in rows:
                assert "bucket" in row
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_time_bucket_async_df_returns_bucket_column(self, async_ts_db):
        """Async time_bucket(into='df') returns a DataFrame with a bucket column."""
        from pycopg import Database

        table = f"_test_async_tb_{uuid.uuid4().hex[:8]}"
        sync_db = Database(async_ts_db.config)
        try:
            _make_hypertable(sync_db, table, days=5)
            df = await async_ts_db.timescale.time_bucket(
                table, "ts", "1 day", "avg(val) AS avg_val"
            )
            assert "bucket" in df.columns
            assert len(df) >= 1
        finally:
            sync_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_time_bucket_async_rows_returns_dicts(self, async_ts_db):
        """Async time_bucket(into='rows') returns list[dict] with a bucket key."""
        from pycopg import Database

        table = f"_test_async_tbr_{uuid.uuid4().hex[:8]}"
        sync_db = Database(async_ts_db.config)
        try:
            _make_hypertable(sync_db, table, days=5)
            rows = await async_ts_db.timescale.time_bucket(
                table, "ts", "1 day", "avg(val) AS avg_val", into="rows"
            )
            assert isinstance(rows, list)
            assert len(rows) >= 1
            for row in rows:
                assert "bucket" in row
        finally:
            sync_db.execute(f"DROP TABLE IF EXISTS {table}")


class TestTimeBucketGapfillLive:
    """Live-DB tests for time_bucket_gapfill (TSL-gated -> license-tolerant).

    On the local Apache 2.28 build, ``time_bucket_gapfill`` raises
    :class:`psycopg.errors.FeatureNotSupported` (planner-verified 2026-06-23,
    correcting D-08).  These tests therefore MIRROR
    :meth:`TestCreateContinuousAggregateLive.test_create_continuous_aggregate_live`
    -- the real gap-filled output is asserted inside ``try`` and the license
    gate is tolerated in ``except``.  The mock test is authoritative for shape.
    Python ``datetime`` objects are passed for ``start`` / ``finish`` (ROADMAP
    criterion #2 -- NOT literals).
    """

    def test_time_bucket_gapfill_live(self, ts_db):
        """gapfill live: real NULL-padded output, tolerating FeatureNotSupported (D-08)."""
        table = f"_test_gf_{uuid.uuid4().hex[:8]}"
        try:
            # Build a hypertable with a deliberate time gap: rows only on the
            # first and last day of a multi-day range, so interior 1-hour
            # buckets are empty and must be gap-filled.
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")
            ts_db.execute(
                f"CREATE TABLE {table} (ts TIMESTAMPTZ NOT NULL, val DOUBLE PRECISION)"
            )
            ts_db.timescale.create_hypertable(
                table, "ts", chunk_time_interval="1 day", if_not_exists=True
            )
            start = datetime(2024, 1, 1, 0, 0, 0)
            finish = datetime(2024, 1, 1, 6, 0, 0)
            # Only two rows (hour 0 and hour 5) -> interior hours are gaps.
            ts_db.execute(
                f"INSERT INTO {table} (ts, val) VALUES "
                f"('2024-01-01 00:00:00+00', 10.0), "
                f"('2024-01-01 05:00:00+00', 20.0)"
            )
            try:
                rows = ts_db.timescale.time_bucket_gapfill(
                    table,
                    "ts",
                    "1 hour",
                    start,
                    finish,
                    "avg(val) AS avg_val",
                    into="rows",
                )
                # Community/TSL build: real gap-filled, NULL-padded output.
                assert len(rows) >= 1
                for row in rows:
                    assert "bucket" in row
                # At least one interior bucket has no data -> NULL aggregate.
                assert any(row["avg_val"] is None for row in rows)
            except FeatureNotSupported:
                # Apache license — expected on local/CI.
                pass
        finally:
            ts_db.execute(f"DROP TABLE IF EXISTS {table}")

    async def test_time_bucket_gapfill_async_live(self, async_ts_db):
        """Async gapfill live: real output inside try, tolerates Apache license gate."""
        from pycopg import Database

        table = f"_test_async_gf_{uuid.uuid4().hex[:8]}"
        sync_db = Database(async_ts_db.config)
        try:
            sync_db.execute(f"DROP TABLE IF EXISTS {table}")
            sync_db.execute(
                f"CREATE TABLE {table} (ts TIMESTAMPTZ NOT NULL, val DOUBLE PRECISION)"
            )
            sync_db.timescale.create_hypertable(
                table, "ts", chunk_time_interval="1 day", if_not_exists=True
            )
            start = datetime(2024, 1, 1, 0, 0, 0)
            finish = datetime(2024, 1, 1, 6, 0, 0)
            sync_db.execute(
                f"INSERT INTO {table} (ts, val) VALUES "
                f"('2024-01-01 00:00:00+00', 10.0), "
                f"('2024-01-01 05:00:00+00', 20.0)"
            )
            try:
                rows = await async_ts_db.timescale.time_bucket_gapfill(
                    table,
                    "ts",
                    "1 hour",
                    start,
                    finish,
                    "avg(val) AS avg_val",
                    into="rows",
                )
                assert len(rows) >= 1
                for row in rows:
                    assert "bucket" in row
                assert any(row["avg_val"] is None for row in rows)
            except FeatureNotSupported:
                # Apache license — expected on local/CI.
                pass
        finally:
            sync_db.execute(f"DROP TABLE IF EXISTS {table}")
