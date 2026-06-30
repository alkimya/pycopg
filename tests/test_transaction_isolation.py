"""TXN-01: transaction() and session() isolation_level control — unit tests.

These tests use mocking so they do NOT require a live database connection.
All sync and async guard/isolation behaviours are covered.
"""

from __future__ import annotations

from contextlib import contextmanager, asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
import pytest_asyncio
import psycopg
from psycopg import IsolationLevel

from pycopg import AsyncDatabase, Database
from pycopg import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> Config:
    return Config(host="localhost", port=5432, database="testdb", user="u", password="p")


# ---------------------------------------------------------------------------
# Sync — Database
# ---------------------------------------------------------------------------


class TestTransactionIsolationOutsideSession:
    """transaction(isolation_level=X) outside a session sets conn.isolation_level."""

    def test_transaction_isolation_outside_session_sets_level(self):
        """isolation_level is set on the per-call connection before the transaction."""
        db = Database(_make_config())
        assert db._session_conn is None

        fake_conn = MagicMock()
        fake_conn.__enter__ = MagicMock(return_value=fake_conn)
        fake_conn.__exit__ = MagicMock(return_value=False)
        # conn.transaction() must return a context manager
        fake_txn_cm = MagicMock()
        fake_txn_cm.__enter__ = MagicMock(return_value=fake_txn_cm)
        fake_txn_cm.__exit__ = MagicMock(return_value=False)
        fake_conn.transaction.return_value = fake_txn_cm

        @contextmanager
        def fake_connect():
            yield fake_conn

        with patch.object(db, "connect", side_effect=fake_connect):
            with db.transaction(isolation_level=IsolationLevel.SERIALIZABLE):
                pass

        # isolation_level must have been set on the connection
        assert fake_conn.isolation_level == IsolationLevel.SERIALIZABLE
        # transaction() was called with savepoint_name=None (default)
        fake_conn.transaction.assert_called_once_with(savepoint_name=None)


class TestTransactionIsolationInsideSession:
    """transaction(isolation_level=X) inside a session raises RuntimeError."""

    def test_isolation_inside_session_raises(self):
        """Cannot set isolation_level on an already-active session connection."""
        db = Database(_make_config())

        # Manually plant a fake session connection
        fake_session_conn = MagicMock()
        db._session_conn = fake_session_conn

        with pytest.raises(RuntimeError, match="isolation_level"):
            with db.transaction(isolation_level=IsolationLevel.SERIALIZABLE):
                pass  # pragma: no cover

        # Clean up
        db._session_conn = None

    def test_transaction_inside_session_no_isolation_ok(self):
        """transaction() inside a session without isolation_level is fine."""
        db = Database(_make_config())

        fake_session_conn = MagicMock()
        fake_txn_cm = MagicMock()
        fake_txn_cm.__enter__ = MagicMock(return_value=fake_txn_cm)
        fake_txn_cm.__exit__ = MagicMock(return_value=False)
        fake_session_conn.transaction.return_value = fake_txn_cm
        db._session_conn = fake_session_conn

        with db.transaction():
            pass

        # transaction() called without raising
        fake_session_conn.transaction.assert_called_once_with(savepoint_name=None)
        db._session_conn = None


class TestSessionIsolationSetsLevel:
    """session(isolation_level=X) sets the level on the session connection."""

    def test_session_isolation_sets_level(self):
        """isolation_level is set on the session connection right after connect."""
        db = Database(_make_config())

        fake_conn = MagicMock()
        # Session calls commit() then close() in finally
        fake_conn.commit = MagicMock()
        fake_conn.close = MagicMock()

        with patch("psycopg.connect", return_value=fake_conn):
            with db.session(isolation_level=IsolationLevel.REPEATABLE_READ):
                assert fake_conn.isolation_level == IsolationLevel.REPEATABLE_READ

        fake_conn.commit.assert_called_once()
        fake_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# Async — AsyncDatabase
# ---------------------------------------------------------------------------


class TestAsyncTransactionIsolationOutsideSession:
    """async transaction(isolation_level=X) outside a session sets conn.isolation_level."""

    @pytest.mark.asyncio
    async def test_async_transaction_isolation_outside_session_sets_level(self):
        """isolation_level is set on the per-call async connection before the transaction."""
        db = AsyncDatabase(_make_config())
        assert db._session_conn is None

        fake_conn = AsyncMock()
        fake_conn.__aenter__ = AsyncMock(return_value=fake_conn)
        fake_conn.__aexit__ = AsyncMock(return_value=False)
        # conn.transaction() must return a *sync* async-context-manager object
        # (not a coroutine — AsyncMock would make it a coro, which breaks async with)
        fake_txn_cm = MagicMock()
        fake_txn_cm.__aenter__ = AsyncMock(return_value=fake_txn_cm)
        fake_txn_cm.__aexit__ = AsyncMock(return_value=False)
        fake_conn.transaction = MagicMock(return_value=fake_txn_cm)

        @asynccontextmanager
        async def fake_connect():
            yield fake_conn

        with patch.object(db, "connect", side_effect=fake_connect):
            async with db.transaction(isolation_level=IsolationLevel.SERIALIZABLE):
                pass

        assert fake_conn.isolation_level == IsolationLevel.SERIALIZABLE
        fake_conn.transaction.assert_called_once_with(savepoint_name=None)


class TestAsyncTransactionIsolationInsideSession:
    """async transaction(isolation_level=X) inside a session raises RuntimeError."""

    @pytest.mark.asyncio
    async def test_async_isolation_inside_session_raises(self):
        """Cannot set isolation_level on an already-active async session."""
        db = AsyncDatabase(_make_config())

        fake_session_conn = AsyncMock()
        db._session_conn = fake_session_conn

        with pytest.raises(RuntimeError, match="isolation_level"):
            async with db.transaction(isolation_level=IsolationLevel.SERIALIZABLE):
                pass  # pragma: no cover

        db._session_conn = None

    @pytest.mark.asyncio
    async def test_async_transaction_inside_session_no_isolation_ok(self):
        """async transaction() inside a session without isolation_level is fine."""
        db = AsyncDatabase(_make_config())

        fake_session_conn = AsyncMock()
        fake_txn_cm = MagicMock()
        fake_txn_cm.__aenter__ = AsyncMock(return_value=fake_txn_cm)
        fake_txn_cm.__aexit__ = AsyncMock(return_value=False)
        fake_session_conn.transaction = MagicMock(return_value=fake_txn_cm)
        db._session_conn = fake_session_conn

        async with db.transaction():
            pass

        fake_session_conn.transaction.assert_called_once_with(savepoint_name=None)
        db._session_conn = None


class TestAsyncSessionIsolationSetsLevel:
    """async session(isolation_level=X) sets the level on the session connection."""

    @pytest.mark.asyncio
    async def test_async_session_isolation_sets_level(self):
        """isolation_level is set on the async session connection right after connect."""
        db = AsyncDatabase(_make_config())

        fake_conn = AsyncMock()
        fake_conn.commit = AsyncMock()
        fake_conn.close = AsyncMock()

        with patch(
            "psycopg.AsyncConnection.connect",
            new_callable=AsyncMock,
            return_value=fake_conn,
        ):
            async with db.session(isolation_level=IsolationLevel.REPEATABLE_READ):
                assert fake_conn.isolation_level == IsolationLevel.REPEATABLE_READ

        fake_conn.commit.assert_called_once()
        fake_conn.close.assert_called_once()
