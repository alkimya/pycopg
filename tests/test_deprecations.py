"""Tests for pycopg deprecation warnings and aliases."""

# xfail plan cross-reference:
#   TestExceptionAliases tests  — xfail until Plan 02 (exception renames + PEP 562 __getattr__)
#   TestWhereDeprecation tests  — xfail until Plan 03 (where= → filter= shim on spatial methods)
#   TestKwOnlyEnforcement tests — xfail until Plan 04 (kw-only audit + FREEZE-03 fixes)

import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from pycopg import exceptions
from pycopg.spatial import AsyncSpatialAccessor, SpatialAccessor


class TestExceptionAliases:
    """PEP 562 deprecated exception name behaviour (FREEZE-02)."""

    def test_exception_alias_same_object(self):
        """Old name resolves to the identical class object."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            OldName = exceptions.InvalidIdentifier  # noqa: N806 — intentional class alias
        assert OldName is exceptions.InvalidIdentifierError

    def test_exception_alias_warns_on_access(self):
        """Accessing old exception name emits DeprecationWarning."""
        with pytest.warns(DeprecationWarning) as record:
            _ = exceptions.InvalidIdentifier
        w = record[0]
        assert "InvalidIdentifierError" in str(w.message)
        # D-09: stacklevel must point at THIS file, not exceptions.py
        assert w.filename.endswith("test_deprecations.py"), (
            f"Warning pointed at {w.filename!r}, expected test file"
        )

    def test_old_exception_name_still_catchable(self):
        """except OldName: catches exception raised with NewNameError (same object)."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            OldName = exceptions.InvalidIdentifier  # noqa: N806 — intentional class alias
        with pytest.raises(OldName):
            raise exceptions.InvalidIdentifierError("test")


def _make_sync_accessor() -> SpatialAccessor:
    """Return a SpatialAccessor with a mocked DB (PostGIS pre-checked)."""
    db = MagicMock()
    db.schema.has_extension.return_value = True
    db.execute.return_value = []
    return SpatialAccessor(db)


def _make_async_accessor() -> AsyncSpatialAccessor:
    """Return an AsyncSpatialAccessor with a mocked async DB (PostGIS pre-checked)."""
    db = MagicMock()
    db.schema.has_extension = AsyncMock(return_value=True)
    db.execute = AsyncMock(return_value=[])
    return AsyncSpatialAccessor(db)


# Required positional/keyword args per method.
# within has a unique two-table signature: (left_table, left_geom, right_table, right_geom)
# so it's stored as (method, positional_args, keyword_args).
# All others use: (method, keyword_args) with a single "tbl" positional arg.
_SYNC_WHERE_CASES = [
    ("contains", {"point": (0.0, 0.0)}),
    ("intersects", {"point": (0.0, 0.0)}),
    ("dwithin", {"point": (0.0, 0.0), "distance": 100.0}),
    ("distance", {"point": (0.0, 0.0)}),
    ("nearest", {"point": (0.0, 0.0)}),
    ("area", {}),
    ("perimeter", {}),
    ("centroid", {}),
    ("buffer", {"distance": 50.0}),
    ("transform", {"to_srid": 3857}),
]

# within uses a distinct call pattern
_WITHIN_ARGS = ("ltbl", "lgeom", "rtbl", "rgeom")


class TestWhereDeprecation:
    """where= shim deprecation behaviour (FREEZE-01)."""

    def test_where_deprecation_points_to_caller(self):
        """DeprecationWarning from where= must point to THIS file, not spatial.py."""
        accessor = _make_sync_accessor()
        with pytest.warns(DeprecationWarning) as record:
            accessor.contains("tbl", point=(0.0, 0.0), where="id > 0")
        assert len(record) == 1
        w = record[0]
        assert "filter" in str(w.message)
        assert w.filename.endswith("test_deprecations.py"), (
            f"Warning pointed at {w.filename!r}, expected test file"
        )

    def test_filter_and_where_both_supplied_raises(self):
        """Supplying both filter= and where= raises TypeError."""
        accessor = _make_sync_accessor()
        with pytest.raises(TypeError, match="Cannot specify both"):
            accessor.contains("tbl", point=(0.0, 0.0), filter="x > 0", where="y > 0")

    @pytest.mark.parametrize("method,kwargs", _SYNC_WHERE_CASES)
    def test_sync_where_warns_for_all_methods(self, method, kwargs):
        """All non-within sync accessor methods emit DeprecationWarning when where= is used."""
        accessor = _make_sync_accessor()
        with pytest.warns(DeprecationWarning, match="filter="):
            getattr(accessor, method)("tbl", **kwargs, where="id > 0")

    @pytest.mark.parametrize("method,kwargs", _SYNC_WHERE_CASES)
    def test_sync_filter_and_where_both_raises_for_all_methods(self, method, kwargs):
        """All non-within sync accessor methods raise TypeError when both filter= and where= given."""
        accessor = _make_sync_accessor()
        with pytest.raises(TypeError, match="Cannot specify both"):
            getattr(accessor, method)(
                "tbl", **kwargs, filter="x > 0", where="y > 0"
            )

    def test_sync_within_where_warns(self):
        """SpatialAccessor.within emits DeprecationWarning when where= is used."""
        accessor = _make_sync_accessor()
        with pytest.warns(DeprecationWarning, match="filter="):
            accessor.within(*_WITHIN_ARGS, where="id > 0")

    def test_sync_within_filter_and_where_raises(self):
        """SpatialAccessor.within raises TypeError when both filter= and where= given."""
        accessor = _make_sync_accessor()
        with pytest.raises(TypeError, match="Cannot specify both"):
            accessor.within(*_WITHIN_ARGS, filter="x > 0", where="y > 0")

    @pytest.mark.parametrize("method,kwargs", _SYNC_WHERE_CASES)
    async def test_async_where_warns_for_all_methods(self, method, kwargs):
        """All non-within async accessor methods emit DeprecationWarning when where= is used."""
        accessor = _make_async_accessor()
        with pytest.warns(DeprecationWarning, match="filter="):
            await getattr(accessor, method)("tbl", **kwargs, where="id > 0")

    @pytest.mark.parametrize("method,kwargs", _SYNC_WHERE_CASES)
    async def test_async_filter_and_where_both_raises_for_all_methods(
        self, method, kwargs
    ):
        """All non-within async accessor methods raise TypeError when both filter= and where= given."""
        accessor = _make_async_accessor()
        with pytest.raises(TypeError, match="Cannot specify both"):
            await getattr(accessor, method)(
                "tbl", **kwargs, filter="x > 0", where="y > 0"
            )

    async def test_async_within_where_warns(self):
        """AsyncSpatialAccessor.within emits DeprecationWarning when where= is used."""
        accessor = _make_async_accessor()
        with pytest.warns(DeprecationWarning, match="filter="):
            await accessor.within(*_WITHIN_ARGS, where="id > 0")

    async def test_async_within_filter_and_where_raises(self):
        """AsyncSpatialAccessor.within raises TypeError when both filter= and where= given."""
        accessor = _make_async_accessor()
        with pytest.raises(TypeError, match="Cannot specify both"):
            await accessor.within(*_WITHIN_ARGS, filter="x > 0", where="y > 0")


class TestKwOnlyEnforcement:
    """Keyword-only boundary enforcement (FREEZE-03, D-03/D-04)."""

    @pytest.mark.xfail(reason="Implemented in Plan 04 (kw-only audit + FREEZE-03 signature fixes)", strict=False)
    def test_contains_geom_is_kw_only(self):
        """Passing geom positionally must raise TypeError in 1.0."""
        db = MagicMock()
        accessor = SpatialAccessor(db)
        with pytest.raises(TypeError):
            accessor.contains("tbl", "geometry")  # geom is now kw-only
