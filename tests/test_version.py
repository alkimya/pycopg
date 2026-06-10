"""Tests for pycopg.__version__ (DOC-10)."""

import pycopg


class TestVersion:
    """Tests for package version metadata."""

    def test_version_is_string(self):
        """__version__ is a non-empty string."""
        assert isinstance(pycopg.__version__, str)
        assert len(pycopg.__version__) > 0

    def test_version_format(self):
        """__version__ follows semver-like format x.y.z."""
        parts = pycopg.__version__.split(".")
        assert len(parts) >= 2

    def test_version_in_all(self):
        """__version__ is exported in __all__."""
        assert "__version__" in pycopg.__all__
