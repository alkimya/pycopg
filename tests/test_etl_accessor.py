"""Tests for ETLAccessor — unit (param order / status string) + DB integration (SC-1..SC-4)."""

import traceback
import uuid
from datetime import datetime

import pandas as pd
import pytest
from psycopg.rows import dict_row

from pycopg import AsyncDatabase, Database, queries
from pycopg.etl import ETLAccessor, Pipeline, RunResult
from pycopg.exceptions import ETLError, ETLTargetNotFoundError, ETLTransformError

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
    """Minimal fake Database that records connect()+cursor.execute() calls."""

    def __init__(self):
        self.calls = []  # list of (sql, params, autocommit)

    def connect(self, autocommit=False):
        """Return a context manager yielding a fake connection."""
        calls = self.calls
        autocommit_flag = autocommit

        class _FakeCursor:
            def __init__(self):
                self._sql = None
                self._params = None

            def execute(self, sql, params=None):
                calls.append((sql, params, autocommit_flag))
                self._sql = sql
                self._params = params

            def fetchone(self):
                return {"run_id": 42}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        class _FakeConn:
            def cursor(self, row_factory=None):
                return _FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        class _FakeConnCtx:
            def __enter__(self_inner):  # noqa: N805
                return _FakeConn()

            def __exit__(self_inner, *args):  # noqa: N805
                pass

        return _FakeConnCtx()


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
        tbl = f"etl_autocreate_{uuid.uuid4().hex[:8]}"
        p = Pipeline(
            name="auto",
            source="SELECT 1 AS id",
            target=tbl,
            load_mode="replace",
        )
        try:
            db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        rows = db.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_name = 'pipeline_runs'
              AND table_schema = current_schema()
            """)
        assert rows[0]["cnt"] == 1

    def test_run_writes_full_row(self, db, cleanup_pipeline_runs):
        """SC-1: run() writes a complete pipeline_runs row including NULL watermark."""
        tbl = f"etl_fullrow_{uuid.uuid4().hex[:8]}"
        p = Pipeline(
            name="demo",
            source="SELECT 1 AS id",
            target=tbl,
            load_mode="replace",
        )
        try:
            result = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        rows = db.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
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
        # end of test_failed_run_commits_despite_load_rollback

    def test_failed_run_commits_inside_session(self, db, cleanup_pipeline_runs):
        """SC-4 session path: run-log writes commit immediately on own connection (D-04/D-05).

        Proves structural isolation under a db.session(): _start_run and
        _end_run commit their rows on a dedicated autocommit connection that is
        INDEPENDENT of the session connection.  A fresh out-of-session read
        confirms each row is durably committed BEFORE the session closes.

        Gap-catching property: with pre-fix etl.py, _start_run/_end_run write
        on the session connection via cursor(autocommit=True).  Those rows are
        PENDING until the session commits — and are lost if the session
        connection is rolled back.  After Task 1's fix, the rows are committed
        on their own connections immediately and survive a session rollback,
        proving ETL-08/ETL-09 holds for the session-active path.
        """
        db.etl.init()

        # Create a scratch target table with one known baseline row
        scratch = f"etl_scratch_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE "{scratch}" (val INTEGER)',
            autocommit=True,
        )
        db.execute(f'INSERT INTO "{scratch}" VALUES (1)', autocommit=True)

        run_id = None
        with db.session():
            # _start_run opens its OWN autocommit connection (post-fix) —
            # NOT the session conn (D-04); the INSERT must be committed
            # IMMEDIATELY, visible from outside before the session closes.
            run_id = db.etl._start_run("session_rollback_case")

            # Read the run-log row via a FRESH out-of-band connection to confirm
            # it is ALREADY committed — not pending in the session transaction.
            # Pre-fix: the row is pending on _session_conn and NOT visible here.
            # Post-fix: the row committed on its own conn and IS visible here.
            with db.connect(autocommit=True) as fresh_conn:
                with fresh_conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        "SELECT status FROM pipeline_runs WHERE run_id = %s",
                        [run_id],
                    )
                    early_rows = cur.fetchall()
            assert (
                len(early_rows) == 1
            ), "_start_run row must be committed before session closes (D-04)"
            assert early_rows[0]["status"] == "running"

            # Perform a load mutation inside a transaction on the session connection
            # and force it to roll back (proving session isolation from run-log).
            try:
                with db.transaction() as conn:
                    with conn.cursor() as cur:
                        cur.execute(f'INSERT INTO "{scratch}" VALUES (999)')
                    raise RuntimeError("forced load failure")
            except RuntimeError:
                # _end_run opens its own autocommit connection (post-fix)
                db.etl._end_run(
                    run_id,
                    "failed",
                    0,
                    0,
                    error_message="forced load failure",
                    error_traceback=traceback.format_exc(),
                )

            # Confirm _end_run row also committed on its own conn, still inside session
            with db.connect(autocommit=True) as fresh_conn:
                with fresh_conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        "SELECT status, error_message, error_traceback "
                        "FROM pipeline_runs WHERE run_id = %s",
                        [run_id],
                    )
                    mid_rows = cur.fetchall()
            assert (
                len(mid_rows) == 1
            ), "_end_run row must be committed before session closes (D-04)"
            assert mid_rows[0]["status"] == "failed"
            assert mid_rows[0]["error_message"] is not None

        # (a) After the session closes, pipeline_runs row still has status='failed'
        run_rows = db.execute(
            "SELECT status, error_message, error_traceback FROM pipeline_runs WHERE run_id = %s",
            [run_id],
        )
        assert len(run_rows) == 1, "pipeline_runs row must exist after session exits"
        assert run_rows[0]["status"] == "failed"
        assert run_rows[0]["error_message"] is not None
        assert run_rows[0]["error_traceback"] is not None

        # (b) load mutation (sentinel 999) was rolled back by db.transaction()
        scratch_rows = db.execute(f'SELECT val FROM "{scratch}" ORDER BY val')
        vals = [r["val"] for r in scratch_rows]
        assert 999 not in vals, "sentinel row from rolled-back load txn must be absent"
        assert 1 in vals, "baseline row must still be present"

        # Cleanup scratch table
        db.execute(f'DROP TABLE IF EXISTS "{scratch}" CASCADE', autocommit=True)


# ---------------------------------------------------------------------------
# Phase 18 integration tests — run(pipeline: Pipeline) body
# ---------------------------------------------------------------------------


@pytest.fixture
def etl_table(db):
    """Create a fresh ETL target table for each test; drop on teardown."""
    tbl = f"etl_tgt_{uuid.uuid4().hex[:8]}"
    db.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
        autocommit=True,
    )
    yield tbl
    db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)


@pytest.fixture
def etl_src(db):
    """Create a fresh ETL source table and return its name; drop on teardown."""
    tbl = f"etl_src_{uuid.uuid4().hex[:8]}"
    db.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
        autocommit=True,
    )
    yield tbl
    db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)


class TestRunPipelineIntegration:
    """Integration tests for the full run(pipeline: Pipeline) body (Phase 18)."""

    # -- signature / return value --

    def test_run_accepts_pipeline_object(self, db, cleanup_pipeline_runs, etl_table):
        """run() accepts a Pipeline and returns a RunResult."""
        p = Pipeline(
            name="sig_test",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
        )
        result = db.etl.run(p)
        assert isinstance(result, RunResult)

    def test_run_derives_pipeline_name_from_pipeline(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """run() stores pipeline.name in the pipeline_runs row."""
        p = Pipeline(
            name="named_pipeline",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
        )
        result = db.etl.run(p)
        rows = db.execute(
            "SELECT pipeline_name FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        assert rows[0]["pipeline_name"] == "named_pipeline"

    # -- extract --

    def test_extract_sql_source(self, db, cleanup_pipeline_runs, etl_table):
        """run() with a SQL source extracts the correct rows into the target."""
        p = Pipeline(
            name="sql_extract",
            source="SELECT 42 AS id, 'hello' AS val",
            target=etl_table,
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id, val FROM public."{etl_table}"')
        assert len(rows) == 1
        assert rows[0]["id"] == 42
        assert rows[0]["val"] == "hello"

    def test_extract_table_source(self, db, cleanup_pipeline_runs, etl_table, etl_src):
        """run() with a table source extracts all rows from the source table."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" VALUES (1, 'a'), (2, 'b')",
            autocommit=True,
        )
        p = Pipeline(
            name="table_extract",
            source=etl_src,
            target=etl_table,
            schema="public",
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id FROM public."{etl_table}" ORDER BY id')
        ids = [r["id"] for r in rows]
        assert ids == [1, 2]

    def test_extract_limit(self, db, cleanup_pipeline_runs, etl_table, etl_src):
        """run() with extract_limit fetches at most N rows (bound :lim param)."""
        for i in range(5):
            db.execute(
                f"INSERT INTO public.\"{etl_src}\" VALUES ({i}, 'v')",
                autocommit=True,
            )
        p = Pipeline(
            name="limited",
            source=etl_src,
            target=etl_table,
            extract_limit=3,
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        assert len(rows) == 3

    def test_rows_extracted_recorded(
        self, db, cleanup_pipeline_runs, etl_table, etl_src
    ):
        """run() records rows_extracted = len(df) in the pipeline_runs row."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" VALUES (1, 'a'), (2, 'b')",
            autocommit=True,
        )
        p = Pipeline(name="count_test", source=etl_src, target=etl_table)
        result = db.etl.run(p)
        rows = db.execute(
            "SELECT rows_extracted, rows_loaded FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        assert rows[0]["rows_extracted"] == 2
        assert rows[0]["rows_loaded"] == 2

    # -- transform --

    def test_transform_none_is_noop(self, db, cleanup_pipeline_runs, etl_table):
        """transform=None leaves the DataFrame unchanged (D-05)."""
        p = Pipeline(
            name="no_transform",
            source="SELECT 7 AS id, 'z' AS val",
            target=etl_table,
            transform=None,
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        assert rows[0]["id"] == 7

    def test_transform_single_callable(self, db, cleanup_pipeline_runs, etl_table):
        """A single callable transform is applied once before load (D-05)."""

        def double_id(df):
            df = df.copy()
            df["id"] = df["id"] * 2
            return df

        p = Pipeline(
            name="single_transform",
            source="SELECT 5 AS id, 'q' AS val",
            target=etl_table,
            transform=double_id,
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        assert rows[0]["id"] == 10

    def test_transform_list_applied_in_sequence(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """A list of transforms is applied in sequence, each seeing prior output (D-05/ETL-16)."""

        def add_1(df):
            df = df.copy()
            df["id"] = df["id"] + 1
            return df

        def mul_3(df):
            df = df.copy()
            df["id"] = df["id"] * 3
            return df

        p = Pipeline(
            name="chain_transform",
            source="SELECT 2 AS id, 'q' AS val",
            target=etl_table,
            transform=[add_1, mul_3],  # (2+1)*3 = 9
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        assert rows[0]["id"] == 9

    def test_transform_error_raises_etl_transform_error(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """A failing transform raises ETLTransformError naming the step (D-06/ETL-03)."""

        def bad_step(df):
            raise ValueError("deliberate failure")

        p = Pipeline(
            name="bad_transform",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
            transform=bad_step,
        )
        with pytest.raises(ETLTransformError) as exc_info:
            db.etl.run(p)
        assert "bad_step" in str(exc_info.value)
        assert "ValueError" in str(exc_info.value)

    def test_transform_error_step_index_in_message(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """ETLTransformError message includes the 1-based step index (D-06/ETL-16)."""

        def ok_step(df):
            return df

        def fail_step(df):
            raise RuntimeError("oops")

        p = Pipeline(
            name="step_index_test",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
            transform=[ok_step, fail_step],
        )
        with pytest.raises(ETLTransformError) as exc_info:
            db.etl.run(p)
        msg = str(exc_info.value)
        assert "step 2" in msg  # 1-based index
        assert "fail_step" in msg

    def test_transform_error_records_failed_run(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """A failing transform records a failed run row with error_message (ETL-03/ETL-08)."""

        def explode(df):
            raise TypeError("type mismatch")

        p = Pipeline(
            name="fail_record",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
            transform=explode,
        )
        try:
            db.etl.run(p)
        except ETLTransformError:
            pass

        rows = db.execute(
            "SELECT status, error_message FROM pipeline_runs ORDER BY run_id DESC LIMIT 1"
        )
        assert rows[0]["status"] == "failed"
        assert rows[0]["error_message"] is not None

    # -- load: append --

    def test_append_inserts_rows(self, db, cleanup_pipeline_runs, etl_table):
        """append mode inserts rows into the existing target (D-01/ETL-04)."""
        p = Pipeline(
            name="append_test",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
            load_mode="append",
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        assert len(rows) == 1

    def test_append_reruns_doubles_row_count(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """Running append twice doubles the row count (ETL-04 idempotency contract)."""
        p = Pipeline(
            name="append_double",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
            load_mode="append",
        )
        db.etl.run(p)
        db.etl.run(p)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        assert len(rows) == 2

    def test_append_missing_target_raises(self, db, cleanup_pipeline_runs):
        """append on a missing target raises ETLTargetNotFoundError (D-03/ETL-04)."""
        p = Pipeline(
            name="append_missing",
            source="SELECT 1 AS id, 'a' AS val",
            target="definitely_not_a_real_table_xyz",
            load_mode="append",
        )
        with pytest.raises(ETLTargetNotFoundError):
            db.etl.run(p)

    # -- load: replace --

    def test_replace_reruns_keeps_latest_only(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """Running replace twice keeps only the latest rows (ETL-05)."""
        p1 = Pipeline(
            name="replace_first",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
            load_mode="replace",
        )
        p2 = Pipeline(
            name="replace_second",
            source="SELECT 2 AS id, 'b' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p1)
        db.etl.run(p2)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        ids = [r["id"] for r in rows]
        assert ids == [2]  # latest run only

    def test_replace_atomic_rollback(self, db, cleanup_pipeline_runs, etl_table):
        """replace is atomic: a mid-load error leaves ORIGINAL rows intact (SC-3/ETL-05)."""
        # Seed the target with a baseline row
        db.execute(
            f"INSERT INTO public.\"{etl_table}\" VALUES (1, 'original')",
            autocommit=True,
        )

        # Add a NOT NULL constraint so inserting NULL will fail mid-INSERT
        db.execute(
            f'ALTER TABLE public."{etl_table}" ALTER COLUMN val SET NOT NULL',
            autocommit=True,
        )

        def inject_null(df):
            """Insert a row with NULL val that will violate the NOT NULL constraint."""
            bad = pd.DataFrame({"id": [99], "val": [None]})
            return pd.concat([df, bad], ignore_index=True)

        p = Pipeline(
            name="atomic_test",
            source="SELECT 2 AS id, 'new' AS val",
            target=etl_table,
            load_mode="replace",
            transform=inject_null,
        )
        with pytest.raises(Exception):
            db.etl.run(p)

        # The original row must still be present (TRUNCATE + INSERT was atomic)
        rows = db.execute(f'SELECT id, val FROM public."{etl_table}"')
        ids = [r["id"] for r in rows]
        assert 1 in ids, "baseline row must survive the failed replace (SC-3 atomicity)"
        assert 99 not in ids, "partial insert must be rolled back"

    def test_replace_auto_creates_missing_target(self, db, cleanup_pipeline_runs):
        """replace auto-creates a missing target table (D-03/ETL-05)."""
        tbl = f"etl_autocreate_{uuid.uuid4().hex[:8]}"
        p = Pipeline(
            name="autocreate",
            source="SELECT 1 AS id, 'a' AS val",
            target=tbl,
            load_mode="replace",
        )
        try:
            db.etl.run(p)
            rows = db.execute(f'SELECT id FROM public."{tbl}"')
            assert len(rows) == 1
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

    # -- load: upsert --

    def test_upsert_inserts_new_no_duplicates(self, db, cleanup_pipeline_runs):
        """upsert inserts new rows and updates existing ones with no duplicates (ETL-06)."""
        tbl = f"etl_upsert_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            # Insert initial row
            db.execute(
                f"INSERT INTO public.\"{tbl}\" VALUES (1, 'old')", autocommit=True
            )

            p = Pipeline(
                name="upsert_test",
                source="SELECT 1 AS id, 'new' AS val",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
            )
            db.etl.run(p)
            rows = db.execute(f'SELECT id, val FROM public."{tbl}"')
            assert len(rows) == 1  # no duplicates
            assert rows[0]["val"] == "new"  # updated
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

    def test_upsert_missing_target_raises(self, db, cleanup_pipeline_runs):
        """upsert on a missing target raises ETLTargetNotFoundError (D-03/ETL-06)."""
        p = Pipeline(
            name="upsert_missing",
            source="SELECT 1 AS id",
            target="definitely_not_a_real_table_xyz",
            load_mode="upsert",
            conflict_columns=["id"],
        )
        with pytest.raises(ETLTargetNotFoundError):
            db.etl.run(p)

    # -- NaN -> NULL --

    def test_nan_becomes_null(self, db, cleanup_pipeline_runs, etl_table):
        """NaN values in the DataFrame are coerced to SQL NULL before load (D-07/Q2)."""

        def inject_nan(df):
            df = df.copy()
            df["val"] = float("nan")
            return df

        p = Pipeline(
            name="nan_test",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
            transform=inject_nan,
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id, val FROM public."{etl_table}"')
        assert rows[0]["val"] is None  # NaN -> NULL

    # -- run-log isolation (ETL-09 non-regression) --

    def test_run_log_isolation_on_pipeline_run(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """run() records success even when called with a Pipeline object (ETL-09)."""
        p = Pipeline(
            name="isolation_check",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
        )
        result = db.etl.run(p)
        rows = db.execute(
            "SELECT status FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        assert rows[0]["status"] == "success"

    # -----------------------------------------------------------------------
    # Validation slug tests (18-VALIDATION.md per-task verification map)
    # -----------------------------------------------------------------------

    def test_extract_table_limit(self, db, cleanup_pipeline_runs, etl_table, etl_src):
        """Table source + extract_limit: at most N rows fetched, rows_extracted recorded."""
        for i in range(4):
            db.execute(
                f"INSERT INTO public.\"{etl_src}\" VALUES ({i}, 'v')",
                autocommit=True,
            )
        p = Pipeline(
            name="table_limit",
            source=etl_src,
            target=etl_table,
            extract_limit=2,
        )
        result = db.etl.run(p)
        target_rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        assert len(target_rows) == 2
        run_rows = db.execute(
            "SELECT rows_extracted FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        assert run_rows[0]["rows_extracted"] == 2

    def test_transform_error_failed_run(self, db, cleanup_pipeline_runs, etl_table):
        """Failing transform raises ETLTransformError; pipeline_runs row has status='failed'."""

        def bad_transform(df):
            raise ValueError("deliberate transform error")

        p = Pipeline(
            name="transform_fail",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
            transform=bad_transform,
        )
        with pytest.raises(ETLTransformError):
            db.etl.run(p)

        rows = db.execute(
            "SELECT status, error_message FROM pipeline_runs"
            " WHERE pipeline_name = 'transform_fail'"
            " ORDER BY run_id DESC LIMIT 1"
        )
        assert rows[0]["status"] == "failed"
        assert rows[0]["error_message"] is not None

    def test_append_double_count(self, db, cleanup_pipeline_runs, etl_table):
        """append re-run doubles the target row count (ETL-04 idempotency)."""
        p = Pipeline(
            name="append_dbl",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
            load_mode="append",
        )
        db.etl.run(p)
        db.etl.run(p)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        assert len(rows) == 2

    def test_replace_latest_only(self, db, cleanup_pipeline_runs, etl_table):
        """replace re-run keeps only the latest extract's rows (ETL-05)."""
        p1 = Pipeline(
            name="r_latest_1",
            source="SELECT 10 AS id, 'first' AS val",
            target=etl_table,
            load_mode="replace",
        )
        p2 = Pipeline(
            name="r_latest_2",
            source="SELECT 20 AS id, 'second' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p1)
        db.etl.run(p2)
        rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        ids = [r["id"] for r in rows]
        assert ids == [20]

    def test_replace_creates_missing(self, db, cleanup_pipeline_runs):
        """replace auto-creates a missing target table then loads rows (D-03/ETL-05)."""
        tbl = f"etl_cm_{uuid.uuid4().hex[:8]}"
        p = Pipeline(
            name="creates_missing",
            source="SELECT 5 AS id, 'c' AS val",
            target=tbl,
            load_mode="replace",
        )
        try:
            db.etl.run(p)
            rows = db.execute(f'SELECT id FROM public."{tbl}"')
            assert len(rows) == 1
            assert rows[0]["id"] == 5
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

    def test_upsert_no_duplicates(self, db, cleanup_pipeline_runs):
        """upsert re-run updates existing + inserts new rows with no duplicates (ETL-06)."""
        tbl = f"etl_und_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            db.execute(
                f"INSERT INTO public.\"{tbl}\" VALUES (1, 'old'), (2, 'keep')",
                autocommit=True,
            )
            p = Pipeline(
                name="upsert_nd",
                source="SELECT 1 AS id, 'updated' AS val",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
            )
            db.etl.run(p)
            rows = db.execute(f'SELECT id, val FROM public."{tbl}" ORDER BY id')
            assert len(rows) == 2  # no duplicates
            vals = {r["id"]: r["val"] for r in rows}
            assert vals[1] == "updated"  # updated
            assert vals[2] == "keep"  # untouched
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

    def test_nan_to_null(self, db, cleanup_pipeline_runs, etl_table):
        """NaN in extracted DataFrame lands as SQL NULL in target (D-07/Q2)."""
        import numpy as np

        def inject_nan(df):
            df = df.copy()
            df["val"] = np.nan
            return df

        p = Pipeline(
            name="nan_null",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
            transform=inject_nan,
        )
        db.etl.run(p)
        rows = db.execute(f'SELECT id, val FROM public."{etl_table}"')
        assert rows[0]["val"] is None  # NaN → SQL NULL

    def test_run_level_failed_load_rolls_back_but_run_committed(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """ETL-09 run()-level: failed load rolls back while failed pipeline_runs row commits.

        Seeds a target with a baseline row, then runs a replace pipeline whose
        transform injects a row violating a NOT NULL constraint.  Asserts (a)
        the exception propagates, (b) the target retains baseline rows (load
        txn rolled back), and (c) a pipeline_runs row with status='failed' is
        committed despite the load rollback.
        """
        # Seed baseline
        db.execute(
            f"INSERT INTO public.\"{etl_table}\" VALUES (1, 'base')",
            autocommit=True,
        )
        db.execute(
            f'ALTER TABLE public."{etl_table}" ALTER COLUMN val SET NOT NULL',
            autocommit=True,
        )

        def inject_null_val(df):
            """Return a row with NULL val to violate the NOT NULL constraint."""
            bad = pd.DataFrame({"id": [99], "val": [None]})
            return pd.concat([df, bad], ignore_index=True)

        p = Pipeline(
            name="run_level_fail",
            source="SELECT 2 AS id, 'new' AS val",
            target=etl_table,
            load_mode="replace",
            transform=inject_null_val,
        )
        with pytest.raises(Exception):
            db.etl.run(p)

        # (a) target retains baseline — TRUNCATE+INSERT was atomic
        target_rows = db.execute(f'SELECT id FROM public."{etl_table}"')
        ids = [r["id"] for r in target_rows]
        assert (
            1 in ids
        ), "baseline row must survive the failed replace (load txn rolled back)"
        assert 99 not in ids, "partial insert must be rolled back"

        # (b) pipeline_runs row committed with status='failed' (ETL-09)
        run_rows = db.execute(
            "SELECT status, error_message FROM pipeline_runs"
            " WHERE pipeline_name = 'run_level_fail'"
            " ORDER BY run_id DESC LIMIT 1"
        )
        assert len(run_rows) == 1, "failed run row must be committed"
        assert run_rows[0]["status"] == "failed"
        assert run_rows[0]["error_message"] is not None


class TestRunResultSurface:
    """SC-1..SC-4: run/history/last_run/dry_run return RunResult objects (ETL-10/11/15/17)."""

    # ------------------------------------------------------------------
    # SC-1 (ETL-10): run() returns a RunResult whose fields match the DB row
    # ------------------------------------------------------------------

    def test_run_returns_run_result(self, db, cleanup_pipeline_runs, etl_table):
        """SC-1: run() returns a RunResult instance (isinstance check)."""
        p = Pipeline(
            name="sc1_type",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p)
        assert isinstance(result, RunResult)

    def test_run_result_fields_match_pipeline_runs_row(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """SC-1: RunResult fields equal the pipeline_runs row re-SELECTed by run_id (D-11)."""
        p = Pipeline(
            name="sc1_fields",
            source="SELECT 1 AS id, 'b' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p)
        rows = db.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        assert len(rows) == 1
        row = rows[0]
        assert result.pipeline_name == row["pipeline_name"]
        assert result.status == row["status"]
        assert result.rows_extracted == row["rows_extracted"]
        assert result.rows_loaded == row["rows_loaded"]
        assert result.error == row["error_message"]

    def test_run_result_status_success(self, db, cleanup_pipeline_runs, etl_table):
        """SC-1: A successful run produces RunResult.status == 'success' (D-11 re-SELECT)."""
        p = Pipeline(
            name="sc1_status",
            source="SELECT 42 AS id, 'v' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p)
        assert result.status == "success"
        assert result.run_id is not None
        assert isinstance(result.run_id, int)

    # ------------------------------------------------------------------
    # SC-2 (ETL-11): history() returns list[RunResult], newest-first
    # ------------------------------------------------------------------

    def test_history_returns_list_of_run_results(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """SC-2: history() returns a list; each element is a RunResult."""
        p = Pipeline(
            name="sc2_hist",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p)
        hist = db.etl.history("sc2_hist")
        assert isinstance(hist, list)
        assert len(hist) == 1
        assert isinstance(hist[0], RunResult)

    def test_history_two_runs_returns_two_entries_newest_first(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """SC-2: Two runs of the same pipeline -> two entries; newest-first (started_at DESC)."""
        p = Pipeline(
            name="sc2_order",
            source="SELECT 1 AS id, 'y' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result1 = db.etl.run(p)
        result2 = db.etl.run(p)
        hist = db.etl.history("sc2_order")
        assert len(hist) == 2
        # newest-first: history[0] is the later run
        assert hist[0].run_id == result2.run_id
        assert hist[1].run_id == result1.run_id
        assert hist[0].started_at >= hist[1].started_at

    def test_history_default_limit_returns_up_to_100(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """SC-2: history() with default limit returns at most 100 entries (D-06)."""
        p = Pipeline(
            name="sc2_limit",
            source="SELECT 1 AS id, 'z' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p)
        hist = db.etl.history("sc2_limit")
        assert len(hist) <= 100

    def test_history_unknown_pipeline_returns_empty_list(
        self, db, cleanup_pipeline_runs
    ):
        """SC-2: history() for an unknown pipeline name returns an empty list."""
        db.etl.init()  # ensure pipeline_runs table exists
        hist = db.etl.history("no_such_pipeline_xyz")
        assert hist == []

    # ------------------------------------------------------------------
    # SC-3 (ETL-17): last_run() returns most-recent RunResult or None
    # ------------------------------------------------------------------

    def test_last_run_returns_most_recent(self, db, cleanup_pipeline_runs, etl_table):
        """SC-3: last_run(name) returns the most-recent RunResult (equals history[0])."""
        p = Pipeline(
            name="sc3_last",
            source="SELECT 1 AS id, 'r' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p)
        db.etl.run(p)
        last = db.etl.last_run("sc3_last")
        hist = db.etl.history("sc3_last")
        assert last is not None
        assert isinstance(last, RunResult)
        assert last.run_id == hist[0].run_id

    def test_last_run_returns_none_when_no_runs(self, db, cleanup_pipeline_runs):
        """SC-3: last_run() returns None when no runs exist for the given pipeline name."""
        db.etl.init()  # ensure pipeline_runs table exists
        result = db.etl.last_run("no_runs_yet_xyz")
        assert result is None

    def test_last_run_not_the_older_run_when_two_exist(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """SC-3: last_run() is the newer run, not the older one."""
        p = Pipeline(
            name="sc3_newer",
            source="SELECT 1 AS id, 's' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result1 = db.etl.run(p)
        result2 = db.etl.run(p)
        last = db.etl.last_run("sc3_newer")
        assert last is not None
        assert last.run_id == result2.run_id
        assert last.run_id != result1.run_id

    # ------------------------------------------------------------------
    # SC-4 (ETL-15): dry_run=True skips load and writes no pipeline_runs row
    # ------------------------------------------------------------------

    def test_dry_run_returns_run_result_with_dry_run_status(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """SC-4: dry_run=True returns RunResult with status='dry_run'."""
        p = Pipeline(
            name="sc4_status",
            source="SELECT 1 AS id, 't' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p, dry_run=True)
        assert isinstance(result, RunResult)
        assert result.status == "dry_run"

    def test_dry_run_run_id_is_none(self, db, cleanup_pipeline_runs, etl_table):
        """SC-4: dry_run=True produces run_id=None (no DB row, no PK assigned, D-05/D-08)."""
        p = Pipeline(
            name="sc4_run_id",
            source="SELECT 1 AS id, 'u' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p, dry_run=True)
        assert result.run_id is None

    def test_dry_run_rows_loaded_is_zero(self, db, cleanup_pipeline_runs, etl_table):
        """SC-4: dry_run=True produces rows_loaded==0 (load skipped, D-08)."""
        p = Pipeline(
            name="sc4_loaded",
            source="SELECT 1 AS id, 'v' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p, dry_run=True)
        assert result.rows_loaded == 0

    def test_dry_run_rows_extracted_reflects_actual_extract(
        self, db, cleanup_pipeline_runs, etl_table, etl_src
    ):
        """SC-4: dry_run rows_extracted reflects rows that would have been loaded (D-08)."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" VALUES (1, 'a'), (2, 'b'), (3, 'c')",
            autocommit=True,
        )
        p = Pipeline(
            name="sc4_extracted",
            source=etl_src,
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p, dry_run=True)
        assert result.rows_extracted == 3

    def test_dry_run_writes_no_pipeline_runs_row(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """SC-4: dry_run=True writes NO pipeline_runs row (D-08/D-09/T-19-06)."""
        db.etl.init()  # ensure pipeline_runs table exists so COUNT(*) can run
        p = Pipeline(
            name="sc4_norow",
            source="SELECT 1 AS id, 'w' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p, dry_run=True)
        rows = db.execute(
            "SELECT COUNT(*) AS cnt FROM pipeline_runs WHERE pipeline_name = %s",
            ["sc4_norow"],
        )
        assert rows[0]["cnt"] == 0

    def test_dry_run_target_table_unchanged(self, db, cleanup_pipeline_runs, etl_table):
        """SC-4: dry_run=True leaves the target table untouched (no rows inserted)."""
        p = Pipeline(
            name="sc4_target",
            source="SELECT 99 AS id, 'x' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p, dry_run=True)
        rows = db.execute(f'SELECT COUNT(*) AS cnt FROM public."{etl_table}"')
        assert rows[0]["cnt"] == 0

    def test_dry_run_with_extract_limit_sql_source(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """dry_run + SQL source + extract_limit covers line 808 (sync dry-run extract_limit)."""
        p = Pipeline(
            name="sc4_extlim_sql",
            source="SELECT generate_series(1,10) AS id, 'v' AS val",
            target=etl_table,
            load_mode="replace",
            extract_limit=3,
        )
        r = db.etl.run(p, dry_run=True)
        assert r.status == "dry_run"
        assert r.rows_extracted == 3

    def test_dry_run_with_transform_list(self, db, cleanup_pipeline_runs, etl_table):
        """dry_run + transform as list covers lines 839-842, 844-847 (sync dry-run transform list)."""

        def add_one(df):
            df = df.copy()
            df["id"] = df["id"] + 1
            return df

        def add_ten(df):
            df = df.copy()
            df["id"] = df["id"] + 10
            return df

        p = Pipeline(
            name="sc4_transform_list",
            source="SELECT 0 AS id, 'v' AS val",
            target=etl_table,
            load_mode="replace",
            transform=[add_one, add_ten],
        )
        r = db.etl.run(p, dry_run=True)
        assert r.status == "dry_run"
        assert r.rows_extracted == 1

    def test_sync_run_with_extract_limit_sql(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """run() + SQL source + extract_limit covers line 877 (sync normal extract_limit)."""
        p = Pipeline(
            name="sc_extlim_normal",
            source="SELECT generate_series(1,10) AS id, 'v' AS val",
            target=etl_table,
            load_mode="replace",
            extract_limit=4,
        )
        r = db.etl.run(p)
        assert r.status == "success"
        assert r.rows_extracted == 4

    def test_sync_run_empty_dataframe(self, db, cleanup_pipeline_runs, etl_table):
        """run() with zero-row source covers lines 934-935 (empty DF early return)."""
        p = Pipeline(
            name="sc_empty_df",
            source="SELECT 1 AS id, 'e' AS val WHERE FALSE",
            target=etl_table,
            load_mode="replace",
        )
        r = db.etl.run(p)
        assert r.status == "success"
        assert r.rows_extracted == 0
        assert r.rows_loaded == 0

    # -----------------------------------------------------------------------
    # Phase 27 — incremental watermark integration tests (SC-1..SC-4 / D-04 / D-06)
    # -----------------------------------------------------------------------

    def test_first_run_records_watermark(self, db, cleanup_pipeline_runs, etl_src):
        """SC-1/ETL-INC-02: first incremental run persists max(col) as non-NULL watermark."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (1, 'a'), (5, 'b'), (3, 'c')",
            autocommit=True,
        )
        tbl = f"etl_wm1_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_first_run",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            result = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)
        rows = db.execute(
            "SELECT watermark FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        row = rows[0]
        assert row["watermark"] == {"type": "int", "value": 5}
        assert db.etl._read_watermark("wm_first_run") == 5

    def test_failed_run_does_not_advance_watermark(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """SC-2/ETL-INC-06: failed run leaves watermark NULL; _read_watermark returns prior W0."""
        # Seed a prior successful run with W0
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (10, 'x')",
            autocommit=True,
        )
        tbl = f"etl_wm2_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p_seed = Pipeline(
                name="wm_fail_test",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            db.etl.run(p_seed)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)
        w0 = db.etl._read_watermark("wm_fail_test")
        assert w0 == 10

        # Induce a deterministic failure using the _start_run + transaction harness
        db.etl.init()
        failed_run_id = db.etl._start_run("wm_fail_test")
        try:
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")  # no-op inside txn
                raise RuntimeError("forced load failure")
        except RuntimeError:
            db.etl._end_run(
                failed_run_id,
                "failed",
                0,
                0,
                error_message="forced load failure",
                error_traceback=traceback.format_exc(),
            )

        # The failed row must have status='failed' and watermark IS NULL
        frows = db.execute(
            "SELECT status, watermark FROM pipeline_runs WHERE run_id = %s",
            [failed_run_id],
        )
        assert frows[0]["status"] == "failed"
        assert frows[0]["watermark"] is None
        # _read_watermark must still return the prior success watermark W0
        assert db.etl._read_watermark("wm_fail_test") == w0

    def test_empty_batch_preserves_watermark(self, db, cleanup_pipeline_runs, etl_src):
        """SC-3/ETL-INC-05: empty batch leaves watermark NULL; _read_watermark returns prior W0."""
        # Seed a prior successful run with W0
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (7, 'y')",
            autocommit=True,
        )
        tbl = f"etl_wm3_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p_seed = Pipeline(
                name="wm_empty_test",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            db.etl.run(p_seed)
            w0 = db.etl._read_watermark("wm_empty_test")
            assert w0 == 7

            # Run with empty source (0 rows)
            p_empty = Pipeline(
                name="wm_empty_test",
                source="SELECT 1 AS id, 'z' AS val WHERE FALSE",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            empty_result = db.etl.run(p_empty)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        erows = db.execute(
            "SELECT status, rows_loaded, watermark FROM pipeline_runs WHERE run_id = %s",
            [empty_result.run_id],
        )
        assert erows[0]["status"] == "success"
        assert erows[0]["rows_loaded"] == 0
        assert erows[0]["watermark"] is None
        # Prior watermark must be preserved
        assert db.etl._read_watermark("wm_empty_test") == w0

    @pytest.mark.parametrize(
        "source_sql, col, col_ddl, expected_type_tag",
        [
            (
                "SELECT 42 AS qty, 'a' AS tag",
                "qty",
                "qty INTEGER PRIMARY KEY, tag TEXT",
                "int",
            ),
            (
                "SELECT 'omega' AS label, 1 AS n",
                "label",
                "label TEXT PRIMARY KEY, n INTEGER",
                "str",
            ),
            (
                "SELECT TIMESTAMPTZ '2026-01-02 12:00:00.123456+02:00' AS ts, 'x' AS tag",
                "ts",
                "ts TIMESTAMPTZ PRIMARY KEY, tag TEXT",
                "datetime",
            ),
        ],
    )
    def test_watermark_jsonb_roundtrip(
        self,
        db,
        cleanup_pipeline_runs,
        source_sql,
        col,
        col_ddl,
        expected_type_tag,
    ):
        """SC-4/ETL-INC-10: watermark round-trips through JSONB for int/str/timestamp."""
        import pandas as pd

        # Extract the raw batch to compute the coerced max for comparison
        raw_df = db.to_dataframe(sql=source_sql)
        m = raw_df[col].max()
        if isinstance(m, pd.Timestamp):
            expected_value = m.to_pydatetime()
        elif isinstance(m, str):
            expected_value = str(m)
        else:
            expected_value = int(m)

        # Fresh target table with a PK on the watermark column + a non-conflict
        # column so the upsert SET clause is non-empty (SQL validity requirement).
        tbl = f"etl_wm_rt_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" ({col_ddl})',
            autocommit=True,
        )
        pipe_name = f"wm_roundtrip_{col}"
        try:
            p = Pipeline(
                name=pipe_name,
                source=source_sql,
                target=tbl,
                load_mode="upsert",
                conflict_columns=[col],
                incremental_column=col,
            )
            result = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        wm_row = db.execute(
            "SELECT watermark FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )[0]
        assert wm_row["watermark"]["type"] == expected_type_tag
        decoded = db.etl._read_watermark(pipe_name)
        assert decoded == expected_value
        if expected_type_tag == "datetime":
            # Offset and microseconds must be preserved in the stored ISO string
            stored_iso = wm_row["watermark"]["value"]
            assert "." in stored_iso  # microseconds present
            assert decoded.tzinfo is not None  # tz-aware

    def test_read_watermark_none_first_run(self, db, cleanup_pipeline_runs):
        """D-04: _read_watermark returns None when no qualifying success row exists."""
        db.etl.init()
        assert db.etl._read_watermark("no_such_pipeline_xzq99") is None

    def test_incremental_column_missing_raises_etlerror(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """D-06: missing incremental_column in extracted batch raises ETLError, not KeyError."""
        p = Pipeline(
            name="wm_missing_col",
            source="SELECT 1 AS id",
            target=etl_table,
            load_mode="upsert",
            conflict_columns=["id"],
            incremental_column="missing_col",
        )
        with pytest.raises(ETLError, match="missing_col"):
            db.etl.run(p)

    def test_float_incremental_column_raises_etlerror(self, db, cleanup_pipeline_runs):
        """WR-01: float incremental_column raises ETLError (no silent truncation)."""
        tbl = f"etl_wmf_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, score NUMERIC)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_float_col",
                # NUMERIC column read by pandas as float64; max() would be
                # silently truncated by int() — must fail loud instead.
                source="SELECT 1 AS id, 99.99::float8 AS score",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="score",
            )
            with pytest.raises(ETLError, match="float"):
                db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

    def test_all_null_incremental_column_preserves_watermark(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """WR-02: an all-NULL incremental column records no watermark (no crash), prior W0 preserved."""
        # Seed a prior successful run with W0 = 7
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (7, 'seed')",
            autocommit=True,
        )
        tbl = f"etl_wmn_{uuid.uuid4().hex[:8]}"
        # Target carries a `wm` column so the all-NULL batch below loads cleanly;
        # `val` lets the seed run upsert a non-conflict column.
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT, wm INTEGER)',
            autocommit=True,
        )
        try:
            p_seed = Pipeline(
                name="wm_allnull_test",
                source=f'SELECT id, val FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            db.etl.run(p_seed)
            w0 = db.etl._read_watermark("wm_allnull_test")
            assert w0 == 7

            # A non-empty batch whose incremental_column (wm) is entirely NULL:
            # df[wm].max() is NaN — must NOT crash; records no watermark.
            p_null = Pipeline(
                name="wm_allnull_test",
                source="SELECT 2 AS id, NULL::integer AS wm",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="wm",
            )
            result = db.etl.run(p_null)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        nrows = db.execute(
            "SELECT status, watermark FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        assert nrows[0]["status"] == "success"
        assert nrows[0]["watermark"] is None
        # Prior success watermark must be preserved
        assert db.etl._read_watermark("wm_allnull_test") == w0

    # -----------------------------------------------------------------------
    # Phase 28 — RunResult watermark surface (ETL-INC-07 / ETL-INC-08 / D-A1)
    # -----------------------------------------------------------------------

    def test_non_incremental_run_watermark_fields_none(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """D-A1: non-incremental run() returns watermark_used=None and watermark_recorded=None."""
        p = Pipeline(
            name="wm_noninc_fields",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p)
        assert result.watermark_used is None
        assert result.watermark_recorded is None

    def test_non_incremental_history_watermark_fields_none(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """D-A1: history() rows for a non-incremental pipeline have watermark_used/recorded=None."""
        p = Pipeline(
            name="wm_noninc_hist",
            source="SELECT 1 AS id, 'b' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p)
        hist = db.etl.history("wm_noninc_hist")
        assert len(hist) == 1
        assert hist[0].watermark_used is None
        assert hist[0].watermark_recorded is None

    def test_non_incremental_last_run_watermark_fields_none(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """D-A1: last_run() for a non-incremental pipeline has watermark_used/recorded=None."""
        p = Pipeline(
            name="wm_noninc_last",
            source="SELECT 1 AS id, 'c' AS val",
            target=etl_table,
            load_mode="replace",
        )
        db.etl.run(p)
        last = db.etl.last_run("wm_noninc_last")
        assert last is not None
        assert last.watermark_used is None
        assert last.watermark_recorded is None

    def test_row_to_result_maps_null_watermark_to_none(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """D-A1a: _row_to_result of a stored non-incremental row gives watermark_recorded=None."""
        p = Pipeline(
            name="wm_row_null",
            source="SELECT 1 AS id, 'd' AS val",
            target=etl_table,
            load_mode="replace",
        )
        result = db.etl.run(p)
        # Non-incremental run stores watermark=NULL; _row_to_result must map it to None
        rows = db.execute(
            "SELECT watermark FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        assert rows[0]["watermark"] is None  # confirm stored NULL
        assert result.watermark_recorded is None

    # -----------------------------------------------------------------------
    # Phase 28 Task 2 — filtered extract + RunResult fields + incremental dry_run
    # (ETL-INC-03 / ETL-INC-07 / ETL-INC-09 / SC-1 / D-A2)
    # -----------------------------------------------------------------------

    def test_incremental_first_run_watermark_used_none(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """ETL-INC-07: first incremental run has watermark_used=None (no prior watermark)."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (3, 'a'), (7, 'b')",
            autocommit=True,
        )
        tbl = f"etl_wm_first_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_first_used",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            result = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)
        assert result.watermark_used is None  # first run — no prior watermark
        assert result.watermark_recorded == 7  # max(id)

    def test_incremental_second_run_pulls_only_new_rows(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """ETL-INC-03: second run extracts only rows with col > prior watermark."""
        # First run: seed rows 1, 3, 5 → watermark = 5
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (1, 'a'), (3, 'b'), (5, 'c')",
            autocommit=True,
        )
        tbl = f"etl_wm_2nd_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_second_run",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            result1 = db.etl.run(p)
            assert result1.watermark_recorded == 5

            # Insert rows below (2) and above (6, 8) the prior watermark
            db.execute(
                f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (2, 'below'), (6, 'new1'), (8, 'new2')",
                autocommit=True,
            )
            result2 = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        # Only rows with id > 5 should have been extracted
        assert result2.rows_extracted == 2  # ids 6 and 8
        assert result2.watermark_used == 5  # floor from first run
        assert result2.watermark_recorded == 8  # new max

    def test_incremental_watermark_as_bound_param(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """SC-1 / T-28-01: watermark value is a bound param, never interpolated into SQL.

        DEBT-01 fixture-isolation note: uses a local ``captured_calls`` spy list
        (equivalent to ``mock.call_args_list``) rather than ``mock.call_args``
        to avoid the ~2.7% flake from mock call-order sensitivity when tests run
        in randomized order. Asserts on the last entry to target the exact call.
        """
        from unittest.mock import patch

        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (10, 'x')",
            autocommit=True,
        )
        tbl = f"etl_wm_param_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_param_check",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            db.etl.run(p)  # first run, watermark=10

            # DEBT-01: local spy list (call_args_list equivalent) captures calls
            # in insertion order; fresh per test invocation — no cross-test leakage.
            captured_calls = []
            original_to_dataframe = db.to_dataframe

            def spy_to_dataframe(**kwargs):
                captured_calls.append(kwargs)
                return original_to_dataframe(**kwargs)

            with patch.object(db, "to_dataframe", side_effect=spy_to_dataframe):
                db.etl.run(p)  # second run — should use wm=10 as bound param
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        # The second-run call should have bound the watermark as a param (not in SQL text)
        assert len(captured_calls) >= 1
        last_call = captured_calls[-1]  # explicit last-call assertion (DEBT-01 fix)
        params = last_call.get("params") or {}
        sql = last_call.get("sql", "")
        # The watermark VALUE travels as a bound param, and the SQL carries the
        # ``:wm`` placeholder rather than the interpolated value. Asserting on the
        # placeholder (not "10" not in sql) is robust to random table-name hex
        # suffixes that can incidentally contain the digit string.
        assert "wm" in params, "watermark must be a bound param 'wm'"
        assert params["wm"] == 10, "the watermark value must be carried in the params"
        assert ":wm" in sql, "SQL must reference the watermark via the :wm bind"

    def test_incremental_run_result_watermark_fields(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """ETL-INC-07: first run watermark_used=None/recorded=max; second run watermark_used=prior."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (2, 'a'), (9, 'b')",
            autocommit=True,
        )
        tbl = f"etl_wm_fields_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_result_fields",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            r1 = db.etl.run(p)
            # Insert new rows above watermark
            db.execute(
                f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (15, 'c')",
                autocommit=True,
            )
            r2 = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        assert r1.watermark_used is None
        assert r1.watermark_recorded == 9
        assert r2.watermark_used == 9  # prior recorded
        assert r2.watermark_recorded == 15

    def test_incremental_history_surfaces_watermark_recorded(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """ETL-INC-08: history()/last_run() surface watermark_recorded, watermark_used=None."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (4, 'a'), (12, 'b')",
            autocommit=True,
        )
        tbl = f"etl_wm_hist_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_hist_surface",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            r = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        hist = db.etl.history("wm_hist_surface")
        last = db.etl.last_run("wm_hist_surface")
        assert len(hist) == 1
        assert hist[0].watermark_recorded == r.watermark_recorded
        assert hist[0].watermark_used is None  # stored rows always None
        assert last is not None
        assert last.watermark_recorded == r.watermark_recorded
        assert last.watermark_used is None

    def test_incremental_dry_run_applies_filter_and_sets_watermark_fields(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """ETL-INC-09: dry_run on incremental pipeline reads prior watermark, filters, reports fields, no row written."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (1, 'a'), (5, 'b'), (10, 'c')",
            autocommit=True,
        )
        tbl = f"etl_wm_dry_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_dry_inc",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            db.etl.run(p)  # first real run: watermark = 10
            prior_wm = db.etl._read_watermark("wm_dry_inc")
            assert prior_wm == 10

            # Insert new rows
            db.execute(
                f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (15, 'd'), (20, 'e')",
                autocommit=True,
            )

            # Count pipeline_runs before dry_run
            count_before = db.execute("SELECT COUNT(*) AS n FROM pipeline_runs")[0]["n"]
            dry_result = db.etl.run(p, dry_run=True)
            count_after = db.execute("SELECT COUNT(*) AS n FROM pipeline_runs")[0]["n"]
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        assert dry_result.status == "dry_run"
        assert dry_result.run_id is None
        assert dry_result.rows_extracted == 2  # only ids 15, 20 (above watermark 10)
        assert dry_result.watermark_used == 10
        assert dry_result.watermark_recorded == 20  # max of filtered batch
        assert count_after == count_before  # no new pipeline_runs row

    def test_incremental_dry_run_empty_filtered_batch(
        self, db, cleanup_pipeline_runs, etl_src
    ):
        """ETL-INC-09: dry_run when filtered batch is empty has watermark_recorded=None."""
        db.execute(
            f"INSERT INTO public.\"{etl_src}\" (id, val) VALUES (100, 'z')",
            autocommit=True,
        )
        tbl = f"etl_wm_drye_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="wm_dry_empty",
                source=f'SELECT * FROM public."{etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            db.etl.run(p)  # watermark = 100 — no rows above this
            dry_result = db.etl.run(p, dry_run=True)  # no new rows above 100
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        assert dry_result.watermark_used == 100
        assert dry_result.watermark_recorded is None  # empty filtered batch
        assert dry_result.rows_extracted == 0

    def test_incremental_tz_aware_offset_preserved_second_run(
        self, db, cleanup_pipeline_runs
    ):
        """ETL-INC-07 / D-A2: tz-aware datetime watermark offset is preserved on second-run filter and watermark_recorded."""
        # Source: two tz-aware timestamps; first run records ts1 as watermark
        ts1_sql = "TIMESTAMPTZ '2026-01-10 10:00:00.000000+02:00'"
        ts2_sql = "TIMESTAMPTZ '2026-01-20 15:30:00.123456+02:00'"

        tbl = f"etl_tz_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (ts TIMESTAMPTZ PRIMARY KEY, tag TEXT)',
            autocommit=True,
        )
        pipe_name = f"wm_tz_second_{uuid.uuid4().hex[:8]}"
        try:
            # First run: load row with ts1 as watermark
            p = Pipeline(
                name=pipe_name,
                source=f"SELECT {ts1_sql} AS ts, 'first' AS tag",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["ts"],
                incremental_column="ts",
            )
            r1 = db.etl.run(p)
            assert r1.watermark_recorded is not None
            assert r1.watermark_recorded.tzinfo is not None

            # Second run: source has both ts1 and ts2; filter should exclude ts1
            p2 = Pipeline(
                name=pipe_name,
                source=f"SELECT {ts1_sql} AS ts, 'first' AS tag UNION ALL SELECT {ts2_sql}, 'second'",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["ts"],
                incremental_column="ts",
            )
            r2 = db.etl.run(p2)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        # watermark_used = ts1; only ts2 extracted
        assert r2.rows_extracted == 1
        assert r2.watermark_used is not None
        assert r2.watermark_used.tzinfo is not None  # tz preserved on filter floor
        # utcoffset intact (no UTC normalization)
        assert r2.watermark_used.utcoffset() == r1.watermark_recorded.utcoffset()
        assert r2.watermark_recorded is not None
        assert (
            r2.watermark_recorded.tzinfo is not None
        )  # tz preserved on new high-water
        # microseconds preserved on watermark_recorded
        assert r2.watermark_recorded.microsecond == 123456

    # -----------------------------------------------------------------------
    # Phase 39 Plan 01 — COV-01: sync dry_run watermark + transform branch tests
    # (etl.py L1215, L1224, L1226, L1241, L1248-1249)
    # -----------------------------------------------------------------------

    def test_dry_run_incremental_string_watermark(self, db, cleanup_pipeline_runs):
        """Covers etl.py L1226 — str watermark branch in sync dry_run."""
        src = f"str_wm_src_{uuid.uuid4().hex[:8]}"
        dst = f"str_wm_dst_{uuid.uuid4().hex[:8]}"
        try:
            db.execute(
                f'CREATE TABLE public."{src}" (code TEXT, val INTEGER)',
                autocommit=True,
            )
            db.execute(
                f"INSERT INTO public.\"{src}\" VALUES ('beta', 2), ('alpha', 1)",
                autocommit=True,
            )
            db.execute(
                f'CREATE TABLE public."{dst}" (code TEXT, val INTEGER)',
                autocommit=True,
            )
            p = Pipeline(
                name=f"str_wm_{uuid.uuid4().hex[:6]}",
                source=src,
                target=dst,
                load_mode="upsert",
                conflict_columns=["code"],
                incremental_column="code",
            )
            db.etl.init()  # ensure pipeline_runs exists before dry_run on incremental
            result = db.etl.run(p, dry_run=True)
            assert result.status == "dry_run"
            assert isinstance(result.watermark_recorded, str)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{src}" CASCADE', autocommit=True)
            db.execute(f'DROP TABLE IF EXISTS public."{dst}" CASCADE', autocommit=True)

    def test_dry_run_incremental_timestamp_watermark(self, db, cleanup_pipeline_runs):
        """Covers etl.py L1224 — Timestamp.to_pydatetime() branch in sync dry_run."""
        src = f"ts_wm_src_{uuid.uuid4().hex[:8]}"
        dst = f"ts_wm_dst_{uuid.uuid4().hex[:8]}"
        try:
            db.execute(
                f'CREATE TABLE public."{src}" (ts TIMESTAMP, val INTEGER)',
                autocommit=True,
            )
            db.execute(
                f"INSERT INTO public.\"{src}\" VALUES ('2026-01-01 10:00:00', 1), ('2026-01-02 12:00:00', 2)",
                autocommit=True,
            )
            db.execute(
                f'CREATE TABLE public."{dst}" (ts TIMESTAMP, val INTEGER)',
                autocommit=True,
            )
            p = Pipeline(
                name=f"ts_wm_{uuid.uuid4().hex[:6]}",
                source=src,
                target=dst,
                load_mode="upsert",
                conflict_columns=["ts"],
                incremental_column="ts",
            )
            db.etl.init()  # ensure pipeline_runs exists before dry_run on incremental
            result = db.etl.run(p, dry_run=True)
            assert result.status == "dry_run"
            assert isinstance(result.watermark_recorded, datetime)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{src}" CASCADE', autocommit=True)
            db.execute(f'DROP TABLE IF EXISTS public."{dst}" CASCADE', autocommit=True)

    def test_dry_run_incremental_column_missing_raises(self, db, cleanup_pipeline_runs):
        """Covers etl.py L1215 — ETLError when incremental_column not in extracted batch."""
        src = f"missing_col_src_{uuid.uuid4().hex[:8]}"
        dst = f"missing_col_dst_{uuid.uuid4().hex[:8]}"
        try:
            db.execute(
                f'CREATE TABLE public."{src}" (id INTEGER, val TEXT)',
                autocommit=True,
            )
            db.execute(
                f"INSERT INTO public.\"{src}\" VALUES (1, 'a')",
                autocommit=True,
            )
            db.execute(
                f'CREATE TABLE public."{dst}" (id INTEGER, val TEXT)',
                autocommit=True,
            )
            p = Pipeline(
                name=f"missing_col_{uuid.uuid4().hex[:6]}",
                source=src,
                target=dst,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="nonexistent",
            )
            db.etl.init()  # ensure pipeline_runs exists before dry_run on incremental
            with pytest.raises(ETLError):
                db.etl.run(p, dry_run=True)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{src}" CASCADE', autocommit=True)
            db.execute(f'DROP TABLE IF EXISTS public."{dst}" CASCADE', autocommit=True)

    def test_dry_run_transform_single_callable(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """Covers etl.py L1241 — single callable transform in dry_run path."""

        def double_val(df):
            df = df.copy()
            df["id"] = df["id"] * 2
            return df

        p = Pipeline(
            name=f"dry_transform_single_{uuid.uuid4().hex[:6]}",
            source="SELECT 5 AS id, 'x' AS val",
            target=etl_table,
            load_mode="replace",
            transform=double_val,
        )
        result = db.etl.run(p, dry_run=True)
        assert result.status == "dry_run"
        assert result.rows_extracted == 1

    def test_dry_run_transform_step_raises_etl_transform_error(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """Covers etl.py L1248-1249 — transform step raises ETLTransformError in dry_run."""

        def bad_transform(df):
            raise ValueError("boom")

        p = Pipeline(
            name=f"dry_transform_raises_{uuid.uuid4().hex[:6]}",
            source="SELECT 1 AS id, 'v' AS val",
            target=etl_table,
            load_mode="replace",
            transform=bad_transform,
        )
        with pytest.raises(ETLTransformError):
            db.etl.run(p, dry_run=True)


# ---------------------------------------------------------------------------
# Phase 20 behavioral async tests — async_db.etl.run/history/last_run/dry_run
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_db(db_config):
    """Yield an AsyncDatabase connected to pycopg_test."""
    database = AsyncDatabase(db_config)
    yield database


@pytest.fixture
async def async_etl_table(db_config):
    """Create a fresh ETL target table via async connection; drop on teardown."""
    tbl = f"etl_atgt_{uuid.uuid4().hex[:8]}"
    adb = AsyncDatabase(db_config)
    await adb.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
        autocommit=True,
    )
    yield tbl
    await adb.execute(
        f'DROP TABLE IF EXISTS public."{tbl}" CASCADE',
        autocommit=True,
    )


@pytest.fixture
async def cleanup_async_pipeline_runs(db_config):
    """Drop pipeline_runs after each async integration test."""
    yield
    try:
        adb = AsyncDatabase(db_config)
        await adb.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE", autocommit=True)
    except Exception:
        pass


@pytest.fixture
async def async_etl_src(db_config):
    """Create a fresh ETL source table via async connection; drop on teardown."""
    tbl = f"etl_asrc_{uuid.uuid4().hex[:8]}"
    adb = AsyncDatabase(db_config)
    await adb.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
        autocommit=True,
    )
    yield tbl
    await adb.execute(
        f'DROP TABLE IF EXISTS public."{tbl}" CASCADE',
        autocommit=True,
    )


class TestAsyncRunResultSurface:
    """Behavioral async parity tests for async_db.etl (ETL-12/ETL-13, SC-1..SC-4).

    Exercises ``await async_db.etl.run/history/last_run/run(dry_run=True)``
    against the real ``pycopg_test`` DB so the async code path is covered by
    the coverage gate — not just structurally enumerated by ``TestEtlParity``.

    ``asyncio_mode = "auto"`` in ``pyproject.toml`` means no
    ``@pytest.mark.asyncio`` marker is needed.
    """

    # ------------------------------------------------------------------
    # SC-1: run() returns a RunResult with expected fields
    # ------------------------------------------------------------------

    async def test_async_run_returns_run_result(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() returns a RunResult with status='success' and a valid run_id."""
        p = Pipeline(
            name="asc1_run",
            source="SELECT 1 AS id, 'a' AS val",
            target=async_etl_table,
            load_mode="replace",
        )
        r = await async_db.etl.run(p)
        assert isinstance(r, RunResult)
        assert r.status == "success"
        assert r.run_id is not None
        assert isinstance(r.run_id, int)

    async def test_async_run_rows_extracted_and_loaded(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() records correct rows_extracted and rows_loaded counts."""
        p = Pipeline(
            name="asc1_counts",
            source="SELECT 1 AS id, 'x' AS val UNION ALL SELECT 2, 'y'",
            target=async_etl_table,
            load_mode="replace",
        )
        r = await async_db.etl.run(p)
        assert r.rows_extracted == 2
        assert r.rows_loaded == 2

    # ------------------------------------------------------------------
    # SC-2: history() returns list[RunResult], newest-first
    # ------------------------------------------------------------------

    async def test_async_history_two_runs_newest_first(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async history() returns two entries newest-first after two runs."""
        p = Pipeline(
            name="asc2_hist",
            source="SELECT 1 AS id, 'h' AS val",
            target=async_etl_table,
            load_mode="replace",
        )
        await async_db.etl.run(p)
        await async_db.etl.run(p)
        h = await async_db.etl.history("asc2_hist")
        assert len(h) == 2
        assert all(isinstance(item, RunResult) for item in h)
        assert h[0].started_at >= h[1].started_at

    # ------------------------------------------------------------------
    # SC-3: last_run() returns most-recent or None
    # ------------------------------------------------------------------

    async def test_async_last_run_returns_most_recent(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async last_run() returns the most recent RunResult after a run."""
        p = Pipeline(
            name="asc3_last",
            source="SELECT 7 AS id, 'l' AS val",
            target=async_etl_table,
            load_mode="replace",
        )
        r = await async_db.etl.run(p)
        last = await async_db.etl.last_run("asc3_last")
        assert last is not None
        assert isinstance(last, RunResult)
        assert last.run_id == r.run_id

    async def test_async_last_run_returns_none_for_unknown(
        self, async_db, cleanup_async_pipeline_runs
    ):
        """async last_run() returns None when no runs exist for the pipeline name."""
        await async_db.etl.init()
        result = await async_db.etl.last_run("nonexistent_pipeline_xyz")
        assert result is None

    # ------------------------------------------------------------------
    # SC-4: dry_run=True skips load and writes no pipeline_runs row
    # ------------------------------------------------------------------

    async def test_async_dry_run_status_and_no_row(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run(dry_run=True) returns status='dry_run', run_id=None, rows_loaded=0.

        Also asserts that no pipeline_runs row is written for the dry run.
        """
        await async_db.etl.init()  # ensure pipeline_runs exists for the COUNT query
        p = Pipeline(
            name="asc4_dry",
            source="SELECT 5 AS id, 'd' AS val",
            target=async_etl_table,
            load_mode="replace",
        )
        r = await async_db.etl.run(p, dry_run=True)
        assert r.status == "dry_run"
        assert r.run_id is None
        assert r.rows_loaded == 0

        # No pipeline_runs row written
        rows = await async_db.execute(
            "SELECT COUNT(*) AS cnt FROM pipeline_runs WHERE pipeline_name = %s",
            ["asc4_dry"],
        )
        assert rows[0]["cnt"] == 0

    # ------------------------------------------------------------------
    # SC-2 bonus: transform via asyncio.to_thread is dispatched correctly
    # ------------------------------------------------------------------

    async def test_async_run_transform_applied_via_to_thread(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() dispatches transform via asyncio.to_thread (SC-2 behavioral proof)."""

        def double_id(df):
            df = df.copy()
            df["id"] = df["id"] * 10
            return df

        p = Pipeline(
            name="asc2_transform",
            source="SELECT 3 AS id, 't' AS val",
            target=async_etl_table,
            load_mode="replace",
            transform=double_id,
        )
        await async_db.etl.run(p)
        rows = await async_db.execute(f'SELECT id FROM public."{async_etl_table}"')
        assert rows[0]["id"] == 30

    async def test_async_run_table_source(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() with a table-name source (non-SQL) reads from the table."""
        # Seed source data into async_etl_table then copy to a new table
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_table}\" (id, val) VALUES (99, 'src')",
            autocommit=True,
        )
        tgt_tbl = f"etl_atgt_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tgt_tbl}" (id INTEGER, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="asc_tbl_src",
                source=async_etl_table,
                target=tgt_tbl,
                load_mode="replace",
            )
            r = await async_db.etl.run(p)
            assert r.status == "success"
            assert r.rows_extracted >= 1
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tgt_tbl}" CASCADE', autocommit=True
            )

    async def test_async_run_extract_limit(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() respects extract_limit in both SQL-source and dry-run paths."""
        # SQL source with extract_limit
        p = Pipeline(
            name="asc_extlim",
            source="SELECT generate_series(1,10) AS id, 'v' AS val",
            target=async_etl_table,
            load_mode="replace",
            extract_limit=3,
        )
        r = await async_db.etl.run(p)
        assert r.rows_extracted == 3
        assert r.rows_loaded == 3

    async def test_async_dry_run_extract_limit_table_source(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run(dry_run=True) with a table source and extract_limit (covers async dry-run
        table branch + extract_limit branch)."""
        # Seed some rows
        for i in range(5):
            await async_db.execute(
                f"INSERT INTO public.\"{async_etl_table}\" (id, val) VALUES ({i}, 'x')",
                autocommit=True,
            )
        p = Pipeline(
            name="asc_dry_tbl",
            source=async_etl_table,
            target=async_etl_table,
            load_mode="replace",
            extract_limit=2,
        )
        r = await async_db.etl.run(p, dry_run=True)
        assert r.status == "dry_run"
        assert r.rows_extracted == 2

    async def test_async_run_transform_list(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() with transform as a list of callables covers the list branch."""

        def add_one(df):
            df = df.copy()
            df["id"] = df["id"] + 1
            return df

        def add_ten(df):
            df = df.copy()
            df["id"] = df["id"] + 10
            return df

        p = Pipeline(
            name="asc_transform_list",
            source="SELECT 0 AS id, 'list' AS val",
            target=async_etl_table,
            load_mode="replace",
            transform=[add_one, add_ten],
        )
        await async_db.etl.run(p)
        rows = await async_db.execute(f'SELECT id FROM public."{async_etl_table}"')
        assert rows[0]["id"] == 11  # 0 + 1 + 10

    async def test_async_run_empty_dataframe(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() with a zero-row source records success with 0 rows_loaded."""
        p = Pipeline(
            name="asc_empty",
            source="SELECT 1 AS id, 'e' AS val WHERE FALSE",
            target=async_etl_table,
            load_mode="replace",
        )
        r = await async_db.etl.run(p)
        assert r.status == "success"
        assert r.rows_extracted == 0
        assert r.rows_loaded == 0

    async def test_async_run_upsert_mode(self, async_db, cleanup_async_pipeline_runs):
        """async run() with load_mode='upsert' inserts/updates via conflict columns."""
        upsert_tbl = f"etl_upsert_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{upsert_tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            # Seed a row
            await async_db.execute(
                f"INSERT INTO public.\"{upsert_tbl}\" (id, val) VALUES (1, 'old')",
                autocommit=True,
            )
            p = Pipeline(
                name="asc_upsert",
                source="SELECT 1 AS id, 'new' AS val",
                target=upsert_tbl,
                load_mode="upsert",
                conflict_columns=["id"],
            )
            r = await async_db.etl.run(p)
            assert r.status == "success"
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{upsert_tbl}" CASCADE', autocommit=True
            )

    async def test_async_run_append_mode(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() with load_mode='append' adds rows without truncating."""
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_table}\" (id, val) VALUES (1, 'existing')",
            autocommit=True,
        )
        p = Pipeline(
            name="asc_append",
            source="SELECT 2 AS id, 'new' AS val",
            target=async_etl_table,
            load_mode="append",
        )
        r = await async_db.etl.run(p)
        assert r.status == "success"
        rows = await async_db.execute(
            f'SELECT COUNT(*) AS cnt FROM public."{async_etl_table}"'
        )
        assert rows[0]["cnt"] == 2

    async def test_async_run_target_not_found_upsert(
        self, async_db, cleanup_async_pipeline_runs
    ):
        """async run() raises ETLTargetNotFoundError when upsert target doesn't exist."""
        from pycopg.exceptions import ETLTargetNotFoundError

        p = Pipeline(
            name="asc_no_target",
            source="SELECT 1 AS id, 'v' AS val",
            target="nonexistent_table_xyz_99",
            load_mode="upsert",
            conflict_columns=["id"],
        )
        with pytest.raises(ETLTargetNotFoundError):
            await async_db.etl.run(p)

    async def test_async_run_exception_records_failed_status(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """async run() records status='failed' in pipeline_runs when an error occurs."""
        from pycopg.exceptions import ETLTransformError

        def bad_transform(df):
            raise ValueError("deliberate transform error")

        p = Pipeline(
            name="asc_exc",
            source="SELECT 1 AS id, 'e' AS val",
            target=async_etl_table,
            load_mode="replace",
            transform=bad_transform,
        )
        with pytest.raises(ETLTransformError):
            await async_db.etl.run(p)

        # The run should be recorded as 'failed' in pipeline_runs
        rows = await async_db.execute(
            "SELECT status FROM pipeline_runs WHERE pipeline_name = %s ORDER BY run_id DESC LIMIT 1",
            ["asc_exc"],
        )
        assert rows[0]["status"] == "failed"

    # -----------------------------------------------------------------------
    # Phase 28 — async incremental ETL parity tests (ETL-INC-03/04/07/08/09/11)
    # Mirrors the sync tests in TestRunResultSurface; D-A3 strict parity.
    # -----------------------------------------------------------------------

    async def test_async_non_incremental_run_watermark_fields_none(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """D-A1: async non-incremental run() returns watermark_used=None and watermark_recorded=None."""
        p = Pipeline(
            name="awm_noninc_fields",
            source="SELECT 1 AS id, 'a' AS val",
            target=async_etl_table,
            load_mode="replace",
        )
        result = await async_db.etl.run(p)
        assert result.watermark_used is None
        assert result.watermark_recorded is None

    async def test_async_incremental_first_run_watermark_used_none(
        self, async_db, cleanup_async_pipeline_runs, async_etl_src
    ):
        """ETL-INC-07: first async incremental run has watermark_used=None (no prior watermark)."""
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (3, 'a'), (7, 'b')",
            autocommit=True,
        )
        tbl = f"etl_awm_first_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="awm_first_used",
                source=f'SELECT * FROM public."{async_etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            result = await async_db.etl.run(p)
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )
        assert result.watermark_used is None  # first run — no prior watermark
        assert result.watermark_recorded == 7  # max(id)

    async def test_async_incremental_second_run_pulls_only_new_rows(
        self, async_db, cleanup_async_pipeline_runs, async_etl_src
    ):
        """ETL-INC-03: async second run extracts only rows with col > prior watermark."""
        # First run: seed rows 1, 3, 5 → watermark = 5
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (1, 'a'), (3, 'b'), (5, 'c')",
            autocommit=True,
        )
        tbl = f"etl_awm_2nd_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="awm_second_run",
                source=f'SELECT * FROM public."{async_etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            result1 = await async_db.etl.run(p)
            assert result1.watermark_recorded == 5

            # Insert rows below (2) and above (6, 8) the prior watermark
            await async_db.execute(
                f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (2, 'below'), (6, 'new1'), (8, 'new2')",
                autocommit=True,
            )
            result2 = await async_db.etl.run(p)
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

        # Only rows with id > 5 should have been extracted
        assert result2.rows_extracted == 2  # ids 6 and 8
        assert result2.watermark_used == 5  # floor from first run
        assert result2.watermark_recorded == 8  # new max

    async def test_async_incremental_watermark_as_bound_param(
        self, async_db, cleanup_async_pipeline_runs, async_etl_src
    ):
        """SC-1 / T-28-A1: async watermark value is a bound param, never interpolated into SQL.

        DEBT-01 fixture-isolation note: uses a local ``captured_calls`` spy list
        (equivalent to ``mock.call_args_list``) rather than ``mock.call_args``
        to avoid the ~2.7% flake from mock call-order sensitivity when tests run
        in randomized order. Asserts on the last entry to target the exact call.
        """
        from unittest.mock import patch

        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (10, 'x')",
            autocommit=True,
        )
        tbl = f"etl_awm_param_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="awm_param_check",
                source=f'SELECT * FROM public."{async_etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            await async_db.etl.run(p)  # first run, watermark=10

            # DEBT-01: local spy list (call_args_list equivalent) captures calls
            # in insertion order; fresh per test invocation — no cross-test leakage.
            captured_calls = []
            original_to_dataframe = async_db.to_dataframe

            async def spy_to_dataframe(**kwargs):
                captured_calls.append(kwargs)
                return await original_to_dataframe(**kwargs)

            with patch.object(async_db, "to_dataframe", side_effect=spy_to_dataframe):
                await async_db.etl.run(
                    p
                )  # second run — should use wm=10 as bound param
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

        # The second-run call should have bound the watermark as a param (not in SQL text)
        assert len(captured_calls) >= 1
        last_call = captured_calls[-1]  # explicit last-call assertion (DEBT-01 fix)
        params = last_call.get("params") or {}
        sql = last_call.get("sql", "")
        # The watermark VALUE travels as a bound param, and the SQL carries the
        # ``:wm`` placeholder rather than the interpolated value. Asserting on the
        # placeholder (not "10" not in sql) is robust to random table-name hex
        # suffixes that can incidentally contain the digit string.
        assert "wm" in params, "watermark must be a bound param 'wm'"
        assert params["wm"] == 10, "the watermark value must be carried in the params"
        assert ":wm" in sql, "SQL must reference the watermark via the :wm bind"

    async def test_async_incremental_run_result_watermark_fields(
        self, async_db, cleanup_async_pipeline_runs, async_etl_src
    ):
        """ETL-INC-07: async first run watermark_used=None/recorded=max; second run watermark_used=prior."""
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (2, 'a'), (9, 'b')",
            autocommit=True,
        )
        tbl = f"etl_awm_fields_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="awm_result_fields",
                source=f'SELECT * FROM public."{async_etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            r1 = await async_db.etl.run(p)
            # Insert new rows above watermark
            await async_db.execute(
                f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (15, 'c')",
                autocommit=True,
            )
            r2 = await async_db.etl.run(p)
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

        assert r1.watermark_used is None
        assert r1.watermark_recorded == 9
        assert r2.watermark_used == 9  # prior recorded
        assert r2.watermark_recorded == 15

    async def test_async_incremental_history_surfaces_watermark_recorded(
        self, async_db, cleanup_async_pipeline_runs, async_etl_src
    ):
        """ETL-INC-08: async history()/last_run() surface watermark_recorded, watermark_used=None."""
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (4, 'a'), (12, 'b')",
            autocommit=True,
        )
        tbl = f"etl_awm_hist_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="awm_hist_surface",
                source=f'SELECT * FROM public."{async_etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            r = await async_db.etl.run(p)
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

        hist = await async_db.etl.history("awm_hist_surface")
        last = await async_db.etl.last_run("awm_hist_surface")
        assert len(hist) == 1
        assert hist[0].watermark_recorded == r.watermark_recorded
        assert hist[0].watermark_used is None  # stored rows always None
        assert last is not None
        assert last.watermark_recorded == r.watermark_recorded
        assert last.watermark_used is None

    async def test_async_incremental_dry_run_applies_filter_and_sets_watermark_fields(
        self, async_db, cleanup_async_pipeline_runs, async_etl_src
    ):
        """ETL-INC-09: async dry_run on incremental pipeline reads prior watermark, filters, reports fields, no row written."""
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (1, 'a'), (5, 'b'), (10, 'c')",
            autocommit=True,
        )
        tbl = f"etl_awm_dry_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="awm_dry_inc",
                source=f'SELECT * FROM public."{async_etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            await async_db.etl.run(p)  # first real run: watermark = 10
            prior_wm = await async_db.etl._read_watermark("awm_dry_inc")
            assert prior_wm == 10

            # Insert new rows
            await async_db.execute(
                f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (15, 'd'), (20, 'e')",
                autocommit=True,
            )

            # Count pipeline_runs before dry_run
            count_before = (
                await async_db.execute("SELECT COUNT(*) AS n FROM pipeline_runs")
            )[0]["n"]
            dry_result = await async_db.etl.run(p, dry_run=True)
            count_after = (
                await async_db.execute("SELECT COUNT(*) AS n FROM pipeline_runs")
            )[0]["n"]
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

        assert dry_result.status == "dry_run"
        assert dry_result.run_id is None
        assert dry_result.rows_extracted == 2  # only ids 15, 20 (above watermark 10)
        assert dry_result.watermark_used == 10
        assert dry_result.watermark_recorded == 20  # max of filtered batch
        assert count_after == count_before  # no new pipeline_runs row

    async def test_async_incremental_dry_run_empty_filtered_batch(
        self, async_db, cleanup_async_pipeline_runs, async_etl_src
    ):
        """ETL-INC-09: async dry_run when filtered batch is empty has watermark_recorded=None."""
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (100, 'z')",
            autocommit=True,
        )
        tbl = f"etl_awm_drye_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="awm_dry_empty",
                source=f'SELECT * FROM public."{async_etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            await async_db.etl.run(p)  # watermark = 100 — no rows above this
            dry_result = await async_db.etl.run(
                p, dry_run=True
            )  # no new rows above 100
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

        assert dry_result.watermark_used == 100
        assert dry_result.watermark_recorded is None  # empty filtered batch
        assert dry_result.rows_extracted == 0

    async def test_async_incremental_tz_aware_offset_preserved_second_run(
        self, async_db, cleanup_async_pipeline_runs
    ):
        """ETL-INC-07 / D-A3: async tz-aware datetime watermark offset is preserved on second-run filter and watermark_recorded."""
        ts1_sql = "TIMESTAMPTZ '2026-01-10 10:00:00.000000+02:00'"
        ts2_sql = "TIMESTAMPTZ '2026-01-20 15:30:00.123456+02:00'"

        tbl = f"etl_atz_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (ts TIMESTAMPTZ PRIMARY KEY, tag TEXT)',
            autocommit=True,
        )
        pipe_name = f"awm_tz_second_{uuid.uuid4().hex[:8]}"
        try:
            # First run: load row with ts1 as watermark
            p = Pipeline(
                name=pipe_name,
                source=f"SELECT {ts1_sql} AS ts, 'first' AS tag",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["ts"],
                incremental_column="ts",
            )
            r1 = await async_db.etl.run(p)
            assert r1.watermark_recorded is not None
            assert r1.watermark_recorded.tzinfo is not None

            # Second run: source has both ts1 and ts2; filter should exclude ts1
            p2 = Pipeline(
                name=pipe_name,
                source=f"SELECT {ts1_sql} AS ts, 'first' AS tag UNION ALL SELECT {ts2_sql}, 'second'",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["ts"],
                incremental_column="ts",
            )
            r2 = await async_db.etl.run(p2)
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

        # watermark_used = ts1; only ts2 extracted
        assert r2.rows_extracted == 1
        assert r2.watermark_used is not None
        assert r2.watermark_used.tzinfo is not None  # tz preserved on filter floor
        # utcoffset intact (no UTC normalization)
        assert r2.watermark_used.utcoffset() == r1.watermark_recorded.utcoffset()
        assert r2.watermark_recorded is not None
        assert (
            r2.watermark_recorded.tzinfo is not None
        )  # tz preserved on new high-water
        # microseconds preserved on watermark_recorded
        assert r2.watermark_recorded.microsecond == 123456

    # -----------------------------------------------------------------------
    # ETL-INC-04 async guard parity tests (D-A3: byte-for-byte ETLError text)
    # -----------------------------------------------------------------------

    async def test_async_incremental_column_missing_raises_etlerror(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """D-06 / D-A3: async missing incremental_column raises ETLError with identical message to sync."""
        p = Pipeline(
            name="awm_missing_col",
            source="SELECT 1 AS id",
            target=async_etl_table,
            load_mode="upsert",
            conflict_columns=["id"],
            incremental_column="missing_col",
        )
        with pytest.raises(ETLError, match="missing_col"):
            await async_db.etl.run(p)

        # Assert the message text is byte-for-byte identical to sync (D-A3)
        try:
            await async_db.etl.run(p)
        except ETLError as exc:
            async_msg = str(exc)
        expected_msg = (
            "incremental_column 'missing_col' not found in extracted batch "
            "columns ['id'] (ETL-INC-04)"
        )
        assert async_msg == expected_msg, (
            f"ETLError message must be byte-for-byte identical to sync.\n"
            f"Got:      {async_msg!r}\n"
            f"Expected: {expected_msg!r}"
        )

    async def test_async_float_incremental_column_raises_etlerror(
        self, async_db, cleanup_async_pipeline_runs
    ):
        """WR-01 / D-A3: async float incremental_column raises ETLError with identical message to sync."""
        tbl = f"etl_awmf_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, score NUMERIC)',
            autocommit=True,
        )
        try:
            p = Pipeline(
                name="awm_float_col",
                source="SELECT 1 AS id, 99.99::float8 AS score",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="score",
            )
            with pytest.raises(ETLError, match="float"):
                await async_db.etl.run(p)

            # Assert the message text is byte-for-byte identical to sync (D-A3)
            from pycopg.etl import _WATERMARK_SUPPORTED

            try:
                await async_db.etl.run(p)
            except ETLError as exc:
                async_msg = str(exc)
            expected_msg = (
                f"incremental_column 'score' has float dtype; float "
                f"watermarks are not supported (cast to INTEGER or "
                f"TIMESTAMP). Supported types are {_WATERMARK_SUPPORTED}"
            )
            assert async_msg == expected_msg, (
                f"ETLError message must be byte-for-byte identical to sync.\n"
                f"Got:      {async_msg!r}\n"
                f"Expected: {expected_msg!r}"
            )
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

    async def test_async_all_null_incremental_column_preserves_watermark(
        self, async_db, cleanup_async_pipeline_runs, async_etl_src
    ):
        """WR-02 / D-A3: async all-NULL incremental column records no watermark (no crash), prior W0 preserved."""
        # Seed a prior successful run with W0 = 7
        await async_db.execute(
            f"INSERT INTO public.\"{async_etl_src}\" (id, val) VALUES (7, 'seed')",
            autocommit=True,
        )
        tbl = f"etl_awmn_{uuid.uuid4().hex[:8]}"
        await async_db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT, wm INTEGER)',
            autocommit=True,
        )
        try:
            p_seed = Pipeline(
                name="awm_allnull_test",
                source=f'SELECT id, val FROM public."{async_etl_src}"',
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="id",
            )
            await async_db.etl.run(p_seed)
            w0 = await async_db.etl._read_watermark("awm_allnull_test")
            assert w0 == 7

            # A non-empty batch whose incremental_column (wm) is entirely NULL:
            # df[wm].max() is NaN — must NOT crash; records no watermark.
            p_null = Pipeline(
                name="awm_allnull_test",
                source="SELECT 2 AS id, NULL::integer AS wm",
                target=tbl,
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="wm",
            )
            result = await async_db.etl.run(p_null)
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True
            )

        nrows = await async_db.execute(
            "SELECT status, watermark FROM pipeline_runs WHERE run_id = %s",
            [result.run_id],
        )
        assert nrows[0]["status"] == "success"
        assert nrows[0]["watermark"] is None
        # Prior success watermark must be preserved
        assert await async_db.etl._read_watermark("awm_allnull_test") == w0

    # -----------------------------------------------------------------------
    # Phase 39 Plan 01 — COV-01: async dry_run watermark + transform branch tests
    # (etl.py L1891, L1900, L1902, L1916-1919, L1922-1925)
    # -----------------------------------------------------------------------

    async def test_async_dry_run_incremental_string_watermark(
        self, async_db, cleanup_async_pipeline_runs
    ):
        """Covers etl.py L1902 — str watermark branch in async dry_run."""
        src = f"a_str_wm_src_{uuid.uuid4().hex[:8]}"
        dst = f"a_str_wm_dst_{uuid.uuid4().hex[:8]}"
        try:
            await async_db.execute(
                f'CREATE TABLE public."{src}" (code TEXT, val INTEGER)',
                autocommit=True,
            )
            await async_db.execute(
                f"INSERT INTO public.\"{src}\" VALUES ('beta', 2), ('alpha', 1)",
                autocommit=True,
            )
            await async_db.execute(
                f'CREATE TABLE public."{dst}" (code TEXT, val INTEGER)',
                autocommit=True,
            )
            p = Pipeline(
                name=f"a_str_wm_{uuid.uuid4().hex[:6]}",
                source=src,
                target=dst,
                load_mode="upsert",
                conflict_columns=["code"],
                incremental_column="code",
            )
            await async_db.etl.init()  # ensure pipeline_runs exists before dry_run on incremental
            result = await async_db.etl.run(p, dry_run=True)
            assert result.status == "dry_run"
            assert isinstance(result.watermark_recorded, str)
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{src}" CASCADE', autocommit=True
            )
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{dst}" CASCADE', autocommit=True
            )

    async def test_async_dry_run_incremental_timestamp_watermark(
        self, async_db, cleanup_async_pipeline_runs
    ):
        """Covers etl.py L1900 — Timestamp.to_pydatetime() branch in async dry_run."""
        src = f"a_ts_wm_src_{uuid.uuid4().hex[:8]}"
        dst = f"a_ts_wm_dst_{uuid.uuid4().hex[:8]}"
        try:
            await async_db.execute(
                f'CREATE TABLE public."{src}" (ts TIMESTAMP, val INTEGER)',
                autocommit=True,
            )
            await async_db.execute(
                f"INSERT INTO public.\"{src}\" VALUES ('2026-01-01 10:00:00', 1), ('2026-01-02 12:00:00', 2)",
                autocommit=True,
            )
            await async_db.execute(
                f'CREATE TABLE public."{dst}" (ts TIMESTAMP, val INTEGER)',
                autocommit=True,
            )
            p = Pipeline(
                name=f"a_ts_wm_{uuid.uuid4().hex[:6]}",
                source=src,
                target=dst,
                load_mode="upsert",
                conflict_columns=["ts"],
                incremental_column="ts",
            )
            await async_db.etl.init()  # ensure pipeline_runs exists before dry_run on incremental
            result = await async_db.etl.run(p, dry_run=True)
            assert result.status == "dry_run"
            assert isinstance(result.watermark_recorded, datetime)
        finally:
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{src}" CASCADE', autocommit=True
            )
            await async_db.execute(
                f'DROP TABLE IF EXISTS public."{dst}" CASCADE', autocommit=True
            )

    async def test_async_dry_run_transform_single_callable(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """Covers etl.py L1916-1919 — single callable transform in async dry_run path."""

        def double_val(df):
            df = df.copy()
            df["id"] = df["id"] * 2
            return df

        p = Pipeline(
            name=f"a_dry_transform_single_{uuid.uuid4().hex[:6]}",
            source="SELECT 5 AS id, 'x' AS val",
            target=async_etl_table,
            load_mode="replace",
            transform=double_val,
        )
        result = await async_db.etl.run(p, dry_run=True)
        assert result.status == "dry_run"
        assert result.rows_extracted == 1

    async def test_async_dry_run_transform_step_raises(
        self, async_db, cleanup_async_pipeline_runs, async_etl_table
    ):
        """Covers etl.py L1922-1925 — transform step raises ETLTransformError in async dry_run."""

        def bad_transform(df):
            raise ValueError("async boom")

        p = Pipeline(
            name=f"a_dry_transform_raises_{uuid.uuid4().hex[:6]}",
            source="SELECT 1 AS id, 'v' AS val",
            target=async_etl_table,
            load_mode="replace",
            transform=bad_transform,
        )
        with pytest.raises(ETLTransformError):
            await async_db.etl.run(p, dry_run=True)


# ---------------------------------------------------------------------------
# Phase 38 Plan 02: ETL COPY-path tests (PERF-02 / D-02 / D-02c)
# ---------------------------------------------------------------------------


class TestETLCopyPath:
    """Behavioral tests for the COPY load seam introduced in Plan 38-02.

    Verifies that append/replace modes stream rows via COPY (exact rows_loaded
    from cur.rowcount), NaN/NaT cells land as SQL NULL, and upsert continues
    to work via INSERT ON CONFLICT (D-02c).  No timing assertions (D-06).
    """

    # ------------------------------------------------------------------
    # COPY path — exact rows_loaded for append and replace (PERF-02 / D-02b)
    # ------------------------------------------------------------------

    def test_etl_run_copy_path_rows_loaded_replace(self, db, cleanup_pipeline_runs):
        """replace mode: result.rows_loaded equals exact DataFrame row count (COPY rowcount).

        Proves the COPY seam sets cur.rowcount correctly through
        _stream_df_copy on the transaction cursor (D-02 / D-02b).
        """
        tbl = f"etl_copy_rep_{uuid.uuid4().hex[:8]}"
        expected_rows = 5
        p = Pipeline(
            name="copy_replace_rows",
            source=f"SELECT generate_series(1, {expected_rows}) AS id, 'v' AS val",
            target=tbl,
            load_mode="replace",
        )
        try:
            result = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        assert result.status == "success"
        assert result.rows_loaded == expected_rows

    def test_etl_run_copy_path_rows_loaded_append(self, db, cleanup_pipeline_runs):
        """append mode: result.rows_loaded equals exact DataFrame row count (COPY rowcount).

        Proves the COPY seam sets cur.rowcount correctly through
        _stream_df_copy on the transaction cursor (D-02 / D-02b).
        """
        tbl = f"etl_copy_app_{uuid.uuid4().hex[:8]}"
        expected_rows = 3
        # Create the target table first (append requires pre-existing table)
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
            autocommit=True,
        )
        p = Pipeline(
            name="copy_append_rows",
            source=f"SELECT generate_series(1, {expected_rows}) AS id, 'w' AS val",
            target=tbl,
            load_mode="append",
        )
        try:
            result = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        assert result.status == "success"
        assert result.rows_loaded == expected_rows

    # ------------------------------------------------------------------
    # NaN / NaT → SQL NULL via ETL COPY path (D-02 / PERF-02)
    # ------------------------------------------------------------------

    def test_etl_run_copy_nan_null(self, db, cleanup_pipeline_runs):
        """NaN in a float column and NaT in a datetime column land as SQL NULL via COPY path.

        Uses a replace Pipeline so the target table is created by the ETL
        seam (head(0).to_sql DDL step).  Confirms the _stream_df_copy null-
        mask mechanism works through the ETL seam, not just from_dataframe.
        """
        tbl = f"etl_copy_nan_{uuid.uuid4().hex[:8]}"

        def inject_nulls(df):
            """Add a float column with NaN and a datetime column with NaT."""
            df = df.copy()
            df["score"] = [float("nan"), 2.5]
            df["ts"] = pd.to_datetime([None, "2024-06-01"])
            return df

        p = Pipeline(
            name="copy_nan_null",
            source="SELECT generate_series(1, 2) AS id",
            target=tbl,
            load_mode="replace",
            transform=inject_nulls,
        )
        try:
            result = db.etl.run(p)
            # Read back the rows and check nulls
            rows = db.execute(f'SELECT id, score, ts FROM public."{tbl}" ORDER BY id')
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        assert result.status == "success"
        assert result.rows_loaded == 2

        # Row 1: score is NaN → NULL, ts is NaT → NULL
        assert rows[0]["score"] is None, "NaN in float column must land as SQL NULL"
        assert rows[0]["ts"] is None, "NaT in datetime column must land as SQL NULL"

        # Row 2: score and ts are real values
        assert rows[1]["score"] == pytest.approx(2.5)
        assert rows[1]["ts"] is not None

    # ------------------------------------------------------------------
    # upsert path still works via INSERT ON CONFLICT (D-02c)
    # ------------------------------------------------------------------

    def test_etl_run_upsert_unchanged(self, db, cleanup_pipeline_runs):
        """upsert mode: INSERT ON CONFLICT path unchanged after COPY seam rewrite (D-02c).

        Ensures that routing append/replace through COPY did not accidentally
        break the upsert path, which must stay on _build_upsert_sql.
        """
        tbl = f"etl_copy_upsert_{uuid.uuid4().hex[:8]}"
        db.execute(
            f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val TEXT)',
            autocommit=True,
        )
        # Seed one row
        db.execute(f"INSERT INTO public.\"{tbl}\" VALUES (1, 'old')", autocommit=True)

        p = Pipeline(
            name="copy_upsert_check",
            source="SELECT 1 AS id, 'new' AS val",
            target=tbl,
            load_mode="upsert",
            conflict_columns=["id"],
        )
        try:
            result = db.etl.run(p)
            rows = db.execute(f'SELECT id, val FROM public."{tbl}"')
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

        assert result.status == "success"
        assert result.rows_loaded == 1
        assert len(rows) == 1
        assert rows[0]["id"] == 1
        assert rows[0]["val"] == "new"  # upsert updated the existing row
