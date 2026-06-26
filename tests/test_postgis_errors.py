"""
PostGIS error handling tests (TEST-05).

Tests graceful error handling for spatial operations when PostGIS is not available
or when called with invalid parameters.
"""

import pytest

from pycopg import Database


def has_postgis(db_config):
    """Check if PostGIS extension is installed in test database."""
    db = Database(db_config)
    try:
        result = db.execute("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
        return len(result) > 0
    except Exception:
        return False


class TestPostGISErrorHandling:
    """Test PostGIS error handling using real PostgreSQL."""

    def test_create_spatial_index_without_geometry_column(self, db_config):
        """Test create_spatial_index with non-geometry column produces error."""
        db = Database(db_config)

        table_name = "test_spatial_index_non_geom"

        try:
            # Create table with text column (not geometry)
            db.execute(f"CREATE TEMP TABLE {table_name} (id INTEGER, name TEXT)")

            # Try to create spatial index on text column - should fail
            with pytest.raises(Exception) as exc_info:
                db.spatial.create_spatial_index(table_name, "name")

            # Error should be related to the column type or operator class
            error_msg = str(exc_info.value).lower()
            # PostgreSQL will complain about operator class or data type
            # The key is that an error IS raised (not silently failing)
            assert len(error_msg) > 0  # Some error message exists

        finally:
            # Temp tables auto-cleanup, but be explicit
            try:
                db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
            except Exception:
                pass

    def test_create_spatial_index_on_nonexistent_table(self, db_config):
        """Test create_spatial_index on non-existent table produces error."""
        db = Database(db_config)

        # Try to create spatial index on table that doesn't exist
        with pytest.raises(Exception) as exc_info:
            db.spatial.create_spatial_index("nonexistent_table_xyz123", "geometry")

        # Error should mention the table doesn't exist
        error_msg = str(exc_info.value).lower()
        assert (
            "exist" in error_msg or "not found" in error_msg or "relation" in error_msg
        )

    @pytest.mark.skipif(
        not has_postgis(
            pytest.lazy_fixture("db_config")
            if hasattr(pytest, "lazy_fixture")
            else None
        ),
        reason="PostGIS not installed",
    )
    def test_list_geometry_columns_with_postgis(self, db_config):
        """Test list_geometry_columns works when PostGIS is available."""
        # Skip if PostGIS not available
        if not has_postgis(db_config):
            pytest.skip("PostGIS not installed")

        db = Database(db_config)

        # Should return list (may be empty if no geometry columns)
        result = db.spatial.list_geometry_columns()
        assert isinstance(result, list)

        # If result is not empty, verify structure
        if result:
            first = result[0]
            assert "schema" in first or "table_name" in first

    def test_list_geometry_columns_without_postgis(self, db_config):
        """Test list_geometry_columns behavior when PostGIS is not available."""
        # Only run this test if PostGIS is NOT available
        if has_postgis(db_config):
            pytest.skip("PostGIS is available, test not applicable")

        db = Database(db_config)

        # Without PostGIS, geometry_columns view doesn't exist
        with pytest.raises(Exception) as exc_info:
            db.spatial.list_geometry_columns()

        # Error should mention geometry_columns doesn't exist
        error_msg = str(exc_info.value).lower()
        assert (
            "geometry_columns" in error_msg
            or "exist" in error_msg
            or "relation" in error_msg
        )

    def test_create_spatial_index_name_parameter(self, db_config):
        """Test create_spatial_index with custom name parameter."""
        # Skip if PostGIS not available (we need actual geometry column)
        if not has_postgis(db_config):
            pytest.skip("PostGIS required for geometry column")

        db = Database(db_config)

        table_name = "test_spatial_custom_name"
        custom_index_name = "my_custom_gist_idx"

        try:
            # Create table with geometry column (requires PostGIS)
            db.execute(f"CREATE TEMP TABLE {table_name} (id INTEGER, geom GEOMETRY)")

            # Create spatial index with custom name
            db.spatial.create_spatial_index(table_name, "geom", name=custom_index_name)

            # Verify index was created with custom name
            result = db.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = %s AND indexname = %s
            """,
                [table_name, custom_index_name],
            )

            assert len(result) == 1
            assert result[0]["indexname"] == custom_index_name

        finally:
            try:
                db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
            except Exception:
                pass

    def test_spatial_operations_error_messages_are_helpful(self, db_config):
        """Test that spatial operation errors provide helpful context."""
        db = Database(db_config)

        # Create table without geometry
        table_name = "test_helpful_error"
        try:
            db.execute(f"CREATE TEMP TABLE {table_name} (id INTEGER)")

            # Try spatial index - error should be clear
            with pytest.raises(Exception) as exc_info:
                db.spatial.create_spatial_index(table_name, "nonexistent_column")

            error_msg = str(exc_info.value)
            # Error should mention something useful (column, table, or SQL context)
            assert len(error_msg) > 20  # Not just a generic error
            # Should contain some context about what went wrong
            assert any(
                word in error_msg.lower()
                for word in [
                    "column",
                    "table",
                    "exist",
                    "found",
                    "gist",
                    "geometry",
                    "index",
                ]
            )

        finally:
            try:
                db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
            except Exception:
                pass
