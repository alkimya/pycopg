"""
Session exception scenario tests (TEST-03).

All tests use real PostgreSQL and test edge cases in session management:
- Cleanup after exceptions
- Nested session detection
- Query errors during sessions
- Autocommit mode
- Session state tracking
"""

import pytest

from pycopg import Database


class TestSessionExceptionScenarios:
    """Test session mode exception scenarios using real PostgreSQL."""

    def test_session_cleanup_after_exception(self, db_config):
        """Test that session connection is cleaned up even after exception inside session."""
        db = Database(db_config)

        # Verify we're not in a session initially
        assert not db.in_session
        assert db._session_conn is None

        # Open session and raise exception inside
        with pytest.raises(ValueError):
            with db.session() as session:
                # Verify we're in session
                assert session.in_session
                assert session._session_conn is not None

                # Execute a successful query
                session.execute("SELECT 1")

                # Raise an exception
                raise ValueError("Test exception inside session")

        # After exception, session should be cleaned up
        assert not db.in_session
        assert db._session_conn is None

    def test_nested_sessions_raise_error(self, db_config):
        """Test that attempting nested sessions raises RuntimeError."""
        db = Database(db_config)

        with db.session() as outer_session:
            assert outer_session.in_session

            # Try to open nested session - should raise
            with pytest.raises(RuntimeError) as exc_info:
                with outer_session.session() as inner_session:
                    pass  # Should never reach here

            # Error message should be clear
            assert "Already in session" in str(exc_info.value)

        # After outer session exits, should be able to open new session
        assert not db.in_session

    def test_session_survives_query_error(self, db_config):
        """Test that session context manager cleans up properly after query error."""
        db = Database(db_config)

        # Use session with a query error inside
        with pytest.raises(Exception) as exc_info:
            with db.session() as session:
                # This query will fail (table doesn't exist)
                session.execute("SELECT * FROM nonexistent_table_xyz123")

        # Session should still clean up properly despite the error
        assert not db.in_session
        assert db._session_conn is None

        # Should be able to use database normally after
        result = db.execute("SELECT 1 AS test")
        assert len(result) == 1
        assert result[0]["test"] == 1

    def test_session_in_session_true_inside(self, db_config):
        """Test that in_session property returns True while inside session block."""
        db = Database(db_config)

        # Not in session initially
        assert not db.in_session

        with db.session() as session:
            # in_session should be True inside the block
            assert session.in_session
            assert db.in_session  # Also true on original db instance

            # Execute some work
            session.execute("SELECT 1")

            # Still in session
            assert session.in_session

        # After exit, should be False
        assert not db.in_session

    def test_session_conn_none_after_normal_exit(self, db_config):
        """Test that _session_conn is None after normal session exit."""
        db = Database(db_config)

        assert db._session_conn is None

        with db.session() as session:
            # Connection should exist during session
            assert session._session_conn is not None

            # Execute some work
            session.execute("SELECT 1")
            session.execute("SELECT 2")

        # Connection should be cleaned up after normal exit
        assert db._session_conn is None

    def test_session_autocommit_mode(self, db_config):
        """Test that session with autocommit=True allows DDL without explicit commit."""
        db = Database(db_config)

        table_name = "test_session_autocommit_temp"

        try:
            # Use session with autocommit
            with db.session(autocommit=True) as session:
                # Create table - should persist without explicit commit
                session.execute(f"CREATE TABLE {table_name} (id SERIAL PRIMARY KEY, value TEXT)")

                # Insert data
                session.execute(f"INSERT INTO {table_name} (value) VALUES ('test')")

            # After session exits, verify table and data persist
            result = db.execute(f"SELECT value FROM {table_name}")
            assert len(result) == 1
            assert result[0]["value"] == "test"

        finally:
            # Cleanup
            db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    def test_session_without_autocommit_commits_on_exit(self, db_config):
        """Test that session without autocommit commits on normal exit."""
        db = Database(db_config)

        table_name = "test_session_commit_temp"

        try:
            # First, create the table outside session
            db.execute(f"CREATE TABLE {table_name} (id SERIAL PRIMARY KEY, value TEXT)")

            # Use session without autocommit (default)
            with db.session() as session:
                # Insert data
                session.execute(f"INSERT INTO {table_name} (value) VALUES ('committed')")
                # Don't explicitly commit

            # After session exits, data should be committed
            result = db.execute(f"SELECT value FROM {table_name}")
            assert len(result) == 1
            assert result[0]["value"] == "committed"

        finally:
            # Cleanup
            db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    def test_session_reusable_after_error(self, db_config):
        """Test that database is reusable after session with error."""
        db = Database(db_config)

        # Session with error
        with pytest.raises(Exception):
            with db.session() as session:
                session.execute("SELECT * FROM nonexistent_table_xyz123")

        # Database should be usable after error
        assert not db.in_session
        assert db._session_conn is None

        # Can open new session
        with db.session() as session:
            result = session.execute("SELECT 1 AS test")
            assert len(result) == 1
            assert result[0]["test"] == 1
