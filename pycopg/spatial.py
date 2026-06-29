"""PostGIS spatial helpers: pure SQL builders and geometry resolution.

This module provides the pure foundation of the ``db.spatial`` accessor
namespace: one module-level SQL builder per spatial helper, plus the single
internal geometry resolver shared by all of them. Builders are stateless
functions returning ``(sql, params)`` tuples — no ``self``, no I/O, no DB —
so they are shared byte-identical between the sync and async accessors and
are fully unit-testable without a database.

Security invariants (Phase 10 / hotfix v0.3.1):

- Every identifier (table, schema, geometry column, ref table/column,
  ``columns=`` entries) passes :func:`pycopg.utils.validate_identifiers`
  before any string interpolation.
- Every user value (coordinates, WKT, GeoJSON, distances, ``k``,
  ``to_srid``) is emitted as a ``%s`` placeholder appended to the params
  list — never f-string interpolated.
- SRID is the only directly interpolated value, and only through an
  ``int(srid)`` coercion (integer cast is injection-safe).

The ``filter=`` parameter is a raw SQL fragment following the existing
``_build_select_sql`` convention — values inside it are the caller's
responsibility (T-14-04 accepted limitation).
"""

from __future__ import annotations

import json
import warnings
from typing import TYPE_CHECKING

from pycopg import queries
from pycopg.exceptions import ExtensionNotAvailableError
from pycopg.utils import validate_identifier, validate_identifiers

if TYPE_CHECKING:
    import geopandas as gpd

    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database

#: Sentinel SQL fragment returned by :func:`_resolve_geometry` for the
#: ``ref=`` input form. When a builder receives this sentinel, the params
#: list holds ``[ref_table, ref_col]`` (already validated identifiers, not
#: query parameters) and the builder assembles an EXISTS subquery (D-08).
_REF_SENTINEL = "__ref__"

#: Accepted ``unit=`` values for metric helpers (D-09/D-10).
_VALID_UNITS = ("m", "srid")


def _validate_unit(unit: str) -> None:
    """Validate a ``unit=`` value.

    Parameters
    ----------
    unit : str
        Unit selector — must be ``"m"`` or ``"srid"`` (D-09).

    Raises
    ------
    ValueError
        If ``unit`` is not one of the accepted values.
    """
    if unit not in _VALID_UNITS:
        raise ValueError(f"unit must be 'm' or 'srid', got {unit!r}")


def _resolve_geometry(
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
) -> tuple[str, list]:
    """Resolve one of the four geometry input forms to a SQL fragment.

    Exactly one of ``point=``, ``wkt=``, ``geojson=``, ``ref=`` must be
    provided (D-05). All values are parameterized with ``%s``; only the
    SRID is interpolated, via ``int(srid)`` coercion (D-07).

    For ``ref=``, the function validates both identifiers and returns the
    sentinel fragment ``"__ref__"`` with params ``[ref_table, ref_col]``.
    The caller turns this sentinel into an EXISTS subquery of the form
    ``EXISTS (SELECT 1 FROM {ref_table} AS _ref WHERE
    ST_<Predicate>(_ref.{ref_col}, t.{geom}))`` (D-08). The two list items
    are identifiers consumed by the caller, not query parameters.

    Parameters
    ----------
    point : tuple of float, optional
        ``(x, y)`` coordinate pair.
    wkt : str, optional
        WKT geometry string.
    geojson : dict, optional
        GeoJSON geometry object (serialized with :func:`json.dumps`).
    ref : tuple of str, optional
        ``(ref_table, ref_col)`` referencing another table's geometry.
    srid : int, optional
        Spatial reference identifier, by default 4326 (WGS84).

    Returns
    -------
    tuple of (str, list)
        SQL fragment and its parameter list (or the ``ref`` sentinel).

    Raises
    ------
    ValueError
        If zero or more than one input form is provided.
    InvalidIdentifierError
        If ``ref=`` identifiers are invalid.
    """
    given = sum(x is not None for x in (point, wkt, geojson, ref))
    if given != 1:
        raise ValueError("Exactly one of point=, wkt=, geojson=, ref= must be provided")

    if point is not None:
        x, y = point
        return f"ST_SetSRID(ST_MakePoint(%s, %s), {int(srid)})", [x, y]

    if wkt is not None:
        return f"ST_GeomFromText(%s, {int(srid)})", [wkt]

    if geojson is not None:
        return f"ST_SetSRID(ST_GeomFromGeoJSON(%s), {int(srid)})", [json.dumps(geojson)]

    ref_table, ref_col = ref
    validate_identifiers(ref_table, ref_col)
    return _REF_SENTINEL, [ref_table, ref_col]


def _cols_str(columns: list[str] | None) -> str:
    """Build the SELECT column list following ``_build_select_sql``.

    Parameters
    ----------
    columns : list of str, optional
        Column names (already validated by the caller), or None for ``*``.

    Returns
    -------
    str
        Comma-joined column list, or ``"*"``.
    """
    return ", ".join(columns) if columns else "*"


def _append_tail(
    sql: str,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
    has_where: bool,
) -> str:
    """Append ``filter``/``order_by``/``limit`` clauses to a SQL string.

    Follows the ``_build_select_sql`` convention (D-11/D-12): when the
    statement already has a WHERE clause (spatial condition first), the
    ``filter=`` fragment is combined as ``AND ({filter})``.

    Parameters
    ----------
    sql : str
        SQL statement built so far.
    filter : str, optional
        Raw SQL filter fragment (without the WHERE keyword).
    order_by : str, optional
        ORDER BY clause body.
    limit : int, optional
        LIMIT value (coerced with ``int``).
    has_where : bool
        Whether ``sql`` already contains a WHERE clause.

    Returns
    -------
    str
        SQL statement with the requested clauses appended.
    """
    if filter:
        sql += f" AND ({filter})" if has_where else f" WHERE {filter}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql


def build_contains_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows whose geometry contains the input geometry.

    Generates ``ST_Contains(t.{geom}, <geom_in>)``. The ``ref=`` form uses
    an EXISTS subquery (D-08).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    point : tuple of float, optional
        ``(x, y)`` input geometry (one of the four D-05 forms).
    wkt : str, optional
        WKT input geometry.
    geojson : dict, optional
        GeoJSON input geometry.
    ref : tuple of str, optional
        ``(ref_table, ref_col)`` input geometry (EXISTS semantics).
    srid : int, optional
        SRID of the input geometry, by default 4326 (D-07).
    columns : list of str, optional
        Columns to select, by default all (D-03).
    filter : str, optional
        Additional raw SQL filter combined as ``AND (...)`` (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list.

    Raises
    ------
    ValueError
        If the geometry input forms are not mutually exclusive.
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    fragment, frag_params = _resolve_geometry(
        point=point, wkt=wkt, geojson=geojson, ref=ref, srid=srid
    )
    params: list = []
    if fragment == _REF_SENTINEL:
        ref_table, ref_col = frag_params
        cond = (
            f"EXISTS (SELECT 1 FROM {ref_table} AS _ref "
            f"WHERE ST_Contains(_ref.{ref_col}, t.{geom}))"
        )
    else:
        cond = f"ST_Contains(t.{geom}, {fragment})"
        params.extend(frag_params)
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t WHERE {cond}"
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
    return sql, params


def build_intersects_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows whose geometry intersects the input geometry.

    Generates ``ST_Intersects(t.{geom}, <geom_in>)``. The ``ref=`` form
    uses an EXISTS subquery (D-08).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    point : tuple of float, optional
        ``(x, y)`` input geometry (one of the four D-05 forms).
    wkt : str, optional
        WKT input geometry.
    geojson : dict, optional
        GeoJSON input geometry.
    ref : tuple of str, optional
        ``(ref_table, ref_col)`` input geometry (EXISTS semantics).
    srid : int, optional
        SRID of the input geometry, by default 4326 (D-07).
    columns : list of str, optional
        Columns to select, by default all (D-03).
    filter : str, optional
        Additional raw SQL filter combined as ``AND (...)`` (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list.

    Raises
    ------
    ValueError
        If the geometry input forms are not mutually exclusive.
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    fragment, frag_params = _resolve_geometry(
        point=point, wkt=wkt, geojson=geojson, ref=ref, srid=srid
    )
    params: list = []
    if fragment == _REF_SENTINEL:
        ref_table, ref_col = frag_params
        cond = (
            f"EXISTS (SELECT 1 FROM {ref_table} AS _ref "
            f"WHERE ST_Intersects(_ref.{ref_col}, t.{geom}))"
        )
    else:
        cond = f"ST_Intersects(t.{geom}, {fragment})"
        params.extend(frag_params)
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t WHERE {cond}"
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
    return sql, params


def build_within_sql(
    left_table: str,
    left_geom: str,
    right_table: str,
    right_geom: str,
    schema: str = "public",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL joining two tables on a within relationship.

    Generates the two-table JOIN form ``ST_Within(a.{left_geom},
    b.{right_geom})`` — this helper keeps its dedicated join signature per
    08-DESIGN §3 and does not take the D-05 geometry input forms.

    Parameters
    ----------
    left_table : str
        Table whose rows are returned (aliased ``a``).
    left_geom : str
        Geometry column of the left table.
    right_table : str
        Containing table (aliased ``b``).
    right_geom : str
        Geometry column of the right table.
    schema : str, optional
        Schema name for both tables, by default "public".
    columns : list of str, optional
        Columns to select, by default all (D-03).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list (always empty for this builder).

    Raises
    ------
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(left_table, left_geom, right_table, right_geom, schema)
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)} FROM {schema}.{left_table} AS a "
        f"JOIN {schema}.{right_table} AS b "
        f"ON ST_Within(a.{left_geom}, b.{right_geom})"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_dwithin_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    distance: float,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows within a distance of the input geometry.

    With ``unit="m"`` (default), both sides are cast to ``::geography`` so
    the distance is in meters (D-09); ``unit="srid"`` uses native SRID
    units. The distance value is always a ``%s`` parameter.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    point : tuple of float, optional
        ``(x, y)`` input geometry (one of the four D-05 forms).
    wkt : str, optional
        WKT input geometry.
    geojson : dict, optional
        GeoJSON input geometry.
    ref : tuple of str, optional
        ``(ref_table, ref_col)`` input geometry (EXISTS semantics).
    srid : int, optional
        SRID of the input geometry, by default 4326 (D-07).
    distance : float
        Search distance, in meters (``unit="m"``) or SRID units.
    unit : str, optional
        ``"m"`` or ``"srid"``, by default "m" (D-09).
    columns : list of str, optional
        Columns to select, by default all (D-03).
    filter : str, optional
        Additional raw SQL filter combined as ``AND (...)`` (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list.

    Raises
    ------
    ValueError
        If ``unit`` is invalid or geometry forms are not exclusive.
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    _validate_unit(unit)
    fragment, frag_params = _resolve_geometry(
        point=point, wkt=wkt, geojson=geojson, ref=ref, srid=srid
    )
    cast = "::geography" if unit == "m" else ""
    params: list = []
    if fragment == _REF_SENTINEL:
        ref_table, ref_col = frag_params
        cond = (
            f"EXISTS (SELECT 1 FROM {ref_table} AS _ref "
            f"WHERE ST_DWithin(_ref.{ref_col}{cast}, t.{geom}{cast}, %s))"
        )
    else:
        cond = f"ST_DWithin(t.{geom}{cast}, {fragment}{cast}, %s)"
        params.extend(frag_params)
    params.append(distance)
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t WHERE {cond}"
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
    return sql, params


def build_distance_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    srid: int = 4326,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with their distance to the input geometry.

    Adds a scalar ``ST_Distance(...) AS distance`` column. With
    ``unit="m"`` (default) both sides are cast to ``::geography`` so the
    distance is in meters (D-09). Callers may pass ``order_by="distance"``
    to sort by proximity. The ``ref=`` input form is not supported here —
    EXISTS semantics (D-08) do not define a scalar distance.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    point : tuple of float, optional
        ``(x, y)`` input geometry.
    wkt : str, optional
        WKT input geometry.
    geojson : dict, optional
        GeoJSON input geometry.
    srid : int, optional
        SRID of the input geometry, by default 4326 (D-07).
    unit : str, optional
        ``"m"`` or ``"srid"``, by default "m" (D-09).
    columns : list of str, optional
        Columns to select alongside the distance, by default all (D-03).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body, e.g. ``"distance"`` (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list.

    Raises
    ------
    ValueError
        If ``unit`` is invalid or geometry forms are not exclusive.
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    _validate_unit(unit)
    fragment, params = _resolve_geometry(
        point=point, wkt=wkt, geojson=geojson, srid=srid
    )
    cast = "::geography" if unit == "m" else ""
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"ST_Distance(t.{geom}{cast}, {fragment}{cast}) AS distance "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, list(params)


def build_nearest_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    srid: int = 4326,
    k: int = 5,
    columns: list[str] | None = None,
    filter: str | None = None,
) -> tuple[str, list]:
    """Build SQL selecting the k rows nearest to the input geometry.

    Uses KNN ordering ``t.{geom}::geography <-> <geom_in>::geography``
    for metric (meter-based) proximity, consistent with the D-09 meter
    default. A GiST index on the geometry column accelerates this
    ordering. ``k`` is emitted as a ``%s`` LIMIT parameter. No ``unit=``
    parameter (D-10), and the ``ref=`` input form is not supported —
    EXISTS semantics (D-08) do not define a KNN ordering target.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    point : tuple of float, optional
        ``(x, y)`` input geometry.
    wkt : str, optional
        WKT input geometry.
    geojson : dict, optional
        GeoJSON input geometry.
    srid : int, optional
        SRID of the input geometry, by default 4326 (D-07).
    k : int, optional
        Number of nearest rows to return, by default 5.
    columns : list of str, optional
        Columns to select, by default all (D-03).
    filter : str, optional
        Raw SQL filter fragment (D-11).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list (k is the last parameter).

    Raises
    ------
    ValueError
        If the geometry input forms are not mutually exclusive.
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    fragment, params = _resolve_geometry(
        point=point, wkt=wkt, geojson=geojson, srid=srid
    )
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t"
    if filter:
        sql += f" WHERE {filter}"
    sql += f" ORDER BY t.{geom}::geography <-> {fragment}::geography LIMIT %s"
    return sql, [*params, k]


def build_area_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with the area of their geometry.

    Adds a scalar ``ST_Area(...) AS area`` column computed on the table's
    own geometry column (no geometry input). With ``unit="m"`` (default)
    the geometry is cast to ``::geography`` so the area is in square
    meters (D-09).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    unit : str, optional
        ``"m"`` or ``"srid"``, by default "m" (D-09).
    columns : list of str, optional
        Columns to select alongside the area, by default all (D-03).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list (always empty for this builder).

    Raises
    ------
    ValueError
        If ``unit`` is invalid.
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    _validate_unit(unit)
    cast = "::geography" if unit == "m" else ""
    sql = (
        f"SELECT {_cols_str(columns)}, ST_Area(t.{geom}{cast}) AS area "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_perimeter_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with the perimeter of their geometry.

    Adds a scalar ``ST_Perimeter(...) AS perimeter`` column computed on
    the table's own geometry column. With ``unit="m"`` (default) the
    geometry is cast to ``::geography`` so the perimeter is in meters
    (D-09).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    unit : str, optional
        ``"m"`` or ``"srid"``, by default "m" (D-09).
    columns : list of str, optional
        Columns to select alongside the perimeter, by default all (D-03).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list (always empty for this builder).

    Raises
    ------
    ValueError
        If ``unit`` is invalid.
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    _validate_unit(unit)
    cast = "::geography" if unit == "m" else ""
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"ST_Perimeter(t.{geom}{cast}) AS perimeter "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_centroid_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with their geometry centroid coordinates.

    Adds scalar ``ST_X(ST_Centroid(...)) AS centroid_x`` and
    ``ST_Y(ST_Centroid(...)) AS centroid_y`` columns. Scalar result — no
    geometry column is returned, so ``into="gdf"`` is forbidden at the
    accessor level (D-02). No ``unit=`` parameter (D-10).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    columns : list of str, optional
        Columns to select alongside the centroid, by default all (D-03).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list (always empty for this builder).

    Raises
    ------
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"ST_X(ST_Centroid(t.{geom})) AS centroid_x, "
        f"ST_Y(ST_Centroid(t.{geom})) AS centroid_y "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_buffer_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    distance: float,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with a buffer around their geometry.

    Adds a ``buffer`` geometry column. With ``unit="m"`` (default) the
    geometry is cast to ``::geography`` for a meter-based buffer, and the
    result is cast back to ``::geometry`` (08-DESIGN §3) so the output is
    valid for ``into="gdf"``. The distance is always a ``%s`` parameter.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    distance : float
        Buffer distance, in meters (``unit="m"``) or SRID units.
    unit : str, optional
        ``"m"`` or ``"srid"``, by default "m" (D-09).
    columns : list of str, optional
        Columns to select alongside the buffer, by default all (D-03).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list ([distance]).

    Raises
    ------
    ValueError
        If ``unit`` is invalid.
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    _validate_unit(unit)
    if unit == "m":
        buffer_expr = f"ST_Buffer(t.{geom}::geography, %s)::geometry"
    else:
        buffer_expr = f"ST_Buffer(t.{geom}, %s)"
    sql = (
        f"SELECT {_cols_str(columns)}, {buffer_expr} AS buffer "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, [distance]


def build_transform_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    to_srid: int,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with their geometry transformed to a SRID.

    Adds a ``geometry_transformed`` geometry column via
    ``ST_Transform(t.{geom}, %s)`` with ``to_srid`` as a parameter. The
    output is a geometry, valid for ``into="gdf"``. No ``unit=``
    parameter (D-10).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    to_srid : int
        Target spatial reference identifier.
    columns : list of str, optional
        Columns to select alongside the transform, by default all (D-03).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list ([to_srid]).

    Raises
    ------
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"ST_Transform(t.{geom}, %s) AS geometry_transformed "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, [to_srid]


def _build_binary_geom_sql(
    op_func: str,
    result_col: str,
    table: str,
    geom: str,
    schema: str,
    *,
    other_geom: str,
    columns: list[str] | None,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
) -> tuple[str, list]:
    """Build SQL for a pairwise (binary, 2-column) geometry operation."""
    validate_identifiers(table, schema, geom, other_geom)
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"{op_func}(t.{geom}, t.{other_geom}) AS {result_col} "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_union_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting the pairwise union of two geometry columns.

    Adds a ``union_geom`` geometry column via
    ``ST_Union(t.{geom}, t.{other_geom})``. No ``%s`` parameters are
    emitted — both geometry columns are identifier-validated and
    interpolated directly into the SQL. The result is a geometry, valid
    for ``into="gdf"``.

    Note: inputs with mismatched SRIDs will raise a native PostGIS error
    at execution time (D-06). No pre-check is performed.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        First geometry column name, by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    other_geom : str
        Second geometry column name (required, keyword-only).
    columns : list of str, optional
        Columns to select alongside the result, by default all.
    filter : str, optional
        Raw SQL filter fragment.
    order_by : str, optional
        ORDER BY clause body.
    limit : int, optional
        LIMIT value.

    Returns
    -------
    tuple of (str, list)
        SQL string and empty parameter list (``[]``).

    Raises
    ------
    InvalidIdentifierError
        If any identifier (``table``, ``schema``, ``geom``, ``other_geom``,
        or any element of ``columns``) is invalid.
    """
    return _build_binary_geom_sql(
        "ST_Union",
        "union_geom",
        table,
        geom,
        schema,
        other_geom=other_geom,
        columns=columns,
        filter=filter,
        order_by=order_by,
        limit=limit,
    )


def build_difference_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting the pairwise difference of two geometry columns.

    Adds a ``difference`` geometry column via
    ``ST_Difference(t.{geom}, t.{other_geom})`` (A minus B). No ``%s``
    parameters are emitted — both geometry columns are identifier-validated
    and interpolated directly into the SQL. The result is a geometry, valid
    for ``into="gdf"``.

    Note: inputs with mismatched SRIDs will raise a native PostGIS error
    at execution time (D-06). No pre-check is performed.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        First geometry column name (minuend), by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    other_geom : str
        Second geometry column name (subtrahend, required, keyword-only).
    columns : list of str, optional
        Columns to select alongside the result, by default all.
    filter : str, optional
        Raw SQL filter fragment.
    order_by : str, optional
        ORDER BY clause body.
    limit : int, optional
        LIMIT value.

    Returns
    -------
    tuple of (str, list)
        SQL string and empty parameter list (``[]``).

    Raises
    ------
    InvalidIdentifierError
        If any identifier (``table``, ``schema``, ``geom``, ``other_geom``,
        or any element of ``columns``) is invalid.
    """
    return _build_binary_geom_sql(
        "ST_Difference",
        "difference",
        table,
        geom,
        schema,
        other_geom=other_geom,
        columns=columns,
        filter=filter,
        order_by=order_by,
        limit=limit,
    )


def build_intersection_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting the pairwise intersection of two geometry columns.

    Adds an ``intersection`` geometry column via
    ``ST_Intersection(t.{geom}, t.{other_geom})`` (shared portion of A and
    B). No ``%s`` parameters are emitted — both geometry columns are
    identifier-validated and interpolated directly into the SQL. The result
    is a geometry, valid for ``into="gdf"``.

    Note: inputs with mismatched SRIDs will raise a native PostGIS error
    at execution time (D-06). No pre-check is performed.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        First geometry column name, by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    other_geom : str
        Second geometry column name (required, keyword-only).
    columns : list of str, optional
        Columns to select alongside the result, by default all.
    filter : str, optional
        Raw SQL filter fragment.
    order_by : str, optional
        ORDER BY clause body.
    limit : int, optional
        LIMIT value.

    Returns
    -------
    tuple of (str, list)
        SQL string and empty parameter list (``[]``).

    Raises
    ------
    InvalidIdentifierError
        If any identifier (``table``, ``schema``, ``geom``, ``other_geom``,
        or any element of ``columns``) is invalid.
    """
    return _build_binary_geom_sql(
        "ST_Intersection",
        "intersection",
        table,
        geom,
        schema,
        other_geom=other_geom,
        columns=columns,
        filter=filter,
        order_by=order_by,
        limit=limit,
    )


#: Valid ``method=`` values for :func:`build_make_valid_sql` (D-02).
_VALID_MAKE_VALID_METHODS = {None, "linework", "structure"}


def build_simplify_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    tolerance: float,
    preserve_topology: bool = True,
    preserve_collapsed: bool = False,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with their geometry simplified.

    By default uses ``ST_SimplifyPreserveTopology``, which guarantees a
    non-NULL result even when all points collapse within ``tolerance``
    (topology is preserved). Pass ``preserve_topology=False`` to use
    ``ST_Simplify`` instead — that variant *may* return ``NULL`` when the
    geometry collapses below ``tolerance`` (D-07).

    When ``preserve_topology=False``, the ``preserve_collapsed`` flag is
    forwarded to ``ST_Simplify`` as its third bound parameter.

    The simplified geometry is aliased as ``simplified`` (D-01).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    tolerance : float
        Simplification tolerance (required keyword-only, D-05). Units
        depend on the geometry's SRID (degrees for 4326).
    preserve_topology : bool, optional
        If ``True`` (default) use ``ST_SimplifyPreserveTopology`` (no
        NULL collapse). If ``False`` use ``ST_Simplify`` (faster,
        but can return ``NULL``).
    preserve_collapsed : bool, optional
        Passed to ``ST_Simplify`` only when ``preserve_topology=False``.
        Setting ``preserve_collapsed=True`` while ``preserve_topology=True``
        raises ``ValueError`` (D-05).
    columns : list of str, optional
        Columns to select alongside the result, by default all.
    filter : str, optional
        Raw SQL filter fragment.
    order_by : str, optional
        ORDER BY clause body.
    limit : int, optional
        LIMIT value.

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list.

    Raises
    ------
    ValueError
        If ``preserve_collapsed=True`` and ``preserve_topology=True``
        (contradictory, D-05).
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
    if columns:
        validate_identifiers(*columns)
    # Contradictory-arg guard (D-05) — AFTER validate_identifiers
    if preserve_collapsed and preserve_topology:
        raise ValueError(
            "preserve_collapsed=True has no effect when preserve_topology=True; "
            "set preserve_topology=False to use ST_Simplify with preserve_collapsed."
        )
    if preserve_topology:
        expr = f"ST_SimplifyPreserveTopology(t.{geom}, %s)"
        params: list = [tolerance]
    else:
        expr = f"ST_Simplify(t.{geom}, %s, %s)"
        params = [tolerance, preserve_collapsed]
    sql = (
        f"SELECT {_cols_str(columns)}, {expr} AS simplified "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, params


def build_convex_hull_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with the convex hull of each geometry.

    Adds a ``convex_hull`` geometry column via ``ST_ConvexHull(t.{geom})``
    (D-01). Returns ``NULL`` for empty geometries — pass-through (D-07).
    Valid for ``into="gdf"``.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    columns : list of str, optional
        Columns to select alongside the result, by default all.
    filter : str, optional
        Raw SQL filter fragment.
    order_by : str, optional
        ORDER BY clause body.
    limit : int, optional
        LIMIT value.

    Returns
    -------
    tuple of (str, list)
        SQL string and empty parameter list (``[]``).

    Raises
    ------
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, ST_ConvexHull(t.{geom}) AS convex_hull "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_make_valid_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    method: str | None = None,
    keep_collapsed: bool | None = None,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build SQL selecting rows with their geometry repaired via ST_MakeValid.

    Adds a ``made_valid`` geometry column (D-01). Geometries that are
    already valid are returned unchanged. Invalid geometries (e.g. bowtie
    self-intersections) are repaired — the output type may change
    (``POLYGON`` → ``MULTIPOLYGON`` or ``GEOMETRYCOLLECTION``, D-07).

    ``method`` selects the repair algorithm:

    - ``None`` (default) — PostGIS default algorithm (``ST_MakeValid(geom)``
      form; available since PostGIS 3.0).
    - ``"linework"`` — re-node the linework and assemble valid polygons;
      bound as the params string ``"method=linework"`` via ``%s``.
    - ``"structure"`` — divide into structure components and rebuild;
      requires PostGIS ≥ 3.2 / GEOS ≥ 3.10 (D-04). On older servers,
      PostGIS raises a native error — no server-version pre-check is
      performed (D-04 passthrough). Bound as ``"method=structure"`` (plus
      optional ``keepcollapsed`` key) via ``%s``.

    The params string is assembled from programmer-controlled literals and
    bound through ``%s`` — it is never f-string-interpolated (D-02, Pitfall 4).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    method : {None, "linework", "structure"}, optional
        Repair algorithm, by default ``None``.
    keep_collapsed : bool or None, optional
        Only valid when ``method="structure"``. Controls whether degenerate
        geometries that collapse to lower-dimensional forms are kept as
        such (``True``/``False``) or dropped by PostGIS's default. Setting
        ``keep_collapsed`` when ``method != "structure"`` raises
        ``ValueError`` (D-03).
    columns : list of str, optional
        Columns to select alongside the result, by default all.
    filter : str, optional
        Raw SQL filter fragment.
    order_by : str, optional
        ORDER BY clause body.
    limit : int, optional
        LIMIT value.

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list (empty when ``method=None``).

    Raises
    ------
    ValueError
        If ``method`` is not in ``{None, "linework", "structure"}`` (D-02),
        or if ``keep_collapsed`` is set when ``method != "structure"`` (D-03).
    InvalidIdentifierError
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
    if columns:
        validate_identifiers(*columns)
    # method whitelist guard (D-02) — AFTER validate_identifiers, BEFORE SQL
    if method not in _VALID_MAKE_VALID_METHODS:
        raise ValueError(
            f"method must be one of "
            f"{sorted(str(m) for m in _VALID_MAKE_VALID_METHODS if m is not None) + [str(None)]}, "
            f"got {method!r}"
        )
    # Contradictory-arg guard (D-03)
    if keep_collapsed is not None and method != "structure":
        raise ValueError(
            "keep_collapsed is only valid when method='structure'; "
            f"got method={method!r}"
        )
    if method is None:
        expr = f"ST_MakeValid(t.{geom})"
        params: list = []
    else:
        # Assemble params string from whitelisted literals — never f-string (D-02)
        if method == "linework":
            params_str = "method=linework"
        else:  # "structure"
            if keep_collapsed is None:
                params_str = "method=structure"
            elif keep_collapsed:
                params_str = "method=structure keepcollapsed=true"
            else:
                params_str = "method=structure keepcollapsed=false"
        expr = f"ST_MakeValid(t.{geom}, %s)"
        params = [params_str]
    sql = (
        f"SELECT {_cols_str(columns)}, {expr} AS made_valid "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, params


#: Helpers whose result set has no geometry column — ``into="gdf"`` is
#: rejected for these (D-02).
_SCALAR_HELPERS = frozenset({"area", "perimeter", "distance", "centroid"})

#: Accepted ``into=`` values (D-01; ``into="query"`` deferred to the ETL
#: milestone).
_VALID_INTO = ("rows", "gdf")

#: Exact PostGIS guard message (mirrors ``from_geodataframe``).
_POSTGIS_GUARD_MSG = (
    "PostGIS extension not installed. Run db.schema.create_extension('postgis')"
)


def _check_into(into: str, helper: str) -> None:
    """Validate the ``into=`` value for a helper before any SQL runs.

    Parameters
    ----------
    into : str
        Requested output form — ``"rows"`` or ``"gdf"`` (D-01).
    helper : str
        Helper name, used for error messages and the scalar check.

    Raises
    ------
    ValueError
        If ``into`` is not in the allowed set, or if ``into="gdf"`` is
        requested on a scalar helper (D-02).
    """
    if into not in _VALID_INTO:
        raise ValueError(f"into must be one of {_VALID_INTO}, got {into!r}")
    if into == "gdf" and helper in _SCALAR_HELPERS:
        raise ValueError(
            f"into='gdf' is invalid for {helper}(): it returns a scalar, "
            "not a geometry"
        )


def _to_named_binds(sql: str, params: list) -> tuple[str, dict]:
    """Convert ``%s`` placeholders to named binds for SQLAlchemy ``text()``.

    The pure builders emit psycopg-style ``%s`` placeholders with a
    positional params list, but ``to_geodataframe`` wraps SQL in
    SQLAlchemy ``text()``, which requires ``:name`` binds with a dict.
    This adapter rewrites placeholders to ``:p0``, ``:p1``, ... in order.

    Parameters
    ----------
    sql : str
        SQL containing ``%s`` placeholders.
    params : list
        Positional parameter values (one per placeholder).

    Returns
    -------
    tuple of (str, dict)
        SQL with named binds and the matching parameter dict.
    """
    parts = sql.split("%s")
    out = parts[0]
    binds: dict = {}
    for i, part in enumerate(parts[1:]):
        out += f":p{i}{part}"
        binds[f"p{i}"] = params[i]
    return out, binds


class SpatialAccessor:
    """Sync spatial helper namespace exposed as ``db.spatial``.

    Each method delegates SQL assembly to the module-level pure builders
    and routes the result per ``into=`` (D-01): ``"rows"`` returns
    ``list[dict]`` via ``Database.execute``; ``"gdf"`` returns a
    GeoDataFrame via ``Database.to_geodataframe``. PostGIS availability is
    guarded at construction (SPA-04).
    """

    def __init__(self, db: Database) -> None:
        """Initialize the accessor and verify PostGIS availability.

        Parameters
        ----------
        db : Database
            Parent database instance.

        Raises
        ------
        ExtensionNotAvailableError
            If the PostGIS extension is not installed.
        """
        self._db = db
        if not db.schema.has_extension("postgis"):
            raise ExtensionNotAvailableError(_POSTGIS_GUARD_MSG)

    def _run(
        self, sql: str, params: list, into: str, geometry_column: str
    ) -> list[dict] | gpd.GeoDataFrame:
        """Execute built SQL, routing on ``into=``.

        Parameters
        ----------
        sql : str
            SQL from a pure builder (``%s`` placeholders).
        params : list
            Positional parameters for the SQL.
        into : str
            ``"rows"`` or ``"gdf"`` (already validated).
        geometry_column : str
            Geometry column name for the GeoDataFrame path.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Query results in the requested form.
        """
        if into == "gdf":
            named_sql, binds = _to_named_binds(sql, params)
            return self._db.to_geodataframe(
                sql=named_sql, params=binds, geometry_column=geometry_column
            )
        return self._db.execute(sql, params)

    def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows whose geometry contains the input geometry.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry (one of the four D-05 forms).
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        ref : tuple of str, optional
            ``(ref_table, ref_col)`` input geometry (EXISTS, D-08).
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        into : str, optional
            ``"rows"`` (list of dict) or ``"gdf"`` (GeoDataFrame), by
            default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Additional raw SQL filter (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Matching rows in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is invalid or geometry forms are not exclusive.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "contains")
        sql, params = build_contains_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            ref=ref,
            srid=srid,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, geom)

    def within(
        self,
        left_table: str,
        left_geom: str,
        right_table: str,
        right_geom: str,
        *,
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select left-table rows whose geometry is within a right-table row.

        Two-table JOIN form per 08-DESIGN §3 (dedicated signature, D-08).

        Parameters
        ----------
        left_table : str
            Table whose rows are returned.
        left_geom : str
            Geometry column of the left table.
        right_table : str
            Containing table.
        right_geom : str
            Geometry column of the right table.
        schema : str, optional
            Schema name for both tables, by default "public".
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Matching rows in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "within")
        sql, params = build_within_sql(
            left_table,
            left_geom,
            right_table,
            right_geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, left_geom)

    def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows whose geometry intersects the input geometry.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry (one of the four D-05 forms).
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        ref : tuple of str, optional
            ``(ref_table, ref_col)`` input geometry (EXISTS, D-08).
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Additional raw SQL filter (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Matching rows in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is invalid or geometry forms are not exclusive.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "intersects")
        sql, params = build_intersects_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            ref=ref,
            srid=srid,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, geom)

    def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        distance: float,
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows within a distance of the input geometry.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry (one of the four D-05 forms).
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        ref : tuple of str, optional
            ``(ref_table, ref_col)`` input geometry (EXISTS, D-08).
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        distance : float
            Search distance, meters by default (D-09).
        unit : str, optional
            ``"m"`` or ``"srid"``, by default "m" (D-09).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Additional raw SQL filter (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Matching rows in the requested form.

        Raises
        ------
        ValueError
            If ``into``/``unit`` is invalid or geometry forms are not
            exclusive.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "dwithin")
        sql, params = build_dwithin_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            ref=ref,
            srid=srid,
            distance=distance,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, geom)

    def distance(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        srid: int = 4326,
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Select rows with their distance to the input geometry.

        Scalar result (``distance`` column); ``into="gdf"`` raises
        ``ValueError`` per D-02.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry.
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        unit : str, optional
            ``"m"`` or ``"srid"``, by default "m" (D-09).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-02).
        columns : list of str, optional
            Columns to select alongside the distance (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body, e.g. ``"distance"`` (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``distance`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper) or inputs are invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "distance")
        sql, params = build_distance_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            srid=srid,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, geom)

    def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        srid: int = 4326,
        k: int = 5,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select the k rows nearest to the input geometry (KNN).

        Metric ordering via ``::geography`` casts; a GiST index on the
        geometry column accelerates this. No ``unit=`` parameter (D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry.
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        k : int, optional
            Number of nearest rows to return, by default 5.
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            The k nearest rows in proximity order.

        Raises
        ------
        ValueError
            If ``into`` is invalid or geometry forms are not exclusive.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "nearest")
        sql, params = build_nearest_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            srid=srid,
            k=k,
            columns=columns,
            filter=filter,
        )
        return self._run(sql, params, into, geom)

    def area(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Select rows with the area of their geometry.

        Scalar result (``area`` column); ``into="gdf"`` raises
        ``ValueError`` per D-02.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        unit : str, optional
            ``"m"`` (square meters) or ``"srid"``, by default "m" (D-09).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-02).
        columns : list of str, optional
            Columns to select alongside the area (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``area`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper) or ``unit`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "area")
        sql, params = build_area_sql(
            table,
            geom=geom,
            schema=schema,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, geom)

    def perimeter(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Select rows with the perimeter of their geometry.

        Scalar result (``perimeter`` column); ``into="gdf"`` raises
        ``ValueError`` per D-02.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        unit : str, optional
            ``"m"`` (meters) or ``"srid"``, by default "m" (D-09).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-02).
        columns : list of str, optional
            Columns to select alongside the perimeter (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``perimeter`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper) or ``unit`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "perimeter")
        sql, params = build_perimeter_sql(
            table,
            geom=geom,
            schema=schema,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, geom)

    def centroid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Select rows with their geometry centroid coordinates.

        Scalar result (``centroid_x``/``centroid_y`` columns);
        ``into="gdf"`` raises ``ValueError`` per D-02. No ``unit=``
        parameter (D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-02).
        columns : list of str, optional
            Columns to select alongside the centroid (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including ``centroid_x`` and ``centroid_y`` columns.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper).
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "centroid")
        sql, params = build_centroid_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, geom)

    def buffer(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        distance: float,
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with a buffer around their geometry.

        Returns a ``buffer`` geometry column — valid for ``into="gdf"``.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        distance : float
            Buffer distance, meters by default (D-09).
        unit : str, optional
            ``"m"`` or ``"srid"``, by default "m" (D-09).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select alongside the buffer (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``buffer`` geometry column.

        Raises
        ------
        ValueError
            If ``into``/``unit`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "buffer")
        sql, params = build_buffer_sql(
            table,
            geom=geom,
            schema=schema,
            distance=distance,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "buffer")

    def transform(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        to_srid: int,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with their geometry transformed to another SRID.

        Returns a ``geometry_transformed`` geometry column — valid for
        ``into="gdf"``. No ``unit=`` parameter (D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        to_srid : int
            Target spatial reference identifier.
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select alongside the transform (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``geometry_transformed`` column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        _check_into(into, "transform")
        sql, params = build_transform_sql(
            table,
            geom=geom,
            schema=schema,
            to_srid=to_srid,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "geometry_transformed")

    def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with the pairwise union of two geometry columns.

        Returns a ``union_geom`` geometry column via
        ``ST_Union(t.{geom}, t.{other_geom})`` — valid for ``into="gdf"``.
        No ``where=`` deprecated alias (born clean for 1.0 freeze, D-10).

        Note: inputs with mismatched SRIDs will raise a native PostGIS error
        at execution time (D-06). No pre-check is performed.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            First geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        other_geom : str
            Second geometry column name (required, keyword-only).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows".
        columns : list of str, optional
            Columns to select alongside the result.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``union_geom`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "union")
        sql, params = build_union_sql(
            table,
            geom=geom,
            schema=schema,
            other_geom=other_geom,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "union_geom")

    def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with the pairwise difference of two geometry columns.

        Returns a ``difference`` geometry column via
        ``ST_Difference(t.{geom}, t.{other_geom})`` (A minus B) — valid for
        ``into="gdf"``. No ``where=`` deprecated alias (born clean, D-10).

        Note: inputs with mismatched SRIDs will raise a native PostGIS error
        at execution time (D-06). No pre-check is performed.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            First geometry column name (minuend), by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        other_geom : str
            Second geometry column name (subtrahend, required, keyword-only).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows".
        columns : list of str, optional
            Columns to select alongside the result.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``difference`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "difference")
        sql, params = build_difference_sql(
            table,
            geom=geom,
            schema=schema,
            other_geom=other_geom,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "difference")

    def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with the pairwise intersection of two geometry columns.

        Returns an ``intersection`` geometry column via
        ``ST_Intersection(t.{geom}, t.{other_geom})`` (shared portion) —
        valid for ``into="gdf"``. No ``where=`` deprecated alias (born clean,
        D-10).

        Note: inputs with mismatched SRIDs will raise a native PostGIS error
        at execution time (D-06). No pre-check is performed.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            First geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        other_geom : str
            Second geometry column name (required, keyword-only).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows".
        columns : list of str, optional
            Columns to select alongside the result.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``intersection`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "intersection")
        sql, params = build_intersection_sql(
            table,
            geom=geom,
            schema=schema,
            other_geom=other_geom,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "intersection")

    def create_spatial_index(
        self,
        table: str,
        *,
        column: str = "geometry",
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Create a GIST spatial index on a geometry column.

        Parameters
        ----------
        table : str
            Table name.
        column : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Index name (auto-generated if not provided).
        """
        validate_identifiers(table, column, schema)
        if name:
            validate_identifier(name)
        index_name = name or f"idx_{table}_{column}_gist"
        self._db.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {schema}.{table} USING GIST ({column})
        """)

    def list_geometry_columns(self, *, schema: str | None = None) -> list[dict]:
        """List geometry columns in the database.

        Parameters
        ----------
        schema : str, optional
            Schema filter.

        Returns
        -------
        list of dict
            List of geometry column info.
        """
        where_clause = "WHERE f_table_schema = %s" if schema else ""
        params = [schema] if schema else None
        return self._db.execute(
            queries.LIST_GEOMETRY_COLUMNS.format(where_clause=where_clause),
            params,
        )


class AsyncSpatialAccessor:
    """Async spatial helper namespace exposed as ``async_db.spatial``.

    Mirrors :class:`SpatialAccessor` exactly — same builders, same
    parameters, same ``into=`` routing — with awaited execution. The
    PostGIS guard is deferred to the first method call because
    ``__init__`` cannot ``await`` (lazy ``_postgis_ok`` flag, SPA-04).
    """

    def __init__(self, db: AsyncDatabase) -> None:
        """Initialize the accessor (PostGIS guard deferred to first call).

        Parameters
        ----------
        db : AsyncDatabase
            Parent async database instance.
        """
        self._db = db
        self._postgis_ok: bool = False

    async def _check_postgis(self) -> None:
        """Verify PostGIS availability once, caching the positive result.

        Raises
        ------
        ExtensionNotAvailableError
            If the PostGIS extension is not installed.
        """
        if not self._postgis_ok:
            if not await self._db.schema.has_extension("postgis"):
                raise ExtensionNotAvailableError(_POSTGIS_GUARD_MSG)
            self._postgis_ok = True

    async def _run(
        self, sql: str, params: list, into: str, geometry_column: str
    ) -> list[dict] | gpd.GeoDataFrame:
        """Execute built SQL asynchronously, routing on ``into=``.

        Parameters
        ----------
        sql : str
            SQL from a pure builder (``%s`` placeholders).
        params : list
            Positional parameters for the SQL.
        into : str
            ``"rows"`` or ``"gdf"`` (already validated).
        geometry_column : str
            Geometry column name for the GeoDataFrame path.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Query results in the requested form.
        """
        if into == "gdf":
            named_sql, binds = _to_named_binds(sql, params)
            return await self._db.to_geodataframe(
                sql=named_sql, params=binds, geometry_column=geometry_column
            )
        return await self._db.execute(sql, params)

    async def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows whose geometry contains the input geometry (async).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry (one of the four D-05 forms).
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        ref : tuple of str, optional
            ``(ref_table, ref_col)`` input geometry (EXISTS, D-08).
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Additional raw SQL filter (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Matching rows in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is invalid or geometry forms are not exclusive.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "contains")
        sql, params = build_contains_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            ref=ref,
            srid=srid,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, geom)

    async def within(
        self,
        left_table: str,
        left_geom: str,
        right_table: str,
        right_geom: str,
        *,
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select left rows whose geometry is within a right row (async).

        Two-table JOIN form per 08-DESIGN §3 (dedicated signature, D-08).

        Parameters
        ----------
        left_table : str
            Table whose rows are returned.
        left_geom : str
            Geometry column of the left table.
        right_table : str
            Containing table.
        right_geom : str
            Geometry column of the right table.
        schema : str, optional
            Schema name for both tables, by default "public".
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Matching rows in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "within")
        sql, params = build_within_sql(
            left_table,
            left_geom,
            right_table,
            right_geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, left_geom)

    async def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows whose geometry intersects the input geometry (async).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry (one of the four D-05 forms).
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        ref : tuple of str, optional
            ``(ref_table, ref_col)`` input geometry (EXISTS, D-08).
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Additional raw SQL filter (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Matching rows in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is invalid or geometry forms are not exclusive.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "intersects")
        sql, params = build_intersects_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            ref=ref,
            srid=srid,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, geom)

    async def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        distance: float,
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows within a distance of the input geometry (async).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry (one of the four D-05 forms).
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        ref : tuple of str, optional
            ``(ref_table, ref_col)`` input geometry (EXISTS, D-08).
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        distance : float
            Search distance, meters by default (D-09).
        unit : str, optional
            ``"m"`` or ``"srid"``, by default "m" (D-09).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Additional raw SQL filter (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Matching rows in the requested form.

        Raises
        ------
        ValueError
            If ``into``/``unit`` is invalid or geometry forms are not
            exclusive.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "dwithin")
        sql, params = build_dwithin_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            ref=ref,
            srid=srid,
            distance=distance,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, geom)

    async def distance(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        srid: int = 4326,
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Select rows with their distance to the input geometry (async).

        Scalar result (``distance`` column); ``into="gdf"`` raises
        ``ValueError`` per D-02.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry.
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        unit : str, optional
            ``"m"`` or ``"srid"``, by default "m" (D-09).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-02).
        columns : list of str, optional
            Columns to select alongside the distance (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body, e.g. ``"distance"`` (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``distance`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper) or inputs are invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "distance")
        sql, params = build_distance_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            srid=srid,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, geom)

    async def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict | None = None,
        srid: int = 4326,
        k: int = 5,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select the k rows nearest to the input geometry (async KNN).

        Metric ordering via ``::geography`` casts; a GiST index on the
        geometry column accelerates this. No ``unit=`` parameter (D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        point : tuple of float, optional
            ``(x, y)`` input geometry.
        wkt : str, optional
            WKT input geometry.
        geojson : dict, optional
            GeoJSON input geometry.
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        k : int, optional
            Number of nearest rows to return, by default 5.
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            The k nearest rows in proximity order.

        Raises
        ------
        ValueError
            If ``into`` is invalid or geometry forms are not exclusive.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "nearest")
        sql, params = build_nearest_sql(
            table,
            geom=geom,
            schema=schema,
            point=point,
            wkt=wkt,
            geojson=geojson,
            srid=srid,
            k=k,
            columns=columns,
            filter=filter,
        )
        return await self._run(sql, params, into, geom)

    async def area(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Select rows with the area of their geometry (async).

        Scalar result (``area`` column); ``into="gdf"`` raises
        ``ValueError`` per D-02.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        unit : str, optional
            ``"m"`` (square meters) or ``"srid"``, by default "m" (D-09).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-02).
        columns : list of str, optional
            Columns to select alongside the area (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``area`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper) or ``unit`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "area")
        sql, params = build_area_sql(
            table,
            geom=geom,
            schema=schema,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, geom)

    async def perimeter(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Select rows with the perimeter of their geometry (async).

        Scalar result (``perimeter`` column); ``into="gdf"`` raises
        ``ValueError`` per D-02.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        unit : str, optional
            ``"m"`` (meters) or ``"srid"``, by default "m" (D-09).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-02).
        columns : list of str, optional
            Columns to select alongside the perimeter (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``perimeter`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper) or ``unit`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "perimeter")
        sql, params = build_perimeter_sql(
            table,
            geom=geom,
            schema=schema,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, geom)

    async def centroid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Select rows with their geometry centroid coordinates (async).

        Scalar result (``centroid_x``/``centroid_y`` columns);
        ``into="gdf"`` raises ``ValueError`` per D-02. No ``unit=``
        parameter (D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-02).
        columns : list of str, optional
            Columns to select alongside the centroid (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including ``centroid_x`` and ``centroid_y`` columns.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper).
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "centroid")
        sql, params = build_centroid_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, geom)

    async def buffer(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        distance: float,
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with a buffer around their geometry (async).

        Returns a ``buffer`` geometry column — valid for ``into="gdf"``.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        distance : float
            Buffer distance, meters by default (D-09).
        unit : str, optional
            ``"m"`` or ``"srid"``, by default "m" (D-09).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select alongside the buffer (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``buffer`` geometry column.

        Raises
        ------
        ValueError
            If ``into``/``unit`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "buffer")
        sql, params = build_buffer_sql(
            table,
            geom=geom,
            schema=schema,
            distance=distance,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "buffer")

    async def transform(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        to_srid: int,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with their geometry transformed to a SRID (async).

        Returns a ``geometry_transformed`` geometry column — valid for
        ``into="gdf"``. No ``unit=`` parameter (D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry" (D-06).
        schema : str, optional
            Schema name, by default "public".
        to_srid : int
            Target spatial reference identifier.
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select alongside the transform (D-03).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        where : str, optional
            Deprecated. Use ``filter=`` instead.
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``geometry_transformed`` column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierErrorError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        if where is not None:
            if filter is not None:
                raise TypeError(
                    "Cannot specify both 'filter' and 'where'; use 'filter=' only."
                )
            warnings.warn(
                "The 'where' keyword argument is deprecated and will be removed in "
                "pycopg 2.0. Use 'filter=' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            filter = where
        await self._check_postgis()
        _check_into(into, "transform")
        sql, params = build_transform_sql(
            table,
            geom=geom,
            schema=schema,
            to_srid=to_srid,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "geometry_transformed")

    async def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with the pairwise union of two geometry columns (async).

        Returns a ``union_geom`` geometry column via
        ``ST_Union(t.{geom}, t.{other_geom})`` — valid for ``into="gdf"``.
        No ``where=`` deprecated alias (born clean for 1.0 freeze, D-10).

        Note: inputs with mismatched SRIDs will raise a native PostGIS error
        at execution time (D-06). No pre-check is performed.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            First geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        other_geom : str
            Second geometry column name (required, keyword-only).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows".
        columns : list of str, optional
            Columns to select alongside the result.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``union_geom`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "union")
        sql, params = build_union_sql(
            table,
            geom=geom,
            schema=schema,
            other_geom=other_geom,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "union_geom")

    async def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with the pairwise difference of two geometry columns (async).

        Returns a ``difference`` geometry column via
        ``ST_Difference(t.{geom}, t.{other_geom})`` (A minus B) — valid for
        ``into="gdf"``. No ``where=`` deprecated alias (born clean, D-10).

        Note: inputs with mismatched SRIDs will raise a native PostGIS error
        at execution time (D-06). No pre-check is performed.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            First geometry column name (minuend), by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        other_geom : str
            Second geometry column name (subtrahend, required, keyword-only).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows".
        columns : list of str, optional
            Columns to select alongside the result.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``difference`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "difference")
        sql, params = build_difference_sql(
            table,
            geom=geom,
            schema=schema,
            other_geom=other_geom,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "difference")

    async def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | gpd.GeoDataFrame:
        """Select rows with the pairwise intersection of two geometry columns (async).

        Returns an ``intersection`` geometry column via
        ``ST_Intersection(t.{geom}, t.{other_geom})`` (shared portion) —
        valid for ``into="gdf"``. No ``where=`` deprecated alias (born clean,
        D-10).

        Note: inputs with mismatched SRIDs will raise a native PostGIS error
        at execution time (D-06). No pre-check is performed.

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            First geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        other_geom : str
            Second geometry column name (required, keyword-only).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows".
        columns : list of str, optional
            Columns to select alongside the result.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows including the ``intersection`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "intersection")
        sql, params = build_intersection_sql(
            table,
            geom=geom,
            schema=schema,
            other_geom=other_geom,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "intersection")

    async def create_spatial_index(
        self,
        table: str,
        *,
        column: str = "geometry",
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Create a GIST spatial index on a geometry column.

        Parameters
        ----------
        table : str
            Table name.
        column : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Index name (auto-generated if not provided).
        """
        await self._check_postgis()
        validate_identifiers(table, column, schema)
        if name:
            validate_identifier(name)
        index_name = name or f"idx_{table}_{column}_gist"
        await self._db.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {schema}.{table} USING GIST ({column})
        """)

    async def list_geometry_columns(self, *, schema: str | None = None) -> list[dict]:
        """List geometry columns in the database.

        Parameters
        ----------
        schema : str, optional
            Schema filter.

        Returns
        -------
        list of dict
            List of geometry column info.
        """
        await self._check_postgis()
        where_clause = "WHERE f_table_schema = %s" if schema else ""
        params = [schema] if schema else None
        return await self._db.execute(
            queries.LIST_GEOMETRY_COLUMNS.format(where_clause=where_clause),
            params,
        )
