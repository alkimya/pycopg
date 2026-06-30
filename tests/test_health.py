"""Tests for HEALTH-01: health() on Database, AsyncDatabase, PooledDatabase, AsyncPooledDatabase.

Covers:
- health() returns {connected, latency_ms, server_version} shape on success
- health() NEVER raises — returns connected=False + error on failure
- server_version decoded via _decode_server_version (160001 -> "16.1")
- Pooled classes include pool_stats from self.stats property
- Async mirrors for Database and AsyncPooledDatabase
- One live smoke (PGDATABASE=pycopg_test2)
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.base import _decode_server_version
from pycopg.pool import AsyncPooledDatabase, PooledDatabase

# ---------------------------------------------------------------------------
# Unit — _decode_server_version
# ---------------------------------------------------------------------------


def test_server_version_decode():
    """_decode_server_version converts psycopg int to dotted string."""
    assert _decode_server_version(160001) == "16.1"
    assert _decode_server_version(90605) == "9.6.5"
    assert _decode_server_version(150004) == "15.4"
    assert _decode_server_version(100000) == "10.0"


# ---------------------------------------------------------------------------
# Unit — Database.health() (sync, mocked connection)
# ---------------------------------------------------------------------------


def _make_sync_db(config=None):
    """Return a Database with a fake config (no real connection needed for mocked tests)."""
    from pycopg import Config

    cfg = config or Config(
        host="localhost", port=5432, database="test", user="u", password="p"
    )
    return Database(cfg)


def test_health_connected():
    """health() returns the expected shape on a successful connection."""
    db = _make_sync_db()

    fake_cur = MagicMock()
    fake_cur.__enter__ = MagicMock(return_value=fake_cur)
    fake_cur.__exit__ = MagicMock(return_value=False)
    fake_cur.execute = MagicMock()

    fake_conn = MagicMock()
    fake_conn.__enter__ = MagicMock(return_value=fake_conn)
    fake_conn.__exit__ = MagicMock(return_value=False)
    fake_conn.cursor.return_value = fake_cur
    fake_conn.info.server_version = 160001

    with patch.object(db, "connect", return_value=fake_conn):
        result = db.health()

    assert result["connected"] is True
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0.0
    assert result["server_version"] == "16.1"
    assert "error" not in result


def test_health_never_raises():
    """health() returns connected=False dict and NEVER raises on connection failure."""
    db = _make_sync_db()

    with patch.object(db, "connect", side_effect=Exception("boom")):
        result = db.health()

    assert result["connected"] is False
    assert result["latency_ms"] is None
    assert result["server_version"] is None
    assert "boom" in result["error"]
    # Critically: calling health() must not raise — the test itself proves this
    # (if health() raised, we would never reach the assert below)
    assert "error" in result


# ---------------------------------------------------------------------------
# Unit — AsyncDatabase.health() (async, mocked connection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_health_connected():
    """AsyncDatabase.health() returns the expected shape on a successful connection."""
    from contextlib import asynccontextmanager

    from pycopg import Config

    cfg = Config(host="localhost", port=5432, database="test", user="u", password="p")
    db = AsyncDatabase(cfg)

    fake_cur = AsyncMock()
    fake_cur.execute = AsyncMock()

    fake_conn = MagicMock()
    fake_conn.info.server_version = 150004

    @asynccontextmanager
    async def _fake_cur_cm():
        yield fake_cur

    fake_conn.cursor = MagicMock(side_effect=lambda: _fake_cur_cm())

    @asynccontextmanager
    async def _fake_connect_cm():
        yield fake_conn

    with patch.object(db, "connect", return_value=_fake_connect_cm()):
        result = await db.health()

    assert result["connected"] is True
    assert isinstance(result["latency_ms"], float)
    assert result["server_version"] == "15.4"
    assert "error" not in result


@pytest.mark.asyncio
async def test_async_health_never_raises():
    """AsyncDatabase.health() returns connected=False dict and NEVER raises on failure."""
    from contextlib import asynccontextmanager

    from pycopg import Config

    cfg = Config(host="localhost", port=5432, database="test", user="u", password="p")
    db = AsyncDatabase(cfg)

    @asynccontextmanager
    async def _failing_cm():
        raise Exception("async boom")
        yield  # pragma: no cover

    with patch.object(db, "connect", return_value=_failing_cm()):
        result = await db.health()

    assert result["connected"] is False
    assert result["latency_ms"] is None
    assert result["server_version"] is None
    assert "async boom" in result["error"]


# ---------------------------------------------------------------------------
# Unit — PooledDatabase.health() (sync, mocked pool connection + stats property)
# ---------------------------------------------------------------------------


def _make_pooled_db():
    """Return a PooledDatabase with a mocked underlying pool (no real server)."""
    from pycopg import Config

    cfg = Config(host="localhost", port=5432, database="test", user="u", password="p")
    # Bypass real pool creation by patching ConnectionPool.__init__
    with patch("pycopg.pool.ConnectionPool.__init__", return_value=None):
        db = PooledDatabase.__new__(PooledDatabase)
        db.config = cfg
        db._pool = MagicMock()
    return db


def test_pooled_health_connected():
    """PooledDatabase.health() returns shape including pool_stats on success."""
    db = _make_pooled_db()

    fake_cur = MagicMock()
    fake_cur.__enter__ = MagicMock(return_value=fake_cur)
    fake_cur.__exit__ = MagicMock(return_value=False)
    fake_cur.execute = MagicMock()

    fake_conn = MagicMock()
    fake_conn.__enter__ = MagicMock(return_value=fake_conn)
    fake_conn.__exit__ = MagicMock(return_value=False)
    fake_conn.cursor.return_value = fake_cur
    fake_conn.info.server_version = 160001

    fake_stats = {"pool_min": 2, "pool_max": 10, "pool_size": 2, "pool_available": 2}
    with (
        patch.object(db, "connection", return_value=fake_conn),
        patch.object(
            type(db), "stats", new_callable=PropertyMock, return_value=fake_stats
        ),
    ):
        result = db.health()

    assert result["connected"] is True
    assert result["server_version"] == "16.1"
    assert result["pool_stats"] == fake_stats


def test_pooled_health_stats_is_property_not_call():
    """pool_stats in health() uses self.stats (property access, NOT self.stats())."""
    db = _make_pooled_db()

    fake_cur = MagicMock()
    fake_cur.__enter__ = MagicMock(return_value=fake_cur)
    fake_cur.__exit__ = MagicMock(return_value=False)

    fake_conn = MagicMock()
    fake_conn.__enter__ = MagicMock(return_value=fake_conn)
    fake_conn.__exit__ = MagicMock(return_value=False)
    fake_conn.cursor.return_value = fake_cur
    fake_conn.info.server_version = 160001

    # stats as a PropertyMock — if health() called self.stats() it would fail
    expected_stats = {"pool_size": 3}
    with (
        patch.object(db, "connection", return_value=fake_conn),
        patch.object(
            type(db), "stats", new_callable=PropertyMock, return_value=expected_stats
        ),
    ):
        result = db.health()

    assert result["pool_stats"] is expected_stats


def test_pooled_health_never_raises():
    """PooledDatabase.health() returns connected=False and pool_stats=None on failure."""
    db = _make_pooled_db()

    with patch.object(db, "connection", side_effect=Exception("pool error")):
        result = db.health()

    assert result["connected"] is False
    assert result["pool_stats"] is None
    assert "pool error" in result["error"]


# ---------------------------------------------------------------------------
# Unit — AsyncPooledDatabase.health() (async, mocked pool connection)
# ---------------------------------------------------------------------------


def _make_async_pooled_db():
    """Return an AsyncPooledDatabase with a mocked underlying pool."""
    from pycopg import Config

    cfg = Config(host="localhost", port=5432, database="test", user="u", password="p")
    with patch("pycopg.pool.AsyncConnectionPool.__init__", return_value=None):
        db = AsyncPooledDatabase.__new__(AsyncPooledDatabase)
        db.config = cfg
        db._pool = MagicMock()
    return db


@pytest.mark.asyncio
async def test_async_pooled_health_connected():
    """AsyncPooledDatabase.health() returns shape including pool_stats on success."""
    from contextlib import asynccontextmanager

    db = _make_async_pooled_db()

    fake_cur = AsyncMock()
    fake_cur.execute = AsyncMock()

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    fake_conn.info.server_version = 160001

    @asynccontextmanager
    async def _fake_cur_cm():
        yield fake_cur

    fake_conn.cursor.return_value = _fake_cur_cm()
    # Make cursor() return a new async CM each time it's called
    fake_conn.cursor = MagicMock(side_effect=lambda: _fake_cur_cm())

    @asynccontextmanager
    async def _fake_connection_cm():
        yield fake_conn

    fake_stats = {"pool_min": 2, "pool_max": 10, "pool_size": 2}
    with (
        patch.object(db, "connection", return_value=_fake_connection_cm()),
        patch.object(
            type(db), "stats", new_callable=PropertyMock, return_value=fake_stats
        ),
    ):
        result = await db.health()

    assert result["connected"] is True
    assert result["server_version"] == "16.1"
    assert result["pool_stats"] == fake_stats


@pytest.mark.asyncio
async def test_async_pooled_health_never_raises():
    """AsyncPooledDatabase.health() returns connected=False on failure without raising."""
    from contextlib import asynccontextmanager

    db = _make_async_pooled_db()

    @asynccontextmanager
    async def _failing_cm():
        raise Exception("async pool error")
        yield  # pragma: no cover

    with patch.object(db, "connection", return_value=_failing_cm()):
        result = await db.health()

    assert result["connected"] is False
    assert result["pool_stats"] is None
    assert "async pool error" in result["error"]


# ---------------------------------------------------------------------------
# Live smoke test (PGDATABASE=pycopg_test2)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_health_live_smoke(db_config):
    """Real db.health() returns connected=True and a valid dotted server_version."""
    db = Database(db_config)
    result = db.health()

    assert result["connected"] is True, f"Expected connected=True, got: {result}"
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0.0
    # server_version must match M.m or M.m.p pattern
    assert re.match(
        r"^\d+\.\d+", result["server_version"]
    ), f"server_version {result['server_version']!r} does not match \\d+.\\d+ pattern"
    assert "error" not in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_health_live_smoke(db_config):
    """Real await db.health() returns connected=True and a valid dotted server_version."""
    db = AsyncDatabase(db_config)
    result = await db.health()

    assert result["connected"] is True, f"Expected connected=True, got: {result}"
    assert isinstance(result["latency_ms"], float)
    assert re.match(
        r"^\d+\.\d+", result["server_version"]
    ), f"server_version {result['server_version']!r} does not match \\d+.\\d+ pattern"
    assert "error" not in result
