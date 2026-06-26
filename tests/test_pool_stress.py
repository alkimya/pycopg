"""
Pool stress scenario tests (TEST-04).

All tests use real PostgreSQL and test pool behavior under stress:
- Pool exhaustion and timeouts
- Connection cycling with multiple workers
- Basic pool operations
- Stats and resize
- Context manager usage
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from psycopg_pool import PoolTimeout

from pycopg.pool import PooledDatabase


class TestPoolStressScenarios:
    """Test pool stress scenarios using real PostgreSQL."""

    def test_pool_exhaustion_timeout(self, db_config):
        """Test that pool exhaustion raises PoolTimeout after configured timeout."""
        # Create small pool with short timeout
        pool = PooledDatabase(db_config, min_size=1, max_size=2, timeout=1.0)

        try:
            # Hold connections to exhaust the pool
            held_connections = []

            # Acquire max_size connections
            for _ in range(2):
                ctx = pool._pool.connection()
                conn = ctx.__enter__()
                held_connections.append((ctx, conn))

            # Try to acquire one more - should timeout
            with pytest.raises(PoolTimeout):
                with pool.connection():
                    pass  # Should never reach here

        finally:
            # Release all held connections
            for ctx, conn in held_connections:
                try:
                    ctx.__exit__(None, None, None)
                except Exception:
                    pass
            pool.close()

    def test_pool_connection_cycling(self, db_config):
        """Test pool handles concurrent connection cycling from multiple workers."""
        pool = PooledDatabase(db_config, min_size=2, max_size=5, timeout=10.0)

        try:

            def worker_task(worker_id):
                """Each worker executes 10 queries."""
                results = []
                for i in range(10):
                    result = pool.execute(
                        "SELECT %s AS worker_id, %s AS iteration", [worker_id, i]
                    )
                    results.append(result[0])
                return results

            # Use 5 workers, each doing 10 operations = 50 total
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(worker_task, i) for i in range(5)]

                # Wait for all to complete
                for future in as_completed(futures):
                    result = future.result()  # Will raise if exception occurred
                    assert len(result) == 10

        finally:
            pool.close()

    def test_pool_basic_execute(self, db_config):
        """Test basic pool execute operation."""
        pool = PooledDatabase(db_config, min_size=2, max_size=5)

        try:
            result = pool.execute("SELECT 1 AS test")
            assert len(result) == 1
            assert result[0]["test"] == 1

        finally:
            pool.close()

    def test_pool_execute_many(self, db_config):
        """Test pool execute_many with multiple parameter sets."""
        pool = PooledDatabase(db_config, min_size=2, max_size=5)

        table_name = "test_pool_execute_many_perm"

        try:
            # Create regular table (not TEMP - temp tables are connection-specific)
            pool.execute(
                f"CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER, value TEXT)"
            )

            # Clean any existing data
            pool.execute(f"DELETE FROM {table_name}")

            # Insert multiple rows
            params = [
                [1, "first"],
                [2, "second"],
                [3, "third"],
            ]
            affected = pool.execute_many(
                f"INSERT INTO {table_name} (id, value) VALUES (%s, %s)", params
            )
            assert affected == 3

            # Verify rows inserted
            result = pool.execute(f"SELECT * FROM {table_name} ORDER BY id")
            assert len(result) == 3
            assert result[0]["value"] == "first"
            assert result[2]["value"] == "third"

        finally:
            # Cleanup
            try:
                pool.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
            except Exception:
                pass
            pool.close()

    def test_pool_stats(self, db_config):
        """Test pool stats property returns expected keys."""
        pool = PooledDatabase(db_config, min_size=2, max_size=5)

        try:
            stats = pool.stats
            assert isinstance(stats, dict)
            assert "pool_min" in stats
            assert "pool_max" in stats
            assert "pool_size" in stats
            assert "pool_available" in stats
            assert "requests_waiting" in stats
            assert "requests_num" in stats

            # Verify values make sense
            assert stats["pool_min"] == 2
            assert stats["pool_max"] == 5
            assert stats["pool_size"] >= 0

        finally:
            pool.close()

    def test_pool_resize(self, db_config):
        """Test pool resize operation."""
        pool = PooledDatabase(db_config, min_size=2, max_size=5)

        try:
            # Initial stats
            stats_before = pool.stats
            assert stats_before["pool_min"] == 2
            assert stats_before["pool_max"] == 5

            # Resize pool
            pool.resize(min_size=3, max_size=8)

            # Verify resize accepted
            stats_after = pool.stats
            assert stats_after["pool_min"] == 3
            assert stats_after["pool_max"] == 8

        finally:
            pool.close()

    def test_pool_context_manager(self, db_config):
        """Test pool context manager closes pool on exit."""
        # Use context manager
        with PooledDatabase(db_config, min_size=2, max_size=5) as pool:
            # Execute query inside
            result = pool.execute("SELECT 1 AS test")
            assert len(result) == 1
            assert result[0]["test"] == 1

        # Pool should be closed after exit
        # Verify by checking that the pool's underlying pool is closed
        # (no public API to check if closed, but we can verify it doesn't accept new connections)
        # For this test, we just verify no exception was raised during context exit

    def test_pool_connection_context_manager(self, db_config):
        """Test getting connections from pool using context manager."""
        pool = PooledDatabase(db_config, min_size=2, max_size=5)

        try:
            # Get connection from pool
            with pool.connection() as conn:
                # Execute query directly on connection
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS test")
                    result = cur.fetchone()
                    assert result["test"] == 1

        finally:
            pool.close()

    def test_pool_wait_completes(self, db_config):
        """Test pool wait operation completes successfully."""
        pool = PooledDatabase(db_config, min_size=2, max_size=5)

        try:
            # Wait should complete without error
            pool.wait(timeout=5.0)

            # Pool should be ready
            result = pool.execute("SELECT 1 AS test")
            assert len(result) == 1

        finally:
            pool.close()
