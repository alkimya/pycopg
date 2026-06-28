"""Tests for pycopg deprecation warnings and aliases."""

# xfail plan cross-reference:
#   TestExceptionAliases tests  — xfail until Plan 02 (exception renames + PEP 562 __getattr__)
#   TestWhereDeprecation tests  — xfail until Plan 03 (where= → filter= shim on spatial methods)
#   TestKwOnlyEnforcement tests — xfail until Plan 04 (kw-only audit + FREEZE-03 fixes)

import warnings

import pytest
from unittest.mock import MagicMock

from pycopg import exceptions
from pycopg.spatial import SpatialAccessor


class TestExceptionAliases:
    """PEP 562 deprecated exception name behaviour (FREEZE-02)."""

    @pytest.mark.xfail(reason="Implemented in Plan 02 (exception renames + __getattr__)", strict=False)
    def test_exception_alias_same_object(self):
        """Old name resolves to the identical class object."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            OldName = exceptions.InvalidIdentifier
        assert OldName is exceptions.InvalidIdentifierError

    @pytest.mark.xfail(reason="Implemented in Plan 02 (exception renames + __getattr__)", strict=False)
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

    @pytest.mark.xfail(reason="Implemented in Plan 02 (exception renames + __getattr__)", strict=False)
    def test_old_exception_name_still_catchable(self):
        """except OldName: catches exception raised with NewNameError (same object)."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            OldName = exceptions.InvalidIdentifier
        with pytest.raises(OldName):
            raise exceptions.InvalidIdentifierError("test")


class TestWhereDeprecation:
    """where= shim deprecation behaviour (FREEZE-01)."""

    @pytest.mark.xfail(reason="Implemented in Plan 03 (where= -> filter= shim on spatial methods)", strict=False)
    def test_where_deprecation_points_to_caller(self):
        """DeprecationWarning from where= must point to THIS file, not spatial.py."""
        db = MagicMock()
        db.schema.has_extension.return_value = True
        db.execute.return_value = []
        accessor = SpatialAccessor(db)
        with pytest.warns(DeprecationWarning) as record:
            accessor.contains("tbl", point=(0.0, 0.0), where="id > 0")
        assert len(record) == 1
        w = record[0]
        assert "filter" in str(w.message)
        assert w.filename.endswith("test_deprecations.py"), (
            f"Warning pointed at {w.filename!r}, expected test file"
        )

    @pytest.mark.xfail(reason="Implemented in Plan 03 (where= -> filter= shim on spatial methods)", strict=False)
    def test_filter_and_where_both_supplied_raises(self):
        """Supplying both filter= and where= raises TypeError."""
        db = MagicMock()
        db.schema.has_extension.return_value = True
        db.execute.return_value = []
        accessor = SpatialAccessor(db)
        with pytest.raises(TypeError, match="Cannot specify both"):
            accessor.contains("tbl", point=(0.0, 0.0), filter="x > 0", where="y > 0")


class TestKwOnlyEnforcement:
    """Keyword-only boundary enforcement (FREEZE-03, D-03/D-04)."""

    @pytest.mark.xfail(reason="Implemented in Plan 04 (kw-only audit + FREEZE-03 signature fixes)", strict=False)
    def test_contains_geom_is_kw_only(self):
        """Passing geom positionally must raise TypeError in 1.0."""
        db = MagicMock()
        accessor = SpatialAccessor(db)
        with pytest.raises(TypeError):
            accessor.contains("tbl", "geometry")  # geom is now kw-only
