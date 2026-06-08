"""
Red->green regression test for B2 residual (SEC-02, T-10-05).

Decision D-06 form: targeted mock — the defect is exit-path control flow on the
close() path, not real DB behaviour.  A real DB is not needed; patching psycopg
connect/AsyncConnection.connect to return a mock whose commit() raises is
sufficient to exercise the exact code paths.

REVERT TEST:
To reproduce the RED (failing) state, revert session() in database.py and
async_database.py so commit() and close() share one try body (the pre-fix shape):

    try:
        if not autocommit:
            self._session_conn.commit()   # if this raises...
        self._session_conn.close()        # ...this line is skipped -> assertion (ii) FAILS
    except Exception:
        raise
    finally:
        self._session_conn = None

With that shape, test_close_called_even_when_commit_raises() and
test_async_close_called_even_when_commit_raises() fail because conn.close()
(or await conn.close()) is never called when commit() raises.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
import pytest

from pycopg import AsyncDatabase, Config, Database


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_config() -> Config:
    """Minimal config — connect_params() must return valid kwarg dict."""
    return Config(
        host="localhost",
        port=5432,
        database="testdb",
        user="testuser",
        password="testpass",
    )


# ---------------------------------------------------------------------------
# Sync: Database.session()
# ---------------------------------------------------------------------------


class TestSyncSessionCloseOnCommitFailure:
    """Sync Database.session() — close() guaranteed even when commit() raises."""

    def _make_conn_mock(self, commit_raises: bool = False) -> MagicMock:
        conn = MagicMock()
        if commit_raises:
            conn.commit.side_effect = psycopg.OperationalError("commit failed — injected")
        return conn

    def test_close_called_even_when_commit_raises(self):
        """
        (i) commit exception propagates; (ii) close() called exactly once; (iii) _session_conn is None.

        D-06: targeted mock — control-flow test, not a real-DB test.
        """
        mock_conn = self._make_conn_mock(commit_raises=True)
        db = Database(_make_config())

        with patch("pycopg.database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.connect.return_value = mock_conn
            mock_psycopg_mod.OperationalError = psycopg.OperationalError

            # (i) commit exception must propagate
            with pytest.raises(psycopg.OperationalError, match="commit failed"):
                with db.session() as _s:
                    pass  # trivial body — error comes from commit() at exit

        # (ii) close() called exactly once despite the failing commit
        mock_conn.close.assert_called_once()

        # (iii) _session_conn reset to None
        assert db._session_conn is None

    def test_close_called_on_body_exception(self):
        """close() and _session_conn reset even when the session body raises."""
        mock_conn = self._make_conn_mock(commit_raises=False)
        db = Database(_make_config())

        with patch("pycopg.database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.connect.return_value = mock_conn

            with pytest.raises(ValueError, match="body error"):
                with db.session() as _s:
                    raise ValueError("body error")

        mock_conn.close.assert_called_once()
        assert db._session_conn is None

    def test_close_called_on_success(self):
        """close() called once on clean exit."""
        mock_conn = self._make_conn_mock(commit_raises=False)
        db = Database(_make_config())

        with patch("pycopg.database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.connect.return_value = mock_conn

            with db.session() as _s:
                pass

        mock_conn.close.assert_called_once()
        mock_conn.commit.assert_called_once()
        assert db._session_conn is None

    def test_autocommit_no_commit_but_close_called(self):
        """autocommit=True: commit NOT called, close() called, _session_conn reset."""
        mock_conn = self._make_conn_mock(commit_raises=False)
        db = Database(_make_config())

        with patch("pycopg.database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.connect.return_value = mock_conn

            with db.session(autocommit=True) as _s:
                pass

        mock_conn.commit.assert_not_called()
        mock_conn.close.assert_called_once()
        assert db._session_conn is None

    def test_session_conn_none_after_commit_failure(self):
        """_session_conn is None even when commit raises (no reference leak)."""
        mock_conn = self._make_conn_mock(commit_raises=True)
        db = Database(_make_config())

        with patch("pycopg.database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.connect.return_value = mock_conn
            mock_psycopg_mod.OperationalError = psycopg.OperationalError

            with pytest.raises(psycopg.OperationalError):
                with db.session():
                    pass

        assert db._session_conn is None


# ---------------------------------------------------------------------------
# Async: AsyncDatabase.session()
# ---------------------------------------------------------------------------


class TestAsyncSessionCloseOnCommitFailure:
    """Async AsyncDatabase.session() — close() guaranteed even when commit() raises."""

    def _make_async_conn_mock(self, commit_raises: bool = False) -> MagicMock:
        conn = MagicMock()
        conn.close = AsyncMock()
        if commit_raises:
            conn.commit = AsyncMock(side_effect=psycopg.OperationalError("async commit failed"))
        else:
            conn.commit = AsyncMock()
        return conn

    @pytest.mark.asyncio
    async def test_async_close_called_even_when_commit_raises(self):
        """
        Async mirror of the sync test:
        (i) commit exception propagates; (ii) close awaited once; (iii) _session_conn is None.
        """
        mock_conn = self._make_async_conn_mock(commit_raises=True)
        db = AsyncDatabase(_make_config())

        connect_mock = AsyncMock(return_value=mock_conn)

        with patch("pycopg.async_database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.AsyncConnection.connect = connect_mock
            mock_psycopg_mod.OperationalError = psycopg.OperationalError

            with pytest.raises(psycopg.OperationalError, match="async commit failed"):
                async with db.session() as _s:
                    pass

        # (ii) close awaited exactly once despite the failing commit
        mock_conn.close.assert_awaited_once()

        # (iii) _session_conn reset to None
        assert db._session_conn is None

    @pytest.mark.asyncio
    async def test_async_close_called_on_body_exception(self):
        """Async: close() and reset even when body raises."""
        mock_conn = self._make_async_conn_mock(commit_raises=False)
        db = AsyncDatabase(_make_config())

        connect_mock = AsyncMock(return_value=mock_conn)

        with patch("pycopg.async_database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.AsyncConnection.connect = connect_mock

            with pytest.raises(ValueError, match="async body error"):
                async with db.session() as _s:
                    raise ValueError("async body error")

        mock_conn.close.assert_awaited_once()
        assert db._session_conn is None

    @pytest.mark.asyncio
    async def test_async_close_called_on_success(self):
        """Async: close() awaited once on clean exit."""
        mock_conn = self._make_async_conn_mock(commit_raises=False)
        db = AsyncDatabase(_make_config())

        connect_mock = AsyncMock(return_value=mock_conn)

        with patch("pycopg.async_database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.AsyncConnection.connect = connect_mock

            async with db.session() as _s:
                pass

        mock_conn.close.assert_awaited_once()
        mock_conn.commit.assert_awaited_once()
        assert db._session_conn is None

    @pytest.mark.asyncio
    async def test_async_autocommit_no_commit_but_close_called(self):
        """Async autocommit=True: commit NOT awaited, close() awaited, _session_conn reset."""
        mock_conn = self._make_async_conn_mock(commit_raises=False)
        db = AsyncDatabase(_make_config())

        connect_mock = AsyncMock(return_value=mock_conn)

        with patch("pycopg.async_database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.AsyncConnection.connect = connect_mock

            async with db.session(autocommit=True) as _s:
                pass

        mock_conn.commit.assert_not_awaited()
        mock_conn.close.assert_awaited_once()
        assert db._session_conn is None

    @pytest.mark.asyncio
    async def test_async_session_conn_none_after_commit_failure(self):
        """Async: _session_conn is None even when commit raises."""
        mock_conn = self._make_async_conn_mock(commit_raises=True)
        db = AsyncDatabase(_make_config())

        connect_mock = AsyncMock(return_value=mock_conn)

        with patch("pycopg.async_database.psycopg") as mock_psycopg_mod:
            mock_psycopg_mod.AsyncConnection.connect = connect_mock
            mock_psycopg_mod.OperationalError = psycopg.OperationalError

            with pytest.raises(psycopg.OperationalError):
                async with db.session():
                    pass

        assert db._session_conn is None
