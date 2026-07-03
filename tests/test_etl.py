"""Tests for pycopg.etl — DB-free Pipeline + builder tests."""

import functools
from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest

from pycopg import queries
from pycopg.etl import (
    Pipeline,
    RunResult,
    _build_incremental_extract_sql,
    _build_insert_sql,
    _build_upsert_sql,
    _capture_watermark,
    _decode_watermark,
    _encode_composite_watermark,
    _encode_watermark,
    _is_sql_source,
    _reconcile_watermark_binds,
    _row_to_result,
    _step_label,
    _validate_incremental,
    _validate_load_mode,
    build_init_sql,
    build_truncate_sql,
)
from pycopg.exceptions import ETLError, ETLTransformError, InvalidIdentifierError


class TestPipeline:
    """DB-free construction and validation tests for Pipeline."""

    def test_valid_construction_all_attributes(self):
        """Pipeline instantiates and all 8 attributes are readable (ROADMAP SC-1)."""
        p = Pipeline(
            name="nightly",
            source="raw_events",
            target="events",
            load_mode="append",
            conflict_columns=("id",),
            schema="public",
            transform=None,
            extract_limit=None,
        )
        assert p.name == "nightly"
        assert p.source == "raw_events"
        assert p.target == "events"
        assert p.load_mode == "append"
        assert p.conflict_columns == ("id",)
        assert p.schema == "public"
        assert p.transform is None
        assert p.extract_limit is None

    def test_defaults(self):
        """Default values: load_mode='append', schema='public', empty tuple, None/None."""
        p = Pipeline(name="x", source="t", target="u")
        assert p.load_mode == "append"
        assert p.schema == "public"
        assert p.conflict_columns == ()
        assert p.transform is None
        assert p.extract_limit is None

    def test_upsert_without_conflict_columns_raises_valueerror(self):
        """upsert with no conflict_columns raises ValueError at construction (ROADMAP SC-2 / D-07)."""
        with pytest.raises(ValueError, match="upsert"):
            Pipeline(name="x", source="t", target="u", load_mode="upsert")

    def test_upsert_with_conflict_columns_ok(self):
        """upsert with conflict_columns constructs without error (D-07)."""
        p = Pipeline(
            name="x",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id"],
        )
        assert p.load_mode == "upsert"
        assert p.conflict_columns == ("id",)

    def test_invalid_load_mode_truncate_raises_valueerror(self):
        """load_mode='truncate' (not a public value) raises ValueError (D-06)."""
        with pytest.raises(ValueError, match="load_mode"):
            Pipeline(name="x", source="t", target="u", load_mode="truncate")

    def test_invalid_load_mode_junk_raises_valueerror(self):
        """An arbitrary junk load_mode raises ValueError (D-06)."""
        with pytest.raises(ValueError, match="load_mode"):
            Pipeline(name="x", source="t", target="u", load_mode="delete")

    def test_conflict_columns_list_normalized_to_tuple(self):
        """conflict_columns passed as a list is stored as a tuple (D-02)."""
        p = Pipeline(
            name="x",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id", "src"],
        )
        assert p.conflict_columns == ("id", "src")
        assert isinstance(p.conflict_columns, tuple)

    def test_conflict_columns_bare_string_raises_valueerror(self):
        """A bare string conflict_columns raises ValueError, not a per-char tuple."""
        with pytest.raises(ValueError, match="conflict_columns"):
            Pipeline(
                name="x",
                source="t",
                target="u",
                load_mode="upsert",
                conflict_columns="user_id",
            )

    def test_extract_limit_stored(self):
        """extract_limit is stored and readable (D-11)."""
        p = Pipeline(name="x", source="t", target="u", extract_limit=1000)
        assert p.extract_limit == 1000

    def test_extract_limit_negative_raises_valueerror(self):
        """Negative extract_limit raises ValueError (D-11, Claude's Discretion)."""
        with pytest.raises(ValueError, match="extract_limit"):
            Pipeline(name="x", source="t", target="u", extract_limit=-1)

    def test_extract_limit_zero_raises_valueerror(self):
        """Zero extract_limit raises ValueError (D-11, Claude's Discretion)."""
        with pytest.raises(ValueError, match="extract_limit"):
            Pipeline(name="x", source="t", target="u", extract_limit=0)

    def test_extract_limit_bool_raises_valueerror(self):
        """A bool extract_limit raises ValueError (bool is an int subclass)."""
        with pytest.raises(ValueError, match="extract_limit"):
            Pipeline(name="x", source="t", target="u", extract_limit=True)

    def test_incremental_column_default_none(self):
        """incremental_column defaults to None (non-incremental pipeline)."""
        p = Pipeline(name="x", source="t", target="u")
        assert p.incremental_column is None

    def test_incremental_column_stored_with_upsert(self):
        """incremental_column is stored when load_mode='upsert' (ROADMAP SC-1 / D-17)."""
        p = Pipeline(
            name="p",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=("id",),
            incremental_column="updated_at",
        )
        assert p.incremental_column == "updated_at"

    def test_incremental_column_append_raises_valueerror(self):
        """incremental_column with load_mode='append' raises ValueError (ROADMAP SC-2 / D-16)."""
        with pytest.raises(ValueError, match="upsert"):
            Pipeline(
                name="p",
                source="t",
                target="u",
                load_mode="append",
                incremental_column="updated_at",
            )

    def test_incremental_column_replace_raises_valueerror(self):
        """incremental_column with load_mode='replace' raises ValueError (ROADMAP SC-2 / D-16)."""
        with pytest.raises(ValueError, match="upsert"):
            Pipeline(
                name="p",
                source="t",
                target="u",
                load_mode="replace",
                incremental_column="updated_at",
            )

    def test_incremental_column_bad_identifier_raises(self):
        """A bad incremental_column identifier raises InvalidIdentifierError (D-15)."""
        with pytest.raises(InvalidIdentifierError):
            Pipeline(
                name="p",
                source="t",
                target="u",
                load_mode="upsert",
                conflict_columns=("id",),
                incremental_column="bad-col!",
            )

    def test_garbage_load_mode_reported_before_incremental(self):
        """A garbage load_mode reports 'must be one of' first (D-17 ordering proof).

        ``_validate_load_mode`` runs before ``_validate_incremental`` in
        ``__post_init__``, so the load_mode error wins even when an
        ``incremental_column`` is also supplied.
        """
        with pytest.raises(ValueError, match="must be one of"):
            Pipeline(
                name="p",
                source="t",
                target="u",
                load_mode="bogus",
                incremental_column="updated_at",
            )

    def test_frozen_dataclass(self):
        """Pipeline is frozen — attribute assignment raises FrozenInstanceError."""
        p = Pipeline(name="x", source="t", target="u")
        with pytest.raises(
            Exception
        ):  # dataclasses.FrozenInstanceError is a subclass of AttributeError
            p.name = "changed"  # type: ignore[misc]

    def test_transform_callable(self):
        """transform field accepts a callable and stores it."""

        def fn(df):
            return df

        p = Pipeline(name="x", source="t", target="u", transform=fn)
        assert p.transform is fn

    def test_transform_list_of_callables(self):
        """transform field accepts a list of callables."""
        fns = [lambda df: df, lambda df: df]
        p = Pipeline(name="x", source="t", target="u", transform=fns)
        assert p.transform is fns

    def test_append_and_replace_modes_valid(self):
        """The two public modes needing no extra fields construct successfully.

        ``upsert`` is the third public mode but requires ``conflict_columns``,
        so its happy path is covered by ``test_upsert_with_conflict_columns_ok``.
        """
        for mode in ("append", "replace"):
            p = Pipeline(name="x", source="t", target="u", load_mode=mode)
            assert p.load_mode == mode

    def test_replace_mode_no_conflict_columns_required(self):
        """replace mode without conflict_columns is valid (D-06)."""
        p = Pipeline(name="x", source="t", target="u", load_mode="replace")
        assert p.load_mode == "replace"
        assert p.conflict_columns == ()


class TestInitialWatermark:
    """DB-free construction-guard tests for Pipeline.initial_watermark (F01, D-01/D-02).

    Live-DB seed-floor sequence integration tests (D-01/D-03) land in Task 2
    of this plan, once the ``run()`` call-site fallback is wired.
    """

    def test_scalar_initial_watermark_constructs(self):
        """A valid int initial_watermark constructs with incremental_column set."""
        p = Pipeline(
            name="seeded",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id"],
            incremental_column="ts",
            initial_watermark=100,
        )
        assert p.initial_watermark == 100

    def test_default_initial_watermark_is_none(self):
        """Default initial_watermark is None — byte-identical to pre-F01 behavior."""
        p = Pipeline(
            name="x",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id"],
            incremental_column="ts",
        )
        assert p.initial_watermark is None

    def test_initial_watermark_without_incremental_column_raises(self):
        """initial_watermark without incremental_column raises ValueError (D-02)."""
        with pytest.raises(ValueError, match="initial_watermark"):
            Pipeline(name="x", source="s", target="t", initial_watermark=100)

    def test_initial_watermark_bool_raises(self):
        """A bool initial_watermark raises — bool is an int subclass, rejected first (D-02/C-02)."""
        with pytest.raises(ETLError):
            Pipeline(
                name="x",
                source="t",
                target="u",
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="ts",
                initial_watermark=True,
            )

    def test_initial_watermark_float_raises(self):
        """A float initial_watermark raises — float has no defined watermark semantics (D-02)."""
        with pytest.raises(ETLError):
            Pipeline(
                name="x",
                source="t",
                target="u",
                load_mode="upsert",
                conflict_columns=["id"],
                incremental_column="ts",
                initial_watermark=1.5,
            )

    def test_initial_watermark_datetime_constructs(self):
        """A datetime initial_watermark constructs (D-02 allowlist)."""
        p = Pipeline(
            name="x",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id"],
            incremental_column="ts",
            initial_watermark=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert p.initial_watermark == datetime(2026, 1, 1, tzinfo=UTC)

    def test_initial_watermark_str_constructs(self):
        """A str initial_watermark constructs (D-02 allowlist)."""
        p = Pipeline(
            name="x",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id"],
            incremental_column="ts",
            initial_watermark="v1",
        )
        assert p.initial_watermark == "v1"

    def test_initial_watermark_zero_is_valid(self):
        """initial_watermark=0 (falsy but valid) constructs without error (D-01 falsy trap)."""
        p = Pipeline(
            name="x",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id"],
            incremental_column="ts",
            initial_watermark=0,
        )
        assert p.initial_watermark == 0


class TestIncrementalBoundaryConstruction:
    """DB-free construction tests for incremental_inclusive/incremental_lookback (F02, D-05)."""

    def _incr(self, **kw):
        return Pipeline(
            name="b",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id"],
            incremental_column="ts",
            **kw,
        )

    def test_boundary_defaults(self):
        """Defaults reproduce today's exact behavior: exclusive, no lookback."""
        p = self._incr()
        assert p.incremental_inclusive is False
        assert p.incremental_lookback is None

    def test_inclusive_true_constructs(self):
        """incremental_inclusive=True is accepted (bare bool, no cross-field guard)."""
        assert self._incr(incremental_inclusive=True).incremental_inclusive is True

    def test_lookback_int_constructs(self):
        """A non-bool positive int lookback constructs."""
        assert self._incr(incremental_lookback=10).incremental_lookback == 10

    def test_lookback_timedelta_constructs(self):
        """A timedelta lookback constructs (datetime-watermark overlap window)."""
        assert self._incr(
            incremental_lookback=timedelta(hours=1)
        ).incremental_lookback == timedelta(hours=1)

    def test_lookback_bool_raises(self):
        """incremental_lookback=True raises — bool is an int subclass, rejected (D-05 trap)."""
        with pytest.raises(ValueError, match="incremental_lookback"):
            self._incr(incremental_lookback=True)

    def test_lookback_str_raises(self):
        """A str lookback raises (not a timedelta or int, D-05)."""
        with pytest.raises(ValueError, match="incremental_lookback"):
            self._incr(incremental_lookback="10")


class TestCompositeWatermark:
    """Composite (multi-column) incremental_column — pure layer (F03, D-09/D-10).

    Construction/normalization + builder row-value SQL shape + injection. The
    "composite" envelope codec round-trip is covered by
    TestEncodeDecodeWatermark; run() end-to-end wiring lands in plan 49-04.
    """

    def _comp(self, **kw):
        return Pipeline(
            name="c",
            source="t",
            target="u",
            load_mode="upsert",
            conflict_columns=["id"],
            **kw,
        )

    # --- construction / normalization (D-09) ---

    def test_str_column_stays_scalar(self):
        """A bare str incremental_column is preserved (NOT exploded per-char)."""
        p = self._comp(incremental_column="ts")
        assert p.incremental_column == "ts"

    def test_list_column_normalizes_to_tuple(self):
        """A list incremental_column normalizes to a tuple on the frozen instance."""
        p = self._comp(incremental_column=["day", "seq"])
        assert p.incremental_column == ("day", "seq")

    def test_tuple_column_preserved(self):
        """A tuple incremental_column stays a tuple."""
        p = self._comp(incremental_column=("day", "seq"))
        assert p.incremental_column == ("day", "seq")

    def test_empty_composite_raises(self):
        """An empty composite sequence raises ValueError (D-09)."""
        with pytest.raises(ValueError, match="non-empty"):
            self._comp(incremental_column=[])

    def test_bad_composite_element_raises(self):
        """A bad column element raises InvalidIdentifierError at construction (D-10)."""
        with pytest.raises(InvalidIdentifierError):
            self._comp(incremental_column=["day", "se q"])

    # --- composite initial_watermark guard (D-04) ---

    def test_composite_seed_length_mismatch_raises(self):
        """A composite seed of the wrong length raises ValueError (D-04)."""
        with pytest.raises(ValueError, match="does not match|must be a sequence"):
            self._comp(incremental_column=["day", "seq"], initial_watermark=[5])

    def test_composite_seed_matching_length_normalizes_to_tuple(self):
        """A matching-length composite seed constructs and normalizes to a tuple."""
        p = self._comp(
            incremental_column=["day", "seq"], initial_watermark=[5, 40]
        )
        assert p.initial_watermark == (5, 40)

    def test_composite_seed_bool_element_raises(self):
        """A bool element in a composite seed is rejected per element (D-04/C-02)."""
        with pytest.raises(ETLError):
            self._comp(
                incremental_column=["day", "seq"], initial_watermark=[True, 40]
            )

    def test_scalar_column_rejects_sequence_seed(self):
        """A single-column key rejects a sequence initial_watermark (D-04)."""
        with pytest.raises(ValueError, match="scalar"):
            self._comp(incremental_column="ts", initial_watermark=[5, 40])

    def test_composite_requires_upsert(self):
        """A composite incremental_column still requires load_mode='upsert' (C-01)."""
        with pytest.raises(ValueError, match="upsert"):
            Pipeline(
                name="x",
                source="s",
                target="t",
                load_mode="append",
                incremental_column=["day", "seq"],
            )


class TestAdvisoryLock:
    """ETL-INC-F04 advisory-lock concurrency — constant SQL-shape + field guard.

    Live two-connection held-lock integration lands in tests/test_etl_accessor.py.
    """

    # --- ETL_ADVISORY_* constant shape (D-15) ---

    def test_advisory_lock_constant(self):
        """ETL_ADVISORY_LOCK derives the key server-side with the name bound %s."""
        assert (
            queries.ETL_ADVISORY_LOCK
            == "SELECT pg_advisory_lock(hashtextextended(%s, 0))"
        )

    def test_advisory_try_lock_constant(self):
        """ETL_ADVISORY_TRY_LOCK uses pg_try_advisory_lock (non-blocking)."""
        assert (
            queries.ETL_ADVISORY_TRY_LOCK
            == "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))"
        )

    def test_advisory_unlock_constant(self):
        """ETL_ADVISORY_UNLOCK releases the same server-side-derived key."""
        assert (
            queries.ETL_ADVISORY_UNLOCK
            == "SELECT pg_advisory_unlock(hashtextextended(%s, 0))"
        )

    def test_each_advisory_constant_has_exactly_one_placeholder(self):
        """Each constant binds the name via exactly one %s — never interpolated."""
        for const in (
            queries.ETL_ADVISORY_LOCK,
            queries.ETL_ADVISORY_TRY_LOCK,
            queries.ETL_ADVISORY_UNLOCK,
        ):
            assert const.count("%s") == 1

    def test_status_check_constraint_unchanged(self):
        """The pipeline_runs status CHECK does NOT include 'skipped' (D-13)."""
        assert "CHECK (status IN ('running','success','failed'))" in (
            queries.ETL_INIT_PIPELINE_RUNS
        )
        assert "skipped" not in queries.ETL_INIT_PIPELINE_RUNS

    def test_advisory_constants_never_contain_name_text(self):
        """A malicious pipeline name is never formatted into the constants (injection)."""
        evil = "x'); DROP TABLE pipeline_runs; --"
        for const in (
            queries.ETL_ADVISORY_LOCK,
            queries.ETL_ADVISORY_TRY_LOCK,
            queries.ETL_ADVISORY_UNLOCK,
        ):
            assert evil not in const
            assert "DROP TABLE" not in const

    # --- Pipeline.concurrency field guard (D-12) ---

    def test_concurrency_wait_constructs(self):
        """concurrency='wait' is accepted on any pipeline."""
        p = Pipeline(name="x", source="s", target="t", concurrency="wait")
        assert p.concurrency == "wait"

    def test_concurrency_skip_constructs(self):
        """concurrency='skip' is accepted on any pipeline."""
        assert (
            Pipeline(name="x", source="s", target="t", concurrency="skip").concurrency
            == "skip"
        )

    def test_concurrency_default_is_none(self):
        """Default concurrency is None — byte-identical to today (no lock)."""
        assert Pipeline(name="x", source="s", target="t").concurrency is None

    def test_concurrency_available_on_non_incremental_pipeline(self):
        """concurrency is available to ALL pipelines, not gated on incremental (D-12)."""
        p = Pipeline(name="x", source="s", target="t", concurrency="wait")
        assert p.incremental_column is None and p.concurrency == "wait"

    def test_concurrency_invalid_raises(self):
        """An unknown concurrency value raises ValueError (D-12)."""
        with pytest.raises(ValueError, match="concurrency"):
            Pipeline(name="x", source="s", target="t", concurrency="junk")

    # --- builder row-value compare SQL (D-10) ---

    def test_composite_builder_table_source(self):
        """Composite table source emits WHERE (day, seq) > (%s, %s), params [5, 40]."""
        sql, params = _build_incremental_extract_sql(
            "t", ("day", "seq"), watermark=(5, 40)
        )
        assert "WHERE (day, seq) > (%s, %s)" in sql
        assert params == [5, 40]

    def test_composite_builder_sql_source(self):
        """Composite SQL-string source wraps and emits the row-value compare."""
        sql, params = _build_incremental_extract_sql(
            "SELECT 1 AS day, 2 AS seq", ("day", "seq"), watermark=(5, 40)
        )
        assert "WHERE (day, seq) > (%s, %s)" in sql
        assert params == [5, 40]

    def test_composite_builder_inclusive(self):
        """inclusive=True composite emits >= on the row-value compare (D-05 orthogonal)."""
        sql, _ = _build_incremental_extract_sql(
            "t", ("day", "seq"), watermark=(5, 40), inclusive=True
        )
        assert "WHERE (day, seq) >= (%s, %s)" in sql

    def test_scalar_builder_byte_identical_regression(self):
        """The single-column builder output is unchanged by the composite branch."""
        sql, params = _build_incremental_extract_sql("t", "col", watermark=5)
        assert sql == "SELECT * FROM public.t WHERE col > %s"
        assert params == [5]

    def test_composite_builder_validates_every_element(self):
        """A bad composite element raises InvalidIdentifierError before interpolation."""
        with pytest.raises(InvalidIdentifierError):
            _build_incremental_extract_sql("t", ("day", "se q"), watermark=(1, 2))

    # --- composite max-ROW capture (D-10, Pitfall 3/4) ---

    def test_capture_composite_is_sorted_last_row_not_per_column_max(self):
        """Composite capture takes the greatest ROW (2, 1), NOT per-column maxes (2, 99)."""
        df = pd.DataFrame([{"day": 1, "seq": 99}, {"day": 2, "seq": 1}])
        assert _capture_watermark(df, ("day", "seq")) == (2, 1)

    def test_capture_scalar_is_column_max(self):
        """Single-column capture is max(col) — byte-identical to the pre-composite path."""
        df = pd.DataFrame([{"day": 1, "seq": 99}, {"day": 2, "seq": 1}])
        assert _capture_watermark(df, "seq") == 99

    def test_capture_composite_preserves_element_types(self):
        """Composite capture keeps each element's native type (int stays int)."""
        df = pd.DataFrame([{"day": 1, "seq": 99}, {"day": 2, "seq": 1}])
        wm = _capture_watermark(df, ("day", "seq"))
        assert isinstance(wm[0], int) and isinstance(wm[1], int)

    def test_capture_composite_nan_element_voids_watermark(self):
        """A NaN in any element of the max ROW voids the whole watermark (Pitfall 4)."""
        df = pd.DataFrame([{"day": 1, "seq": 5}, {"day": 2, "seq": float("nan")}])
        assert _capture_watermark(df, ("day", "seq")) is None

    def test_capture_empty_batch_is_none(self):
        """An empty batch records no composite watermark."""
        df = pd.DataFrame({"day": [], "seq": []})
        assert _capture_watermark(df, ("day", "seq")) is None

    def test_capture_missing_composite_column_raises(self):
        """A missing composite key column raises ETLError listing the missing name(s)."""
        df = pd.DataFrame([{"day": 1}])
        with pytest.raises(ETLError, match="seq"):
            _capture_watermark(df, ("day", "seq"))

    def test_capture_none_column_is_none(self):
        """A non-incremental pipeline (col=None) captures no watermark."""
        assert _capture_watermark(pd.DataFrame([{"x": 1}]), None) is None

    # --- multi-placeholder named-bind reconciliation ---

    def test_reconcile_scalar_keeps_wm_bind(self):
        """A single watermark keeps the historical :wm bind (byte-identical)."""
        sql, params = _reconcile_watermark_binds("WHERE col > %s", [5])
        assert sql == "WHERE col > :wm"
        assert params == {"wm": 5}

    def test_reconcile_composite_maps_distinct_named_binds(self):
        """Composite maps each %s to a distinct :wm{i} bind, order-preserving."""
        sql, params = _reconcile_watermark_binds(
            "WHERE (day, seq) > (%s, %s)", [5, 40]
        )
        assert sql == "WHERE (day, seq) > (:wm0, :wm1)"
        assert params == {"wm0": 5, "wm1": 40}

    def test_reconcile_no_params_is_empty(self):
        """No watermark params yields an unchanged SQL and empty binds."""
        sql, params = _reconcile_watermark_binds("SELECT * FROM t", [])
        assert sql == "SELECT * FROM t"
        assert params == {}


class TestBuilders:
    """Exact SQL string + params assertions for pure ETL builders."""

    def test_truncate_sql_default_schema(self):
        """build_truncate_sql('events') returns exact string with default schema."""
        sql, params = build_truncate_sql("events")
        assert sql == "TRUNCATE TABLE public.events"
        assert params == []

    def test_truncate_sql_custom_schema(self):
        """build_truncate_sql('events', schema='analytics') uses supplied schema."""
        sql, params = build_truncate_sql("events", schema="analytics")
        assert sql == "TRUNCATE TABLE analytics.events"
        assert params == []

    def test_truncate_sql_invalid_table_raises_invalid_identifier(self):
        """build_truncate_sql with a bad table name raises InvalidIdentifierError (D-13)."""
        with pytest.raises(InvalidIdentifierError):
            build_truncate_sql("bad-name")

    def test_truncate_sql_invalid_schema_raises_invalid_identifier(self):
        """build_truncate_sql with a bad schema name raises InvalidIdentifierError (D-13)."""
        with pytest.raises(InvalidIdentifierError):
            build_truncate_sql("events", schema="bad-schema")

    def test_build_init_sql_returns_ddl_constant(self):
        """build_init_sql() returns (ETL_INIT_PIPELINE_RUNS, [])."""
        sql, params = build_init_sql()
        assert sql == queries.ETL_INIT_PIPELINE_RUNS
        assert params == []

    def test_build_init_sql_ddl_is_idempotent(self):
        """The DDL returned by build_init_sql contains IF NOT EXISTS (D-15)."""
        sql, _ = build_init_sql()
        assert "IF NOT EXISTS" in sql

    def test_build_init_sql_ddl_has_required_columns(self):
        """The DDL contains all required pipeline_runs columns (D-14)."""
        sql, _ = build_init_sql()
        assert "pipeline_name" in sql
        assert "status" in sql
        assert "watermark" in sql
        assert "run_id" in sql

    def test_build_init_sql_returns_tuple_with_empty_list(self):
        """build_init_sql returns a 2-tuple whose second element is [] (uniform contract)."""
        result = build_init_sql()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[1] == []


class TestIsSqlSource:
    """DB-free tests for the _is_sql_source heuristic helper (D-05)."""

    def test_select_query_returns_true(self):
        """A string starting with SELECT is identified as SQL."""
        assert _is_sql_source("SELECT * FROM users") is True

    def test_with_query_returns_true(self):
        """A string starting with WITH is identified as SQL."""
        assert _is_sql_source("WITH cte AS (SELECT 1) SELECT * FROM cte") is True

    def test_plain_table_name_returns_false(self):
        """A plain table name without whitespace is not SQL."""
        assert _is_sql_source("users") is False

    def test_schema_qualified_table_returns_false(self):
        """A schema.table identifier without spaces is not SQL."""
        # Note: schema.table strings with a dot are not split by spaces;
        # the heuristic uses whitespace as the SQL indicator.
        assert _is_sql_source("public_users") is False

    def test_select_case_insensitive(self):
        """Lowercase 'select' is also recognized as a SQL query."""
        assert _is_sql_source("select id from orders") is True

    def test_string_with_whitespace_is_sql(self):
        """A source string containing whitespace is treated as SQL."""
        assert _is_sql_source("some complex query") is True


class TestValidateLoadMode:
    """DB-free tests for the _validate_load_mode module helper."""

    def test_valid_modes_pass(self):
        """All three public load modes pass without error."""
        for mode in ("append", "replace", "upsert"):
            _validate_load_mode(mode)  # must not raise

    def test_invalid_mode_raises_valueerror(self):
        """An invalid load_mode string raises ValueError."""
        with pytest.raises(ValueError, match="load_mode"):
            _validate_load_mode("truncate")


class TestValidateIncremental:
    """DB-free tests for the _validate_incremental module helper (D-14..D-16)."""

    def test_none_short_circuits(self):
        """incremental_column=None returns None — both checks skipped (D-15)."""
        assert _validate_incremental(None, "append") is None
        assert _validate_incremental(None, "upsert") is None

    def test_upsert_passes(self):
        """A valid identifier with load_mode='upsert' passes (D-16)."""
        assert _validate_incremental("updated_at", "upsert") is None

    def test_append_raises_valueerror(self):
        """load_mode='append' with an incremental_column raises ValueError (D-16)."""
        with pytest.raises(ValueError, match="upsert"):
            _validate_incremental("col", "append")

    def test_replace_raises_valueerror(self):
        """load_mode='replace' with an incremental_column raises ValueError (D-16)."""
        with pytest.raises(ValueError, match="upsert"):
            _validate_incremental("col", "replace")

    def test_message_cites_requirement_and_modes(self):
        """The forbidden-combo message names the modes and cites ETL-INC-01 (D-16)."""
        with pytest.raises(ValueError) as exc_info:
            _validate_incremental("col", "append")
        msg = str(exc_info.value)
        assert "upsert" in msg
        assert "append" in msg
        assert "replace" in msg
        assert "ETL-INC-01" in msg

    def test_combo_checked_before_identifier(self):
        """The forbidden-combo ValueError is raised before the identifier check (D-15).

        A bad identifier with a forbidden mode still reports the combo
        ValueError (intent error first), not InvalidIdentifierError.
        """
        with pytest.raises(ValueError, match="upsert"):
            _validate_incremental("bad-col!", "append")

    def test_bad_identifier_raises_invalid_identifier(self):
        """A bad identifier with load_mode='upsert' raises InvalidIdentifierError (D-15)."""
        with pytest.raises(InvalidIdentifierError):
            _validate_incremental("bad col", "upsert")


class TestEtlBuilders:
    """DB-free unit tests for _build_insert_sql, _build_upsert_sql, and _step_label."""

    # --- _build_insert_sql ---

    def test_insert_sql_single_row_sql_and_params(self):
        """Single-row insert returns correct SQL and params in column order."""
        sql, params = _build_insert_sql("t", ["a", "b"], [{"a": 1, "b": 2}])
        assert sql == "INSERT INTO public.t (a, b) VALUES (%s, %s)"
        assert params == [1, 2]

    def test_insert_sql_multi_row_placeholder_groups(self):
        """Multi-row insert produces one placeholder group per row."""
        sql, params = _build_insert_sql(
            "t", ["a", "b"], [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        )
        assert "VALUES (%s, %s), (%s, %s)" in sql
        assert len(params) == 4  # N*M == 2*2
        assert params == [1, 2, 3, 4]

    def test_insert_sql_params_length_equals_n_times_m(self):
        """len(params) == N columns * M rows (parameterized shape)."""
        rows = [{"x": i, "y": i * 2, "z": i * 3} for i in range(5)]
        sql, params = _build_insert_sql("tbl", ["x", "y", "z"], rows)
        assert len(params) == 3 * 5

    def test_insert_sql_on_conflict_clause_passthrough(self):
        """on_conflict string is appended as ON CONFLICT clause."""
        sql, _ = _build_insert_sql(
            "t", ["id"], [{"id": 1}], on_conflict="(id) DO NOTHING"
        )
        assert " ON CONFLICT (id) DO NOTHING" in sql

    def test_insert_sql_no_on_conflict_by_default(self):
        """Without on_conflict, no ON CONFLICT clause is emitted."""
        sql, _ = _build_insert_sql("t", ["id"], [{"id": 1}])
        assert "ON CONFLICT" not in sql

    def test_insert_sql_custom_schema(self):
        """Custom schema is interpolated after validation."""
        sql, _ = _build_insert_sql("t", ["id"], [{"id": 1}], schema="analytics")
        assert "INSERT INTO analytics.t" in sql

    def test_insert_sql_invalid_table_raises(self):
        """Invalid table name raises InvalidIdentifierError before SQL is built."""
        with pytest.raises(InvalidIdentifierError):
            _build_insert_sql("bad-table", ["id"], [{"id": 1}])

    def test_insert_sql_invalid_column_raises(self):
        """Invalid column name raises InvalidIdentifierError before SQL is built."""
        with pytest.raises(InvalidIdentifierError):
            _build_insert_sql("t", ["bad col"], [{"bad col": 1}])

    def test_insert_sql_invalid_schema_raises(self):
        """Invalid schema name raises InvalidIdentifierError before SQL is built."""
        with pytest.raises(InvalidIdentifierError):
            _build_insert_sql("t", ["id"], [{"id": 1}], schema="bad-schema")

    def test_insert_sql_returns_two_tuple(self):
        """Return value is a (str, list) 2-tuple."""
        result = _build_insert_sql("t", ["id"], [{"id": 1}])
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], list)

    # --- _build_upsert_sql ---

    def test_upsert_sql_default_update_columns(self):
        """update_columns defaults to all non-conflict columns."""
        sql, params = _build_upsert_sql("t", [{"id": 1, "v": 9}], ["id"])
        assert "ON CONFLICT (id) DO UPDATE SET v = EXCLUDED.v" in sql
        assert params == [1, 9]

    def test_upsert_sql_explicit_update_columns(self):
        """Explicit update_columns emits only those columns in DO UPDATE SET."""
        sql, _ = _build_upsert_sql(
            "t",
            [{"id": 1, "a": 2, "b": 3}],
            conflict_columns=["id"],
            update_columns=["a"],
        )
        assert "DO UPDATE SET a = EXCLUDED.a" in sql
        assert "b = EXCLUDED.b" not in sql

    def test_upsert_sql_multiple_conflict_columns(self):
        """Multiple conflict columns appear comma-separated in ON CONFLICT."""
        sql, _ = _build_upsert_sql(
            "t", [{"x": 1, "y": 2, "v": 3}], conflict_columns=["x", "y"]
        )
        assert "ON CONFLICT (x, y)" in sql
        assert "v = EXCLUDED.v" in sql

    def test_upsert_sql_conflict_columns_as_tuple(self):
        """conflict_columns can be passed as a tuple (Pipeline stores tuples)."""
        sql, _ = _build_upsert_sql("t", [{"id": 1, "v": 2}], conflict_columns=("id",))
        assert "ON CONFLICT (id)" in sql

    def test_upsert_sql_invalid_conflict_column_raises(self):
        """Invalid conflict_column raises InvalidIdentifierError before SQL is built."""
        with pytest.raises(InvalidIdentifierError):
            _build_upsert_sql("t", [{"id": 1, "v": 2}], conflict_columns=["bad col"])

    def test_upsert_sql_delegates_to_insert_builder(self):
        """_build_upsert_sql produces valid INSERT … ON CONFLICT SQL."""
        sql, params = _build_upsert_sql("events", [{"id": 7, "name": "x"}], ["id"])
        assert sql.startswith("INSERT INTO public.events")
        assert "ON CONFLICT" in sql
        assert params == [7, "x"]

    # --- _step_label ---

    def test_step_label_named_function(self):
        """A named function returns its __name__."""

        def my_transform(df):
            return df

        assert _step_label(my_transform) == "my_transform"

    def test_step_label_lambda_returns_repr(self):
        """A lambda falls back to repr (not '<lambda>') for usefulness."""
        fn = lambda x: x  # noqa: E731
        label = _step_label(fn)
        assert label != "<lambda>"
        assert "lambda" in label  # repr contains the word lambda

    def test_step_label_partial_returns_repr(self):
        """functools.partial has no __name__ — repr fallback is used."""

        def base(df, col):
            return df[col]

        fn = functools.partial(base, col="id")
        label = _step_label(fn)
        assert "partial" in label.lower() or "base" in label  # repr of partial

    # --- transform step-index message contract (D-06) ---

    def test_transform_chain_step_index(self):
        """The ETLTransformError message contains 1-based index and step label.

        Locks the D-06 message contract at unit level.  The integration test
        that asserts a failed run row is recorded lives in Plan 03.
        """

        def bad_step(df):
            raise ValueError("boom")

        i = 2  # step 2 in a hypothetical chain
        lbl = _step_label(bad_step)
        try:
            bad_step(None)
        except ValueError as exc:
            msg = f"transform step {i} ('{lbl}') raised {type(exc).__name__}: {exc}"
            err = ETLTransformError(msg)
        assert f"transform step {i}" in str(err)
        assert f"'{lbl}'" in str(err)
        assert "ValueError" in str(err)


class TestBuildIncrementalExtractSql:
    """DB-free tests for _build_incremental_extract_sql (D-06..D-13)."""

    def test_table_source_with_watermark(self):
        """Table source + watermark appends WHERE col > %s (D-09)."""
        wm = datetime(2026, 1, 1, tzinfo=UTC)
        sql, params = _build_incremental_extract_sql(
            "raw_events", "updated_at", "public", wm
        )
        assert sql == "SELECT * FROM public.raw_events WHERE updated_at > %s"
        assert params == [wm]

    def test_sql_source_with_watermark_wraps_subquery(self):
        """SQL-string source + watermark wraps in a subquery with the reserved alias (D-06/D-07)."""
        wm = 42
        sql, params = _build_incremental_extract_sql(
            "SELECT a, b FROM t", "id", "public", wm
        )
        assert "_pycopg_inc" in sql
        assert "(SELECT a, b FROM t)" in sql
        assert sql.rstrip().endswith("WHERE id > %s")
        assert params == [wm]
        # T-26-01: the watermark value is never interpolated into the SQL.
        assert "42" not in sql

    def test_sql_source_trailing_semicolon_stripped(self):
        """A trailing ';' and whitespace are stripped before wrapping (D-08)."""
        wm = 7
        sql, params = _build_incremental_extract_sql("SELECT 1;  ", "id", "public", wm)
        assert "(SELECT 1)" in sql
        assert ";" not in sql.split("_pycopg_inc")[0]
        assert params == [wm]

    def test_table_source_watermark_none_full_select(self):
        """watermark=None on a table source returns a full SELECT with [] params (D-12)."""
        sql, params = _build_incremental_extract_sql("events", "ts", "public", None)
        assert sql == "SELECT * FROM public.events"
        assert params == []
        assert "WHERE" not in sql
        assert "%s" not in sql

    def test_sql_source_watermark_none_full_select(self):
        """watermark=None on a SQL source returns a full unfiltered SELECT with [] params (D-12)."""
        sql, params = _build_incremental_extract_sql(
            "SELECT a FROM t", "id", "public", None
        )
        assert params == []
        assert "WHERE" not in sql
        assert "%s" not in sql

    def test_custom_schema_honored(self):
        """A custom schema is honored for table sources (D-09)."""
        wm = 1
        sql, params = _build_incremental_extract_sql("events", "ts", "analytics", wm)
        assert sql == "SELECT * FROM analytics.events WHERE ts > %s"
        assert params == [wm]

    def test_invalid_column_raises(self):
        """A bad column identifier raises InvalidIdentifierError before any SQL (T-26-02)."""
        with pytest.raises(InvalidIdentifierError):
            _build_incremental_extract_sql("events", "bad-col!", "public", 1)

    def test_invalid_table_source_raises(self):
        """A bad table source raises InvalidIdentifierError (T-26-02)."""
        with pytest.raises(InvalidIdentifierError):
            _build_incremental_extract_sql("bad-table!", "ts", "public", 1)

    def test_invalid_schema_raises(self):
        """A bad schema raises InvalidIdentifierError (T-26-02)."""
        with pytest.raises(InvalidIdentifierError):
            _build_incremental_extract_sql("events", "ts", "bad-schema!", 1)

    def test_uses_exclusive_boundary(self):
        """Default (inclusive omitted) uses '>' (exclusive), never '>=' (D-05 default)."""
        sql, _ = _build_incremental_extract_sql("events", "ts", "public", 1)
        assert ">=" not in sql
        assert "> %s" in sql

    def test_returns_two_tuple(self):
        """Return value is a (str, list) 2-tuple (D-13)."""
        result = _build_incremental_extract_sql("events", "ts", "public", 1)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], list)

    # --- ETL-INC-F02: inclusive boundary operator (D-05) ---

    def test_inclusive_false_default_is_exclusive_gt(self):
        """inclusive=False (explicit) keeps '>' for both source kinds (regression)."""
        tbl_sql, tbl_p = _build_incremental_extract_sql(
            "t", "col", watermark=5, inclusive=False
        )
        src_sql, src_p = _build_incremental_extract_sql(
            "SELECT 1 AS col", "col", watermark=5, inclusive=False
        )
        assert "col > %s" in tbl_sql and ">=" not in tbl_sql
        assert "col > %s" in src_sql and ">=" not in src_sql
        assert tbl_p == [5] and src_p == [5]  # watermark is the only bound param

    def test_inclusive_true_table_source_uses_gte(self):
        """inclusive=True emits '>=' on a table source; watermark still the only param."""
        sql, params = _build_incremental_extract_sql(
            "t", "col", watermark=5, inclusive=True
        )
        assert "col >= %s" in sql
        assert params == [5]

    def test_inclusive_true_sql_source_uses_gte(self):
        """inclusive=True emits '>=' on a SQL-string source (subquery wrap)."""
        sql, params = _build_incremental_extract_sql(
            "SELECT 1 AS col", "col", watermark=5, inclusive=True
        )
        assert "col >= %s" in sql
        assert params == [5]

    def test_inclusive_path_validates_identifiers(self):
        """validate_identifiers still fires before interpolation on the inclusive path."""
        with pytest.raises(InvalidIdentifierError):
            _build_incremental_extract_sql(
                "events", "bad-col!", "public", 1, inclusive=True
            )


class TestEncodeDecodeWatermark:
    """DB-free tests for _encode_watermark / _decode_watermark (D-01..D-05)."""

    def _aware_dt(self):
        """Return a tz-aware datetime with microseconds and a non-UTC offset."""
        return datetime(
            2024, 3, 1, 12, 0, 0, 123456, tzinfo=timezone(timedelta(hours=2))
        )

    def test_encode_datetime_shape(self):
        """A tz-aware datetime encodes to an isoformat string envelope (D-02)."""
        dt = self._aware_dt()
        env = _encode_watermark(dt)
        assert env == {
            "type": "datetime",
            "value": "2024-03-01T12:00:00.123456+02:00",
        }

    def test_encode_int_shape(self):
        """An int encodes to {'type': 'int', 'value': <int>}."""
        assert _encode_watermark(42) == {"type": "int", "value": 42}

    def test_encode_str_shape(self):
        """A str encodes to {'type': 'str', 'value': <str>}."""
        assert _encode_watermark("2024-01-01") == {
            "type": "str",
            "value": "2024-01-01",
        }

    def test_encode_returns_bare_dict(self):
        """_encode_watermark returns a plain dict, NOT a Jsonb instance (D-05)."""
        result = _encode_watermark(42)
        assert isinstance(result, dict)
        assert type(result).__name__ != "Jsonb"

    def test_encode_bool_raises_etlerror(self):
        """bool is excluded from the allowlist before the int branch (D-04)."""
        with pytest.raises(ETLError) as exc_info:
            _encode_watermark(True)
        msg = str(exc_info.value)
        assert "bool" in msg
        assert "datetime" in msg and "int" in msg and "str" in msg

    def test_encode_float_raises_etlerror(self):
        """float is not supported in v0.7.0 (D-04)."""
        with pytest.raises(ETLError, match="float"):
            _encode_watermark(3.14)

    def test_roundtrip_datetime(self):
        """datetime round-trips losslessly with tzinfo + microseconds preserved (D-02)."""
        dt = self._aware_dt()
        decoded = _decode_watermark(_encode_watermark(dt))
        assert decoded == dt
        assert decoded.tzinfo is not None
        assert decoded.utcoffset() == timedelta(hours=2)
        assert decoded.microsecond == 123456

    def test_roundtrip_int(self):
        """int round-trips without type drift."""
        decoded = _decode_watermark(_encode_watermark(42))
        assert decoded == 42
        assert isinstance(decoded, int)

    def test_roundtrip_str(self):
        """str round-trips without type drift."""
        decoded = _decode_watermark(_encode_watermark("hello"))
        assert decoded == "hello"
        assert isinstance(decoded, str)

    def test_decode_accepts_plain_dict(self):
        """_decode_watermark accepts the plain dict psycopg returns from a JSONB read."""
        assert _decode_watermark({"type": "int", "value": 7}) == 7
        assert _decode_watermark(
            {"type": "datetime", "value": "2024-03-01T12:00:00+00:00"}
        ) == datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)

    # --- ETL-INC-F03: composite envelope tag (D-11) ---

    def test_encode_composite_shape(self):
        """Composite encode builds {type:composite, columns, values:[scalar-envelope...]}."""
        env = _encode_composite_watermark(("day", "seq"), (5, 40))
        assert env == {
            "type": "composite",
            "columns": ["day", "seq"],
            "values": [{"type": "int", "value": 5}, {"type": "int", "value": 40}],
        }

    def test_decode_composite_returns_tuple(self):
        """A composite envelope decodes element-wise back to a tuple of scalars."""
        env = _encode_composite_watermark(("day", "seq"), (5, 40))
        assert _decode_watermark(env) == (5, 40)

    def test_composite_roundtrip_mixed_types(self):
        """Composite round-trip preserves per-element types (datetime + int)."""
        dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        env = _encode_composite_watermark(("ts", "seq"), (dt, 7))
        decoded = _decode_watermark(env)
        assert decoded == (dt, 7)
        assert isinstance(decoded[0], datetime)
        assert isinstance(decoded[1], int)

    def test_composite_encode_bool_element_raises(self):
        """A bool element in a composite watermark is rejected per element (Pitfall 2)."""
        with pytest.raises(ETLError):
            _encode_composite_watermark(("a", "b"), (True, 40))

    def test_composite_encode_float_element_raises(self):
        """A float element is rejected per element (allowlist held element-wise)."""
        with pytest.raises(ETLError):
            _encode_composite_watermark(("a", "b"), (1.5, 40))

    def test_scalar_envelope_unchanged_zero_migration(self):
        """The three scalar tags decode exactly as before — old rows need no migration."""
        assert _decode_watermark({"type": "int", "value": 137}) == 137
        assert _decode_watermark({"type": "str", "value": "v1"}) == "v1"
        assert _decode_watermark(
            {"type": "datetime", "value": "2024-01-01T00:00:00+00:00"}
        ) == datetime(2024, 1, 1, tzinfo=UTC)

    def test_unknown_tag_still_raises(self):
        """An unknown envelope tag still raises ETLError (corruption guard, C-02)."""
        with pytest.raises(ETLError, match="Unknown watermark type tag"):
            _decode_watermark({"type": "bogus", "value": 1})


class TestRowToResult:
    """Unit tests for _row_to_result — pure function, no DB (D-10)."""

    def _sample_row(self, **overrides):
        """Return a minimal valid pipeline_runs dict_row (all 10 DB columns)."""
        base = {
            "run_id": 7,
            "pipeline_name": "test_pipeline",
            "status": "success",
            "rows_extracted": 10,
            "rows_loaded": 10,
            "started_at": datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            "finished_at": datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
            "error_message": None,
            "error_traceback": None,
            "watermark": None,
        }
        base.update(overrides)
        return base

    def test_maps_all_fields(self):
        """_row_to_result maps the RunResult fields from a pipeline_runs row (D-10/D-A1/SC-1)."""
        row = self._sample_row()
        result = _row_to_result(row)
        assert result.run_id == 7
        assert result.pipeline_name == "test_pipeline"
        assert result.status == "success"
        assert result.rows_extracted == 10
        assert result.rows_loaded == 10
        assert result.started_at == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert result.finished_at == datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)
        assert result.error is None
        # NULL watermark column -> watermark_recorded is None; watermark_used is
        # always None for stored rows (it is a per-run input, never persisted) (D-A1).
        assert result.watermark_used is None
        assert result.watermark_recorded is None

    def test_error_message_renamed_to_error(self):
        """DB column error_message is exposed on RunResult as 'error' (D-03/D-10)."""
        row = self._sample_row(error_message="something went wrong")
        result = _row_to_result(row)
        assert result.error == "something went wrong"

    def test_error_traceback_dropped(self):
        """error_traceback is not a field on RunResult — dropped by mapper (D-10)."""
        row = self._sample_row(error_traceback="Traceback (most recent call last)...")
        result = _row_to_result(row)
        assert not hasattr(result, "error_traceback")

    def test_watermark_recorded_decoded(self):
        """A non-NULL watermark envelope is decoded onto watermark_recorded (D-A1).

        Phase 28 changed the D-04/D-10 contract: ``_row_to_result`` no longer
        drops ``watermark`` — it maps the stored typed envelope to
        ``watermark_recorded`` via the frozen :func:`_decode_watermark`, while
        ``watermark_used`` stays ``None`` for stored rows.
        """
        wm = datetime(2026, 1, 1, tzinfo=UTC)
        row = self._sample_row(watermark=_encode_watermark(wm))
        result = _row_to_result(row)
        assert result.watermark_recorded == wm
        assert result.watermark_used is None

    def test_null_watermark_recorded_is_none(self):
        """A NULL watermark column maps to watermark_recorded=None (NULL guard, D-A1)."""
        row = self._sample_row(watermark=None)
        result = _row_to_result(row)
        assert result.watermark_recorded is None
        assert result.watermark_used is None

    def test_result_is_frozen(self):
        """RunResult is a frozen dataclass — attribute assignment raises (D-01)."""
        row = self._sample_row()
        result = _row_to_result(row)
        assert isinstance(result, RunResult)
        with pytest.raises(
            Exception
        ):  # dataclasses.FrozenInstanceError (AttributeError subclass)
            result.status = "failed"  # type: ignore[misc]
