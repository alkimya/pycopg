"""Tests for pycopg.spatial — DB-free builder tests (no DB connection)."""

import json

import pytest

from pycopg.exceptions import InvalidIdentifier
from pycopg.spatial import (
    _REF_SENTINEL,
    _resolve_geometry,
    build_area_sql,
    build_buffer_sql,
    build_centroid_sql,
    build_contains_sql,
    build_distance_sql,
    build_dwithin_sql,
    build_intersects_sql,
    build_nearest_sql,
    build_perimeter_sql,
    build_transform_sql,
    build_within_sql,
)

_GJ = {"type": "Point", "coordinates": [1.0, 2.0]}


class TestGeometryResolver:
    """DB-free tests for _resolve_geometry — all 4 forms + exclusivity."""

    def test_point_form(self):
        """point=(x, y) yields ST_MakePoint fragment with [x, y] params."""
        frag, params = _resolve_geometry(point=(1, 2))
        assert frag == "ST_SetSRID(ST_MakePoint(%s, %s), 4326)"
        assert params == [1, 2]

    def test_wkt_form(self):
        """wkt= yields ST_GeomFromText fragment with the WKT as param."""
        frag, params = _resolve_geometry(wkt="POINT(0 0)")
        assert frag == "ST_GeomFromText(%s, 4326)"
        assert params == ["POINT(0 0)"]

    def test_geojson_form(self):
        """geojson= yields ST_GeomFromGeoJSON with json.dumps param."""
        frag, params = _resolve_geometry(geojson=_GJ)
        assert frag == "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)"
        assert params == [json.dumps(_GJ)]

    def test_ref_form_returns_sentinel(self):
        """ref= returns the sentinel with the validated identifiers."""
        frag, params = _resolve_geometry(ref=("zones", "geom"))
        assert frag == _REF_SENTINEL
        assert params == ["zones", "geom"]

    def test_ref_form_validates_identifiers(self):
        """ref= with an invalid table name raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            _resolve_geometry(ref=("bad-name", "g"))

    def test_no_form_raises_valueerror(self):
        """Zero geometry input forms raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one of"):
            _resolve_geometry()

    def test_two_forms_raise_valueerror(self):
        """Two geometry input forms raise ValueError."""
        with pytest.raises(ValueError, match="Exactly one of"):
            _resolve_geometry(point=(1, 2), wkt="POINT(0 0)")

    def test_custom_srid_interpolated(self):
        """srid=3857 is interpolated as an int literal."""
        frag, _ = _resolve_geometry(point=(1, 2), srid=3857)
        assert frag == "ST_SetSRID(ST_MakePoint(%s, %s), 3857)"

    def test_srid_coerced_to_int(self):
        """A string srid is coerced via int() before interpolation."""
        frag, _ = _resolve_geometry(wkt="POINT(0 0)", srid="3857")
        assert frag == "ST_GeomFromText(%s, 3857)"


class TestBuilders:
    """Exact SQL string + params assertions for every pure builder."""

    # -- contains ------------------------------------------------------

    def test_contains_point_form(self):
        """contains with point= builds ST_Contains with %s coords."""
        sql, params = build_contains_sql("parcels", point=(-122.4, 37.8))
        assert sql == (
            "SELECT * FROM public.parcels AS t WHERE ST_Contains(t.geometry, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
        )
        assert params == [-122.4, 37.8]

    def test_contains_wkt_form(self):
        """contains with wkt= parameterizes the WKT string."""
        sql, params = build_contains_sql("parcels", wkt="POINT(0 0)")
        assert "ST_Contains(t.geometry, ST_GeomFromText(%s, 4326))" in sql
        assert params == ["POINT(0 0)"]

    def test_contains_geojson_form(self):
        """contains with geojson= parameterizes the serialized JSON."""
        sql, params = build_contains_sql("parcels", geojson=_GJ)
        assert "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)" in sql
        assert params == [json.dumps(_GJ)]

    def test_contains_ref_form_builds_exists(self):
        """contains with ref= produces an EXISTS subquery (D-08)."""
        sql, params = build_contains_sql("parcels", ref=("zones", "geom"))
        assert sql == (
            "SELECT * FROM public.parcels AS t WHERE EXISTS "
            "(SELECT 1 FROM zones AS _ref "
            "WHERE ST_Contains(_ref.geom, t.geometry))"
        )
        assert params == []

    def test_contains_ref_invalid_identifier(self):
        """contains with an invalid ref table raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            build_contains_sql("t", ref=("bad-name", "g"))

    def test_contains_invalid_table(self):
        """An invalid table name raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            build_contains_sql("bad-name", point=(1, 2))

    def test_contains_custom_geom_and_schema(self):
        """Custom geom= and schema= are interpolated after validation."""
        sql, _ = build_contains_sql("parcels", geom="geog", schema="gis", point=(1, 2))
        assert "FROM gis.parcels AS t" in sql
        assert "ST_Contains(t.geog," in sql

    def test_contains_columns(self):
        """columns= replaces * with a comma-joined list."""
        sql, _ = build_contains_sql("parcels", point=(1, 2), columns=["id", "name"])
        assert sql.startswith("SELECT id, name FROM public.parcels AS t")

    def test_contains_invalid_column(self):
        """An invalid column name raises InvalidIdentifier."""
        with pytest.raises(InvalidIdentifier):
            build_contains_sql("parcels", point=(1, 2), columns=["bad-col"])

    def test_contains_where_appended_with_and(self):
        """where= is combined as AND (...) after the spatial condition."""
        sql, _ = build_contains_sql("parcels", point=(1, 2), where="status = 'active'")
        assert sql.endswith("AND (status = 'active')")

    def test_contains_order_by_and_limit(self):
        """order_by= and limit= append the trailing clauses."""
        sql, _ = build_contains_sql(
            "parcels", point=(1, 2), order_by="id DESC", limit=10
        )
        assert sql.endswith("ORDER BY id DESC LIMIT 10")

    # -- intersects ----------------------------------------------------

    def test_intersects_point_form(self):
        """intersects builds ST_Intersects with %s coords."""
        sql, params = build_intersects_sql("roads", point=(1.5, 2.5))
        assert sql == (
            "SELECT * FROM public.roads AS t WHERE ST_Intersects(t.geometry, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
        )
        assert params == [1.5, 2.5]

    def test_intersects_ref_form_builds_exists(self):
        """intersects with ref= produces an EXISTS subquery (D-08)."""
        sql, params = build_intersects_sql("roads", ref=("zones", "geom"))
        assert (
            "EXISTS (SELECT 1 FROM zones AS _ref "
            "WHERE ST_Intersects(_ref.geom, t.geometry))" in sql
        )
        assert params == []

    def test_intersects_columns_where(self):
        """intersects supports columns= and where= together."""
        sql, _ = build_intersects_sql(
            "roads", wkt="LINESTRING(0 0, 1 1)", columns=["id"], where="lanes > 2"
        )
        assert sql.startswith("SELECT id FROM public.roads AS t")
        assert sql.endswith("AND (lanes > 2)")

    # -- within (two-table join form) ----------------------------------

    def test_within_join_form(self):
        """within builds the dedicated two-table JOIN (08-DESIGN §3)."""
        sql, params = build_within_sql("parcels", "geometry", "zones", "geom")
        assert sql == (
            "SELECT * FROM public.parcels AS a JOIN public.zones AS b "
            "ON ST_Within(a.geometry, b.geom)"
        )
        assert params == []

    def test_within_where_uses_where_keyword(self):
        """within has no prior WHERE — where= starts the clause."""
        sql, _ = build_within_sql(
            "parcels", "geometry", "zones", "geom", where="a.id > 5"
        )
        assert " WHERE a.id > 5" in sql

    def test_within_columns_order_limit(self):
        """within supports columns=, order_by= and limit=."""
        sql, _ = build_within_sql(
            "parcels",
            "geometry",
            "zones",
            "geom",
            columns=["id"],
            order_by="id",
            limit=3,
        )
        assert sql.startswith("SELECT id FROM")
        assert sql.endswith("ORDER BY id LIMIT 3")

    def test_within_invalid_identifier(self):
        """within validates all four table/geom identifiers."""
        with pytest.raises(InvalidIdentifier):
            build_within_sql("parcels", "geometry", "bad-name", "geom")

    # -- dwithin -------------------------------------------------------

    def test_dwithin_unit_m_uses_geography_cast(self):
        """dwithin unit='m' casts both sides to ::geography (D-09)."""
        sql, params = build_dwithin_sql("parcels", point=(1.0, 2.0), distance=100)
        assert sql == (
            "SELECT * FROM public.parcels AS t WHERE "
            "ST_DWithin(t.geometry::geography, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
        )
        assert params == [1.0, 2.0, 100]

    def test_dwithin_unit_srid_no_cast(self):
        """dwithin unit='srid' has no ::geography cast (D-09)."""
        sql, params = build_dwithin_sql(
            "parcels", point=(1.0, 2.0), distance=0.5, unit="srid"
        )
        assert "::geography" not in sql
        assert "ST_DWithin(t.geometry, " in sql
        assert params == [1.0, 2.0, 0.5]

    def test_dwithin_ref_form_builds_exists(self):
        """dwithin with ref= embeds the distance %s inside EXISTS."""
        sql, params = build_dwithin_sql("parcels", ref=("zones", "geom"), distance=250)
        assert sql == (
            "SELECT * FROM public.parcels AS t WHERE EXISTS "
            "(SELECT 1 FROM zones AS _ref "
            "WHERE ST_DWithin(_ref.geom::geography, "
            "t.geometry::geography, %s))"
        )
        assert params == [250]

    def test_dwithin_invalid_unit(self):
        """dwithin with an unknown unit raises ValueError."""
        with pytest.raises(ValueError, match="unit must be"):
            build_dwithin_sql("parcels", point=(1, 2), distance=1, unit="km")

    def test_dwithin_tail_clauses(self):
        """dwithin supports where=/order_by=/limit= (D-12)."""
        sql, _ = build_dwithin_sql(
            "parcels",
            point=(1, 2),
            distance=10,
            where="kind = 'park'",
            order_by="id",
            limit=5,
        )
        assert sql.endswith("AND (kind = 'park') ORDER BY id LIMIT 5")

    # -- distance ------------------------------------------------------

    def test_distance_unit_m(self):
        """distance unit='m' casts both sides and aliases AS distance."""
        sql, params = build_distance_sql("parcels", point=(1.0, 2.0))
        assert sql == (
            "SELECT *, ST_Distance(t.geometry::geography, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) AS distance "
            "FROM public.parcels AS t"
        )
        assert params == [1.0, 2.0]

    def test_distance_unit_srid_no_cast(self):
        """distance unit='srid' has no ::geography casts."""
        sql, _ = build_distance_sql("parcels", point=(1, 2), unit="srid")
        assert "::geography" not in sql
        assert "ST_Distance(t.geometry, " in sql

    def test_distance_order_by_distance_column(self):
        """distance supports ordering by the computed column."""
        sql, _ = build_distance_sql(
            "parcels", wkt="POINT(0 0)", order_by="distance", limit=2
        )
        assert sql.endswith("ORDER BY distance LIMIT 2")

    def test_distance_where_uses_where_keyword(self):
        """distance has no spatial WHERE — where= starts the clause."""
        sql, _ = build_distance_sql("parcels", point=(1, 2), where="id > 3")
        assert " WHERE id > 3" in sql

    def test_distance_invalid_unit(self):
        """distance with an unknown unit raises ValueError."""
        with pytest.raises(ValueError, match="unit must be"):
            build_distance_sql("parcels", point=(1, 2), unit="ft")

    # -- nearest -------------------------------------------------------

    def test_nearest_knn_operator_and_limit_param(self):
        """nearest emits geography <-> ordering with k as LIMIT %s."""
        sql, params = build_nearest_sql("parcels", point=(1.0, 2.0), k=3)
        assert sql == (
            "SELECT * FROM public.parcels AS t ORDER BY "
            "t.geometry::geography <-> "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography LIMIT %s"
        )
        assert params == [1.0, 2.0, 3]

    def test_nearest_default_k(self):
        """nearest defaults to k=5."""
        _, params = build_nearest_sql("parcels", point=(1, 2))
        assert params[-1] == 5

    def test_nearest_with_where(self):
        """nearest places where= before the KNN ORDER BY."""
        sql, _ = build_nearest_sql("parcels", point=(1, 2), where="id > 0")
        assert " WHERE id > 0 ORDER BY " in sql

    def test_nearest_columns(self):
        """nearest supports columns=."""
        sql, _ = build_nearest_sql("parcels", point=(1, 2), columns=["id"])
        assert sql.startswith("SELECT id FROM public.parcels AS t")

    # -- area / perimeter ----------------------------------------------

    def test_area_unit_m_geography(self):
        """area unit='m' computes ST_Area on ::geography."""
        sql, params = build_area_sql("parcels")
        assert sql == (
            "SELECT *, ST_Area(t.geometry::geography) AS area "
            "FROM public.parcels AS t"
        )
        assert params == []

    def test_area_unit_srid_native(self):
        """area unit='srid' computes ST_Area without cast."""
        sql, _ = build_area_sql("parcels", unit="srid")
        assert "ST_Area(t.geometry) AS area" in sql

    def test_area_invalid_unit(self):
        """area with an unknown unit raises ValueError."""
        with pytest.raises(ValueError, match="unit must be"):
            build_area_sql("parcels", unit="acres")

    def test_area_tail_clauses(self):
        """area supports where=/order_by=/limit=."""
        sql, _ = build_area_sql(
            "parcels", where="id > 1", order_by="area DESC", limit=4
        )
        assert sql.endswith("WHERE id > 1 ORDER BY area DESC LIMIT 4")

    def test_perimeter_unit_m_geography(self):
        """perimeter unit='m' computes ST_Perimeter on ::geography."""
        sql, params = build_perimeter_sql("parcels")
        assert sql == (
            "SELECT *, ST_Perimeter(t.geometry::geography) AS perimeter "
            "FROM public.parcels AS t"
        )
        assert params == []

    def test_perimeter_unit_srid_native(self):
        """perimeter unit='srid' computes ST_Perimeter without cast."""
        sql, _ = build_perimeter_sql("parcels", unit="srid")
        assert "ST_Perimeter(t.geometry) AS perimeter" in sql

    def test_perimeter_invalid_unit(self):
        """perimeter with an unknown unit raises ValueError."""
        with pytest.raises(ValueError, match="unit must be"):
            build_perimeter_sql("parcels", unit="yd")

    def test_perimeter_columns(self):
        """perimeter supports columns=."""
        sql, _ = build_perimeter_sql("parcels", columns=["id"])
        assert sql.startswith("SELECT id, ST_Perimeter(")

    # -- centroid ------------------------------------------------------

    def test_centroid_emits_x_y_columns(self):
        """centroid emits ST_X/ST_Y scalar columns (no unit=, D-10)."""
        sql, params = build_centroid_sql("parcels")
        assert sql == (
            "SELECT *, ST_X(ST_Centroid(t.geometry)) AS centroid_x, "
            "ST_Y(ST_Centroid(t.geometry)) AS centroid_y "
            "FROM public.parcels AS t"
        )
        assert params == []

    def test_centroid_tail_clauses(self):
        """centroid supports where=/order_by=/limit=."""
        sql, _ = build_centroid_sql("parcels", where="id = 1", order_by="id", limit=1)
        assert sql.endswith("WHERE id = 1 ORDER BY id LIMIT 1")

    def test_centroid_columns(self):
        """centroid supports columns= and invalid columns raise."""
        sql, _ = build_centroid_sql("parcels", columns=["id"])
        assert sql.startswith("SELECT id, ST_X(")
        with pytest.raises(InvalidIdentifier):
            build_centroid_sql("parcels", columns=["bad-col"])

    # -- buffer --------------------------------------------------------

    def test_buffer_unit_m_geography_roundtrip(self):
        """buffer unit='m' casts to geography then back to geometry."""
        sql, params = build_buffer_sql("parcels", distance=50)
        assert sql == (
            "SELECT *, ST_Buffer(t.geometry::geography, %s)::geometry "
            "AS buffer FROM public.parcels AS t"
        )
        assert params == [50]

    def test_buffer_unit_srid_no_cast(self):
        """buffer unit='srid' buffers the raw geometry."""
        sql, params = build_buffer_sql("parcels", distance=0.1, unit="srid")
        assert "ST_Buffer(t.geometry, %s) AS buffer" in sql
        assert "::geography" not in sql
        assert params == [0.1]

    def test_buffer_invalid_unit(self):
        """buffer with an unknown unit raises ValueError."""
        with pytest.raises(ValueError, match="unit must be"):
            build_buffer_sql("parcels", distance=1, unit="mi")

    def test_buffer_tail_clauses(self):
        """buffer supports where=/order_by=/limit=."""
        sql, _ = build_buffer_sql(
            "parcels", distance=10, where="id > 0", order_by="id", limit=2
        )
        assert sql.endswith("WHERE id > 0 ORDER BY id LIMIT 2")

    # -- transform -----------------------------------------------------

    def test_transform_parameterizes_to_srid(self):
        """transform emits ST_Transform with to_srid as %s param."""
        sql, params = build_transform_sql("parcels", to_srid=3857)
        assert sql == (
            "SELECT *, ST_Transform(t.geometry, %s) AS geometry_transformed "
            "FROM public.parcels AS t"
        )
        assert params == [3857]

    def test_transform_tail_clauses(self):
        """transform supports columns=/where=/order_by=/limit=."""
        sql, _ = build_transform_sql(
            "parcels",
            to_srid=2154,
            columns=["id"],
            where="id < 9",
            order_by="id",
            limit=7,
        )
        assert sql.startswith("SELECT id, ST_Transform(")
        assert sql.endswith("WHERE id < 9 ORDER BY id LIMIT 7")

    def test_transform_invalid_table(self):
        """transform validates the table identifier."""
        with pytest.raises(InvalidIdentifier):
            build_transform_sql("bad-name", to_srid=4326)
