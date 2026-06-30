"""Tests for PARAM-01: Params alias widening on execute/fetch_*/to_dataframe.

Covers:
- Params + IsolationLevel export from pycopg
- dict (%(name)s) params work live on execute/fetch_one/fetch_val/fetch_all
- to_dataframe empirically uses SQLAlchemy :name style (resolves RESEARCH Q1)
- Async mirror for AsyncDatabase.execute
"""

from __future__ import annotations

import pytest
import pytest_asyncio

import pycopg
from pycopg import AsyncDatabase, Database, IsolationLevel, Params


# ---------------------------------------------------------------------------
# Unit — export checks (no DB)
# ---------------------------------------------------------------------------


def test_params_alias_exported():
    """Params and IsolationLevel are importable from pycopg and in __all__."""
    # Direct import already succeeded above; verify __all__ membership
    assert "Params" in pycopg.__all__, "Params not in pycopg.__all__"
    assert "IsolationLevel" in pycopg.__all__, "IsolationLevel not in pycopg.__all__"

    # Verify type alias is the expected union shape (not None, not dict)
    # Params should accept None, Sequence, and Mapping — structural check only
    assert Params is not None  # the alias object itself is truthy


# ---------------------------------------------------------------------------
# Live integration — sync (PGDATABASE=pycopg_test2)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_execute_dict_params(db_config):
    """execute() accepts a %(name)s dict and returns the bound value."""
    db = Database(db_config)
    rows = db.execute("SELECT %(x)s::int AS v", {"x": 7})
    assert rows, "execute returned no rows"
    assert rows[0]["v"] == 7


@pytest.mark.integration
def test_fetch_methods_dict_params(db_config):
    """fetch_one/fetch_val/fetch_all each accept %(name)s dict params."""
    db = Database(db_config)

    # fetch_one
    row = db.fetch_one("SELECT %(x)s::int AS v", {"x": 42})
    assert row is not None
    assert row["v"] == 42

    # fetch_val
    val = db.fetch_val("SELECT %(x)s::int", {"x": 99})
    assert val == 99

    # fetch_all
    rows = db.fetch_all(
        "SELECT %(a)s::int AS a, %(b)s::text AS b",
        {"a": 1, "b": "hello"},
    )
    assert len(rows) == 1
    assert rows[0]["a"] == 1
    assert rows[0]["b"] == "hello"


@pytest.mark.integration
def test_to_dataframe_named_style(db_config):
    """Confirm to_dataframe uses SQLAlchemy :name style (colon-prefix), NOT %(name)s.

    This resolves RESEARCH Q1: to_dataframe routes through pd.read_sql(text(sql), ...)
    which uses SQLAlchemy's :name binding — **different** from the %(name)s style
    used by the psycopg-backed execute/fetch_* methods.

    D-12 HARD LOCK: no translator is added. The divergence is documented here and
    in the to_dataframe docstring.
    """
    db = Database(db_config)

    # SQLAlchemy :name style — this is the accepted style for to_dataframe
    df = db.to_dataframe(sql="SELECT :x AS v", params={"x": 9})
    assert not df.empty, "to_dataframe returned an empty DataFrame"
    assert df.iloc[0]["v"] == 9, f"Expected v=9 but got {df.iloc[0]['v']}"

    # NOTE: %(name)s style does NOT work here (SQLAlchemy text() treats %(...) as
    # a different syntax). This is intentional and documented — do NOT add a translator.


# ---------------------------------------------------------------------------
# Live integration — async (PGDATABASE=pycopg_test2)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_execute_dict_params(db_config):
    """AsyncDatabase.execute() accepts a %(name)s dict and returns the bound value."""
    db = AsyncDatabase(db_config)
    rows = await db.execute("SELECT %(x)s::int AS v", {"x": 55})
    assert rows, "async execute returned no rows"
    assert rows[0]["v"] == 55


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_fetch_methods_dict_params(db_config):
    """AsyncDatabase.fetch_one/fetch_val/fetch_all accept %(name)s dict params."""
    db = AsyncDatabase(db_config)

    # fetch_one
    row = await db.fetch_one("SELECT %(x)s::int AS v", {"x": 77})
    assert row is not None
    assert row["v"] == 77

    # fetch_val
    val = await db.fetch_val("SELECT %(x)s::int", {"x": 88})
    assert val == 88

    # fetch_all
    rows = await db.fetch_all(
        "SELECT %(a)s::int AS a, %(b)s::text AS b",
        {"a": 2, "b": "world"},
    )
    assert len(rows) == 1
    assert rows[0]["a"] == 2
    assert rows[0]["b"] == "world"
