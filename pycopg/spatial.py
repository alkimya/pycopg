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
from typing import TYPE_CHECKING, Any, Literal, cast, overload

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
    geojson: dict[str, Any] | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
) -> tuple[str, list[Any]]:
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

    # Unreachable at runtime: `given == 1` (checked above) and point/wkt/
    # geojson were all ruled out above, so `ref` is the one non-None form.
    # mypy cannot narrow this through the `sum(...)` exclusivity check.
    assert ref is not None
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
    *,
    group_by: str | None = None,
) -> str:
    """Append ``filter``/``group_by``/``order_by``/``limit`` clauses to a SQL string.

    Follows the ``_build_select_sql`` convention (D-11/D-12): when the
    statement already has a WHERE clause (spatial condition first), the
    ``filter=`` fragment is combined as ``AND ({filter})``.

    The optional ``group_by`` argument is keyword-only (D-03) and inserts a
    ``GROUP BY`` clause between the WHERE and ORDER BY fragments. The value
    must be a pre-assembled, already-validated column expression string
    (e.g., ``"t.region"`` or ``"t.region, t.zone"``); this function does
    **not** call ``validate_identifiers`` — that is the builder's
    responsibility.

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
    group_by : str, optional
        Pre-assembled GROUP BY column expression. Inserted after WHERE and
        before ORDER BY. Default ``None`` (no GROUP BY).

    Returns
    -------
    str
        SQL statement with the requested clauses appended.
    """
    if filter:
        sql += f" AND ({filter})" if has_where else f" WHERE {filter}"
    if group_by:
        sql += f" GROUP BY {group_by}"
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
    geojson: dict[str, Any] | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
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
    params: list[Any] = []
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
    geojson: dict[str, Any] | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
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
    params: list[Any] = []
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


def build_overlaps_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict[str, Any] | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows whose geometry overlaps the input geometry.

    Generates ``ST_Overlaps(t.{geom}, <geom_in>)`` (DE-9IM predicate,
    SPAT-F06/D-06). The ``ref=`` form uses an EXISTS subquery (D-08).
    Mechanically mirrors :func:`build_intersects_sql` — only the ST_*
    function name differs.

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
    params: list[Any] = []
    if fragment == _REF_SENTINEL:
        ref_table, ref_col = frag_params
        cond = (
            f"EXISTS (SELECT 1 FROM {ref_table} AS _ref "
            f"WHERE ST_Overlaps(_ref.{ref_col}, t.{geom}))"
        )
    else:
        cond = f"ST_Overlaps(t.{geom}, {fragment})"
        params.extend(frag_params)
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t WHERE {cond}"
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
    return sql, params


def build_touches_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict[str, Any] | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows whose geometry touches the input geometry.

    Generates ``ST_Touches(t.{geom}, <geom_in>)`` (DE-9IM predicate,
    SPAT-F06/D-06). The ``ref=`` form uses an EXISTS subquery (D-08).
    Mechanically mirrors :func:`build_intersects_sql` — only the ST_*
    function name differs.

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
    params: list[Any] = []
    if fragment == _REF_SENTINEL:
        ref_table, ref_col = frag_params
        cond = (
            f"EXISTS (SELECT 1 FROM {ref_table} AS _ref "
            f"WHERE ST_Touches(_ref.{ref_col}, t.{geom}))"
        )
    else:
        cond = f"ST_Touches(t.{geom}, {fragment})"
        params.extend(frag_params)
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t WHERE {cond}"
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
    return sql, params


def build_crosses_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict[str, Any] | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows whose geometry crosses the input geometry.

    Generates ``ST_Crosses(t.{geom}, <geom_in>)`` (DE-9IM predicate,
    SPAT-F06/D-06). The ``ref=`` form uses an EXISTS subquery (D-08).
    Mechanically mirrors :func:`build_intersects_sql` — only the ST_*
    function name differs.

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
    params: list[Any] = []
    if fragment == _REF_SENTINEL:
        ref_table, ref_col = frag_params
        cond = (
            f"EXISTS (SELECT 1 FROM {ref_table} AS _ref "
            f"WHERE ST_Crosses(_ref.{ref_col}, t.{geom}))"
        )
    else:
        cond = f"ST_Crosses(t.{geom}, {fragment})"
        params.extend(frag_params)
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t WHERE {cond}"
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
    return sql, params


def build_disjoint_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict[str, Any] | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows whose geometry is disjoint from the input.

    Generates ``ST_Disjoint(t.{geom}, <geom_in>)`` (DE-9IM predicate,
    SPAT-F06/D-07). The ``ref=`` form uses the SAME uniform EXISTS
    subquery pattern as every other predicate in this family — it is
    NOT special-cased into a ``NOT EXISTS`` set-complement form (D-07).
    Mechanically mirrors :func:`build_intersects_sql` — only the ST_*
    function name differs.

    Warnings
    --------
    The ``ref=`` form means "EXISTS a ref row disjoint from t" (true as
    soon as ANY row in the reference table is disjoint from the current
    row — near-always true for a sparse reference table), NOT disjoint
    from all reference rows (D-07). ``ST_Disjoint`` does not use indexes
    [postgis.net/docs/ST_Disjoint.html]; a negated ``NOT ST_Intersects``
    predicate (via ``filter=``) is the indexable, performant alternative
    for large tables (D-08).

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
        ``(ref_table, ref_col)`` input geometry (EXISTS semantics —
        see the ``ref=`` footgun warning above, D-07).
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
    params: list[Any] = []
    if fragment == _REF_SENTINEL:
        ref_table, ref_col = frag_params
        cond = (
            f"EXISTS (SELECT 1 FROM {ref_table} AS _ref "
            f"WHERE ST_Disjoint(_ref.{ref_col}, t.{geom}))"
        )
    else:
        cond = f"ST_Disjoint(t.{geom}, {fragment})"
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
) -> tuple[str, list[Any]]:
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
    geojson: dict[str, Any] | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    distance: float,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
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
    params: list[Any] = []
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
    geojson: dict[str, Any] | None = None,
    srid: int = 4326,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
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
    geojson: dict[str, Any] | None = None,
    srid: int = 4326,
    k: int = 5,
    columns: list[str] | None = None,
    filter: str | None = None,
) -> tuple[str, list[Any]]:
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
) -> tuple[str, list[Any]]:
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
) -> tuple[str, list[Any]]:
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


def build_length_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows with the length of their geometry.

    Adds a scalar ``ST_Length(...) AS length`` column computed on the
    table's own geometry column. With ``unit="m"`` (default) the geometry
    is cast to ``::geography`` so the length is in meters (D-09/D-10).
    ``ST_Length`` returns ``0`` for non-linear (areal/point) geometries
    (D-10) — this is a PostGIS pass-through, not a pycopg guard.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    unit : str, optional
        ``"m"`` or ``"srid"``, by default "m" (D-09/D-10).
    columns : list of str, optional
        Columns to select alongside the length, by default all (D-03).
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
        f"ST_Length(t.{geom}{cast}) AS length "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_is_valid_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows with the OGC validity of their geometry.

    Adds a scalar ``ST_IsValid(...) AS is_valid`` boolean column computed
    on the table's own geometry column (D-09/D-12).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    columns : list of str, optional
        Columns to select alongside the validity flag, by default all
        (D-03).
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
        f"SELECT {_cols_str(columns)}, ST_IsValid(t.{geom}) AS is_valid "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_is_valid_reason_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows with the OGC validity reason of their geometry.

    Adds a scalar ``ST_IsValidReason(...) AS is_valid_reason`` text column
    computed on the table's own geometry column (D-09/D-12) — describes
    why a geometry is invalid, or ``"Valid Geometry"`` when it is valid.

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry" (D-06).
    schema : str, optional
        Schema name, by default "public".
    columns : list of str, optional
        Columns to select alongside the validity reason, by default all
        (D-03).
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
        f"ST_IsValidReason(t.{geom}) AS is_valid_reason "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_geojson_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    max_decimal_digits: int = 6,
    include_bbox: bool = False,
    include_crs: bool = False,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows with their geometry as a GeoJSON string.

    Adds a scalar ``ST_AsGeoJSON(...) AS geojson`` column containing the
    geometry serialized as a GeoJSON text string. The result key is the
    frozen alias ``geojson``; callers use ``json.loads(row["geojson"])``
    when a dict is needed (D-06).

    The ``include_bbox`` and ``include_crs`` flags compose the
    ``ST_AsGeoJSON`` options bitmask (``1`` = bounding box, ``2`` = short
    CRS name) passed as a ``%s`` parameter alongside ``max_decimal_digits``
    (D-06).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    max_decimal_digits : int, optional
        Maximum decimal digits in coordinates, by default 6 (D-06).
    include_bbox : bool, optional
        Include bounding box in GeoJSON output (options bit 1), by default
        False (D-06).
    include_crs : bool, optional
        Include short CRS name in GeoJSON output (options bit 2), by
        default False (D-06).
    columns : list of str, optional
        Columns to select alongside the GeoJSON text, by default all
        (D-08).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list ``[max_decimal_digits, options]``.

    Raises
    ------
    InvalidIdentifierError
        If any identifier (table, schema, geom, or columns entries) is
        invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    options = (1 if include_bbox else 0) | (2 if include_crs else 0)
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"ST_AsGeoJSON(t.{geom}, %s, %s) AS geojson "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, [max_decimal_digits, options]


def build_text_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    max_decimal_digits: int | None = None,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows with their geometry as a WKT string.

    Adds a scalar ``ST_AsText(...) AS wkt`` column. The result key is the
    frozen alias ``wkt``. When ``max_decimal_digits`` is ``None`` (default)
    the one-arg ``ST_AsText(t.geom)`` form is used, preserving full
    precision — WKT is intended for exact interchange and round-trip use,
    so silent truncation is undesirable (D-07). When set, the two-arg
    ``ST_AsText(t.geom, %s)`` form is used, which requires PostGIS >= 3.1
    (the one-arg full-precision form works on all PostGIS 3.0+ servers).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    max_decimal_digits : int or None, optional
        Maximum decimal digits in coordinates, by default ``None`` (full
        precision — one-arg form). When set, two-arg form is emitted
        (D-07).
    columns : list of str, optional
        Columns to select alongside the WKT text, by default all (D-08).
    filter : str, optional
        Raw SQL filter fragment (D-11).
    order_by : str, optional
        ORDER BY clause body (D-12).
    limit : int, optional
        LIMIT value (D-12).

    Returns
    -------
    tuple of (str, list)
        SQL string and parameter list (``[]`` when ``max_decimal_digits``
        is ``None``; ``[max_decimal_digits]`` when set).

    Raises
    ------
    InvalidIdentifierError
        If any identifier (table, schema, geom, or columns entries) is
        invalid.
    """
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    if max_decimal_digits is not None:
        st_call = f"ST_AsText(t.{geom}, %s) AS wkt"
        params: list[Any] = [max_decimal_digits]
    else:
        st_call = f"ST_AsText(t.{geom}) AS wkt"
        params = []
    sql = f"SELECT {_cols_str(columns)}, {st_call} FROM {schema}.{table} AS t"
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, params


def build_mvt_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    tile_z: int,
    tile_x: int,
    tile_y: int,
    layer_name: str = "default",
    extent: int = 4096,
    columns: list[str] | None = None,
    feature_id_column: str | None = None,
    srid: int | None = None,
    filter: str | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL that generates a Mapbox Vector Tile (MVT) via ST_AsMVT.

    Always emits the enforced ``ST_Transform → ST_AsMVTGeom →
    ST_AsMVT`` pipeline (D-03). The pipeline transforms input geometry
    to Web Mercator (EPSG:3857), clips it to the tile envelope, and
    encodes it as a protobuf MVT blob. An outer ``WHERE q.geom_mvt IS
    NOT NULL`` filter discards rows that clip entirely outside the tile.

    Tile coordinates (``tile_z``, ``tile_x``, ``tile_y``) and the
    ``extent`` are coerced via ``int()`` and interpolated directly into
    the SQL — not as ``%s`` bind parameters.  The only ``%s``
    placeholders are ``layer_name`` and ``extent``, making the params
    list exactly ``[layer_name, extent]`` (D-03).

    SRID-0 / untagged columns
    --------------------------
    If the source geometry column has SRID 0 (untagged), PostGIS cannot
    determine the source CRS and ``ST_Transform`` silently produces wrong
    results. Use ``srid=4326`` (or the correct source SRID) to inject
    ``ST_SetSRID`` before the transform (D-04)::

        # SRID-0 column rescue:
        build_mvt_sql("points", srid=4326, tile_z=z, tile_x=x, tile_y=y)
        # → ST_Transform(ST_SetSRID(t.geometry, 4326), 3857)

    ``feature_id_column``
    ---------------------
    When set, the column name is embedded as a literal SQL identifier in
    the ``ST_AsMVT`` call. It must reference an **integer-type** column
    in the source table — PostGIS enforces this at query time (MVT spec
    requires 64-bit integer feature IDs). Pass ``feature_id_column=None``
    (the default) to omit the feature ID.

    PostGIS requirement
    -------------------
    Requires PostGIS ≥ 3.0 for ``ST_TileEnvelope`` and the five-arg
    ``ST_AsMVT`` form (documented requirement, not a runtime gate).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default ``"geometry"``.
    schema : str, optional
        Schema name, by default ``"public"``.
    tile_z : int
        Tile zoom level. Required keyword-only (D-02).
    tile_x : int
        Tile column index. Required keyword-only (D-02).
    tile_y : int
        Tile row index. Required keyword-only (D-02).
    layer_name : str, optional
        MVT layer name, by default ``"default"``. Passed as a ``%s``
        bind parameter.
    extent : int, optional
        MVT tile extent in pixel units, by default ``4096``. Interpolated
        as an integer literal (injection-safe) and also passed as a
        ``%s`` bind parameter to ``ST_AsMVT``.
    columns : list of str, optional
        Extra columns to select alongside the geometry in the inner
        subquery (available as MVT feature properties).
    feature_id_column : str or None, optional
        Integer-typed source column to use as the MVT feature ID.
        Validated as an identifier and interpolated directly — not a
        ``%s`` param. Must be an integer column (PostGIS requirement).
        By default ``None`` (no feature ID in the MVT).
    srid : int or None, optional
        Source SRID to inject via ``ST_SetSRID`` before the transform
        (D-04). Use this when the geometry column has SRID 0 or an
        incorrect SRID tag. ``None`` (default) — trusts the stored SRID.
    filter : str, optional
        Raw SQL fragment appended as ``WHERE {filter}`` inside the inner
        subquery (before clipping). This is a documented escape hatch;
        callers own the fragment (T-44-02c).

    Returns
    -------
    tuple of (str, list)
        SQL string with ``%s`` placeholders and the parameter list
        ``[layer_name, extent]`` (exactly two elements).

    Raises
    ------
    InvalidIdentifierError
        If ``table``, ``schema``, ``geom``, any entry in ``columns``, or
        ``feature_id_column`` is an invalid SQL identifier (T-44-02).
    ValueError
        If ``tile_z``, ``tile_x``, ``tile_y``, ``extent``, or ``srid``
        cannot be coerced to ``int`` (T-44-02b).

    Examples
    --------
    Basic tile for a roads table::

        sql, params = build_mvt_sql("roads", tile_z=12, tile_x=2048, tile_y=1361)
        # SELECT ST_AsMVT(q.*, %s, %s, 'geom_mvt') AS mvt
        # FROM (SELECT ST_AsMVTGeom(ST_Transform(t.geometry, 3857),
        #              ST_TileEnvelope(12, 2048, 1361), 4096) AS geom_mvt
        #       FROM public.roads AS t) AS q
        # WHERE q.geom_mvt IS NOT NULL
        # params == ['default', 4096]

    With SRID-0 rescue and a feature ID column::

        sql, params = build_mvt_sql(
            "places", tile_z=10, tile_x=512, tile_y=400,
            srid=4326, feature_id_column="gid",
        )
    """
    validate_identifiers(table, schema, geom)  # LINE 1: security invariant (T-44-02)
    if columns:
        validate_identifiers(*columns)
    if feature_id_column is not None:
        validate_identifiers(feature_id_column)

    # Coerce numerics via int() — non-integer input raises ValueError/TypeError
    # before any SQL assembly (T-44-02b).
    z, x, y, ext = int(tile_z), int(tile_x), int(tile_y), int(extent)

    # Build transform expression per D-04.
    if srid is not None:
        transform = f"ST_Transform(ST_SetSRID(t.{geom}, {int(srid)}), 3857)"
    else:
        transform = f"ST_Transform(t.{geom}, 3857)"

    # Build inner SELECT (clip geometry to tile envelope).
    col_prefix = (_cols_str(columns) + ", ") if columns else ""
    inner = (
        f"SELECT {col_prefix}ST_AsMVTGeom("
        f"{transform}, ST_TileEnvelope({z}, {x}, {y}), {ext}"
        f") AS geom_mvt FROM {schema}.{table} AS t"
    )
    if filter:
        inner += f" WHERE {filter}"

    # Build ST_AsMVT aggregate (feature_id_column is a validated literal, not a param).
    if feature_id_column is not None:
        agg = f"ST_AsMVT(q.*, %s, %s, 'geom_mvt', '{feature_id_column}')"
    else:
        agg = "ST_AsMVT(q.*, %s, %s, 'geom_mvt')"
    sql = f"SELECT {agg} AS mvt FROM ({inner}) AS q WHERE q.geom_mvt IS NOT NULL"
    return sql, [layer_name, ext]


def build_centroid_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
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
) -> tuple[str, list[Any]]:
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
) -> tuple[str, list[Any]]:
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
    grid_size: float | None = None,
    columns: list[str] | None,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
) -> tuple[str, list[Any]]:
    """Build SQL for a pairwise (binary, 2-column) geometry operation.

    Parameters
    ----------
    grid_size : float, optional
        Fixed-precision (snap-rounding) overlay grid size, by default None.
        When set, becomes the 3rd positional arg of ``op_func``, bound as a
        ``%s`` parameter (no client-side range guard, D-02). Requires
        PostGIS >= 3.1 / GEOS >= 3.9 (D-04); older servers raise a native
        PostGIS error, no version pre-check is performed. When None, the
        emitted SQL and params are byte-identical to the no-grid_size form
        (D-03).
    """
    validate_identifiers(table, schema, geom, other_geom)
    if columns:
        validate_identifiers(*columns)
    if grid_size is None:
        expr = f"{op_func}(t.{geom}, t.{other_geom})"
        params: list[Any] = []
    else:
        expr = f"{op_func}(t.{geom}, t.{other_geom}, %s)"
        params = [grid_size]
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"{expr} AS {result_col} "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, params


def build_union_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,
    grid_size: float | None = None,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
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
    grid_size : float, optional
        Fixed-precision (snap-rounding) overlay grid size, by default
        None. When set, emits the 3-arg ``ST_Union(a, b, %s)`` form bound
        to this value (pure passthrough, no range guard, D-02). Requires
        PostGIS >= 3.1 / GEOS >= 3.9 — older servers raise a native
        PostGIS error (D-04, no version pre-check performed). When None,
        SQL and params are byte-identical to the pre-grid_size form (D-03).
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
        SQL string and parameter list (``[]`` when ``grid_size`` is None,
        ``[grid_size]`` otherwise).

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
        grid_size=grid_size,
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
    grid_size: float | None = None,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
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
    grid_size : float, optional
        Fixed-precision (snap-rounding) overlay grid size, by default
        None. When set, emits the 3-arg ``ST_Difference(a, b, %s)`` form
        bound to this value (pure passthrough, no range guard, D-02).
        Requires PostGIS >= 3.1 / GEOS >= 3.9 — older servers raise a
        native PostGIS error (D-04, no version pre-check performed). When
        None, SQL and params are byte-identical to the pre-grid_size form
        (D-03).
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
        SQL string and parameter list (``[]`` when ``grid_size`` is None,
        ``[grid_size]`` otherwise).

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
        grid_size=grid_size,
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
    grid_size: float | None = None,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
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
    grid_size : float, optional
        Fixed-precision (snap-rounding) overlay grid size, by default
        None. When set, emits the 3-arg ``ST_Intersection(a, b, %s)``
        form bound to this value (pure passthrough, no range guard, D-02).
        Requires PostGIS >= 3.1 / GEOS >= 3.9 — older servers raise a
        native PostGIS error (D-04, no version pre-check performed). When
        None, SQL and params are byte-identical to the pre-grid_size form
        (D-03).
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
        SQL string and parameter list (``[]`` when ``grid_size`` is None,
        ``[grid_size]`` otherwise).

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
        grid_size=grid_size,
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
) -> tuple[str, list[Any]]:
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
        params: list[Any] = [tolerance]
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
) -> tuple[str, list[Any]]:
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


def build_envelope_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows with the bounding-box geometry of each row.

    Adds an ``envelope`` geometry column via ``ST_Envelope(t.{geom})``
    (D-11) — the per-row minimum bounding rectangle, preserving SRID.
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
        f"SELECT {_cols_str(columns)}, ST_Envelope(t.{geom}) AS envelope "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_point_on_surface_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL selecting rows with a guaranteed-inside representative point.

    Adds a ``point_on_surface`` geometry column via
    ``ST_PointOnSurface(t.{geom})`` (D-05/D-11). Unlike
    :func:`build_centroid_sql`'s scalar ``x``/``y`` shape, this is a real
    ``POINT`` geometry that is guaranteed to lie on the input geometry
    (useful for labels/markers/mapping) and preserves SRID. Valid for
    ``into="gdf"``.

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
        f"SELECT {_cols_str(columns)}, "
        f"ST_PointOnSurface(t.{geom}) AS point_on_surface "
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
) -> tuple[str, list[Any]]:
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
        params: list[Any] = []
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


def _build_agg_geom_sql(
    agg_func: str,
    result_col: str,
    table: str,
    geom: str,
    schema: str,
    *,
    group_by: list[str] | None,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
) -> tuple[str, list[Any]]:
    """Build SQL for a single-column geometry aggregate (ST_Collect / ST_Union agg).

    Shared internal helper backing ``build_collect_geometries_sql`` and
    ``build_union_aggregate_sql``. Mirrors ``_build_binary_geom_sql`` for the
    aggregate shape.

    Parameters
    ----------
    agg_func : str
        PostGIS aggregate function name (e.g. ``"ST_Collect"``).
    result_col : str
        Result column alias (e.g. ``"collected"`` or ``"dissolved"``).
    table : str
        Table to query (aliased ``t``).
    geom : str
        Geometry column name.
    schema : str
        Schema name.
    group_by : list of str or None
        List of validated column names to group by (already normalized from
        ``str | list[str] | None`` at the accessor level). ``None`` means
        whole-table aggregate (one row). Each element must pass
        ``validate_identifiers`` before any f-string interpolation.
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
        If ``table``, ``schema``, ``geom``, or any element of ``group_by``
        is invalid.
    """
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
    if group_by:
        validate_identifiers(*group_by)
    group_cols = [f"t.{col}" for col in group_by] if group_by else []
    select_prefix = ", ".join(group_cols + [f"{agg_func}(t.{geom}) AS {result_col}"])
    sql = f"SELECT {select_prefix} FROM {schema}.{table} AS t"
    group_by_str = ", ".join(group_cols) if group_cols else None
    sql = _append_tail(
        sql, filter, order_by, limit, has_where=False, group_by=group_by_str
    )
    return sql, []


def build_collect_geometries_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL that collects geometries into a collection via ST_Collect (SPAT2-07).

    Produces ``SELECT [group_cols,] ST_Collect(t.{geom}) AS collected
    FROM {schema}.{table} AS t [WHERE ...] [GROUP BY ...] [ORDER BY ...]
    [LIMIT ...]``. No ``%s`` parameters are emitted — all identifiers are
    validated and interpolated.

    NULL geometry inputs are skipped by the PostGIS aggregate; a group (or
    the whole table) with all-NULL inputs yields one row with a NULL
    ``collected`` value. No ``HAVING`` filter is applied (D-07).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default ``"geometry"``.
    schema : str, optional
        Schema name, by default ``"public"``.
    group_by : list of str or None, optional
        Columns to group by. ``None`` (default) = whole-table aggregate
        (exactly one row). Pass the pre-normalized list from the accessor
        (``str`` inputs are normalized to ``[str]`` at the accessor level).
    filter : str, optional
        Raw SQL filter fragment (pre-aggregate WHERE clause).
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
        If ``table``, ``schema``, ``geom``, or any element of ``group_by``
        is invalid.

    Examples
    --------
    Whole-table aggregate::

        sql, params = build_collect_geometries_sql("zones")
        # SELECT ST_Collect(t.geometry) AS collected FROM public.zones AS t

    Grouped by region::

        sql, params = build_collect_geometries_sql("zones", group_by=["region"])
        # SELECT t.region, ST_Collect(t.geometry) AS collected
        # FROM public.zones AS t GROUP BY t.region
    """
    return _build_agg_geom_sql(
        "ST_Collect",
        "collected",
        table,
        geom,
        schema,
        group_by=group_by,
        filter=filter,
        order_by=order_by,
        limit=limit,
    )


def build_union_aggregate_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL that dissolves geometries into a merged boundary via ST_Union (SPAT2-08).

    Produces ``SELECT [group_cols,] ST_Union(t.{geom}) AS dissolved
    FROM {schema}.{table} AS t [WHERE ...] [GROUP BY ...] [ORDER BY ...]
    [LIMIT ...]``. The result column is ``dissolved`` (not ``union_geom``)
    to distinguish this aggregate form from the Phase 42 pairwise
    ``build_union_sql`` (D-06).

    NULL geometry inputs are skipped by the PostGIS aggregate; a group (or
    the whole table) with all-NULL inputs yields one row with a NULL
    ``dissolved`` value. No ``HAVING`` filter is applied (D-07).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default ``"geometry"``.
    schema : str, optional
        Schema name, by default ``"public"``.
    group_by : list of str or None, optional
        Columns to group by. ``None`` (default) = whole-table aggregate
        (exactly one row).
    filter : str, optional
        Raw SQL filter fragment (pre-aggregate WHERE clause).
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
        If ``table``, ``schema``, ``geom``, or any element of ``group_by``
        is invalid.

    Examples
    --------
    Whole-table dissolve::

        sql, params = build_union_aggregate_sql("zones")
        # SELECT ST_Union(t.geometry) AS dissolved FROM public.zones AS t

    Grouped by region::

        sql, params = build_union_aggregate_sql("zones", group_by=["region"])
        # SELECT t.region, ST_Union(t.geometry) AS dissolved
        # FROM public.zones AS t GROUP BY t.region
    """
    return _build_agg_geom_sql(
        "ST_Union",
        "dissolved",
        table,
        geom,
        schema,
        group_by=group_by,
        filter=filter,
        order_by=order_by,
        limit=limit,
    )


def build_extent_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    srid: int = 4326,
    into: str = "rows",
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL that computes the bounding extent of a geometry column via ST_Extent (SPAT2-09).

    ``ST_Extent`` returns a PostgreSQL ``box2d`` type, **not** a PostGIS
    geometry. This builder branches on ``into`` (D-04 exception — the only
    aggregate builder that sees ``into``):

    - ``into="rows"`` (default): casts to text — ``ST_Extent(t.{geom})::text
      AS extent`` — returning the PostgreSQL ``BOX(xmin ymin, xmax ymax)``
      string.
    - ``into="gdf"``: wraps in ``ST_SetSRID(ST_Extent(t.{geom})::geometry,
      {int(srid)})`` to produce a real SRID-tagged polygon geometry that
      GeoPandas can load.

    ``extent`` is **not** in ``_SCALAR_HELPERS`` — ``into="gdf"`` is valid
    via the geometry cast (D-04, Pitfall 3).

    The ``srid`` parameter is consulted **only** on the ``gdf`` branch via
    ``int(srid)`` (injection-safe integer coercion; D-05). It is ignored for
    ``into="rows"``.

    NULL geometry inputs are skipped by the PostGIS aggregate; a group (or
    the whole table) with all-NULL inputs yields one row with a NULL ``extent``
    value. No ``HAVING`` filter is applied (D-07).

    Parameters
    ----------
    table : str
        Table to query (aliased ``t``).
    geom : str, optional
        Geometry column name, by default ``"geometry"``.
    schema : str, optional
        Schema name, by default ``"public"``.
    group_by : list of str or None, optional
        Columns to group by. ``None`` (default) = whole-table aggregate
        (exactly one row). Each column is validated via ``validate_identifiers``
        before any f-string interpolation.
    srid : int, optional
        Spatial Reference Identifier for the ``into="gdf"`` cast, by default
        ``4326``. Interpolated via ``int(srid)`` — a non-integer raises
        ``ValueError``/``TypeError`` before SQL assembly (T-43-03, D-05).
    into : str, optional
        ``"rows"`` (default) or ``"gdf"`` — controls the SQL branch. The
        accessor calls ``_check_into`` *before* delegating here; this
        parameter is received only to select the SQL fragment.
    filter : str, optional
        Raw SQL filter fragment (pre-aggregate WHERE clause).
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
        If ``table``, ``schema``, ``geom``, or any element of ``group_by``
        is invalid (T-43-01).
    ValueError
        If ``into`` is not ``"rows"`` or ``"gdf"`` (validated by the accessor
        before this builder is called).

    Examples
    --------
    Whole-table bounding box as text::

        sql, params = build_extent_sql("zones")
        # SELECT ST_Extent(t.geometry)::text AS extent FROM public.zones AS t

    Grouped bounding box as geometry for GeoPandas::

        sql, params = build_extent_sql("zones", group_by=["region"], into="gdf", srid=4326)
        # SELECT t.region, ST_SetSRID(ST_Extent(t.geometry)::geometry, 4326) AS extent
        # FROM public.zones AS t GROUP BY t.region
    """
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant (T-43-01)
    if group_by:
        validate_identifiers(*group_by)
    group_cols = [f"t.{col}" for col in group_by] if group_by else []
    if into == "gdf":
        agg_expr = f"ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent"
    else:
        agg_expr = f"ST_Extent(t.{geom})::text AS extent"
    select_prefix = ", ".join(group_cols + [agg_expr]) if group_cols else agg_expr
    sql = f"SELECT {select_prefix} FROM {schema}.{table} AS t"
    group_by_str = ", ".join(group_cols) if group_cols else None
    sql = _append_tail(
        sql, filter, order_by, limit, has_where=False, group_by=group_by_str
    )
    return sql, []


#: Helpers whose result set has no geometry column — ``into="gdf"`` is
#: rejected for these (D-02).
_SCALAR_HELPERS = frozenset(
    {
        "area",
        "perimeter",
        "distance",
        "centroid",
        "as_geojson",
        "as_text",
        "length",
        "is_valid",
        "is_valid_reason",
    }
)

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


def _to_named_binds(sql: str, params: list[Any]) -> tuple[str, dict[str, Any]]:
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
    binds: dict[str, Any] = {}
    for i, part in enumerate(parts[1:]):
        out += f":p{i}{part}"
        binds[f"p{i}"] = params[i]
    return out, binds


class SpatialAccessor:
    """Sync spatial helper namespace exposed as ``db.spatial``.

    Each method delegates SQL assembly to the module-level pure builders
    and routes the result per ``into=`` (D-01): ``"rows"`` returns
    ``list[dict[str, Any]]`` via ``Database.execute``; ``"gdf"`` returns a
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
        self, sql: str, params: list[Any], into: str, geometry_column: str
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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

    def _run_mvt(self, sql: str, params: list[Any]) -> bytes:
        """Execute a build_mvt_sql query and return the MVT tile as bytes.

        Always returns ``bytes``: a ``memoryview`` value is coerced to
        ``bytes``, and ``None`` (theoretically possible for a NULL
        aggregate) is mapped to ``b""`` (D-05 empty-tile contract).

        Parameters
        ----------
        sql : str
            SQL from ``build_mvt_sql`` with ``%s`` placeholders.
        params : list
            Parameter list (``[layer_name, extent]``).

        Returns
        -------
        bytes
            MVT tile bytes, or ``b""`` for an empty tile.
        """
        rows = self._db.execute(sql, params)
        val = rows[0]["mvt"]  # "mvt" alias set in build_mvt_sql (Pitfall 5)
        if isinstance(val, memoryview):
            return bytes(val)
        return val if val is not None else b""

    @overload
    def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    def within(
        self,
        left_table: str,
        left_geom: str,
        right_table: str,
        right_geom: str,
        *,
        schema: str = "public",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def within(
        self,
        left_table: str,
        left_geom: str,
        right_table: str,
        right_geom: str,
        *,
        schema: str = "public",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def within(
        self,
        left_table: str,
        left_geom: str,
        right_table: str,
        right_geom: str,
        *,
        schema: str = "public",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
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
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    def overlaps(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def overlaps(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def overlaps(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def overlaps(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows whose geometry overlaps the input geometry.

        Generates ``ST_Overlaps(t.{geom}, <geom_in>)`` (DE-9IM predicate,
        SPAT-F06/D-06). Mechanically mirrors :meth:`intersects` — only the
        ST_* function name differs. No ``where=`` deprecated alias (born
        clean, D-06).

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
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "overlaps")
        sql, params = build_overlaps_sql(
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

    @overload
    def touches(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def touches(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def touches(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def touches(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows whose geometry touches the input geometry.

        Generates ``ST_Touches(t.{geom}, <geom_in>)`` (DE-9IM predicate,
        SPAT-F06/D-06). Mechanically mirrors :meth:`intersects` — only the
        ST_* function name differs. No ``where=`` deprecated alias (born
        clean, D-06).

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
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "touches")
        sql, params = build_touches_sql(
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

    @overload
    def crosses(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def crosses(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def crosses(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def crosses(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows whose geometry crosses the input geometry.

        Generates ``ST_Crosses(t.{geom}, <geom_in>)`` (DE-9IM predicate,
        SPAT-F06/D-06). Mechanically mirrors :meth:`intersects` — only the
        ST_* function name differs. No ``where=`` deprecated alias (born
        clean, D-06).

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
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "crosses")
        sql, params = build_crosses_sql(
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

    @overload
    def disjoint(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def disjoint(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def disjoint(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def disjoint(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows whose geometry is disjoint from the input geometry.

        Generates ``ST_Disjoint(t.{geom}, <geom_in>)`` (DE-9IM predicate,
        SPAT-F06/D-07). Mechanically mirrors :meth:`intersects` — only the
        ST_* function name differs. No ``where=`` deprecated alias (born
        clean, D-06).

        Warnings
        --------
        The ``ref=`` form means "EXISTS a ref row disjoint from t" (true
        as soon as ANY row in the reference table is disjoint from the
        current row — near-always true for a sparse reference table),
        NOT disjoint from all reference rows (D-07).

        ``ST_Disjoint`` does not use indexes
        [postgis.net/docs/ST_Disjoint.html: "This function call does not
        use indexes"]. For large indexed tables, use a negated
        ``NOT ST_Intersects`` predicate instead — e.g. via the ``filter=``
        escape hatch — for an indexable, more performant equivalent
        (D-08).

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
            ``(ref_table, ref_col)`` input geometry — see the ``ref=``
            EXISTS-quantifier warning above (D-07).
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Additional raw SQL filter (D-11).
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
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "disjoint")
        sql, params = build_disjoint_sql(
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

    @overload
    def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        distance: float,
        unit: str = "m",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        distance: float,
        unit: str = "m",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        distance: float,
        unit: str = "m",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
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
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
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
        InvalidIdentifierError
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
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

    @overload
    def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        k: int = 5,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        k: int = 5,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        k: int = 5,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        k: int = 5,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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
    ) -> list[dict[str, Any]]:
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
        InvalidIdentifierError
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
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

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
    ) -> list[dict[str, Any]]:
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
        InvalidIdentifierError
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
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

    def length(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with the length of their geometry (ST_Length).

        Scalar result (``length`` column); ``into="gdf"`` raises
        ``ValueError`` (D-12). ``ST_Length`` returns ``0`` for non-linear
        (areal/point) geometries (D-10). No ``where=`` deprecated alias
        (born clean).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        unit : str, optional
            ``"m"`` (meters) or ``"srid"``, by default "m" (D-10).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-12).
        columns : list of str, optional
            Columns to select alongside the length.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict
            Rows including the computed ``length`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper) or ``unit`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "length")
        sql, params = build_length_sql(
            table,
            geom=geom,
            schema=schema,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

    def is_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with the OGC validity of their geometry (ST_IsValid).

        Scalar result (boolean ``is_valid`` column); ``into="gdf"`` raises
        ``ValueError`` (D-12). No ``where=`` deprecated alias (born clean).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-12).
        columns : list of str, optional
            Columns to select alongside the validity flag.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict
            Rows including the computed boolean ``is_valid`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper).
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "is_valid")
        sql, params = build_is_valid_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

    def is_valid_reason(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with the OGC validity reason of their geometry.

        Scalar result (text ``is_valid_reason`` column, ST_IsValidReason);
        ``into="gdf"`` raises ``ValueError`` (D-12). No ``where=``
        deprecated alias (born clean).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-12).
        columns : list of str, optional
            Columns to select alongside the validity reason.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict
            Rows including the computed text ``is_valid_reason`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper).
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "is_valid_reason")
        sql, params = build_is_valid_reason_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

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
    ) -> list[dict[str, Any]]:
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
        InvalidIdentifierError
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
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

    def as_geojson(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        max_decimal_digits: int = 6,
        include_bbox: bool = False,
        include_crs: bool = False,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with their geometry serialized as a GeoJSON string.

        Scalar result (``geojson`` column containing a JSON string);
        ``into="gdf"`` raises ``ValueError`` per D-08. Callers use
        ``json.loads(row["geojson"])`` when a dict is needed (D-06).

        Born-clean ``filter=`` only — no ``where=`` deprecated alias
        (D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        max_decimal_digits : int, optional
            Maximum decimal digits in coordinates, by default 6 (D-06).
        include_bbox : bool, optional
            Include bounding box in GeoJSON output (options bit 1), by
            default False (D-06).
        include_crs : bool, optional
            Include short CRS name in GeoJSON output (options bit 2), by
            default False (D-06).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-08).
        columns : list of str, optional
            Columns to select alongside the GeoJSON text (D-08).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``geojson`` column (JSON string).

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper, D-08).
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "as_geojson")
        sql, params = build_geojson_sql(
            table,
            geom=geom,
            schema=schema,
            max_decimal_digits=max_decimal_digits,
            include_bbox=include_bbox,
            include_crs=include_crs,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

    def as_text(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        max_decimal_digits: int | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with their geometry serialized as a WKT string.

        Scalar result (``wkt`` column); ``into="gdf"`` raises
        ``ValueError`` per D-08. Defaults to full precision
        (``max_decimal_digits=None``) — WKT is for exact interchange and
        round-trip use; silent truncation would be a data loss (D-07).

        Born-clean ``filter=`` only — no ``where=`` deprecated alias
        (D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        max_decimal_digits : int or None, optional
            Maximum decimal digits in coordinates, by default ``None``
            (full precision, one-arg ``ST_AsText``). When set, two-arg
            form is used (D-07); the two-arg form requires PostGIS >= 3.1.
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-08).
        columns : list of str, optional
            Columns to select alongside the WKT text (D-08).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``wkt`` column (WKT string).

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper, D-08).
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "as_text")
        sql, params = build_text_sql(
            table,
            geom=geom,
            schema=schema,
            max_decimal_digits=max_decimal_digits,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", self._run(sql, params, into, geom))

    def as_mvt(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tile_z: int,
        tile_x: int,
        tile_y: int,
        layer_name: str = "default",
        extent: int = 4096,
        columns: list[str] | None = None,
        feature_id_column: str | None = None,
        srid: int | None = None,
        filter: str | None = None,
    ) -> bytes:
        """Generate a Mapbox Vector Tile (MVT) for a slippy-map tile coordinate.

        Returns the MVT tile as ``bytes`` (protobuf-encoded). An empty tile
        (all geometry clips outside the tile envelope) returns ``b""`` — never
        ``None`` or ``memoryview`` (D-05).

        Born-clean ``filter=`` only — no deprecated ``where=`` alias (D-09).
        No ``into=`` parameter (this method returns ``bytes``, not rows or a
        GeoDataFrame, and is NOT in ``_SCALAR_HELPERS``).

        The enforced pipeline (D-03)::

            ST_Transform(t.geom, 3857)          # → Web Mercator
            → ST_AsMVTGeom(…, ST_TileEnvelope(z, x, y), extent)  # clip+scale
            → ST_AsMVT(q.*, layer_name, extent, 'geom_mvt')       # encode

        SRID-0 rescue (D-04): if the geometry column stores SRID 0
        (untagged), pass ``srid=<source_srid>`` to inject
        ``ST_SetSRID`` before the transform::

            db.spatial.as_mvt("points", tile_z=10, tile_x=512, tile_y=400, srid=4326)

        ``feature_id_column`` must reference an **integer-type** column —
        PostGIS enforces this (MVT spec requires 64-bit integer feature IDs).

        Requires PostGIS ≥ 3.0 (``ST_TileEnvelope``, five-arg ``ST_AsMVT``).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default ``"geometry"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        tile_z : int
            Tile zoom level. Required keyword-only (D-02).
        tile_x : int
            Tile column index. Required keyword-only (D-02).
        tile_y : int
            Tile row index. Required keyword-only (D-02).
        layer_name : str, optional
            MVT layer name, by default ``"default"``.
        extent : int, optional
            MVT tile extent in pixel units, by default ``4096``.
        columns : list of str, optional
            Extra columns to include as MVT feature properties.
        feature_id_column : str or None, optional
            Integer-typed column to use as MVT feature ID (PostGIS
            requirement). ``None`` (default) = no feature ID.
        srid : int or None, optional
            Source SRID override for SRID-0 geometry columns (D-04).
        filter : str, optional
            Raw SQL fragment appended as ``WHERE {filter}`` inside the
            inner subquery (T-44-02c documented escape hatch).

        Returns
        -------
        bytes
            MVT protobuf tile bytes, or ``b""`` for an empty tile (D-05).

        Raises
        ------
        InvalidIdentifierError
            If any identifier (table, schema, geom, columns, or
            feature_id_column) is invalid (T-44-02).
        """
        sql, params = build_mvt_sql(
            table,
            geom=geom,
            schema=schema,
            tile_z=tile_z,
            tile_x=tile_x,
            tile_y=tile_y,
            layer_name=layer_name,
            extent=extent,
            columns=columns,
            feature_id_column=feature_id_column,
            srid=srid,
            filter=filter,
        )
        return self._run_mvt(sql, params)

    @overload
    def buffer(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        distance: float,
        unit: str = "m",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def buffer(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        distance: float,
        unit: str = "m",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def buffer(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        distance: float,
        unit: str = "m",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
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
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    def transform(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        to_srid: int,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def transform(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        to_srid: int,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def transform(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        to_srid: int,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
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
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        grid_size : float, optional
            Fixed-precision (snap-rounding) overlay grid size, by default
            None. When set, emits the 3-arg ``ST_Union(a, b, %s)`` form
            (pure passthrough, no range guard, D-02). Requires PostGIS
            >= 3.1 / GEOS >= 3.9 — older servers raise a native PostGIS
            error (D-04, no version pre-check performed).
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
            grid_size=grid_size,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "union_geom")

    @overload
    def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        grid_size : float, optional
            Fixed-precision (snap-rounding) overlay grid size, by default
            None. When set, emits the 3-arg ``ST_Difference(a, b, %s)``
            form (pure passthrough, no range guard, D-02). Requires
            PostGIS >= 3.1 / GEOS >= 3.9 — older servers raise a native
            PostGIS error (D-04, no version pre-check performed).
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
            grid_size=grid_size,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "difference")

    @overload
    def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        grid_size : float, optional
            Fixed-precision (snap-rounding) overlay grid size, by default
            None. When set, emits the 3-arg ``ST_Intersection(a, b, %s)``
            form (pure passthrough, no range guard, D-02). Requires
            PostGIS >= 3.1 / GEOS >= 3.9 — older servers raise a native
            PostGIS error (D-04, no version pre-check performed).
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
            grid_size=grid_size,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "intersection")

    @overload
    def simplify(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tolerance: float,
        preserve_topology: bool = True,
        preserve_collapsed: bool = False,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def simplify(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tolerance: float,
        preserve_topology: bool = True,
        preserve_collapsed: bool = False,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def simplify(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tolerance: float,
        preserve_topology: bool = True,
        preserve_collapsed: bool = False,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def simplify(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tolerance: float,
        preserve_topology: bool = True,
        preserve_collapsed: bool = False,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with their geometry simplified (ST_SimplifyPreserveTopology default).

        Adds a ``simplified`` geometry column (D-01). The default uses
        ``ST_SimplifyPreserveTopology`` which guarantees a non-NULL result.
        Pass ``preserve_topology=False`` to use ``ST_Simplify`` — that variant
        may return ``NULL`` when the geometry collapses below ``tolerance`` (D-07).
        Valid for ``into="gdf"``. No ``where=`` deprecated alias (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        tolerance : float
            Simplification tolerance (required keyword-only, D-05).
        preserve_topology : bool, optional
            If ``True`` (default) use ST_SimplifyPreserveTopology (no NULL
            collapse). If ``False`` use ST_Simplify (can return NULL).
        preserve_collapsed : bool, optional
            Only consulted when ``preserve_topology=False``. Setting
            ``preserve_collapsed=True`` while ``preserve_topology=True``
            raises ``ValueError`` (D-05).
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
            Rows including the ``simplified`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid, or if ``preserve_collapsed=True`` and
            ``preserve_topology=True`` (contradictory, D-05).
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "simplify")
        sql, params = build_simplify_sql(
            table,
            geom=geom,
            schema=schema,
            tolerance=tolerance,
            preserve_topology=preserve_topology,
            preserve_collapsed=preserve_collapsed,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "simplified")

    @overload
    def convex_hull(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def convex_hull(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def convex_hull(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def convex_hull(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with the convex hull of each geometry (ST_ConvexHull).

        Adds a ``convex_hull`` geometry column (D-01). Returns ``NULL`` for
        empty geometries (pass-through, D-07). Valid for ``into="gdf"``. No
        ``where=`` deprecated alias (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
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
            Rows including the ``convex_hull`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "convex_hull")
        sql, params = build_convex_hull_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "convex_hull")

    @overload
    def envelope(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def envelope(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def envelope(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def envelope(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with the bounding-box geometry of each row (ST_Envelope).

        Adds an ``envelope`` geometry column (D-11) — the per-row minimum
        bounding rectangle, preserving SRID. Valid for ``into="gdf"``. No
        ``where=`` deprecated alias (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
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
            Rows including the ``envelope`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "envelope")
        sql, params = build_envelope_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "envelope")

    @overload
    def point_on_surface(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def point_on_surface(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def point_on_surface(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def point_on_surface(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with a guaranteed-inside representative point (ST_PointOnSurface).

        Adds a ``point_on_surface`` geometry column (D-05/D-11). Unlike
        :meth:`centroid`'s scalar ``x``/``y`` shape, this is a real
        ``POINT`` geometry guaranteed to lie on the input geometry (useful
        for labels/markers/mapping), preserving SRID. Valid for
        ``into="gdf"``. No ``where=`` deprecated alias (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
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
            Rows including the ``point_on_surface`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "point_on_surface")
        sql, params = build_point_on_surface_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "point_on_surface")

    @overload
    def make_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        method: str | None = None,
        keep_collapsed: bool | None = None,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def make_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        method: str | None = None,
        keep_collapsed: bool | None = None,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def make_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        method: str | None = None,
        keep_collapsed: bool | None = None,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def make_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        method: str | None = None,
        keep_collapsed: bool | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with their geometry repaired via ST_MakeValid.

        Adds a ``made_valid`` geometry column (D-01). Invalid geometries
        (e.g. bowtie self-intersections) are repaired — the output type may
        change (``POLYGON`` → ``MULTIPOLYGON`` or ``GEOMETRYCOLLECTION``,
        D-07). Already-valid geometries are returned unchanged. Valid for
        ``into="gdf"``. No ``where=`` deprecated alias (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        method : {None, "linework", "structure"}, optional
            Repair algorithm, by default ``None`` (PostGIS default).
            ``"structure"`` requires PostGIS ≥ 3.2 / GEOS ≥ 3.10 (D-04);
            on older servers, PostGIS raises a native error.
        keep_collapsed : bool or None, optional
            Only valid when ``method="structure"``. Controls whether
            collapsed geometries are kept (``True``/``False``) or use the
            PostGIS default (``None``). Raises ``ValueError`` when set with
            any other method (D-03).
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
            Rows including the ``made_valid`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid, ``method`` is not in the allowed set
            (D-02), or ``keep_collapsed`` is set with a non-structure method
            (D-03).
        InvalidIdentifierError
            If any identifier is invalid.
        """
        _check_into(into, "make_valid")
        sql, params = build_make_valid_sql(
            table,
            geom=geom,
            schema=schema,
            method=method,
            keep_collapsed=keep_collapsed,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "made_valid")

    @overload
    def collect_geometries(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: Literal["rows"] = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def collect_geometries(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: Literal["gdf"],
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def collect_geometries(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: str,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def collect_geometries(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: str = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Collect geometries into a geometry collection per group via ST_Collect (SPAT2-07).

        Adds a ``collected`` geometry column (D-06). The result is a
        ``GEOMETRYCOLLECTION`` (or the input type for single-row groups).

        NULL geometry inputs are skipped by the PostGIS aggregate; a group (or
        the whole table) with all-NULL inputs yields one row with a NULL
        ``collected`` value. No ``HAVING`` filter is applied (D-07).

        Valid for ``into="gdf"``. No ``where=`` deprecated alias (born clean,
        D-09). ``group_by`` is keyword-only (D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default ``"geometry"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        group_by : str or list of str or None, optional
            Column(s) to group by. A bare ``str`` is normalized to
            ``[str]`` (D-01). Pass ``None`` (default) for a whole-table
            aggregate. Raises ``ValueError`` for an empty list.
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default ``"rows"``.
        filter : str, optional
            Raw SQL filter fragment (pre-aggregate WHERE clause).
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows or GeoDataFrame including the ``collected`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid or ``group_by`` is an empty list.
        InvalidIdentifierError
            If any identifier (``table``, ``schema``, ``geom``, or
            ``group_by`` columns) is invalid.

        Examples
        --------
        Whole-table collection::

            rows = db.spatial.collect_geometries("zones")

        Grouped by region::

            rows = db.spatial.collect_geometries("zones", group_by="region")
        """
        if isinstance(group_by, str):
            group_by = [group_by]
        if group_by == []:
            raise ValueError(
                "group_by cannot be an empty list; pass None for a whole-table aggregate"
            )
        _check_into(into, "collect_geometries")
        sql, params = build_collect_geometries_sql(
            table,
            geom=geom,
            schema=schema,
            group_by=group_by,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "collected")

    @overload
    def union_aggregate(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: Literal["rows"] = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def union_aggregate(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: Literal["gdf"],
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def union_aggregate(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: str,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def union_aggregate(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: str = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Dissolve geometries into a merged boundary per group via ST_Union (SPAT2-08).

        Adds a ``dissolved`` geometry column (D-06). Unlike the pairwise
        ``union`` method (Phase 42), this form aggregates all geometries in
        a group into a single merged result.

        NULL geometry inputs are skipped by the PostGIS aggregate; a group (or
        the whole table) with all-NULL inputs yields one row with a NULL
        ``dissolved`` value. No ``HAVING`` filter is applied (D-07).

        Valid for ``into="gdf"``. No ``where=`` deprecated alias (born clean,
        D-09). ``group_by`` is keyword-only (D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default ``"geometry"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        group_by : str or list of str or None, optional
            Column(s) to group by. A bare ``str`` is normalized to
            ``[str]`` (D-01). Pass ``None`` (default) for a whole-table
            aggregate. Raises ``ValueError`` for an empty list.
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default ``"rows"``.
        filter : str, optional
            Raw SQL filter fragment (pre-aggregate WHERE clause).
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows or GeoDataFrame including the ``dissolved`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid or ``group_by`` is an empty list.
        InvalidIdentifierError
            If any identifier (``table``, ``schema``, ``geom``, or
            ``group_by`` columns) is invalid.

        Examples
        --------
        Whole-table dissolve::

            rows = db.spatial.union_aggregate("zones")

        Grouped by region::

            gdf = db.spatial.union_aggregate("zones", group_by="region", into="gdf")
        """
        if isinstance(group_by, str):
            group_by = [group_by]
        if group_by == []:
            raise ValueError(
                "group_by cannot be an empty list; pass None for a whole-table aggregate"
            )
        _check_into(into, "union_aggregate")
        sql, params = build_union_aggregate_sql(
            table,
            geom=geom,
            schema=schema,
            group_by=group_by,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "dissolved")

    @overload
    def extent(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    def extent(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    def extent(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        srid: int = 4326,
        into: str,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    def extent(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Compute the bounding extent of a geometry column via ST_Extent (SPAT2-09).

        ``ST_Extent`` returns a PostgreSQL ``box2d`` type. This method branches
        on ``into`` (D-04 exception — the only aggregate method that passes
        ``into`` to the builder):

        - ``into="rows"`` (default): returns the ``BOX(xmin ymin, xmax ymax)``
          string via ``ST_Extent(t.{geom})::text AS extent``.
        - ``into="gdf"``: returns a real SRID-tagged polygon geometry via
          ``ST_SetSRID(ST_Extent(t.{geom})::geometry, {srid})``, loadable by
          GeoPandas.

        The ``srid`` parameter is consulted **only** on the ``gdf`` branch via
        ``int(srid)`` (injection-safe; D-05). It is ignored for ``into="rows"``.

        ``extent`` is **not** in ``_SCALAR_HELPERS`` — ``into="gdf"`` is valid
        via the geometry cast (D-04, Pitfall 3).

        NULL geometry inputs are skipped by the PostGIS aggregate; a group (or
        the whole table) with all-NULL inputs yields one row with a NULL
        ``extent`` value. No ``HAVING`` filter is applied (D-07).

        Valid for ``into="gdf"``. No ``where=`` deprecated alias (born clean,
        D-09). ``group_by`` and ``srid`` are keyword-only (D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default ``"geometry"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        group_by : str or list of str or None, optional
            Column(s) to group by. A bare ``str`` is normalized to
            ``[str]`` (D-01). Pass ``None`` (default) for a whole-table
            aggregate. Raises ``ValueError`` for an empty list.
        srid : int, optional
            SRID for the ``into="gdf"`` cast, by default ``4326``.
            Ignored for ``into="rows"`` (D-05).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default ``"rows"``.
        filter : str, optional
            Raw SQL filter fragment (pre-aggregate WHERE clause).
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            For ``into="rows"``: list of dicts with an ``extent`` key
            containing the ``BOX(...)`` text string (or ``None`` for
            all-NULL groups). For ``into="gdf"``: GeoDataFrame with an
            ``extent`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid or ``group_by`` is an empty list.
        InvalidIdentifierError
            If any identifier (``table``, ``schema``, ``geom``, or
            ``group_by`` columns) is invalid.

        Examples
        --------
        Whole-table bounding box as text::

            rows = db.spatial.extent("zones")
            # [{"extent": "BOX(0 0, 10 10)"}]

        Grouped bounding box as a GeoDataFrame::

            gdf = db.spatial.extent("zones", group_by="region", into="gdf", srid=4326)
        """
        if isinstance(group_by, str):
            group_by = [group_by]
        if group_by == []:
            raise ValueError(
                "group_by cannot be an empty list; pass None for a whole-table aggregate"
            )
        _check_into(into, "extent")
        sql, params = build_extent_sql(
            table,
            geom=geom,
            schema=schema,
            group_by=group_by,
            srid=srid,
            into=into,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, "extent")

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

    def list_geometry_columns(
        self, *, schema: str | None = None
    ) -> list[dict[str, Any]]:
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
        self, sql: str, params: list[Any], into: str, geometry_column: str
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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

    async def _arun_mvt(self, sql: str, params: list[Any]) -> bytes:
        """Execute a build_mvt_sql query asynchronously and return MVT bytes.

        Always returns ``bytes``: a ``memoryview`` value is coerced to
        ``bytes``, and ``None`` (theoretically possible for a NULL
        aggregate) is mapped to ``b""`` (D-05 empty-tile contract).

        Parameters
        ----------
        sql : str
            SQL from ``build_mvt_sql`` with ``%s`` placeholders.
        params : list
            Parameter list (``[layer_name, extent]``).

        Returns
        -------
        bytes
            MVT tile bytes, or ``b""`` for an empty tile.
        """
        rows = await self._db.execute(sql, params)
        val = rows[0]["mvt"]  # "mvt" alias set in build_mvt_sql (Pitfall 5)
        if isinstance(val, memoryview):
            return bytes(val)
        return val if val is not None else b""

    @overload
    async def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def contains(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    async def within(
        self,
        left_table: str,
        left_geom: str,
        right_table: str,
        right_geom: str,
        *,
        schema: str = "public",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def within(
        self,
        left_table: str,
        left_geom: str,
        right_table: str,
        right_geom: str,
        *,
        schema: str = "public",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def within(
        self,
        left_table: str,
        left_geom: str,
        right_table: str,
        right_geom: str,
        *,
        schema: str = "public",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
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
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    async def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def intersects(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    async def overlaps(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def overlaps(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def overlaps(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def overlaps(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows whose geometry overlaps the input geometry (async).

        Async mirror of :meth:`SpatialAccessor.overlaps`. Generates
        ``ST_Overlaps(t.{geom}, <geom_in>)`` (DE-9IM predicate,
        SPAT-F06/D-06). No ``where=`` deprecated alias (born clean, D-06).

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
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "overlaps")
        sql, params = build_overlaps_sql(
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

    @overload
    async def touches(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def touches(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def touches(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def touches(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows whose geometry touches the input geometry (async).

        Async mirror of :meth:`SpatialAccessor.touches`. Generates
        ``ST_Touches(t.{geom}, <geom_in>)`` (DE-9IM predicate,
        SPAT-F06/D-06). No ``where=`` deprecated alias (born clean, D-06).

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
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "touches")
        sql, params = build_touches_sql(
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

    @overload
    async def crosses(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def crosses(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def crosses(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def crosses(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows whose geometry crosses the input geometry (async).

        Async mirror of :meth:`SpatialAccessor.crosses`. Generates
        ``ST_Crosses(t.{geom}, <geom_in>)`` (DE-9IM predicate,
        SPAT-F06/D-06). No ``where=`` deprecated alias (born clean, D-06).

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
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "crosses")
        sql, params = build_crosses_sql(
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

    @overload
    async def disjoint(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def disjoint(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def disjoint(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def disjoint(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows whose geometry is disjoint from the input (async).

        Async mirror of :meth:`SpatialAccessor.disjoint`. Generates
        ``ST_Disjoint(t.{geom}, <geom_in>)`` (DE-9IM predicate,
        SPAT-F06/D-07). No ``where=`` deprecated alias (born clean,
        D-06).

        Warnings
        --------
        The ``ref=`` form means "EXISTS a ref row disjoint from t" (true
        as soon as ANY row in the reference table is disjoint from the
        current row — near-always true for a sparse reference table),
        NOT disjoint from all reference rows (D-07).

        ``ST_Disjoint`` does not use indexes
        [postgis.net/docs/ST_Disjoint.html: "This function call does not
        use indexes"]. For large indexed tables, use a negated
        ``NOT ST_Intersects`` predicate instead — e.g. via the ``filter=``
        escape hatch — for an indexable, more performant equivalent
        (D-08).

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
            ``(ref_table, ref_col)`` input geometry — see the ``ref=``
            EXISTS-quantifier warning above (D-07).
        srid : int, optional
            SRID of the input geometry, by default 4326 (D-07).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default "rows" (D-01).
        columns : list of str, optional
            Columns to select, by default all (D-03).
        filter : str, optional
            Additional raw SQL filter (D-11).
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
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "disjoint")
        sql, params = build_disjoint_sql(
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

    @overload
    async def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        distance: float,
        unit: str = "m",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        distance: float,
        unit: str = "m",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        ref: tuple[str, str] | None = None,
        srid: int = 4326,
        distance: float,
        unit: str = "m",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def dwithin(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
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
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
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
        InvalidIdentifierError
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
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

    @overload
    async def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        k: int = 5,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        k: int = 5,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        k: int = 5,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def nearest(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        point: tuple[float, float] | None = None,
        wkt: str | None = None,
        geojson: dict[str, Any] | None = None,
        srid: int = 4326,
        k: int = 5,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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
    ) -> list[dict[str, Any]]:
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
        InvalidIdentifierError
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
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

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
    ) -> list[dict[str, Any]]:
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
        InvalidIdentifierError
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
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

    async def length(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        unit: str = "m",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with the length of their geometry (async, ST_Length).

        Scalar result (``length`` column); ``into="gdf"`` raises
        ``ValueError`` (D-12). ``ST_Length`` returns ``0`` for non-linear
        (areal/point) geometries (D-10). No ``where=`` deprecated alias
        (born clean).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        unit : str, optional
            ``"m"`` (meters) or ``"srid"``, by default "m" (D-10).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-12).
        columns : list of str, optional
            Columns to select alongside the length.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict
            Rows including the computed ``length`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper) or ``unit`` is invalid.
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "length")
        sql, params = build_length_sql(
            table,
            geom=geom,
            schema=schema,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

    async def is_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with the OGC validity of their geometry (async, ST_IsValid).

        Scalar result (boolean ``is_valid`` column); ``into="gdf"`` raises
        ``ValueError`` (D-12). No ``where=`` deprecated alias (born clean).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-12).
        columns : list of str, optional
            Columns to select alongside the validity flag.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict
            Rows including the computed boolean ``is_valid`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper).
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "is_valid")
        sql, params = build_is_valid_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

    async def is_valid_reason(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with the OGC validity reason of their geometry (async).

        Scalar result (text ``is_valid_reason`` column, ST_IsValidReason);
        ``into="gdf"`` raises ``ValueError`` (D-12). No ``where=``
        deprecated alias (born clean).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-12).
        columns : list of str, optional
            Columns to select alongside the validity reason.
        filter : str, optional
            Raw SQL filter fragment.
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict
            Rows including the computed text ``is_valid_reason`` column.

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper).
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "is_valid_reason")
        sql, params = build_is_valid_reason_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

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
    ) -> list[dict[str, Any]]:
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
        InvalidIdentifierError
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
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

    async def as_geojson(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        max_decimal_digits: int = 6,
        include_bbox: bool = False,
        include_crs: bool = False,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with their geometry serialized as a GeoJSON string (async).

        Scalar result (``geojson`` column containing a JSON string);
        ``into="gdf"`` raises ``ValueError`` per D-08. Callers use
        ``json.loads(row["geojson"])`` when a dict is needed (D-06).

        Born-clean ``filter=`` only — no ``where=`` deprecated alias
        (D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        max_decimal_digits : int, optional
            Maximum decimal digits in coordinates, by default 6 (D-06).
        include_bbox : bool, optional
            Include bounding box in GeoJSON output (options bit 1), by
            default False (D-06).
        include_crs : bool, optional
            Include short CRS name in GeoJSON output (options bit 2), by
            default False (D-06).
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-08).
        columns : list of str, optional
            Columns to select alongside the GeoJSON text (D-08).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``geojson`` column (JSON string).

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper, D-08).
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "as_geojson")
        sql, params = build_geojson_sql(
            table,
            geom=geom,
            schema=schema,
            max_decimal_digits=max_decimal_digits,
            include_bbox=include_bbox,
            include_crs=include_crs,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

    async def as_text(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        max_decimal_digits: int | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows with their geometry serialized as a WKT string (async).

        Scalar result (``wkt`` column); ``into="gdf"`` raises
        ``ValueError`` per D-08. Defaults to full precision
        (``max_decimal_digits=None``) — WKT is for exact interchange and
        round-trip use; silent truncation would be a data loss (D-07).

        Born-clean ``filter=`` only — no ``where=`` deprecated alias
        (D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        max_decimal_digits : int or None, optional
            Maximum decimal digits in coordinates, by default ``None``
            (full precision, one-arg ``ST_AsText``). When set, two-arg
            form is used (D-07); the two-arg form requires PostGIS >= 3.1.
        into : str, optional
            Only ``"rows"`` is valid for this helper (D-08).
        columns : list of str, optional
            Columns to select alongside the WKT text (D-08).
        filter : str, optional
            Raw SQL filter fragment (D-11).
        order_by : str, optional
            ORDER BY clause body (D-12).
        limit : int, optional
            LIMIT value (D-12).

        Returns
        -------
        list of dict
            Rows including the computed ``wkt`` column (WKT string).

        Raises
        ------
        ValueError
            If ``into="gdf"`` (scalar helper, D-08).
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "as_text")
        sql, params = build_text_sql(
            table,
            geom=geom,
            schema=schema,
            max_decimal_digits=max_decimal_digits,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        # Scalar helper: _check_into() above already rejected into="gdf",
        # so the runtime result is always list[dict[str, Any]] (D-03).
        return cast("list[dict[str, Any]]", await self._run(sql, params, into, geom))

    async def as_mvt(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tile_z: int,
        tile_x: int,
        tile_y: int,
        layer_name: str = "default",
        extent: int = 4096,
        columns: list[str] | None = None,
        feature_id_column: str | None = None,
        srid: int | None = None,
        filter: str | None = None,
    ) -> bytes:
        """Generate a Mapbox Vector Tile (MVT) for a slippy-map tile coordinate (async).

        Returns the MVT tile as ``bytes`` (protobuf-encoded). An empty tile
        (all geometry clips outside the tile envelope) returns ``b""`` — never
        ``None`` or ``memoryview`` (D-05).

        Born-clean ``filter=`` only — no deprecated ``where=`` alias (D-09).
        No ``into=`` parameter (this method returns ``bytes``, not rows or a
        GeoDataFrame, and is NOT in ``_SCALAR_HELPERS``).

        The enforced pipeline (D-03)::

            ST_Transform(t.geom, 3857)
            → ST_AsMVTGeom(…, ST_TileEnvelope(z, x, y), extent)
            → ST_AsMVT(q.*, layer_name, extent, 'geom_mvt')

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default ``"geometry"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        tile_z : int
            Tile zoom level. Required keyword-only (D-02).
        tile_x : int
            Tile column index. Required keyword-only (D-02).
        tile_y : int
            Tile row index. Required keyword-only (D-02).
        layer_name : str, optional
            MVT layer name, by default ``"default"``.
        extent : int, optional
            MVT tile extent in pixel units, by default ``4096``.
        columns : list of str, optional
            Extra columns to include as MVT feature properties.
        feature_id_column : str or None, optional
            Integer-typed column to use as MVT feature ID. ``None``
            (default) = no feature ID.
        srid : int or None, optional
            Source SRID override for SRID-0 geometry columns (D-04).
        filter : str, optional
            Raw SQL fragment appended as ``WHERE {filter}`` inside the
            inner subquery (T-44-02c documented escape hatch).

        Returns
        -------
        bytes
            MVT protobuf tile bytes, or ``b""`` for an empty tile (D-05).

        Raises
        ------
        InvalidIdentifierError
            If any identifier is invalid (T-44-02).
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        sql, params = build_mvt_sql(
            table,
            geom=geom,
            schema=schema,
            tile_z=tile_z,
            tile_x=tile_x,
            tile_y=tile_y,
            layer_name=layer_name,
            extent=extent,
            columns=columns,
            feature_id_column=feature_id_column,
            srid=srid,
            filter=filter,
        )
        return await self._arun_mvt(sql, params)

    @overload
    async def buffer(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        distance: float,
        unit: str = "m",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def buffer(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        distance: float,
        unit: str = "m",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def buffer(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        distance: float,
        unit: str = "m",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
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
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    async def transform(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        to_srid: int,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def transform(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        to_srid: int,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def transform(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        to_srid: int,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
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
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        InvalidIdentifierError
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

    @overload
    async def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def union(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        grid_size : float, optional
            Fixed-precision (snap-rounding) overlay grid size, by default
            None. When set, emits the 3-arg ``ST_Union(a, b, %s)`` form
            (pure passthrough, no range guard, D-02). Requires PostGIS
            >= 3.1 / GEOS >= 3.9 — older servers raise a native PostGIS
            error (D-04, no version pre-check performed).
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
            grid_size=grid_size,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "union_geom")

    @overload
    async def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def difference(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        grid_size : float, optional
            Fixed-precision (snap-rounding) overlay grid size, by default
            None. When set, emits the 3-arg ``ST_Difference(a, b, %s)``
            form (pure passthrough, no range guard, D-02). Requires
            PostGIS >= 3.1 / GEOS >= 3.9 — older servers raise a native
            PostGIS error (D-04, no version pre-check performed).
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
            grid_size=grid_size,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "difference")

    @overload
    async def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def intersection(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        other_geom: str,
        grid_size: float | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
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
        grid_size : float, optional
            Fixed-precision (snap-rounding) overlay grid size, by default
            None. When set, emits the 3-arg ``ST_Intersection(a, b, %s)``
            form (pure passthrough, no range guard, D-02). Requires
            PostGIS >= 3.1 / GEOS >= 3.9 — older servers raise a native
            PostGIS error (D-04, no version pre-check performed).
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
            grid_size=grid_size,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "intersection")

    @overload
    async def simplify(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tolerance: float,
        preserve_topology: bool = True,
        preserve_collapsed: bool = False,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def simplify(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tolerance: float,
        preserve_topology: bool = True,
        preserve_collapsed: bool = False,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def simplify(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tolerance: float,
        preserve_topology: bool = True,
        preserve_collapsed: bool = False,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def simplify(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tolerance: float,
        preserve_topology: bool = True,
        preserve_collapsed: bool = False,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with their geometry simplified — async (ST_SimplifyPreserveTopology default).

        Async mirror of :meth:`SpatialAccessor.simplify`. Adds a
        ``simplified`` geometry column (D-01). The default uses
        ``ST_SimplifyPreserveTopology`` which guarantees a non-NULL result.
        Pass ``preserve_topology=False`` to use ``ST_Simplify`` — that
        variant may return ``NULL`` when the geometry collapses (D-07).
        Valid for ``into="gdf"``. No ``where=`` deprecated alias (born clean,
        D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        tolerance : float
            Simplification tolerance (required keyword-only, D-05).
        preserve_topology : bool, optional
            If ``True`` (default) use ST_SimplifyPreserveTopology. If
            ``False`` use ST_Simplify (can return NULL).
        preserve_collapsed : bool, optional
            Only consulted when ``preserve_topology=False`` (D-05).
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
            Rows including the ``simplified`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid, or ``preserve_collapsed=True`` and
            ``preserve_topology=True`` (contradictory, D-05).
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "simplify")
        sql, params = build_simplify_sql(
            table,
            geom=geom,
            schema=schema,
            tolerance=tolerance,
            preserve_topology=preserve_topology,
            preserve_collapsed=preserve_collapsed,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "simplified")

    @overload
    async def convex_hull(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def convex_hull(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def convex_hull(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def convex_hull(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with the convex hull of each geometry — async (ST_ConvexHull).

        Async mirror of :meth:`SpatialAccessor.convex_hull`. Adds a
        ``convex_hull`` geometry column (D-01). Valid for ``into="gdf"``.
        No ``where=`` deprecated alias (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
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
            Rows including the ``convex_hull`` geometry column.

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
        _check_into(into, "convex_hull")
        sql, params = build_convex_hull_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "convex_hull")

    @overload
    async def envelope(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def envelope(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def envelope(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def envelope(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with the bounding-box geometry of each row — async (ST_Envelope).

        Async mirror of :meth:`SpatialAccessor.envelope`. Adds an
        ``envelope`` geometry column (D-11) — the per-row minimum bounding
        rectangle, preserving SRID. Valid for ``into="gdf"``. No ``where=``
        deprecated alias (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
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
            Rows including the ``envelope`` geometry column.

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
        _check_into(into, "envelope")
        sql, params = build_envelope_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "envelope")

    @overload
    async def point_on_surface(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def point_on_surface(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def point_on_surface(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def point_on_surface(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with a guaranteed-inside representative point — async (ST_PointOnSurface).

        Async mirror of :meth:`SpatialAccessor.point_on_surface`. Unlike
        :meth:`centroid`'s scalar ``x``/``y`` shape, this is a real
        ``POINT`` geometry guaranteed to lie on the input geometry (useful
        for labels/markers/mapping), preserving SRID. Valid for
        ``into="gdf"``. No ``where=`` deprecated alias (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
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
            Rows including the ``point_on_surface`` geometry column.

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
        _check_into(into, "point_on_surface")
        sql, params = build_point_on_surface_sql(
            table,
            geom=geom,
            schema=schema,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "point_on_surface")

    @overload
    async def make_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        method: str | None = None,
        keep_collapsed: bool | None = None,
        into: Literal["rows"] = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def make_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        method: str | None = None,
        keep_collapsed: bool | None = None,
        into: Literal["gdf"],
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def make_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        method: str | None = None,
        keep_collapsed: bool | None = None,
        into: str,
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def make_valid(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        method: str | None = None,
        keep_collapsed: bool | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Select rows with their geometry repaired via ST_MakeValid — async.

        Async mirror of :meth:`SpatialAccessor.make_valid`. Adds a
        ``made_valid`` geometry column (D-01). The output type may change
        (D-07). Valid for ``into="gdf"``. No ``where=`` deprecated alias
        (born clean, D-10).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        method : {None, "linework", "structure"}, optional
            Repair algorithm, by default ``None``. ``"structure"`` requires
            PostGIS ≥ 3.2 / GEOS ≥ 3.10 (D-04).
        keep_collapsed : bool or None, optional
            Only valid when ``method="structure"`` (D-03).
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
            Rows including the ``made_valid`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid, ``method`` not in allowed set (D-02),
            or ``keep_collapsed`` set with non-structure method (D-03).
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        _check_into(into, "make_valid")
        sql, params = build_make_valid_sql(
            table,
            geom=geom,
            schema=schema,
            method=method,
            keep_collapsed=keep_collapsed,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "made_valid")

    @overload
    async def collect_geometries(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: Literal["rows"] = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def collect_geometries(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: Literal["gdf"],
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def collect_geometries(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: str,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def collect_geometries(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: str = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Collect geometries into a geometry collection per group — async (ST_Collect).

        Async mirror of :meth:`SpatialAccessor.collect_geometries`. Adds a
        ``collected`` geometry column (D-06). Valid for ``into="gdf"``.
        No ``where=`` deprecated alias (born clean, D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default ``"geometry"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        group_by : str or list of str or None, optional
            Column(s) to group by. A bare ``str`` is normalized to
            ``[str]`` (D-01). Pass ``None`` for a whole-table aggregate.
            Raises ``ValueError`` for an empty list.
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default ``"rows"``.
        filter : str, optional
            Raw SQL filter fragment (pre-aggregate WHERE clause).
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows or GeoDataFrame including the ``collected`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid or ``group_by`` is an empty list.
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        if isinstance(group_by, str):
            group_by = [group_by]
        if group_by == []:
            raise ValueError(
                "group_by cannot be an empty list; pass None for a whole-table aggregate"
            )
        _check_into(into, "collect_geometries")
        sql, params = build_collect_geometries_sql(
            table,
            geom=geom,
            schema=schema,
            group_by=group_by,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "collected")

    @overload
    async def union_aggregate(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: Literal["rows"] = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def union_aggregate(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: Literal["gdf"],
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def union_aggregate(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: str,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def union_aggregate(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        into: str = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Dissolve geometries into a merged boundary per group — async (ST_Union).

        Async mirror of :meth:`SpatialAccessor.union_aggregate`. Adds a
        ``dissolved`` geometry column (D-06). Valid for ``into="gdf"``.
        No ``where=`` deprecated alias (born clean, D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default ``"geometry"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        group_by : str or list of str or None, optional
            Column(s) to group by. A bare ``str`` is normalized to
            ``[str]`` (D-01). Pass ``None`` for a whole-table aggregate.
            Raises ``ValueError`` for an empty list.
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default ``"rows"``.
        filter : str, optional
            Raw SQL filter fragment (pre-aggregate WHERE clause).
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows or GeoDataFrame including the ``dissolved`` geometry column.

        Raises
        ------
        ValueError
            If ``into`` is invalid or ``group_by`` is an empty list.
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        if isinstance(group_by, str):
            group_by = [group_by]
        if group_by == []:
            raise ValueError(
                "group_by cannot be an empty list; pass None for a whole-table aggregate"
            )
        _check_into(into, "union_aggregate")
        sql, params = build_union_aggregate_sql(
            table,
            geom=geom,
            schema=schema,
            group_by=group_by,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "dissolved")

    @overload
    async def extent(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        srid: int = 4326,
        into: Literal["rows"] = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def extent(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        srid: int = 4326,
        into: Literal["gdf"],
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> gpd.GeoDataFrame: ...
    @overload
    async def extent(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        srid: int = 4326,
        into: str,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame: ...
    async def extent(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        group_by: str | list[str] | None = None,
        srid: int = 4326,
        into: str = "rows",
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | gpd.GeoDataFrame:
        """Compute the bounding extent of a geometry column — async (ST_Extent).

        Async mirror of :meth:`SpatialAccessor.extent`. Adds an ``extent``
        column — text for ``into="rows"``, geometry for ``into="gdf"`` (D-04).
        Valid for ``into="gdf"`` via the ``box2d::geometry`` cast. No
        ``where=`` deprecated alias (born clean, D-09).

        Parameters
        ----------
        table : str
            Table to query.
        geom : str, optional
            Geometry column name, by default ``"geometry"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        group_by : str or list of str or None, optional
            Column(s) to group by. A bare ``str`` is normalized to
            ``[str]`` (D-01). Pass ``None`` for a whole-table aggregate.
            Raises ``ValueError`` for an empty list.
        srid : int, optional
            SRID for the ``into="gdf"`` cast, by default ``4326``.
            Ignored for ``into="rows"`` (D-05).
        into : str, optional
            ``"rows"`` or ``"gdf"``, by default ``"rows"``.
        filter : str, optional
            Raw SQL filter fragment (pre-aggregate WHERE clause).
        order_by : str, optional
            ORDER BY clause body.
        limit : int, optional
            LIMIT value.

        Returns
        -------
        list of dict or gpd.GeoDataFrame
            Rows or GeoDataFrame including the ``extent`` column.

        Raises
        ------
        ValueError
            If ``into`` is invalid or ``group_by`` is an empty list.
        InvalidIdentifierError
            If any identifier is invalid.
        ExtensionNotAvailableError
            If PostGIS is not installed (first-call guard).
        """
        await self._check_postgis()
        if isinstance(group_by, str):
            group_by = [group_by]
        if group_by == []:
            raise ValueError(
                "group_by cannot be an empty list; pass None for a whole-table aggregate"
            )
        _check_into(into, "extent")
        sql, params = build_extent_sql(
            table,
            geom=geom,
            schema=schema,
            group_by=group_by,
            srid=srid,
            into=into,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return await self._run(sql, params, into, "extent")

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

    async def list_geometry_columns(
        self, *, schema: str | None = None
    ) -> list[dict[str, Any]]:
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
