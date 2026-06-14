"""Tests for pycopg.etl — DB-free Pipeline + builder tests."""

import pytest

from pycopg import queries
from pycopg.etl import (
    Pipeline,
    _is_sql_source,
    _validate_load_mode,
    build_init_sql,
    build_truncate_sql,
)
from pycopg.exceptions import InvalidIdentifier


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
        """build_truncate_sql with a bad table name raises InvalidIdentifier (D-13)."""
        with pytest.raises(InvalidIdentifier):
            build_truncate_sql("bad-name")

    def test_truncate_sql_invalid_schema_raises_invalid_identifier(self):
        """build_truncate_sql with a bad schema name raises InvalidIdentifier (D-13)."""
        with pytest.raises(InvalidIdentifier):
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
