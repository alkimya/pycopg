"""Tests for ETLAccessor — unit (param order / status string) + DB integration (SC-1..SC-4)."""

import traceback
import uuid
from datetime import datetime

import pytest

from pycopg import Database, queries
from pycopg.etl import ETLAccessor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(db_config):
    """Create a Database instance connected to pycopg_test."""
    database = Database(db_config)
    yield database


@pytest.fixture
def cleanup_pipeline_runs(db):
    """Drop pipeline_runs after each integration test so tests are isolated."""
    yield
    try:
        db.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE", autocommit=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helper fake Database for unit tests
# ---------------------------------------------------------------------------


class _FakeDatabase:
    """Minimal fake Database that records execute() calls."""

    def __init__(self):
        self.calls = []  # list of (sql, params, autocommit)

    def execute(self, sql, params=None, autocommit=False):
        """Record the call and return a fixed RETURNING payload."""
        self.calls.append((sql, params, autocommit))
        return [{"run_id": 42}]


# ---------------------------------------------------------------------------
# Unit tests (no DB)
# ---------------------------------------------------------------------------


class TestETLAccessorUnit:
    """DB-free tests: param packing, status literals, constructor shape."""

    def test_start_run_param_order_and_returns_run_id(self):
        """_start_run packs [name, 'running', <datetime>] and returns run_id."""
        fake = _FakeDatabase()
        acc = ETLAccessor(fake)
        result = acc._start_run("my_pipeline")

        assert result == 42
        assert len(fake.calls) == 1
        sql, params, autocommit = fake.calls[0]
        assert sql == queries.ETL_INSERT_RUN
        assert params[0] == "my_pipeline"
        assert params[1] == "running"
        assert isinstance(params[2], datetime)
        assert params[2].tzinfo is not None  # timezone-aware
        assert autocommit is True

    def test_end_run_param_order(self):
        """_end_run packs [status, <datetime>, rows_extracted, rows_loaded, msg, tb, run_id]."""
        fake = _FakeDatabase()
        acc = ETLAccessor(fake)
        acc._end_run(
            42,
            "failed",
            3,
            0,
            error_message="boom",
            error_traceback="tb",
        )

        assert len(fake.calls) == 1
        sql, params, autocommit = fake.calls[0]
        assert sql == queries.ETL_UPDATE_RUN
        assert params[0] == "failed"
        assert isinstance(params[1], datetime)
        assert params[1].tzinfo is not None
        assert params[2] == 3
        assert params[3] == 0
        assert params[4] == "boom"
        assert params[5] == "tb"
        assert params[6] == 42
        assert autocommit is True

    def test_status_literal_is_failed_not_error(self):
        """No call to execute ever passes 'error' as a status string."""
        fake = _FakeDatabase()
        acc = ETLAccessor(fake)
        acc._start_run("p")
        acc._end_run(42, "failed", 0, 0, error_message="x", error_traceback="y")

        for sql, params, autocommit in fake.calls:
            if params:
                for value in params:
                    assert (
                        value != "error"
                    ), "Literal 'error' status passed to execute — must be 'failed' (D-07)"

    def test_constructor_has_no_postgis_guard(self):
        """ETLAccessor(fake) constructs without any has_extension call."""
        fake = _FakeDatabase()
        # Ensure the fake does not have has_extension — construction must not call it
        assert not hasattr(fake, "has_extension")
        acc = ETLAccessor(fake)
        assert acc._db is fake

    def test_end_run_none_defaults(self):
        """_end_run default error_message and error_traceback are None."""
        fake = _FakeDatabase()
        acc = ETLAccessor(fake)
        acc._end_run(1, "success", 5, 5)

        _, params, _ = fake.calls[0]
        assert params[4] is None  # error_message
        assert params[5] is None  # error_traceback

    def test_init_calls_etl_init_constant(self):
        """init() executes ETL_INIT_PIPELINE_RUNS with autocommit=True."""
        fake = _FakeDatabase()
        acc = ETLAccessor(fake)
        acc.init()

        assert len(fake.calls) == 1
        sql, params, autocommit = fake.calls[0]
        assert sql == queries.ETL_INIT_PIPELINE_RUNS
        assert autocommit is True


# ---------------------------------------------------------------------------
# DB integration tests (pycopg_test)
# ---------------------------------------------------------------------------


class TestETLAccessorIntegration:
    """Live-DB tests against pycopg_test proving SC-1..SC-4."""

    def test_init_idempotent(self, db, cleanup_pipeline_runs):
        """SC-2: calling init() twice raises no error and creates exactly one table."""
        db.etl.init()
        db.etl.init()  # must not raise

        rows = db.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_name = 'pipeline_runs'
              AND table_schema = current_schema()
            """)
        assert rows[0]["cnt"] == 1

    def test_first_run_auto_creates(self, db, cleanup_pipeline_runs):
        """SC-3: run() auto-creates pipeline_runs even without an explicit init()."""
        # Ensure table is absent
        db.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE", autocommit=True)

        db.etl.run("auto")

        rows = db.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_name = 'pipeline_runs'
              AND table_schema = current_schema()
            """)
        assert rows[0]["cnt"] == 1

    def test_run_writes_full_row(self, db, cleanup_pipeline_runs):
        """SC-1: run() writes a complete pipeline_runs row including NULL watermark."""
        run_id = db.etl.run("demo")

        rows = db.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = %s",
            [run_id],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["pipeline_name"] == "demo"
        assert row["status"] in ("running", "success", "failed")
        assert row["started_at"] is not None
        assert row["finished_at"] is not None
        assert row["rows_extracted"] is not None
        assert row["rows_loaded"] is not None
        assert row["watermark"] is None

    def test_failed_run_commits_despite_load_rollback(self, db, cleanup_pipeline_runs):
        """SC-4: failed run row commits on dedicated autocommit conn even when load txn rolled back.

        Proves the separate-connection invariant: (a) the pipeline_runs row
        with status='failed' is committed, AND (b) the load mutation (scratch
        table sentinel row) was rolled back — coexistence proves D-04/D-05.
        """
        db.etl.init()

        # Create a scratch target table with one known baseline row
        scratch = f"etl_scratch_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE "{scratch}" (val INTEGER)',
            autocommit=True,
        )
        db.execute(f'INSERT INTO "{scratch}" VALUES (1)', autocommit=True)

        run_id = db.etl._start_run("rollback_case")

        try:
            with db.transaction() as conn:
                # Mutate the scratch table inside the load transaction
                # Use the yielded connection directly so the INSERT is part of the txn
                with conn.cursor() as cur:
                    cur.execute(f'INSERT INTO "{scratch}" VALUES (999)')
                # Force the transaction to roll back
                raise RuntimeError("forced load failure")
        except RuntimeError:
            db.etl._end_run(
                run_id,
                "failed",
                0,
                0,
                error_message="forced load failure",
                error_traceback=traceback.format_exc(),
            )

        # (a) pipeline_runs row must be committed with status='failed'
        run_rows = db.execute(
            "SELECT status, error_message, error_traceback FROM pipeline_runs WHERE run_id = %s",
            [run_id],
        )
        assert len(run_rows) == 1, "pipeline_runs row must exist after failed run"
        assert run_rows[0]["status"] == "failed"
        assert run_rows[0]["error_message"] is not None
        assert run_rows[0]["error_traceback"] is not None

        # (b) load mutation (sentinel 999) must have been rolled back
        scratch_rows = db.execute(f'SELECT val FROM "{scratch}" ORDER BY val')
        vals = [r["val"] for r in scratch_rows]
        assert 999 not in vals, "sentinel row from rolled-back load txn must be absent"
        assert 1 in vals, "baseline row must still be present"

        # Cleanup scratch table
        db.execute(f'DROP TABLE IF EXISTS "{scratch}" CASCADE', autocommit=True)
