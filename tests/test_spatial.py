"""Tests for pycopg.spatial — DB-free builder/guard tests + PostGIS integration."""

import json

import pytest

from pycopg.exceptions import ExtensionNotAvailableError, InvalidIdentifierError
from pycopg.spatial import (
    _REF_SENTINEL,
    AsyncSpatialAccessor,
    SpatialAccessor,
    _resolve_geometry,
    build_area_sql,
    build_buffer_sql,
    build_centroid_sql,
    build_collect_geometries_sql,
    build_contains_sql,
    build_convex_hull_sql,
    build_difference_sql,
    build_distance_sql,
    build_dwithin_sql,
    build_extent_sql,
    build_intersection_sql,
    build_intersects_sql,
    build_make_valid_sql,
    build_nearest_sql,
    build_perimeter_sql,
    build_simplify_sql,
    build_transform_sql,
    build_union_aggregate_sql,
    build_union_sql,
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
        """ref= with an invalid table name raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
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
        """contains with an invalid ref table raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
            build_contains_sql("t", ref=("bad-name", "g"))

    def test_contains_invalid_table(self):
        """An invalid table name raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
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
        """An invalid column name raises InvalidIdentifierError."""
        with pytest.raises(InvalidIdentifierError):
            build_contains_sql("parcels", point=(1, 2), columns=["bad-col"])

    def test_contains_where_appended_with_and(self):
        """filter= is combined as AND (...) after the spatial condition."""
        sql, _ = build_contains_sql("parcels", point=(1, 2), filter="status = 'active'")
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
        """intersects supports columns= and filter= together."""
        sql, _ = build_intersects_sql(
            "roads", wkt="LINESTRING(0 0, 1 1)", columns=["id"], filter="lanes > 2"
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
        """within has no prior WHERE — filter= starts the clause."""
        sql, _ = build_within_sql(
            "parcels", "geometry", "zones", "geom", filter="a.id > 5"
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
        with pytest.raises(InvalidIdentifierError):
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
        """dwithin supports filter=/order_by=/limit= (D-12)."""
        sql, _ = build_dwithin_sql(
            "parcels",
            point=(1, 2),
            distance=10,
            filter="kind = 'park'",
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
        """distance has no spatial WHERE — filter= starts the clause."""
        sql, _ = build_distance_sql("parcels", point=(1, 2), filter="id > 3")
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
        """nearest places filter= before the KNN ORDER BY."""
        sql, _ = build_nearest_sql("parcels", point=(1, 2), filter="id > 0")
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
        """area supports filter=/order_by=/limit=."""
        sql, _ = build_area_sql(
            "parcels", filter="id > 1", order_by="area DESC", limit=4
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
        """centroid supports filter=/order_by=/limit=."""
        sql, _ = build_centroid_sql("parcels", filter="id = 1", order_by="id", limit=1)
        assert sql.endswith("WHERE id = 1 ORDER BY id LIMIT 1")

    def test_centroid_columns(self):
        """centroid supports columns= and invalid columns raise."""
        sql, _ = build_centroid_sql("parcels", columns=["id"])
        assert sql.startswith("SELECT id, ST_X(")
        with pytest.raises(InvalidIdentifierError):
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
        """buffer supports filter=/order_by=/limit=."""
        sql, _ = build_buffer_sql(
            "parcels", distance=10, filter="id > 0", order_by="id", limit=2
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
        """transform supports columns=/filter=/order_by=/limit=."""
        sql, _ = build_transform_sql(
            "parcels",
            to_srid=2154,
            columns=["id"],
            filter="id < 9",
            order_by="id",
            limit=7,
        )
        assert sql.startswith("SELECT id, ST_Transform(")
        assert sql.endswith("WHERE id < 9 ORDER BY id LIMIT 7")

    def test_transform_invalid_table(self):
        """transform validates the table identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_transform_sql("bad-name", to_srid=4326)

    # -- union ---------------------------------------------------------

    def test_union_emits_st_union(self):
        """union emits ST_Union with union_geom alias and empty params."""
        sql, params = build_union_sql("parcels", other_geom="geom2")
        assert sql == (
            "SELECT *, ST_Union(t.geometry, t.geom2) AS union_geom "
            "FROM public.parcels AS t"
        )
        assert params == []

    def test_union_tail_clauses(self):
        """union supports columns=/filter=/order_by=/limit=."""
        sql, _ = build_union_sql(
            "parcels",
            other_geom="geom2",
            columns=["id"],
            filter="id < 9",
            order_by="id",
            limit=7,
        )
        assert sql.startswith("SELECT id, ST_Union(")
        assert sql.endswith("WHERE id < 9 ORDER BY id LIMIT 7")

    def test_union_invalid_table(self):
        """union validates the table identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_union_sql("bad-name", other_geom="geom2")

    def test_union_invalid_other_geom(self):
        """union validates the other_geom identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_union_sql("parcels", other_geom="bad-col; DROP TABLE")

    # -- difference ----------------------------------------------------

    def test_difference_emits_st_difference(self):
        """difference emits ST_Difference with difference alias and empty params."""
        sql, params = build_difference_sql("parcels", other_geom="geom2")
        assert sql == (
            "SELECT *, ST_Difference(t.geometry, t.geom2) AS difference "
            "FROM public.parcels AS t"
        )
        assert params == []

    def test_difference_tail_clauses(self):
        """difference supports columns=/filter=/order_by=/limit=."""
        sql, _ = build_difference_sql(
            "parcels",
            other_geom="geom2",
            columns=["id"],
            filter="id < 9",
            order_by="id",
            limit=7,
        )
        assert sql.startswith("SELECT id, ST_Difference(")
        assert sql.endswith("WHERE id < 9 ORDER BY id LIMIT 7")

    def test_difference_invalid_table(self):
        """difference validates the table identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_difference_sql("bad-name", other_geom="geom2")

    def test_difference_invalid_other_geom(self):
        """difference validates the other_geom identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_difference_sql("parcels", other_geom="bad-col; DROP TABLE")

    # -- intersection --------------------------------------------------

    def test_intersection_emits_st_intersection(self):
        """intersection emits ST_Intersection with intersection alias and empty params."""
        sql, params = build_intersection_sql("parcels", other_geom="geom2")
        assert sql == (
            "SELECT *, ST_Intersection(t.geometry, t.geom2) AS intersection "
            "FROM public.parcels AS t"
        )
        assert params == []

    def test_intersection_tail_clauses(self):
        """intersection supports columns=/filter=/order_by=/limit=."""
        sql, _ = build_intersection_sql(
            "parcels",
            other_geom="geom2",
            columns=["id"],
            filter="id < 9",
            order_by="id",
            limit=7,
        )
        assert sql.startswith("SELECT id, ST_Intersection(")
        assert sql.endswith("WHERE id < 9 ORDER BY id LIMIT 7")

    def test_intersection_invalid_table(self):
        """intersection validates the table identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_intersection_sql("bad-name", other_geom="geom2")

    def test_intersection_invalid_other_geom(self):
        """intersection validates the other_geom identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_intersection_sql("parcels", other_geom="bad-col; DROP TABLE")

    # -- simplify -------------------------------------------------------

    def test_simplify_preserve_topology_default(self):
        """simplify defaults to ST_SimplifyPreserveTopology with 1 param."""
        sql, params = build_simplify_sql("parcels", tolerance=0.5)
        assert sql == (
            "SELECT *, ST_SimplifyPreserveTopology(t.geometry, %s) AS simplified "
            "FROM public.parcels AS t"
        )
        assert params == [0.5]
        assert sql.count("%s") == len(params)

    def test_simplify_no_preserve_topology(self):
        """preserve_topology=False emits ST_Simplify with 2 params."""
        sql, params = build_simplify_sql(
            "parcels", tolerance=0.5, preserve_topology=False
        )
        assert "ST_Simplify(t.geometry, %s, %s)" in sql
        assert "AS simplified" in sql
        assert params == [0.5, False]
        assert sql.count("%s") == len(params)

    def test_simplify_contradictory_args(self):
        """preserve_collapsed=True + preserve_topology=True raises ValueError."""
        with pytest.raises(ValueError, match="preserve_collapsed"):
            build_simplify_sql(
                "parcels",
                tolerance=0.5,
                preserve_topology=True,
                preserve_collapsed=True,
            )

    def test_simplify_tail_clauses(self):
        """simplify supports columns=/filter=/order_by=/limit=."""
        sql, _ = build_simplify_sql(
            "parcels",
            tolerance=0.01,
            columns=["id"],
            filter="id < 9",
            order_by="id",
            limit=5,
        )
        assert sql.startswith("SELECT id, ST_SimplifyPreserveTopology(")
        assert sql.endswith("WHERE id < 9 ORDER BY id LIMIT 5")

    def test_simplify_invalid_table(self):
        """simplify validates the table identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_simplify_sql("bad-name", tolerance=0.5)

    def test_simplify_invalid_columns(self):
        """simplify validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_simplify_sql("parcels", tolerance=0.5, columns=["bad-col"])

    # -- convex_hull ----------------------------------------------------

    def test_convex_hull_emits_st_convex_hull(self):
        """convex_hull emits ST_ConvexHull with convex_hull alias and empty params."""
        sql, params = build_convex_hull_sql("parcels")
        assert sql == (
            "SELECT *, ST_ConvexHull(t.geometry) AS convex_hull "
            "FROM public.parcels AS t"
        )
        assert params == []

    def test_convex_hull_tail_clauses(self):
        """convex_hull supports columns=/filter=/order_by=/limit=."""
        sql, _ = build_convex_hull_sql(
            "parcels",
            columns=["id"],
            filter="id < 9",
            order_by="id",
            limit=3,
        )
        assert sql.startswith("SELECT id, ST_ConvexHull(")
        assert sql.endswith("WHERE id < 9 ORDER BY id LIMIT 3")

    def test_convex_hull_invalid_table(self):
        """convex_hull validates the table identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_convex_hull_sql("bad-name")

    def test_convex_hull_invalid_columns(self):
        """convex_hull validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_convex_hull_sql("parcels", columns=["bad-col"])

    # -- make_valid -----------------------------------------------------

    def test_make_valid_no_method(self):
        """make_valid with no method emits ST_MakeValid(t.geom) with empty params."""
        sql, params = build_make_valid_sql("parcels")
        assert sql == (
            "SELECT *, ST_MakeValid(t.geometry) AS made_valid "
            "FROM public.parcels AS t"
        )
        assert params == []

    def test_make_valid_linework(self):
        """make_valid(method='linework') emits %s with 'method=linework' param."""
        sql, params = build_make_valid_sql("parcels", method="linework")
        assert "ST_MakeValid(t.geometry, %s)" in sql
        assert "AS made_valid" in sql
        assert params == ["method=linework"]
        assert sql.count("%s") == len(params)

    def test_make_valid_structure_keepcollapsed_true(self):
        """make_valid(method='structure', keep_collapsed=True) builds correct params string."""
        sql, params = build_make_valid_sql(
            "parcels", method="structure", keep_collapsed=True
        )
        assert "ST_MakeValid(t.geometry, %s)" in sql
        assert params == ["method=structure keepcollapsed=true"]

    def test_make_valid_structure_keepcollapsed_false(self):
        """make_valid(method='structure', keep_collapsed=False) builds correct params string."""
        sql, params = build_make_valid_sql(
            "parcels", method="structure", keep_collapsed=False
        )
        assert params == ["method=structure keepcollapsed=false"]

    def test_make_valid_structure_no_keepcollapsed(self):
        """make_valid(method='structure', keep_collapsed=None) omits keepcollapsed."""
        sql, params = build_make_valid_sql("parcels", method="structure")
        assert params == ["method=structure"]

    def test_make_valid_invalid_method(self):
        """make_valid with an unknown method raises ValueError."""
        with pytest.raises(ValueError, match="method must be one of"):
            build_make_valid_sql("parcels", method="bogus")

    def test_make_valid_keep_collapsed_without_structure(self):
        """keep_collapsed with method!='structure' raises ValueError."""
        with pytest.raises(ValueError, match="keep_collapsed"):
            build_make_valid_sql("parcels", method="linework", keep_collapsed=True)

    def test_make_valid_keep_collapsed_without_any_method(self):
        """keep_collapsed with method=None raises ValueError."""
        with pytest.raises(ValueError, match="keep_collapsed"):
            build_make_valid_sql("parcels", method=None, keep_collapsed=True)

    def test_make_valid_invalid_table(self):
        """make_valid validates the table identifier."""
        with pytest.raises(InvalidIdentifierError):
            build_make_valid_sql("bad-name")

    def test_make_valid_invalid_columns(self):
        """make_valid validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_make_valid_sql("parcels", columns=["bad-col"])


class _FakeSyncSchema:
    """Minimal schema stub for _FakeSyncDb."""

    def __init__(self, has_postgis):
        self._has_postgis = has_postgis

    def has_extension(self, name):
        return self._has_postgis


class _FakeAsyncSchema:
    """Minimal async schema stub for _FakeAsyncDb."""

    def __init__(self, has_postgis):
        self._has_postgis = has_postgis

    async def has_extension(self, name):
        return self._has_postgis


class _FakeSyncDb:
    """Minimal stand-in for Database in DB-free guard tests."""

    def __init__(self, has_postgis):
        self._has_postgis = has_postgis
        self.schema = _FakeSyncSchema(has_postgis)

    def has_extension(self, name):
        return self._has_postgis


class _FakeAsyncDb:
    """Minimal stand-in for AsyncDatabase in DB-free guard tests."""

    def __init__(self, has_postgis):
        self._has_postgis = has_postgis
        self.schema = _FakeAsyncSchema(has_postgis)

    async def has_extension(self, name):
        return self._has_postgis


class TestGuard:
    """PostGIS guard and into= validation behavior (mocked, no real DB)."""

    def test_sync_accessor_raises_when_postgis_missing(self):
        """SpatialAccessor raises ExtensionNotAvailableError at construction."""
        with pytest.raises(ExtensionNotAvailableError, match="PostGIS extension"):
            SpatialAccessor(_FakeSyncDb(has_postgis=False))

    async def test_async_accessor_raises_on_first_call(self):
        """AsyncSpatialAccessor defers the guard to the first method call."""
        acc = AsyncSpatialAccessor(_FakeAsyncDb(has_postgis=False))
        with pytest.raises(ExtensionNotAvailableError, match="PostGIS extension"):
            await acc.contains("parcels", point=(1, 2))

    @pytest.mark.parametrize("helper", ["area", "perimeter", "distance", "centroid"])
    def test_sync_scalar_helper_rejects_gdf(self, helper):
        """into='gdf' on a scalar helper raises ValueError (D-02)."""
        acc = SpatialAccessor(_FakeSyncDb(has_postgis=True))
        kwargs = {"into": "gdf"}
        if helper == "distance":
            kwargs["point"] = (1, 2)
        with pytest.raises(ValueError, match=f"into='gdf' is invalid for {helper}"):
            getattr(acc, helper)("parcels", **kwargs)

    async def test_async_scalar_helper_rejects_gdf(self):
        """Async into='gdf' scalar rejection mirrors the sync side (D-02)."""
        acc = AsyncSpatialAccessor(_FakeAsyncDb(has_postgis=True))
        with pytest.raises(ValueError, match="into='gdf' is invalid for area"):
            await acc.area("parcels", into="gdf")

    def test_invalid_into_value_rejected(self):
        """An unknown into= value raises ValueError naming the allowed set."""
        acc = SpatialAccessor(_FakeSyncDb(has_postgis=True))
        with pytest.raises(ValueError, match="into must be one of"):
            acc.contains("parcels", point=(1, 2), into="query")


def _uniq(prefix):
    """Generate a unique lowercase table name for integration tests."""
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestIntegration:
    """Real PostGIS integration tests against pycopg_test."""

    @pytest.fixture
    def sdb(self, db_config):
        """Sync Database with PostGIS, or skip."""
        from pycopg import Database

        db = Database(db_config)
        try:
            if not db.schema.has_extension("postgis"):
                pytest.skip("PostGIS not available on test database")
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"test database unavailable: {exc}")
        return db

    def _make_points(self, db, t):
        """Create a points table with three rows at increasing distance."""
        db.execute(
            f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
            "geometry geometry(Point, 4326))",
            autocommit=True,
        )
        db.execute(
            f'INSERT INTO "{t}" VALUES '
            "(1, ST_GeomFromText('POINT(0 0)', 4326)), "
            "(2, ST_GeomFromText('POINT(0.1 0.1)', 4326)), "
            "(3, ST_GeomFromText('POINT(10 10)', 4326))",
            autocommit=True,
        )

    def test_contains_returns_correct_rows(self, sdb):
        """contains returns only the polygon containing the point."""
        t = _uniq("spat_contains")
        try:
            sdb.execute(
                f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
                "geometry geometry(Polygon, 4326))",
                autocommit=True,
            )
            sdb.execute(
                f'INSERT INTO "{t}" VALUES '
                "(1, ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326)), "
                "(2, ST_GeomFromText('POLYGON((5 5, 6 5, 6 6, 5 6, 5 5))', 4326))",
                autocommit=True,
            )
            rows = sdb.spatial.contains(t, point=(0.5, 0.5), columns=["id"])
            assert rows == [{"id": 1}]
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_dwithin_filters_by_distance(self, sdb):
        """dwithin unit='m' keeps only rows within the meter radius."""
        t = _uniq("spat_dwithin")
        try:
            self._make_points(sdb, t)
            rows = sdb.spatial.dwithin(
                t, point=(0, 0), distance=20000, columns=["id"], order_by="id"
            )
            assert [r["id"] for r in rows] == [1, 2]
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_nearest_returns_k_closest_in_order(self, sdb):
        """nearest returns the k closest rows ordered by proximity."""
        t = _uniq("spat_nearest")
        try:
            self._make_points(sdb, t)
            rows = sdb.spatial.nearest(t, point=(0.01, 0.01), k=2, columns=["id"])
            assert [r["id"] for r in rows] == [1, 2]
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_area_returns_positive_scalar(self, sdb):
        """area unit='m' returns a positive square-meter value."""
        t = _uniq("spat_area")
        try:
            sdb.execute(
                f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
                "geometry geometry(Polygon, 4326))",
                autocommit=True,
            )
            sdb.execute(
                f'INSERT INTO "{t}" VALUES '
                "(1, ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326))",
                autocommit=True,
            )
            rows = sdb.spatial.area(t, columns=["id"])
            assert rows[0]["area"] > 0
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_buffer_into_gdf_returns_geodataframe(self, sdb):
        """buffer with into='gdf' returns a GeoDataFrame (gdf params path)."""
        import geopandas as gpd

        t = _uniq("spat_buffer")
        try:
            self._make_points(sdb, t)
            gdf = sdb.spatial.buffer(t, distance=1000, into="gdf")
            assert isinstance(gdf, gpd.GeoDataFrame)
            assert len(gdf) == 3
            assert gdf.geometry.name == "buffer"
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_transform_changes_srid(self, sdb):
        """transform with into='gdf' returns geometry in the target CRS."""
        t = _uniq("spat_transform")
        try:
            self._make_points(sdb, t)
            gdf = sdb.spatial.transform(t, to_srid=3857, into="gdf")
            assert gdf.crs is not None
            assert gdf.crs.to_epsg() == 3857
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_distance_into_gdf_raises_valueerror(self, sdb):
        """distance with into='gdf' raises before executing (D-02)."""
        with pytest.raises(ValueError, match="into='gdf' is invalid for distance"):
            sdb.spatial.distance("any_table", point=(0, 0), into="gdf")

    async def test_async_contains_returns_rows(self, sdb, db_config):
        """Async contains returns the same rows end-to-end (parity proof)."""
        from pycopg import AsyncDatabase

        adb = AsyncDatabase(db_config)
        t = _uniq("spat_async")
        try:
            await adb.execute(
                f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
                "geometry geometry(Polygon, 4326))",
                autocommit=True,
            )
            await adb.execute(
                f'INSERT INTO "{t}" VALUES '
                "(1, ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326))",
                autocommit=True,
            )
            rows = await adb.spatial.contains(t, point=(0.5, 0.5), columns=["id"])
            assert rows == [{"id": 1}]
        finally:
            await adb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def _make_two_geom_table(self, db, t):
        """Create a table with two overlapping polygon geometry columns."""
        db.execute(
            f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
            "geom_a geometry(Polygon, 4326), geom_b geometry(Polygon, 4326))",
            autocommit=True,
        )
        db.execute(
            f'INSERT INTO "{t}" VALUES '
            "(1, ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326), "
            "    ST_GeomFromText('POLYGON((0.5 0.5, 1.5 0.5, 1.5 1.5, 0.5 1.5, 0.5 0.5))', 4326))",
            autocommit=True,
        )

    def _make_mixed_srid_table(self, db, t):
        """Create a table with two geometry columns of different SRIDs."""
        db.execute(
            f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
            "geom_a geometry(Polygon, 4326), geom_b geometry(Polygon, 32632))",
            autocommit=True,
        )
        db.execute(
            f'INSERT INTO "{t}" VALUES '
            "(1, ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326), "
            "    ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 32632))",
            autocommit=True,
        )

    def test_union_pairwise(self, sdb):
        """union returns non-empty rows with the union_geom D-01 key."""
        t = _uniq("spat_union")
        try:
            self._make_two_geom_table(sdb, t)
            rows = sdb.spatial.union(t, geom="geom_a", other_geom="geom_b")
            assert len(rows) == 1
            assert "union_geom" in rows[0]
            assert rows[0]["union_geom"] is not None
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_union_into_gdf(self, sdb):
        """union with into='gdf' returns a GeoDataFrame with union_geom as geometry."""
        import geopandas as gpd

        t = _uniq("spat_union_gdf")
        try:
            self._make_two_geom_table(sdb, t)
            gdf = sdb.spatial.union(t, geom="geom_a", other_geom="geom_b", into="gdf")
            assert isinstance(gdf, gpd.GeoDataFrame)
            assert gdf.geometry.name == "union_geom"
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_union_mixed_srid_raises(self, sdb):
        """union over mismatched-SRID columns raises a native PostGIS error (D-06)."""
        t = _uniq("spat_union_srid")
        try:
            self._make_mixed_srid_table(sdb, t)
            with pytest.raises(Exception):
                sdb.spatial.union(t, geom="geom_a", other_geom="geom_b")
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_difference_pairwise(self, sdb):
        """difference returns non-empty rows with the difference D-01 key."""
        t = _uniq("spat_diff")
        try:
            self._make_two_geom_table(sdb, t)
            rows = sdb.spatial.difference(t, geom="geom_a", other_geom="geom_b")
            assert len(rows) == 1
            assert "difference" in rows[0]
            assert rows[0]["difference"] is not None
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_difference_into_gdf(self, sdb):
        """difference with into='gdf' returns a GeoDataFrame with difference geometry."""
        import geopandas as gpd

        t = _uniq("spat_diff_gdf")
        try:
            self._make_two_geom_table(sdb, t)
            gdf = sdb.spatial.difference(
                t, geom="geom_a", other_geom="geom_b", into="gdf"
            )
            assert isinstance(gdf, gpd.GeoDataFrame)
            assert gdf.geometry.name == "difference"
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_difference_mixed_srid_raises(self, sdb):
        """difference over mismatched-SRID columns raises a native PostGIS error (D-06)."""
        t = _uniq("spat_diff_srid")
        try:
            self._make_mixed_srid_table(sdb, t)
            with pytest.raises(Exception):
                sdb.spatial.difference(t, geom="geom_a", other_geom="geom_b")
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_intersection_pairwise(self, sdb):
        """intersection returns non-empty rows with the intersection D-01 key."""
        t = _uniq("spat_inter")
        try:
            self._make_two_geom_table(sdb, t)
            rows = sdb.spatial.intersection(t, geom="geom_a", other_geom="geom_b")
            assert len(rows) == 1
            assert "intersection" in rows[0]
            assert rows[0]["intersection"] is not None
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_intersection_into_gdf(self, sdb):
        """intersection with into='gdf' returns a GeoDataFrame with intersection geometry."""
        import geopandas as gpd

        t = _uniq("spat_inter_gdf")
        try:
            self._make_two_geom_table(sdb, t)
            gdf = sdb.spatial.intersection(
                t, geom="geom_a", other_geom="geom_b", into="gdf"
            )
            assert isinstance(gdf, gpd.GeoDataFrame)
            assert gdf.geometry.name == "intersection"
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_intersection_mixed_srid_raises(self, sdb):
        """intersection over mismatched-SRID columns raises a native PostGIS error (D-06)."""
        t = _uniq("spat_inter_srid")
        try:
            self._make_mixed_srid_table(sdb, t)
            with pytest.raises(Exception):
                sdb.spatial.intersection(t, geom="geom_a", other_geom="geom_b")
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    # -- unary trio: simplify, convex_hull, make_valid ------------------

    def _make_bowtie_table(self, db, t):
        """Create a table with a single self-intersecting bowtie polygon (D-07)."""
        db.execute(
            f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
            "geometry geometry(Polygon, 4326))",
            autocommit=True,
        )
        db.execute(
            f'INSERT INTO "{t}" VALUES '
            "(1, ST_GeomFromText('POLYGON((0 0, 1 1, 1 0, 0 1, 0 0))', 4326))",
            autocommit=True,
        )

    def _make_tiny_polygon_table(self, db, t):
        """Create a table with a tiny polygon (all points within tolerance=1.0)."""
        db.execute(
            f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
            "geometry geometry(Polygon, 4326))",
            autocommit=True,
        )
        db.execute(
            f'INSERT INTO "{t}" VALUES '
            "(1, ST_GeomFromText('POLYGON((0 0, 0.0001 0, 0.0001 0.0001, 0 0.0001, 0 0))', 4326))",
            autocommit=True,
        )

    def test_simplify_preserve_topology_non_null(self, sdb):
        """simplify(preserve_topology=True) on a tiny polygon returns non-NULL (D-07)."""
        t = _uniq("spat_simplify")
        try:
            self._make_tiny_polygon_table(sdb, t)
            rows = sdb.spatial.simplify(
                t, tolerance=1.0, preserve_topology=True, columns=["id"]
            )
            assert len(rows) == 1
            assert "simplified" in rows[0]
            assert rows[0]["simplified"] is not None
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_simplify_no_preserve_topology_succeeds(self, sdb):
        """simplify(preserve_topology=False) succeeds; NULL is a valid result (D-07)."""
        t = _uniq("spat_simplify_npt")
        try:
            self._make_tiny_polygon_table(sdb, t)
            rows = sdb.spatial.simplify(
                t, tolerance=1.0, preserve_topology=False, columns=["id"]
            )
            # ST_Simplify may return NULL when geometry collapses — no value assertion
            assert len(rows) == 1
            assert "simplified" in rows[0]
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_make_valid_bowtie(self, sdb):
        """make_valid on a bowtie polygon returns a non-NULL repaired geometry (D-07)."""
        t = _uniq("spat_makev")
        try:
            self._make_bowtie_table(sdb, t)
            rows = sdb.spatial.make_valid(t, columns=["id"])
            assert len(rows) == 1
            assert "made_valid" in rows[0]
            assert rows[0]["made_valid"] is not None
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_make_valid_structure(self, sdb):
        """make_valid(method='structure') succeeds on PostGIS 3.6.4 (D-09, no guard)."""
        t = _uniq("spat_makev_struct")
        try:
            self._make_bowtie_table(sdb, t)
            rows = sdb.spatial.make_valid(t, method="structure", columns=["id"])
            assert len(rows) == 1
            assert rows[0]["made_valid"] is not None
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    # -- Phase 43 aggregate integration tests (D-08 layer-b) ----------------

    def _make_grouped_with_nulls(self, db, t):
        """Create a table with grouped geometries including intentional NULL rows.

        north: one non-NULL point + one NULL geometry (mixed-NULL group)
        south: one non-NULL point (clean group)
        Satisfies D-07 NULL-fixture requirement for SPAT2-07/08/09 criterion 3.
        """
        db.execute(
            f'CREATE TABLE "{t}" (id INT, region TEXT, geometry geometry(Point, 4326))',
            autocommit=True,
        )
        db.execute(
            f'INSERT INTO "{t}" VALUES '
            "(1, 'north', ST_GeomFromText('POINT(0 1)', 4326)), "
            "(2, 'north', NULL), "
            "(3, 'south', ST_GeomFromText('POINT(0 -1)', 4326))",
            autocommit=True,
        )

    def test_collect_geometries_whole_table(self, sdb):
        """collect_geometries with group_by=None returns exactly 1 row with 'collected'."""
        t = _uniq("spat_agg_cg_whole")
        try:
            self._make_points(sdb, t)
            rows = sdb.spatial.collect_geometries(t)
            assert len(rows) == 1
            assert "collected" in rows[0]
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_collect_geometries_grouped(self, sdb):
        """collect_geometries with group_by returns one row per group."""
        t = _uniq("spat_agg_cg_grp")
        try:
            self._make_grouped_with_nulls(sdb, t)
            rows = sdb.spatial.collect_geometries(
                t, group_by="region", order_by="region"
            )
            assert len(rows) == 2
            regions = [r["region"] for r in rows]
            assert "north" in regions and "south" in regions
            for row in rows:
                assert "collected" in row
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_collect_geometries_null_rows_pass_through(self, sdb):
        """collect_geometries: mixed-NULL group still returns its row (D-07 pass-through)."""
        t = _uniq("spat_agg_cg_null")
        try:
            self._make_grouped_with_nulls(sdb, t)
            rows = sdb.spatial.collect_geometries(
                t, group_by="region", order_by="region"
            )
            # Both groups present; 'north' aggregate is over 1 non-NULL row (D-07)
            assert len(rows) == 2
            regions = [r["region"] for r in rows]
            assert "north" in regions and "south" in regions
            for row in rows:
                assert "collected" in row
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_collect_geometries_all_null_group(self, sdb):
        """All-NULL group returns one row with NULL aggregate (D-07, no HAVING)."""
        t = _uniq("spat_agg_cg_allnull")
        try:
            sdb.execute(
                f'CREATE TABLE "{t}" (region TEXT, geometry geometry(Point, 4326))',
                autocommit=True,
            )
            sdb.execute(
                f"INSERT INTO \"{t}\" VALUES ('x', NULL)",
                autocommit=True,
            )
            rows = sdb.spatial.collect_geometries(t, group_by="region")
            assert len(rows) == 1
            assert rows[0]["collected"] is None  # NULL aggregate, not zero rows
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_union_aggregate_whole_table(self, sdb):
        """union_aggregate with group_by=None returns exactly 1 row with 'dissolved'."""
        t = _uniq("spat_agg_ua_whole")
        try:
            self._make_points(sdb, t)
            rows = sdb.spatial.union_aggregate(t)
            assert len(rows) == 1
            assert "dissolved" in rows[0]
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_union_aggregate_grouped(self, sdb):
        """union_aggregate with group_by returns one row per group."""
        t = _uniq("spat_agg_ua_grp")
        try:
            self._make_grouped_with_nulls(sdb, t)
            rows = sdb.spatial.union_aggregate(
                t, group_by="region", order_by="region"
            )
            assert len(rows) == 2
            regions = [r["region"] for r in rows]
            assert "north" in regions and "south" in regions
            for row in rows:
                assert "dissolved" in row
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_union_aggregate_null_rows_pass_through(self, sdb):
        """union_aggregate: mixed-NULL group still returns its row (D-07 pass-through)."""
        t = _uniq("spat_agg_ua_null")
        try:
            self._make_grouped_with_nulls(sdb, t)
            rows = sdb.spatial.union_aggregate(
                t, group_by="region", order_by="region"
            )
            assert len(rows) == 2
            for row in rows:
                assert "dissolved" in row
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_union_aggregate_all_null_group(self, sdb):
        """All-NULL group union_aggregate returns one row with NULL aggregate (D-07, no HAVING)."""
        t = _uniq("spat_agg_ua_allnull")
        try:
            sdb.execute(
                f'CREATE TABLE "{t}" (region TEXT, geometry geometry(Point, 4326))',
                autocommit=True,
            )
            sdb.execute(
                f"INSERT INTO \"{t}\" VALUES ('x', NULL)",
                autocommit=True,
            )
            rows = sdb.spatial.union_aggregate(t, group_by="region")
            assert len(rows) == 1
            assert rows[0]["dissolved"] is None  # NULL aggregate, not zero rows
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_extent_whole_table(self, sdb):
        """extent with group_by=None returns exactly 1 row with 'extent'."""
        t = _uniq("spat_agg_ext_whole")
        try:
            self._make_points(sdb, t)
            rows = sdb.spatial.extent(t)
            assert len(rows) == 1
            assert "extent" in rows[0]
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_extent_rows_returns_box2d_text(self, sdb):
        """extent into='rows' returns a box2d text string starting with BOX (D-04)."""
        t = _uniq("spat_agg_ext_box")
        try:
            self._make_points(sdb, t)
            rows = sdb.spatial.extent(t, into="rows")
            assert len(rows) == 1
            val = rows[0]["extent"]
            assert isinstance(val, str)
            assert val.startswith("BOX")
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_extent_gdf_returns_geodataframe(self, sdb):
        """extent into='gdf' returns a GeoDataFrame whose geometry column is 'extent' (D-04)."""
        import geopandas as gpd

        t = _uniq("spat_agg_ext_gdf")
        try:
            self._make_points(sdb, t)
            gdf = sdb.spatial.extent(t, into="gdf")
            assert isinstance(gdf, gpd.GeoDataFrame)
            assert gdf.geometry.name == "extent"
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_extent_grouped(self, sdb):
        """extent with group_by returns one row per group."""
        t = _uniq("spat_agg_ext_grp")
        try:
            self._make_grouped_with_nulls(sdb, t)
            rows = sdb.spatial.extent(t, group_by="region", order_by="region")
            assert len(rows) == 2
            regions = [r["region"] for r in rows]
            assert "north" in regions and "south" in regions
            for row in rows:
                assert "extent" in row
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    def test_extent_null_group(self, sdb):
        """All-NULL group extent returns one row with NULL extent (D-07, no HAVING)."""
        t = _uniq("spat_agg_ext_null")
        try:
            sdb.execute(
                f'CREATE TABLE "{t}" (region TEXT, geometry geometry(Point, 4326))',
                autocommit=True,
            )
            sdb.execute(
                f"INSERT INTO \"{t}\" VALUES ('x', NULL)",
                autocommit=True,
            )
            rows = sdb.spatial.extent(t, group_by="region")
            assert len(rows) == 1
            assert rows[0]["extent"] is None  # NULL aggregate, not zero rows
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)


class _SyncSchemaStub:
    """Minimal schema stub so SpatialAccessor.__init__ passes without a real DB."""

    def has_extension(self, name):
        return True


class _AsyncSchemaStub:
    """Minimal async schema stub so _check_postgis() passes without a real DB."""

    async def has_extension(self, name):
        return True


class _RecordingSyncDb:
    """Recording stand-in for Database covering accessor routing DB-free."""

    def __init__(self):
        self.calls = []
        self.schema = _SyncSchemaStub()

    def has_extension(self, name):
        return True

    def execute(self, sql, params):
        self.calls.append(("execute", sql, params))
        return [{"ok": 1}]

    def to_geodataframe(self, sql=None, params=None, geometry_column=None):
        self.calls.append(("gdf", sql, params, geometry_column))
        return "GDF"


class _RecordingAsyncDb:
    """Recording stand-in for AsyncDatabase covering async routing DB-free."""

    def __init__(self):
        self.calls = []
        self.schema = _AsyncSchemaStub()

    async def has_extension(self, name):
        return True

    async def execute(self, sql, params):
        self.calls.append(("execute", sql, params))
        return [{"ok": 1}]

    async def to_geodataframe(self, sql=None, params=None, geometry_column=None):
        self.calls.append(("gdf", sql, params, geometry_column))
        return "GDF"


# (method name, kwargs) covering every helper in rows mode.
_HELPER_CALLS = [
    ("contains", {"point": (1, 2)}),
    ("intersects", {"wkt": "POINT(0 0)"}),
    ("dwithin", {"point": (1, 2), "distance": 10}),
    ("distance", {"point": (1, 2)}),
    ("nearest", {"point": (1, 2), "k": 2}),
    ("area", {}),
    ("perimeter", {}),
    ("centroid", {}),
    ("buffer", {"distance": 5}),
    ("transform", {"to_srid": 3857}),
    ("union", {"other_geom": "geometry2"}),
    ("difference", {"other_geom": "geometry2"}),
    ("intersection", {"other_geom": "geometry2"}),
    ("simplify", {"tolerance": 0.01}),
    ("convex_hull", {}),
    ("make_valid", {}),
    ("collect_geometries", {}),
    ("union_aggregate", {}),
    ("extent", {}),
]

# Geometry-returning helpers valid for into="gdf", with expected geom column.
_GDF_CALLS = [
    ("contains", {"point": (1, 2)}, "geometry"),
    ("intersects", {"wkt": "POINT(0 0)"}, "geometry"),
    ("dwithin", {"point": (1, 2), "distance": 10}, "geometry"),
    ("nearest", {"point": (1, 2)}, "geometry"),
    ("buffer", {"distance": 5}, "buffer"),
    ("transform", {"to_srid": 3857}, "geometry_transformed"),
    ("union", {"other_geom": "geometry2"}, "union_geom"),
    ("difference", {"other_geom": "geometry2"}, "difference"),
    ("intersection", {"other_geom": "geometry2"}, "intersection"),
    ("simplify", {"tolerance": 0.01}, "simplified"),
    ("convex_hull", {}, "convex_hull"),
    ("make_valid", {}, "made_valid"),
    ("collect_geometries", {}, "collected"),
    ("union_aggregate", {}, "dissolved"),
    ("extent", {}, "extent"),
]


class TestAccessorRouting:
    """DB-free routing tests: every accessor method, rows and gdf paths."""

    @pytest.mark.parametrize("helper,kwargs", _HELPER_CALLS)
    def test_sync_rows_path(self, helper, kwargs):
        """Each sync helper routes into='rows' through db.execute."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        result = getattr(acc, helper)("parcels", **kwargs)
        assert result == [{"ok": 1}]
        kind, sql, params = db.calls[-1]
        assert kind == "execute"
        assert sql.count("%s") == len(params)

    @pytest.mark.parametrize("helper,kwargs", _HELPER_CALLS)
    async def test_async_rows_path(self, helper, kwargs):
        """Each async helper routes into='rows' through await db.execute."""
        db = _RecordingAsyncDb()
        acc = AsyncSpatialAccessor(db)
        result = await getattr(acc, helper)("parcels", **kwargs)
        assert result == [{"ok": 1}]
        kind, sql, params = db.calls[-1]
        assert kind == "execute"
        assert sql.count("%s") == len(params)

    def test_sync_within_rows_path(self):
        """within (two-table signature) routes through db.execute."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        assert acc.within("parcels", "geometry", "zones", "geom") == [{"ok": 1}]

    async def test_async_within_rows_path(self):
        """async within (two-table signature) routes through db.execute."""
        db = _RecordingAsyncDb()
        acc = AsyncSpatialAccessor(db)
        result = await acc.within("parcels", "geometry", "zones", "geom")
        assert result == [{"ok": 1}]

    @pytest.mark.parametrize("helper,kwargs,geom_col", _GDF_CALLS)
    def test_sync_gdf_path_uses_named_binds(self, helper, kwargs, geom_col):
        """Sync gdf path converts %s to named binds and sets geom column."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        result = getattr(acc, helper)("parcels", into="gdf", **kwargs)
        assert result == "GDF"
        kind, sql, params, geometry_column = db.calls[-1]
        assert kind == "gdf"
        assert "%s" not in sql
        assert isinstance(params, dict)
        assert all(f":p{i}" in sql for i in range(len(params)))
        assert geometry_column == geom_col

    @pytest.mark.parametrize("helper,kwargs,geom_col", _GDF_CALLS)
    async def test_async_gdf_path_uses_named_binds(self, helper, kwargs, geom_col):
        """Async gdf path converts %s to named binds and sets geom column."""
        db = _RecordingAsyncDb()
        acc = AsyncSpatialAccessor(db)
        result = await getattr(acc, helper)("parcels", into="gdf", **kwargs)
        assert result == "GDF"
        kind, sql, params, geometry_column = db.calls[-1]
        assert kind == "gdf"
        assert "%s" not in sql
        assert isinstance(params, dict)
        assert geometry_column == geom_col

    def test_sync_within_gdf_path(self):
        """within gdf path uses the left geometry column."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        assert acc.within("parcels", "geometry", "zones", "geom", into="gdf") == "GDF"
        assert db.calls[-1][3] == "geometry"

    async def test_async_within_gdf_path(self):
        """async within gdf path uses the left geometry column."""
        db = _RecordingAsyncDb()
        acc = AsyncSpatialAccessor(db)
        result = await acc.within("parcels", "geometry", "zones", "geom", into="gdf")
        assert result == "GDF"
        assert db.calls[-1][3] == "geometry"

    async def test_async_scalar_helpers_reject_gdf(self):
        """Async perimeter/distance/centroid reject into='gdf' (D-02)."""
        acc = AsyncSpatialAccessor(_RecordingAsyncDb())
        with pytest.raises(ValueError, match="into='gdf' is invalid"):
            await acc.perimeter("parcels", into="gdf")
        with pytest.raises(ValueError, match="into='gdf' is invalid"):
            await acc.distance("parcels", point=(1, 2), into="gdf")
        with pytest.raises(ValueError, match="into='gdf' is invalid"):
            await acc.centroid("parcels", into="gdf")


class TestBuilderColumnsValidation:
    """Residual columns= validation branches (coverage fill, 14-04)."""

    def test_distance_columns_validated(self):
        """distance validates columns= and supports the column list."""
        sql, _ = build_distance_sql("parcels", point=(1, 2), columns=["id"])
        assert sql.startswith("SELECT id, ST_Distance(")
        with pytest.raises(InvalidIdentifierError):
            build_distance_sql("parcels", point=(1, 2), columns=["bad-col"])

    def test_buffer_columns_validated(self):
        """buffer validates columns= and supports the column list."""
        sql, _ = build_buffer_sql("parcels", distance=1, columns=["id"])
        assert sql.startswith("SELECT id, ST_Buffer(")
        with pytest.raises(InvalidIdentifierError):
            build_buffer_sql("parcels", distance=1, columns=["bad-col"])

    def test_area_columns_validated(self):
        """area validates columns=."""
        sql, _ = build_area_sql("parcels", columns=["id"])
        assert sql.startswith("SELECT id, ST_Area(")
        with pytest.raises(InvalidIdentifierError):
            build_area_sql("parcels", columns=["bad-col"])

    def test_dwithin_columns_validated(self):
        """dwithin validates columns=."""
        with pytest.raises(InvalidIdentifierError):
            build_dwithin_sql("parcels", point=(1, 2), distance=1, columns=["bad-col"])

    def test_within_columns_validated(self):
        """within validates columns=."""
        with pytest.raises(InvalidIdentifierError):
            build_within_sql("a", "g", "b", "g", columns=["bad-col"])

    def test_intersects_columns_validated(self):
        """intersects validates columns=."""
        with pytest.raises(InvalidIdentifierError):
            build_intersects_sql("parcels", point=(1, 2), columns=["bad-col"])

    def test_nearest_columns_validated(self):
        """nearest validates columns=."""
        with pytest.raises(InvalidIdentifierError):
            build_nearest_sql("parcels", point=(1, 2), columns=["bad-col"])

    def test_transform_columns_validated(self):
        """transform validates columns=."""
        with pytest.raises(InvalidIdentifierError):
            build_transform_sql("parcels", to_srid=4326, columns=["bad-col"])

    def test_union_columns_validated(self):
        """union validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_union_sql("parcels", other_geom="geom2", columns=["bad-col"])

    def test_difference_columns_validated(self):
        """difference validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_difference_sql("parcels", other_geom="geom2", columns=["bad-col"])

    def test_intersection_columns_validated(self):
        """intersection validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_intersection_sql("parcels", other_geom="geom2", columns=["bad-col"])

    def test_simplify_columns_validated(self):
        """simplify validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_simplify_sql("parcels", tolerance=0.5, columns=["bad-col"])

    def test_convex_hull_columns_validated(self):
        """convex_hull validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_convex_hull_sql("parcels", columns=["bad-col"])

    def test_make_valid_columns_validated(self):
        """make_valid validates columns= identifiers."""
        with pytest.raises(InvalidIdentifierError):
            build_make_valid_sql("parcels", columns=["bad-col"])


class TestAggregateBuilders:
    """DB-free SQL-shape + injection tests for collect_geometries and union_aggregate builders."""

    # -- collect_geometries: whole-table ----------------------------------

    def test_collect_geometries_whole_table(self):
        """collect_geometries whole-table emits ST_Collect AS collected with empty params."""
        sql, params = build_collect_geometries_sql("zones")
        assert "ST_Collect(t.geometry) AS collected" in sql
        assert "FROM public.zones AS t" in sql
        assert "GROUP BY" not in sql
        assert params == []

    def test_collect_geometries_with_group_by(self):
        """collect_geometries with group_by adds group column in SELECT and GROUP BY clause."""
        sql, params = build_collect_geometries_sql("zones", group_by=["region"])
        assert "t.region" in sql
        assert "SELECT t.region," in sql
        assert "ST_Collect(t.geometry) AS collected" in sql
        assert "GROUP BY t.region" in sql
        assert params == []

    def test_collect_geometries_composite_group_by(self):
        """collect_geometries with multiple group_by columns covers composite grouping."""
        sql, params = build_collect_geometries_sql("zones", group_by=["region", "zone"])
        assert "t.region" in sql
        assert "t.zone" in sql
        assert "GROUP BY t.region, t.zone" in sql
        assert params == []

    def test_collect_geometries_tail_clauses(self):
        """collect_geometries: GROUP BY is after WHERE and before ORDER BY / LIMIT."""
        sql, params = build_collect_geometries_sql(
            "zones",
            group_by=["region"],
            filter="active = true",
            order_by="t.region",
            limit=10,
        )
        where_idx = sql.index("WHERE")
        group_idx = sql.index("GROUP BY")
        order_idx = sql.index("ORDER BY")
        limit_idx = sql.index("LIMIT")
        assert where_idx < group_idx < order_idx < limit_idx
        assert params == []

    def test_collect_geometries_no_params(self):
        """collect_geometries always returns empty params list."""
        sql, params = build_collect_geometries_sql("zones", group_by=["region"])
        assert "%" not in sql
        assert params == []

    # -- collect_geometries: injection tests (T-43-01) --------------------

    def test_collect_geometries_invalid_table(self):
        """collect_geometries validates the table identifier (T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_collect_geometries_sql("bad-name")

    def test_collect_geometries_invalid_geom(self):
        """collect_geometries validates the geom identifier (T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_collect_geometries_sql("zones", geom="bad; DROP TABLE")

    def test_collect_geometries_invalid_group_by(self):
        """collect_geometries validates group_by columns before SQL assembly (Pitfall 1, T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_collect_geometries_sql(
                "zones", group_by=["region; DROP TABLE users; --"]
            )

    # -- union_aggregate: whole-table -------------------------------------

    def test_union_aggregate_whole_table(self):
        """union_aggregate whole-table emits ST_Union AS dissolved (not union_geom)."""
        sql, params = build_union_aggregate_sql("zones")
        assert "ST_Union(t.geometry) AS dissolved" in sql
        assert "FROM public.zones AS t" in sql
        assert "GROUP BY" not in sql
        assert params == []

    def test_union_aggregate_with_group_by(self):
        """union_aggregate with group_by adds group column in SELECT and GROUP BY clause."""
        sql, params = build_union_aggregate_sql("zones", group_by=["region"])
        assert "SELECT t.region," in sql
        assert "ST_Union(t.geometry) AS dissolved" in sql
        assert "GROUP BY t.region" in sql
        assert params == []

    def test_union_aggregate_tail_clauses(self):
        """union_aggregate: GROUP BY is after WHERE and before ORDER BY / LIMIT."""
        sql, params = build_union_aggregate_sql(
            "zones",
            group_by=["region"],
            filter="active = true",
            order_by="t.region",
            limit=5,
        )
        where_idx = sql.index("WHERE")
        group_idx = sql.index("GROUP BY")
        order_idx = sql.index("ORDER BY")
        limit_idx = sql.index("LIMIT")
        assert where_idx < group_idx < order_idx < limit_idx
        assert params == []

    def test_union_aggregate_result_col_is_dissolved(self):
        """union_aggregate result column is 'dissolved', NOT 'union_geom' (D-06)."""
        sql, _ = build_union_aggregate_sql("zones")
        assert "AS dissolved" in sql
        assert "union_geom" not in sql

    # -- union_aggregate: injection tests (T-43-01) -----------------------

    def test_union_aggregate_invalid_table(self):
        """union_aggregate validates the table identifier (T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_union_aggregate_sql("bad-name")

    def test_union_aggregate_invalid_geom(self):
        """union_aggregate validates the geom identifier (T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_union_aggregate_sql("zones", geom="bad; DROP TABLE")

    def test_union_aggregate_invalid_group_by(self):
        """union_aggregate validates group_by columns before SQL assembly (Pitfall 1, T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_union_aggregate_sql(
                "zones", group_by=["region; DROP TABLE users; --"]
            )

    # -- extent: rows branch -----------------------------------------------

    def test_extent_rows_branch(self):
        """extent rows branch emits ST_Extent(t.geometry)::text AS extent, NOT ST_SetSRID."""
        sql, params = build_extent_sql("zones")
        assert "ST_Extent(t.geometry)::text AS extent" in sql
        assert "ST_SetSRID" not in sql
        assert "FROM public.zones AS t" in sql
        assert params == []

    def test_extent_gdf_branch(self):
        """extent gdf branch emits ST_SetSRID(ST_Extent(...)::geometry, 4326) AS extent."""
        sql, params = build_extent_sql("zones", into="gdf")
        assert "ST_SetSRID(ST_Extent(t.geometry)::geometry, 4326) AS extent" in sql
        assert "::text" not in sql
        assert params == []

    def test_extent_custom_srid(self):
        """extent gdf with srid=3857 interpolates the custom integer via int(srid)."""
        sql, params = build_extent_sql("zones", into="gdf", srid=3857)
        assert ", 3857) AS extent" in sql
        assert ", 4326)" not in sql
        assert params == []

    def test_extent_with_group_by(self):
        """extent with group_by adds group column in SELECT and GROUP BY clause."""
        sql, params = build_extent_sql("zones", group_by=["region"])
        assert "SELECT t.region," in sql
        assert "ST_Extent(t.geometry)::text AS extent" in sql
        assert "GROUP BY t.region" in sql
        assert params == []

    def test_extent_group_by_clause_ordering(self):
        """extent: GROUP BY is after WHERE and before ORDER BY / LIMIT."""
        sql, params = build_extent_sql(
            "zones",
            group_by=["region"],
            filter="active = true",
            order_by="t.region",
            limit=10,
        )
        where_idx = sql.index("WHERE")
        group_idx = sql.index("GROUP BY")
        order_idx = sql.index("ORDER BY")
        limit_idx = sql.index("LIMIT")
        assert where_idx < group_idx < order_idx < limit_idx
        assert params == []

    # -- extent: injection tests (T-43-01) ---------------------------------

    def test_extent_invalid_table(self):
        """extent validates the table identifier before any SQL (T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_extent_sql("bad-name")

    def test_extent_invalid_geom(self):
        """extent validates the geom identifier before any SQL (T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_extent_sql("zones", geom="bad; DROP TABLE")

    def test_extent_invalid_group_by(self):
        """extent validates group_by columns before SQL assembly (Pitfall 1, T-43-01)."""
        with pytest.raises(InvalidIdentifierError):
            build_extent_sql("zones", group_by=["region; DROP TABLE users; --"])


class TestAggregateAccessorGuards:
    """DB-free guard tests for collect_geometries and union_aggregate accessor methods."""

    def test_collect_geometries_empty_group_by_raises(self):
        """collect_geometries with group_by=[] raises ValueError (Pitfall 5)."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        with pytest.raises(ValueError, match="group_by cannot be an empty list"):
            acc.collect_geometries("zones", group_by=[])

    def test_union_aggregate_empty_group_by_raises(self):
        """union_aggregate with group_by=[] raises ValueError (Pitfall 5)."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        with pytest.raises(ValueError, match="group_by cannot be an empty list"):
            acc.union_aggregate("zones", group_by=[])

    def test_collect_geometries_str_group_by_normalized(self):
        """collect_geometries normalizes a bare str group_by to [str] (D-01)."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        result = acc.collect_geometries("zones", group_by="region")
        assert result == [{"ok": 1}]
        _, sql, _ = db.calls[-1]
        assert "GROUP BY t.region" in sql

    def test_union_aggregate_str_group_by_normalized(self):
        """union_aggregate normalizes a bare str group_by to [str] (D-01)."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        result = acc.union_aggregate("zones", group_by="region")
        assert result == [{"ok": 1}]
        _, sql, _ = db.calls[-1]
        assert "GROUP BY t.region" in sql

    # -- extent accessor guard tests --------------------------------------

    def test_extent_empty_group_by_raises(self):
        """extent with group_by=[] raises ValueError (Pitfall 5)."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        with pytest.raises(ValueError, match="group_by cannot be an empty list"):
            acc.extent("zones", group_by=[])

    def test_extent_str_group_by_normalized(self):
        """extent normalizes a bare str group_by to [str] (D-01)."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        result = acc.extent("zones", group_by="region")
        assert result == [{"ok": 1}]
        _, sql, _ = db.calls[-1]
        assert "GROUP BY t.region" in sql

    def test_extent_gdf_not_rejected(self):
        """extent with into='gdf' does NOT raise — not in _SCALAR_HELPERS (D-04, Pitfall 3)."""
        db = _RecordingSyncDb()
        acc = SpatialAccessor(db)
        result = acc.extent("zones", into="gdf")
        assert result == "GDF"
