"""Regression test for B1 (SEC-01, decision D-03): PooledDatabase.execute commit ordering.

BUG DESCRIPTION
---------------
Pre-fix code in pycopg/pool.py PooledDatabase.execute():

    if cur.description:
        return cur.fetchall()   # <-- returns WITHOUT committing!
    conn.commit()

This means INSERT ... RETURNING returns rows but the transaction is rolled back
when the connection is returned to the pool (since psycopg2/psycopg3 roll back
uncommitted transactions on connection return). The caller sees a non-empty
result list but the row was never persisted.

TO RE-INTRODUCE THE BUG (red): in pycopg/pool.py PooledDatabase.execute(),
change the fixed code:
    rows = cur.fetchall() if cur.description else []
    conn.commit()
    return rows
back to:
    if cur.description:
        return cur.fetchall()
    conn.commit()
    return []

D-06 form choice: real-DB integration test against CI timescale/timescaledb-ha service.
Rationale: the bug only manifests across pool checkouts. A mock-based test cannot
reproduce it because the mock does not enforce transaction semantics.
"""

import uuid

import pytest

from pycopg.pool import PooledDatabase


@pytest.fixture
def pool_db(db_config):
    """Create a PooledDatabase with min=1/max=2 so connections can be reused."""
    db = PooledDatabase(db_config, min_size=1, max_size=2)
    yield db
    db.close()


@pytest.fixture
def unique_table(pool_db):
    """Create a uniquely-named test table; drop it after the test."""
    table_name = f"test_pool_commit_{uuid.uuid4().hex[:8]}"
    pool_db.execute(
        f"CREATE TABLE {table_name} (id SERIAL PRIMARY KEY, val TEXT NOT NULL)"
    )
    yield table_name
    pool_db.execute(f"DROP TABLE IF EXISTS {table_name}")


class TestPooledDatabaseCommit:
    """Prove that INSERT ... RETURNING persists after the pool connection is returned."""

    def test_insert_returning_persists_after_pool_return(self, pool_db, unique_table):
        """Core B1 regression: INSERT ... RETURNING row must survive pool return.

        Three distinct pool checkouts:
        1. CREATE TABLE (via fixture)
        2. INSERT ... RETURNING id  -> capture returned id
        3. SELECT val WHERE id=?    -> row must be present (proves commit happened)

        If the bug is present: checkout #2 returns the row but rolls back on return
        to pool. Checkout #3 finds no row and the SELECT returns empty, failing the
        assertion. After the fix: commit precedes pool return, so the row persists.
        """
        # Checkout #2: INSERT ... RETURNING
        rows = pool_db.execute(
            f"INSERT INTO {unique_table} (val) VALUES (%s) RETURNING id",
            ["hello_pool_commit"],
        )
        assert len(rows) == 1, "INSERT ... RETURNING must return exactly one row"
        inserted_id = rows[0]["id"]
        assert inserted_id is not None

        # Checkout #3: verify row is present on a SEPARATE pool checkout
        # (this is the critical assertion: if the INSERT was rolled back on pool
        # return, this SELECT will return [] and the assert below will fail)
        result = pool_db.execute(
            f"SELECT val FROM {unique_table} WHERE id = %s",
            [inserted_id],
        )
        assert len(result) == 1, (
            f"Row id={inserted_id} is not present after pool checkout return. "
            "This means the INSERT was rolled back when the connection was returned "
            "to the pool (B1 bug). Fix: pool.py PooledDatabase.execute must call "
            "conn.commit() BEFORE returning rows."
        )
        assert result[0]["val"] == "hello_pool_commit"

    def test_insert_without_returning_still_commits(self, pool_db, unique_table):
        """Plain INSERT (no RETURNING) must also commit correctly.

        This is the non-RETURNING path which was already correct pre-fix;
        this test guards against regressions introduced when refactoring.
        """
        pool_db.execute(
            f"INSERT INTO {unique_table} (val) VALUES (%s)",
            ["no_returning"],
        )

        result = pool_db.execute(
            f"SELECT val FROM {unique_table} WHERE val = %s",
            ["no_returning"],
        )
        assert len(result) == 1
        assert result[0]["val"] == "no_returning"

    def test_multiple_returning_rows_all_persist(self, pool_db, unique_table):
        """Verify multi-row INSERT ... RETURNING persists all rows."""
        rows = pool_db.execute(
            f"INSERT INTO {unique_table} (val) "
            f"SELECT 'row_' || g FROM generate_series(1, 5) g "
            f"RETURNING id, val",
        )
        assert len(rows) == 5, "INSERT ... RETURNING should return 5 rows"

        # Separate checkout: count persisted rows
        count_result = pool_db.execute(f"SELECT COUNT(*) AS cnt FROM {unique_table}")
        assert (
            count_result[0]["cnt"] == 5
        ), "All 5 inserted rows must persist after pool connection return."
