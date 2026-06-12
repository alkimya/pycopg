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

The ``where=`` parameter is a raw SQL fragment following the existing
``_build_select_sql`` convention — values inside it are the caller's
responsibility (T-14-04 accepted limitation).
"""

import json

from pycopg.utils import validate_identifiers

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
    InvalidIdentifier
        If ``ref=`` identifiers are invalid.
    """
    given = sum(x is not None for x in (point, wkt, geojson, ref))
    if given != 1:
        raise ValueError(
            "Exactly one of point=, wkt=, geojson=, ref= must be provided"
        )

    if point is not None:
        x, y = point
        return f"ST_SetSRID(ST_MakePoint(%s, %s), {int(srid)})", [x, y]

    if wkt is not None:
        return f"ST_GeomFromText(%s, {int(srid)})", [wkt]

    if geojson is not None:
        return f"ST_SetSRID(ST_GeomFromGeoJSON(%s), {int(srid)})", [
            json.dumps(geojson)
        ]

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
    where: str | None,
    order_by: str | None,
    limit: int | None,
    has_where: bool,
) -> str:
    """Append ``where``/``order_by``/``limit`` clauses to a SQL string.

    Follows the ``_build_select_sql`` convention (D-11/D-12): when the
    statement already has a WHERE clause (spatial condition first), the
    ``where=`` fragment is combined as ``AND ({where})``.

    Parameters
    ----------
    sql : str
        SQL statement built so far.
    where : str, optional
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
    if where:
        sql += f" AND ({where})" if has_where else f" WHERE {where}"
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
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=True)
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
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=True)
    return sql, params


def build_within_sql(
    left_table: str,
    left_geom: str,
    right_table: str,
    right_geom: str,
    schema: str = "public",
    columns: list[str] | None = None,
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=False)
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
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=True)
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
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=False)
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
    where: str | None = None,
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
    where : str, optional
        Raw SQL filter fragment (D-11).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list (k is the last parameter).

    Raises
    ------
    ValueError
        If the geometry input forms are not mutually exclusive.
    InvalidIdentifier
        If any identifier is invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    fragment, params = _resolve_geometry(
        point=point, wkt=wkt, geojson=geojson, srid=srid
    )
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t"
    if where:
        sql += f" WHERE {where}"
    sql += (
        f" ORDER BY t.{geom}::geography <-> {fragment}::geography LIMIT %s"
    )
    return sql, [*params, k]


def build_area_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    unit: str = "m",
    columns: list[str] | None = None,
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=False)
    return sql, []


def build_perimeter_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    unit: str = "m",
    columns: list[str] | None = None,
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=False)
    return sql, []


def build_centroid_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=False)
    return sql, []


def build_buffer_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    distance: float,
    unit: str = "m",
    columns: list[str] | None = None,
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=False)
    return sql, [distance]


def build_transform_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    to_srid: int,
    columns: list[str] | None = None,
    where: str | None = None,
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
    where : str, optional
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
    InvalidIdentifier
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
    sql = _append_tail(sql, where, order_by, limit, has_where=False)
    return sql, [to_srid]
