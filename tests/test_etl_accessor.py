"""Tests for ETLAccessor — unit (param order / status string) + DB integration (SC-1..SC-4)."""

import traceback
import uuid
from datetime import datetime

import pandas as pd
import pytest
from psycopg.rows import dict_row

from pycopg import Database, queries
from pycopg.etl import ETLAccessor, Pipeline
from pycopg.exceptions import ETLTargetNotFoundError, ETLTransformError

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
            run_id = db.etl.run(p)
        finally:
            db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

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
        """run() accepts a Pipeline and returns an int run_id."""
        p = Pipeline(
            name="sig_test",
            source="SELECT 1 AS id, 'a' AS val",
            target=etl_table,
        )
        run_id = db.etl.run(p)
        assert isinstance(run_id, int)

    def test_run_derives_pipeline_name_from_pipeline(
        self, db, cleanup_pipeline_runs, etl_table
    ):
        """run() stores pipeline.name in the pipeline_runs row."""
        p = Pipeline(
            name="named_pipeline",
            source="SELECT 1 AS id, 'x' AS val",
            target=etl_table,
        )
        run_id = db.etl.run(p)
        rows = db.execute(
            "SELECT pipeline_name FROM pipeline_runs WHERE run_id = %s",
            [run_id],
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
        run_id = db.etl.run(p)
        rows = db.execute(
            "SELECT rows_extracted, rows_loaded FROM pipeline_runs WHERE run_id = %s",
            [run_id],
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
        run_id = db.etl.run(p)
        rows = db.execute(
            "SELECT status FROM pipeline_runs WHERE run_id = %s",
            [run_id],
        )
        assert rows[0]["status"] == "success"
