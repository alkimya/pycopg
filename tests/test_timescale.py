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
    database.connect()
    yield database
    database.disconnect()


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
# Wave 0 stubs — keyword-matchable placeholders so per-task -k verify commands
# in Plans 02/03 resolve to real (xfail) tests rather than "no tests collected".
#
# Real assertions replace these stub bodies in Plans 02 and 03.
# =============================================================================


class TestShowChunksStub:
    """Wave 0 stubs for show_chunks (TS-ADV-04).  Replaced in Plan 02."""

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — show_chunks implemented in Plan 02", strict=False
    )
    def test_show_chunks_returns_list(self, ts_db):
        """show_chunks returns a list[str] of fully-qualified chunk names."""
        raise NotImplementedError("Plan 02 will implement this test")

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — show_chunks implemented in Plan 02", strict=False
    )
    def test_show_chunks_oldest_first(self, ts_db):
        """show_chunks list is ordered oldest-first by range_start ASC."""
        raise NotImplementedError("Plan 02 will implement this test")

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — show_chunks implemented in Plan 02", strict=False
    )
    async def test_show_chunks_async(self, async_ts_db):
        """async show_chunks returns identical shape to sync."""
        raise NotImplementedError("Plan 02 will implement this test")


class TestDropChunksStub:
    """Wave 0 stubs for drop_chunks (TS-ADV-05).  Replaced in Plan 02."""

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — drop_chunks implemented in Plan 02", strict=False
    )
    def test_drop_chunks_both_none_raises(self, ts_db):
        """drop_chunks raises ValueError when both bounds are None."""
        raise NotImplementedError("Plan 02 will implement this test")

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — drop_chunks implemented in Plan 02", strict=False
    )
    def test_drop_chunks_dry_run(self, ts_db):
        """drop_chunks dry_run=True previews without deleting."""
        raise NotImplementedError("Plan 02 will implement this test")

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — drop_chunks implemented in Plan 02", strict=False
    )
    async def test_drop_chunks_async(self, async_ts_db):
        """async drop_chunks mirrors sync behavior."""
        raise NotImplementedError("Plan 02 will implement this test")


class TestAddDimensionStub:
    """Wave 0 stubs for add_dimension (TS-ADV-08).  Replaced in Plan 03."""

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — add_dimension implemented in Plan 03", strict=False
    )
    def test_add_dimension_by_hash(self, ts_db):
        """add_dimension by_hash form succeeds on TSDB 2.28."""
        raise NotImplementedError("Plan 03 will implement this test")

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — add_dimension implemented in Plan 03", strict=False
    )
    def test_add_dimension_mutual_exclusivity_raises(self, ts_db):
        """add_dimension raises ValueError on hash/range param mismatch."""
        raise NotImplementedError("Plan 03 will implement this test")

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — add_dimension implemented in Plan 03", strict=False
    )
    async def test_add_dimension_async(self, async_ts_db):
        """async add_dimension mirrors sync behavior."""
        raise NotImplementedError("Plan 03 will implement this test")


class TestAddReorderPolicyStub:
    """Wave 0 stubs for add_reorder_policy (TS-ADV-09).  Replaced in Plan 03."""

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — add_reorder_policy implemented in Plan 03",
        strict=False,
    )
    def test_add_reorder_policy_live(self, ts_db):
        """add_reorder_policy (live test tolerates FeatureNotSupported, D-12)."""
        raise NotImplementedError("Plan 03 will implement this test")

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — add_reorder_policy SQL-shape mock in Plan 03",
        strict=False,
    )
    async def test_add_reorder_policy_sql_shape(self, config):
        """Mock SQL-shape unit test for add_reorder_policy (authoritative per D-12)."""
        raise NotImplementedError("Plan 03 will implement this test")

    @pytest.mark.xfail(
        reason="Wave 0 scaffold — add_reorder_policy async mirror in Plan 03",
        strict=False,
    )
    async def test_add_reorder_policy_async(self, async_ts_db):
        """async add_reorder_policy mirrors sync behavior."""
        raise NotImplementedError("Plan 03 will implement this test")
