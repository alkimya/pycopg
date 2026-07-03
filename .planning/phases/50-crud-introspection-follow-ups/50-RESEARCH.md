# Phase 50: CRUD + Introspection Follow-ups - Research

**Researched:** 2026-07-03
**Domain:** pycopg flat CRUD core + `db.schema.*` introspection (plain PostgreSQL; NO PostGIS/TSDB/TSL)
**Confidence:** HIGH (live-DB validated matview SQL, read all extension points in source, reused shipped ETL/spatial/timescale patterns)

## Summary

Phase 50 is five additive, keyword-only, sync/async-parity follow-ups on the shipped v0.9.0 flat CRUD helpers and `db.schema.*` surface. Every implementation-level unknown the CONTEXT.md deferred is now resolved against the live codebase and the live `pycopg_test3` database:

1. **Matview introspection (INTRO-F02):** CONFIRMED live — `information_schema` (views AND columns AND tables) fully excludes materialized views. `pg_matviews` is the name source; a `pg_catalog.pg_attribute`-based query using the `information_schema._pg_*` helper functions reproduces `TABLE_INFO`'s eight-column shape byte-for-byte.
2. **Keyset SQL (CRUD-F02):** the shipped ETL composite-watermark builder (`etl.py:_build_incremental_extract_sql`, lines 819–835) already emits the exact `(c1, c2) > (%s, %s)` row-value compare pycopg needs; copy its shape, flip `>` → `<` for `descending`.
3. **@overload sets (INTRO-F01 / CRUD-F03):** the house triplet pattern (Literal-default / Literal-explicit / str-fallback) from `timescale.py:1424` and `spatial.py:2239` is the exact template.
4. **Guards (CRUD-F01):** existing destructive guards in `delete_where`/`update_where`/`exists` are plain `if not where: raise ValueError(...)` before `validate_identifiers` and any cursor — the new mutual-exclusion / empty-fragment guards slot in at the same entry point.
5. **Exports/docs:** `Page` and `TableDescription` mirror the `RunResult` precedent exactly (`etl.py:462` dataclass → `__init__.py:18` import → `__init__.py:109` `__all__` → `docs/api-reference.md` table row).

**Primary recommendation:** Split the phase into two independently-plannable halves — CRUD (F01/F02/F03, all in `database.py`/`async_database.py`/`base.py`) and INTRO (F01/F02, all in `schema.py`/`queries.py`) — each editing sync+async in the same commit, each registered in `tests/test_parity.py`. The two halves share nothing except the `Page`/`TableDescription` export precedent.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Raw WHERE escape hatch (F01) | API/Backend (flat core) | — | Predicate helpers live on `Database`/`AsyncDatabase`; user SQL fragment bound server-side |
| Keyset pagination (F02) | API/Backend | Database (index-friendly seek) | Row-value compare pushed to Postgres; index scan is the performance lever |
| Page envelope (F03) | API/Backend | — | Pure Python dataclass wrapper over rows + counts |
| describe() into= (INTRO-F01) | API/Backend | — | Typed wrapper / DataFrame reshape of existing dict output; no new SQL |
| Matview introspection (INTRO-F02) | Database (catalog) | API/Backend | `pg_catalog`/`pg_matviews` queries; two thin accessor methods |

## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01..D-15 — the frame, do NOT re-litigate)
- **C-01** Full sync/async parity, same commit, registered in `test_parity.py` (`test_accessor_parity` + `test_accessor_parameter_kind_parity`).
- **C-02** Builder-pur: `validate_identifiers` line 1 of every new builder; user values bound `%s`. **Exception:** raw `where_sql` fragment (D-01) passes through verbatim (NOT run through `validate_identifiers`); its `where_params` still bound `%s`.
- **C-03** Additive/non-breaking under frozen SemVer 1.0; all new params keyword-only; no `DeprecationWarning`; defaults byte-identical. `paginate()` stays `list[dict]`, `describe()` stays flat dict.
- **C-04** Zero new deps; `mypy --strict` 0 errors (blocking); `@overload` where a param switches return type; `interrogate` 100%; coverage ≥95% (baseline 96.29%); Sphinx `-W` clean.
- **D-01** Two kw-only args `where_sql: str | None = None` + `where_params: Sequence[Any] | None = None` on `delete_where`/`update_where`/`count`/`exists`/`paginate` + new `paginate_page`/`paginate_keyset`. NOT a tuple.
- **D-02** `where` (dict) and `where_sql` mutually exclusive → `ValueError` before any DB round-trip.
- **D-03** On destructive helpers, non-empty `where_sql` satisfies the "predicate required" guard; reject empty/whitespace-only `where_sql`.
- **D-04** `where_params` without `where_sql` (and vice-versa) → `ValueError`. `where_params=None` with a placeholder-free `where_sql` is fine.
- **D-05** New `paginate_keyset()`, both accessors; returns `Page` natively.
- **D-06** Explicit `after=` tuple cursor keyed positionally to `order_by`. `next_cursor` = last row's `order_by`-key tuple.
- **D-07** `order_by` mandatory for keyset; row-value compare `(c1,c2) > (%s,%s)`; `descending=True` flips to `<`; forward-only.
- **D-08** Frozen `Page` dataclass: `rows: list[dict]`, `total: int | None`, `has_next: bool`, `next_cursor: tuple | None`. Exported from `__init__.py`.
- **D-09** New `paginate_page()` returns `Page` for offset pagination; `paginate()` untouched. Three methods total.
- **D-10** `with_total: bool = False`. `has_next` always computed via `limit+1` fetch-and-trim. `total` = separate `COUNT(*)` only when `with_total=True`, else `None`.
- **D-11** `into=` param on `describe()`: `"dict"|"dataclass"|"dataframe"`, default `"dict"`. `@overload` per literal.
- **D-12** `into="dataclass"` → `TableDescription` (typed wrapper, sub-values keep current shapes). `into="dataframe"` → columns section as one-row-per-column DataFrame. `TableDescription` exported.
- **D-13** Two methods both accessors: `materialized_views(*, schema="public") → list[str]`; `materialized_view_columns(name, *, schema="public") → list[dict]` (same shape as `table_info`).
- **D-14** Dedicated `pg_catalog` query REQUIRED (`information_schema.columns` excludes matviews). New query consts.
- **D-15** Names + columns only; `ispopulated`/`definition`/size deferred.

### Deferred Ideas (OUT OF SCOPE)
AND-composition of dict `where` + raw `where_sql`; opaque/encoded cursor token; bidirectional (`before=`) keyset; matview metadata beyond names+columns; per-column dataclass nesting; auto-PK tiebreaker for keyset; SPAT-F01; RASTER-F01; ETL-INC-F05.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CRUD-F01 | Raw-SQL WHERE escape hatch (`where_sql`+`where_params`) on predicate helpers | Guard shapes verified (database.py:1004/1050/1099); `_build_where_dict` sibling-branch pattern (base.py:300) |
| CRUD-F02 | Keyset/seek pagination | ETL row-value builder verified (etl.py:819–835); `paginate` order_by validation reusable (database.py:1455–1466) |
| CRUD-F03 | `Page` envelope (`total`+`has_next`) | `RunResult` dataclass precedent (etl.py:462); limit+1 trim mechanics documented below |
| INTRO-F01 | `describe()` as dataclass and/or DataFrame | `@overload` triplet (timescale.py:1424); pandas `DataFrame(list[dict])` verified in venv |
| INTRO-F02 | `materialized_views()` + per-view columns | Live-validated `pg_matviews` + `pg_attribute` SQL below (byte-for-byte TABLE_INFO shape) |

## Standard Stack

No new packages. Existing runtime deps only.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | (installed) | DB driver; binds `%s` and `%(name)s` natively | Already the core `[VERIFIED: pycopg source]` |
| pandas | ≥2.0.0 | `describe(into="dataframe")` output | Already a runtime dep (pyproject.toml:21,41) `[VERIFIED: pyproject.toml]` |

**Installation:** none — `uv sync --all-extras --dev` covers it.

## Package Legitimacy Audit

Not applicable — this phase installs zero new packages (C-04, verified against pyproject.toml). No slopcheck run required.

## Architecture Patterns

### 1. Matview introspection SQL (INTRO-F02, D-13/D-14) — LIVE-VALIDATED

**Live confirmation (against `pycopg_test3`, PostgreSQL 15+):** created a throwaway matview `pycopg_research_mv` over a base table with `serial PK`, `varchar(50)`, `numeric(10,2)`, `timestamptz`. Results `[VERIFIED: pycopg_test3 live DB]`:
- `information_schema.views WHERE table_name='pycopg_research_mv'` → **0 rows** (matview excluded)
- `information_schema.columns WHERE table_name='pycopg_research_mv'` → **0 rows** (columns excluded)
- `information_schema.tables WHERE table_name='pycopg_research_mv'` → **0 rows** (not a BASE TABLE either)
- `pg_matviews WHERE schemaname='public'` → **1 row** `pycopg_research_mv`

So `TABLE_INFO` genuinely cannot serve matview columns (D-14 confirmed), and `views()` (schema.py:781, backed by `queries.VIEWS` = `information_schema.views`) **already excludes matviews — leave it unchanged** (D-14 confirmed).

**`pg_matviews` columns:** `schemaname, matviewname, matviewowner, tablespace, hasindexes, ispopulated, definition`.

**New query const `MATERIALIZED_VIEWS`** (mirrors `VIEWS` shape — one param, alphabetical):
```sql
SELECT matviewname AS table_name
FROM pg_catalog.pg_matviews
WHERE schemaname = %s
ORDER BY matviewname
```
Note: aliasing `matviewname AS table_name` lets `materialized_views()` reuse the exact accessor line from `views()`: `return [r["table_name"] for r in result]` (schema.py:797). Alternatively alias to `matviewname` and read `r["matviewname"]` — either is fine; `views()` uses `table_name` so mirroring it is the lower-friction choice.

**`TABLE_INFO`'s exact 8-column shape** (queries.py:41–54): `column_name, data_type, is_nullable, column_default, ordinal_position, character_maximum_length, numeric_precision, numeric_scale`.

**New query const `MATERIALIZED_VIEW_COLUMNS`** — byte-for-byte shape match, using the `information_schema._pg_*` helper functions so `data_type`/`numeric_precision`/etc. produce **identical** values to `information_schema.columns` (verified: integer `id` → `numeric_precision=32, numeric_scale=0`, matching what `information_schema.columns` returns for a base-table integer):
```sql
SELECT
    a.attname AS column_name,
    CASE
        WHEN t.typtype = 'd' THEN
            CASE
                WHEN bt.typelem <> 0 AND bt.typlen = -1 THEN 'ARRAY'
                WHEN nbt.nspname = 'pg_catalog' THEN format_type(t.typbasetype, NULL)
                ELSE 'USER-DEFINED'
            END
        ELSE
            CASE
                WHEN t.typelem <> 0 AND t.typlen = -1 THEN 'ARRAY'
                WHEN nt.nspname = 'pg_catalog' THEN format_type(a.atttypid, NULL)
                ELSE 'USER-DEFINED'
            END
    END AS data_type,
    CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable,
    CASE WHEN a.attgenerated = '' THEN pg_get_expr(ad.adbin, ad.adrelid) ELSE NULL END AS column_default,
    a.attnum AS ordinal_position,
    information_schema._pg_char_max_length(
        information_schema._pg_truetypid(a.*, t.*),
        information_schema._pg_truetypmod(a.*, t.*)) AS character_maximum_length,
    information_schema._pg_numeric_precision(
        information_schema._pg_truetypid(a.*, t.*),
        information_schema._pg_truetypmod(a.*, t.*)) AS numeric_precision,
    information_schema._pg_numeric_scale(
        information_schema._pg_truetypid(a.*, t.*),
        information_schema._pg_truetypmod(a.*, t.*)) AS numeric_scale
FROM pg_catalog.pg_attribute a
LEFT JOIN pg_catalog.pg_attrdef ad ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
JOIN (pg_catalog.pg_class c JOIN pg_catalog.pg_namespace nc ON c.relnamespace = nc.oid)
    ON a.attrelid = c.oid
JOIN (pg_catalog.pg_type t JOIN pg_catalog.pg_namespace nt ON t.typnamespace = nt.oid)
    ON a.atttypid = t.oid
LEFT JOIN (pg_catalog.pg_type bt JOIN pg_catalog.pg_namespace nbt ON bt.typnamespace = nbt.oid)
    ON t.typtype = 'd' AND t.typbasetype = bt.oid
WHERE nc.nspname = %s AND c.relname = %s
  AND c.relkind = 'm'
  AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum
```

**Live output of this exact query** on `pycopg_research_mv` `[VERIFIED: pycopg_test3]`:
```
 column_name |        data_type         | is_nullable | column_default | ordinal_position | character_maximum_length | numeric_precision | numeric_scale
 id          | integer                  | YES         |                |                1 |                          |                32 |             0
 name        | character varying        | YES         |                |                2 |                       50 |                   |
 amount      | numeric                  | YES         |                |                3 |                          |                10 |             2
 created_at  | timestamp with time zone | YES         |                |                4 |                          |                   |
```
This matches `TABLE_INFO`'s output structure exactly (same 8 keys, same value semantics: `data_type` bare type name like `character varying` not `character varying(50)`; `character_maximum_length=50` for varchar; `numeric_precision/scale` for numeric).

**Important shape note:** `is_nullable` reads `'YES'` for matview `id` because materialized views do NOT carry a NOT NULL constraint even when the source column is a PK — this is the matview's true nullability and is correct, not a bug. `column_default` is always NULL for matviews (they have no defaults). Both are faithful to what a matview actually is.

**Accessor methods** (schema.py, sync near line 797/827; async near line 1600/1620):
```python
def materialized_views(self, *, schema: str = "public") -> list[str]:
    validate_identifiers(schema)
    result = self._db.execute(queries.MATERIALIZED_VIEWS, [schema])
    return [r["table_name"] for r in result]

def materialized_view_columns(self, name: str, *, schema: str = "public") -> list[dict[str, Any]]:
    validate_identifiers(name, schema)
    return self._db.execute(queries.MATERIALIZED_VIEW_COLUMNS, [schema, name])
```
Note `table_info` (schema.py:412) does NOT call `validate_identifiers` (it passes name/schema purely as bound `%s` params to `information_schema.columns`). For `materialized_view_columns`, name/schema are likewise only bound `%s` — so `validate_identifiers` is defense-in-depth here (they never touch string interpolation). `materialized_views` mirrors `views()` which DOES call `validate_identifiers(schema)`. Keep `validate_identifiers` line-1 for C-02 consistency; it is cheap and harmless.

### 2. Keyset row-value SQL (CRUD-F02, D-06/D-07) — reuse shipped ETL builder

The **shipped** composite-watermark builder `_build_incremental_extract_sql` (etl.py:738–840, lines 819–835) already emits the exact pattern `[VERIFIED: pycopg source]`:
```python
# etl.py:819-829 (composite branch)
wm_seq = cast("Sequence[Any]", watermark)
lhs = "(" + ", ".join(cols) + ")"                 # "(c1, c2)"
placeholders = "(" + ", ".join(["%s"] * len(cols)) + ")"  # "(%s, %s)"
params: list[Any] = list(wm_seq)
# ...
f"... WHERE {lhs} {op} {placeholders}"            # op is ">" (exclusive)
```
This is the reference. Postgres row-value comparison `(c1, c2) > (%s, %s)` is lexicographic tuple compare and is **index-friendly** (a btree on `(c1, c2)` supports it as a range scan). `[VERIFIED: PostgreSQL row-value semantics + ETL builder]`

**Keyset builder for pycopg** (fresh local helper OR extend the `paginate` order-clause code; either satisfies D-07 per CONTEXT discretion). Recommended fresh static helper on `QueryMixin`/`DatabaseBase` (mirrors `_build_where_dict` at base.py:299):
```python
@staticmethod
def _build_keyset_where(order_cols: list[str], after: Sequence[Any], descending: bool) -> tuple[str, list[Any]]:
    validate_identifiers(*order_cols)                      # C-02 line 1
    op = "<" if descending else ">"                        # D-07 flip
    lhs = "(" + ", ".join(order_cols) + ")"
    rhs = "(" + ", ".join(["%s"] * len(order_cols)) + ")"
    return f"{lhs} {op} {rhs}", list(after)
```

**Full `paginate_keyset` SQL assembly** (D-05/D-06/D-07/D-08/D-10):
```
SELECT * FROM {schema}.{table}
  [WHERE <keyset-fragment> [AND <where_sql or dict fragment>]]   -- keyset ANDs with the optional escape-hatch/dict predicate
  ORDER BY {order_cols}[ DESC]
  LIMIT {int(limit) + 1}                                          -- D-10: fetch limit+1
```
- **`after=None`** (first page): omit the keyset fragment entirely, only ORDER BY + LIMIT.
- **`descending=True`**: append ` DESC` to ORDER BY **and** flip `>`→`<` (both must agree).
- **`order_by` mandatory** (D-07): raise `ValueError` if not provided; reuse the `paginate` validation shape (database.py:1455–1466): normalize str→list, reject non-str/empty elements, `validate_identifiers(*cols)`.
- **`after` arity**: if `len(after) != len(order_cols)`, raise `ValueError` before DB round-trip.

**`has_next` limit+1 trim mechanics (D-10):**
```python
sql = "... LIMIT %s" ; params.append(int(limit) + 1)     # or f-string int(limit)+1 like paginate does
rows = cur.fetchall()
has_next = len(rows) > limit
rows = rows[:limit]                                        # trim the sentinel row
next_cursor = tuple(rows[-1][c] for c in order_cols) if rows else None   # D-06
```
Note: `paginate` currently f-string-interpolates `LIMIT {int(limit)}` (database.py:1472) — `int()` cast makes it injection-safe. Follow that idiom (`int(limit) + 1`) OR bind `%s`; both are fine.

**`with_total` separate COUNT (D-10):**
```python
if with_total:
    count_sql = f"SELECT COUNT(*) FROM {schema}.{table}{where_clause}"   # SAME where/where_sql, NO keyset fragment, NO order/limit
    total = int(self.fetch_val(count_sql, where_only_params))
else:
    total = None
```
The COUNT uses the base predicate (dict `where` or `where_sql`) but **not** the keyset `after` fragment (total is the full filtered set, not the remaining-after-cursor set).

**`paginate_page` (D-09, offset variant)** is `paginate`'s body (database.py:1446–1478) + `Page` wrapping + `with_total` COUNT + limit+1 has_next. It keeps `offset=`, has NO `after=`/`order_by`-mandatory constraint, and `next_cursor` is always `None`.

### 3. @overload stub sets (INTRO-F01 / CRUD-F03, C-04/D-11) — house triplet pattern

The established house pattern is the **Literal-default / Literal-explicit / str-fallback triplet** `[VERIFIED: timescale.py:1424-1482, spatial.py:2239-2313]`. For `describe(into=...)` with THREE literals, use a **quadruplet** (three literal overloads + one str fallback):

```python
from typing import overload, Literal

@overload
def describe(self, table: str, *, schema: str = "public",
             into: Literal["dict"] = "dict") -> dict[str, Any]: ...
@overload
def describe(self, table: str, *, schema: str = "public",
             into: Literal["dataclass"]) -> TableDescription: ...
@overload
def describe(self, table: str, *, schema: str = "public",
             into: Literal["dataframe"]) -> pd.DataFrame: ...
@overload
def describe(self, table: str, *, schema: str = "public",
             into: str) -> dict[str, Any] | TableDescription | pd.DataFrame: ...
def describe(self, table: str, *, schema: str = "public",
             into: str = "dict") -> dict[str, Any] | TableDescription | pd.DataFrame:
    # runtime body: build the flat dict (existing describe body, schema.py:822-827), then dispatch on `into`
    ...
```
Rules confirmed from Phase 46 (MEMORY): the **default-valued literal** carries `= "dict"`; the **non-default literals** have NO default (forces callers to pass explicitly to select that return type); the **str fallback** overload preserves the dynamic-value path; the implementation signature is the union. This is exactly `time_bucket`'s shape (default `Literal["df"] = "df"`, explicit `Literal["rows"]`, fallback `into: str`). The async twin gets the identical overload set with `async def`.

**Do the `paginate_page`/`paginate_keyset` methods need `@overload`?** NO — they return `Page` **unconditionally** (no param switches their return type; `with_total` only changes `Page.total`'s value from `None` to `int`, not the return TYPE). So a single plain signature `-> Page` suffices for both. `@overload` is only required where a param **selects among different return types** (C-04 wording, MEMORY Phase 46). `describe(into=...)` is the only new overloaded method in this phase.

**mypy note:** `TableDescription` and `Page` must be importable at type-check time in both `schema.py` and `database.py`/`async_database.py`. `pd` is already imported in `database.py`; `schema.py` will need `import pandas as pd` added for the `into="dataframe"` return annotation (currently schema.py imports no pandas — verified). Guard heavy imports as usual; `pandas` is a hard runtime dep so a top-level `import pandas as pd` is fine.

### 4. Guard shapes (CRUD-F01, D-02/D-03/D-04) — confirmed entry-point pattern

Existing destructive guards fire **before** `validate_identifiers` and before any cursor `[VERIFIED: database.py]`:
- `delete_where` (database.py:1004): `if not where: raise ValueError("delete_where requires a non-empty 'where' dict...")`
- `update_where` (database.py:1050–1056): `if not values: raise ValueError(...)` then `if not where: raise ValueError(...)`
- `exists` (database.py:1099): `if not where: raise ValueError("exists requires a non-empty `where` dict...")`
- `count` (database.py:1138): no destructive guard (where is optional); `where=None` → no WHERE clause.
- `paginate` (database.py:1446): no destructive guard; `where=None` → no WHERE.

**New guard block** to slot in at the top of each helper (before `validate_identifiers`), shared logic — recommend a small static helper on `QueryMixin` to avoid 10× duplication:
```python
@staticmethod
def _resolve_predicate(
    where: dict[str, Any] | None,
    where_sql: str | None,
    where_params: Sequence[Any] | None,
) -> tuple[str, list[Any]]:
    """Return (fragment, params) from exactly one predicate source. Empty string = no predicate."""
    # D-04: where_sql / where_params must co-present-or-co-absent
    if (where_sql is None) != (where_params is None) and not (
        where_sql is not None and where_params is None
    ):
        # where_params without where_sql is always an error
        if where_sql is None and where_params is not None:
            raise ValueError("where_params requires where_sql.")
    if where_params is not None and where_sql is None:
        raise ValueError("where_params requires where_sql.")
    # D-02: dict where and where_sql mutually exclusive
    if where and where_sql is not None:
        raise ValueError("Pass either 'where' (dict) or 'where_sql', not both.")
    if where_sql is not None:
        # D-03: reject empty/whitespace-only fragment
        if not where_sql.strip():
            raise ValueError("where_sql must be a non-empty SQL fragment.")
        return where_sql, list(where_params or [])   # fragment verbatim (NOT validated — C-02 escape hatch)
    if where:
        return QueryMixin._build_where_dict(where)     # base.py:300 — validates keys, binds values
    return "", []
```
(The planner may simplify the D-04 boolean; the invariant is: `where_params` present ⇒ `where_sql` present; `where` present ⇒ `where_sql` absent; empty `where_sql` rejected.)

**Destructive-guard interaction (D-03):** For `delete_where`/`update_where`/`exists`, the "predicate required" check becomes "exactly one predicate source present and non-empty." Concretely: raise the existing destructive `ValueError` only when BOTH `where` is falsy AND `where_sql` is None (or empty). A non-empty `where_sql` satisfies the guard. Pseudo:
```python
frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
if not frag:   # neither source produced a predicate
    raise ValueError("delete_where requires a non-empty 'where' or 'where_sql'...")
```
For `count`/`paginate`/`paginate_page`/`paginate_keyset`, an empty `frag` is legal (no WHERE clause) — they just skip the destructive check.

**Signature change:** `delete_where`/`update_where`/`exists` currently take `where` as a **positional-or-keyword** required arg. Adding `where_sql`/`where_params` as kw-only (after `*`) keeps them additive. But note: to allow `delete_where("t", where_sql=...)` WITHOUT a dict, `where` must become **optional** (`where: dict[str, Any] | None = None`). This is a widening (accepts more), non-breaking under C-03. Update the annotation and the `if not where` logic accordingly. `count` already has `where` kw-only optional (database.py:1113).

### 5. Page / TableDescription dataclasses + exports (D-08/D-12) — RunResult precedent

**`RunResult` precedent** `[VERIFIED: etl.py:462, __init__.py:18/109]`:
- Defined `@dataclass(frozen=True)` at etl.py:462.
- Imported in `__init__.py:18`: `from pycopg.etl import AsyncETLAccessor, ETLAccessor, Pipeline, RunResult`.
- Listed in `__init__.py:109` `__all__` under `# ETL`.
- Documented in `docs/api-reference.md`.

**`Page` dataclass** (D-08) — place in `database.py` (top-level, near other module types) since it is a pagination-core type returned by `Database`/`AsyncDatabase` methods. `async_database.py` imports it from `database.py` (async_database already imports from `pycopg.base`/`pycopg.database` patterns exist — actually `paginate` lives in `QueryMixin`? No: `paginate` is on `Database` directly at database.py:1400 and `AsyncDatabase` at async_database.py:1112). Recommend defining `Page` in `database.py` and `from pycopg.database import Page` in `async_database.py` and `__init__.py`:
```python
@dataclass(frozen=True)
class Page:
    rows: list[dict[str, Any]]
    total: int | None
    has_next: bool
    next_cursor: tuple[Any, ...] | None
```

**`TableDescription` dataclass** (D-12) — place in `schema.py` (introspection-owned). Fields mirror the four `describe` dict keys 1:1, sub-values keep current shapes:
```python
@dataclass(frozen=True)
class TableDescription:
    columns: list[dict[str, Any]]                # table_info() output
    primary_key: dict[str, Any] | None           # primary_key() output
    foreign_keys: list[dict[str, Any]]           # foreign_keys() output
    indexes: list[dict[str, Any]]                # list_indexes() output
```
`into="dataclass"` → `TableDescription(**flat_dict)`. `into="dataframe"` → `pd.DataFrame(flat_dict["columns"])` (verified: `pd.DataFrame(list[dict])` yields one row per column, 8 columns; nullable ints become float64/NaN — acceptable, document it).

**Export insertion points:**
- `pycopg/__init__.py:17` — add `Page` to the `from pycopg.database import Database` line → `from pycopg.database import Database, Page`.
- `pycopg/__init__.py:36` — add `TableDescription` to `from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor` → `..., SchemaAccessor, TableDescription`.
- `pycopg/__init__.py:__all__` (around line 109/125) — add `"Page"` (near CRUD/core) and `"TableDescription"` (near `# Schema`).
- `pycopg/database.py __all__` / `base.py __all__` — `Page` is defined in database.py; database.py has no `__all__` currently (only base.py does), so no `__all__` edit needed there unless one is added. schema.py has no `__all__` either (verified imports). Confirm during planning.

**Docs insertion points** (`docs/api-reference.md`) `[VERIFIED: api-reference.md]`:
- CRUD Methods (v0.9.0) table at line 96–103 → add a v1.1.0 subsection OR extend the table with `where_sql`/`where_params` note on `delete_where`/`update_where`/`exists`/`count`/`paginate`, plus new rows for `paginate_page` and `paginate_keyset` (returns `Page`).
- Introspection Methods (v0.9.0) table at line 138–144 → add rows for `materialized_views` (`schema="public"` → `list[str]`), `materialized_view_columns` (`name, schema="public"` → `list[dict]`), and update `describe` row to show `into="dict"|"dataclass"|"dataframe"`.
- Add `Page` and `TableDescription` to any "Types" / dataclass reference section (mirror where `RunResult` is documented).
- `docs/database.md` and `docs/async-database.md` — narrative examples for the new methods (Sphinx `-W` requires all cross-refs resolve; add autodoc entries if the dataclasses are autodoc'd like `RunResult`).

### Anti-Patterns to Avoid
- **Do NOT** run the raw `where_sql` fragment through `validate_identifiers` (C-02 explicit exception — it IS the escape hatch). Only bind `where_params` as `%s`.
- **Do NOT** reshape describe sub-values in `TableDescription`/DataFrame (D-12 "wrap, don't reshape" — preserves the D-04 no-drift invariant).
- **Do NOT** add `@overload` to `paginate_page`/`paginate_keyset` (return type is unconditionally `Page`).
- **Do NOT** add an auto-PK tiebreaker or hidden introspection round-trip to keyset (D-07 rejected).
- **Do NOT** touch `paginate()` (frozen `list[dict]`, C-03) or `describe()`'s default return (`into="dict"` byte-identical).
- **Do NOT** reuse `TABLE_INFO` for matview columns (live-confirmed it returns 0 rows for matviews).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Matview column type formatting | Custom atttypmod→`numeric(p,s)` decoder | `information_schema._pg_numeric_precision/_scale/_char_max_length` helpers | Byte-for-byte match with `TABLE_INFO`; Postgres-maintained |
| Keyset tuple compare | Manual `(a>%s) OR (a=%s AND b>%s)` expansion | Native row-value `(a,b) > (%s,%s)` | Index-friendly, simpler, already shipped in ETL |
| Predicate dict → SQL | New WHERE builder | `_build_where_dict` (base.py:300) | Validates keys, binds values, shared |
| Page count | Manual row buffering | `limit+1` fetch-and-trim + separate `COUNT(*)` | D-10 avoids surprise COUNT on deep pages |

## Common Pitfalls

### Pitfall 1: matview `is_nullable`/`column_default` look "wrong"
**What goes wrong:** A reviewer expects matview `id` to show `is_nullable='NO'` because the source PK is NOT NULL.
**Why:** Materialized views never carry NOT NULL/DEFAULT — `pg_attribute.attnotnull` is false, `attgenerated=''` with no `pg_attrdef` row.
**How to avoid:** Document that matview columns report `is_nullable='YES'` and `column_default=NULL` — this is faithful. Do NOT try to trace back to source columns (out of scope, D-15).

### Pitfall 2: `where` becomes optional but destructive guard weakens
**What goes wrong:** Making `where` default `None` (to allow `where_sql`-only calls) could silently allow an unpredicated `delete_where("t")`.
**Why:** If both `where` and `where_sql` are None/empty, the destructive helpers must still raise.
**How to avoid:** After `_resolve_predicate`, if the resulting fragment is empty AND the helper is destructive, raise the existing `ValueError`. Add a mock test asserting `delete_where("t")` (no predicate) still raises.

### Pitfall 3: keyset `descending` half-applied
**What goes wrong:** Flipping ORDER BY to `DESC` but leaving the row-value op as `>` (or vice-versa) yields wrong/empty pages.
**Why:** Both the sort direction AND the comparison operator must agree.
**How to avoid:** Derive both from the single `descending` bool in the same builder; add a live-DB test paging forward and backward-order to prove monotonic progress.

### Pitfall 4: `next_cursor` arity drift
**What goes wrong:** `next_cursor` built from `SELECT *` row keys that don't align with `order_by`.
**Why:** Must extract exactly the `order_by` columns, in order.
**How to avoid:** `tuple(rows[-1][c] for c in order_cols)` — keyed to `order_cols`, not row insertion order.

### Pitfall 5: mypy-strict `@overload` default-value placement
**What goes wrong:** Putting `= "dict"` on a non-default literal overload, or omitting it from the default one, breaks overload resolution.
**Why:** Only the default-selected literal carries the default value; others must be defaultless.
**How to avoid:** Copy `time_bucket`'s exact placement (timescale.py:1437 has `= "df"`, 1452 has none, 1467 fallback none).

## Code Examples

### Matview names + columns (accessor)
```python
# Source: schema.py pattern + live-validated queries.py consts
db.schema.materialized_views()                       # -> ["mv_daily", ...]
db.schema.materialized_view_columns("mv_daily")      # -> same 8-key list[dict] as table_info
```

### Raw escape hatch
```python
# Source: CONTEXT specifics
db.count("users", where_sql="age > %s AND status = ANY(%s)", where_params=[30, ["a","b"]])
db.delete_where("logs", where_sql="created_at < now() - %s::interval", where_params=["30 days"])
```

### Keyset + Page
```python
# Source: CONTEXT specifics + ETL row-value builder
page = db.paginate_keyset("events", 50, order_by=["created_at", "id"], after=(last_ts, last_id))
# Page(rows=[...], has_next=True, next_cursor=(ts_n, id_n), total=None)
page2 = db.paginate_page("t", 20, offset=40, with_total=True)
# Page(rows=[...], total=1234, has_next=True, next_cursor=None)
```

### Structured describe
```python
# Source: @overload triplet (timescale.py:1424 pattern)
td = db.schema.describe("orders", into="dataclass")   # -> TableDescription(columns=..., primary_key=..., ...)
df = db.schema.describe("orders", into="dataframe")   # -> one-row-per-column DataFrame
```

## Runtime State Inventory

Not applicable — Phase 50 is purely additive code (new methods, params, dataclasses, query constants). No rename/refactor/migration; no stored data, live-service config, OS-registered state, secrets, or build artifacts are affected. **None — verified: all changes are new public surface, no existing string/identifier is renamed.**

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio + pytest-cov |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, addopts with `--cov-fail-under=95`, line 97) |
| Quick run command | `PGDATABASE=pycopg_test3 uv run pytest tests/ -x -q -o addopts=""` |
| Full suite command | `PGDATABASE=pycopg_test3 uv run pytest` |

**Env gotcha (project memory):** default `pycopg_test`/`pycopg_test2` are broken by TimescaleDB `.so` drift — ALWAYS run DB/parity/coverage tests with `PGDATABASE=pycopg_test3`. Phase 50 is plain PostgreSQL (no TSL gating). Targeted runs use `-o addopts=""` to drop the coverage gate (flaky fixture isolation, project memory).

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CRUD-F01 | `where_sql`+`where_params` on 5 helpers, mock SQL shape (sync+async) | unit (mocked psycopg) | `pytest tests/test_database.py -k where_sql` | ❌ Wave 0 |
| CRUD-F01 | Guards: mutual-exclusion, empty fragment, param-desync, destructive-still-raises | unit | `pytest tests/test_database.py -k "where_sql_guard"` | ❌ Wave 0 |
| CRUD-F01 | Injection: `where_params` bound as `%s`, fragment passthrough verbatim | injection | `pytest tests/test_sql_injection.py -k where_sql` | ❌ Wave 0 (extend existing file) |
| CRUD-F01 | Live: raw predicate returns correct rows (sync+async) | integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k where_sql` | ❌ Wave 0 |
| CRUD-F02 | Keyset SQL shape `(c1,c2) > (%s,%s)`, `<`-flip, limit+1, mock | unit | `pytest tests/test_database.py -k paginate_keyset` | ❌ Wave 0 |
| CRUD-F02 | Injection: keyset tuple compare binds `after` values, validates order_by cols | injection | `pytest tests/test_sql_injection.py -k keyset` | ❌ Wave 0 |
| CRUD-F02 | Live: stable deep pagination, forward-only monotonic progress, `after=None` first page | integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k paginate_keyset` | ❌ Wave 0 |
| CRUD-F03 | `Page` fields; `has_next` limit+1 trim; `with_total` COUNT vs None | unit + integration | `pytest tests/test_database.py -k paginate_page` / `..._integration.py` | ❌ Wave 0 |
| INTRO-F01 | `describe(into=...)` returns dict/dataclass/DataFrame; default byte-identical; `@overload` resolves | unit | `pytest tests/test_database.py -k describe_into` | ❌ Wave 0 |
| INTRO-F01 | Live: dataclass/DataFrame equal the dict sub-values (no drift) | integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k describe_into` | ❌ Wave 0 |
| INTRO-F02 | `materialized_views` + `materialized_view_columns` mock SQL const shape | unit | `pytest tests/test_database.py -k materialized_view` | ❌ Wave 0 |
| INTRO-F02 | Injection: name/schema handling in matview-columns builder | injection | `pytest tests/test_sql_injection.py -k materialized_view` | ❌ Wave 0 |
| INTRO-F02 | Live: create matview in pycopg_test3, columns match `table_info` shape byte-for-byte | integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k materialized_view` | ❌ Wave 0 |
| ALL | Parity: new methods/params registered, KIND-parity holds | unit | `pytest tests/test_parity.py` | ✅ (extend surface frozensets) |

### Sampling Rate
- **Per task commit:** `PGDATABASE=pycopg_test3 uv run pytest tests/test_database.py tests/test_parity.py -x -q -o addopts=""` (fast mock + parity)
- **Per wave merge:** `PGDATABASE=pycopg_test3 uv run pytest tests/ -q -o addopts=""`
- **Phase gate:** `PGDATABASE=pycopg_test3 uv run pytest` (full suite + coverage ≥95%) + `uv run mypy pycopg` (0 errors) + `interrogate` 100% + Sphinx `-W` clean — before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_parity.py` — add `test_crud_v110_surface` frozenset `{paginate_page, paginate_keyset}` and `test_schema_v110_surface` frozenset `{materialized_views, materialized_view_columns}` (mirror `test_schema_v090_surface` at line 128). No change to `ACCESSOR_PAIRS`; KIND-parity auto-covers new params.
- [ ] `tests/test_database.py` — new mock-SQL unit tests for where_sql (5 helpers), paginate_page, paginate_keyset, describe_into, materialized_view* (mirror `test_describe_composes_four_helpers` at line 1237, `test_table_info` at 642).
- [ ] `tests/test_database_integration.py` — new live tests (mirror `test_paginate_*` at 1135–1187, `test_describe_*` at 1353–1390). Add a matview fixture (CREATE MATERIALIZED VIEW / DROP on teardown).
- [ ] `tests/test_async_database.py` — async twins (mirror `test_paginate_async` at 3268, `test_describe_async` at 3417).
- [ ] `tests/test_sql_injection.py` — extend with where_sql passthrough + param-binding, keyset tuple compare, matview name/schema tests (mirror existing `_build_*` import + `EVIL_IDENTIFIERS` payloads at line 21).
- [ ] No framework install needed — pytest/cov/asyncio already configured.

## Security Domain

`security_enforcement` not explicitly set → treated as enabled.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | `validate_identifiers` line-1 on every new builder (order_by cols, matview name/schema); user values bound `%s`; **raw `where_sql` is a documented, intentional escape hatch** (C-02) — the trust boundary shifts to the caller for that fragment only, params still bound |
| V6 Cryptography | no | none |
| V2/V3/V4 | no | no auth/session/access-control surface in this phase |

### Known Threat Patterns for pycopg flat core + catalog introspection
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via identifier (order_by, matview name/schema) | Tampering | `validate_identifiers` before interpolation; dedicated injection test per builder |
| SQL injection via keyset `after` values | Tampering | Bound as `%s` in row-value RHS, never interpolated |
| Injection via `where_sql` fragment | Tampering (accepted risk) | **Documented escape hatch** — caller owns the SQL; `where_params` still bound `%s`; docstring must state the trust model (same posture as spatial `filter=`/aggregates `structural SQL`) |
| Unpredicated destructive delete/update | Tampering/DoS | Destructive guard: empty predicate (neither dict nor where_sql) still raises `ValueError` before any DB round-trip (D-03) |

## State of the Art

No framework churn relevant. `pg_matviews` (Postgres 9.3+) and `information_schema._pg_*` helper functions are long-stable internal APIs. Row-value comparison is SQL-standard and index-friendly on all supported Postgres versions. No deprecations affect this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `information_schema._pg_numeric_precision`/`_pg_char_max_length`/`_pg_truetypid`/`_pg_truetypmod` are callable in all supported Postgres versions | Matview SQL | LOW — they back `information_schema.columns` itself; verified present in pg15 (pycopg_test3). If a target version lacks them, fall back to manual `atttypmod` decode. `[VERIFIED: pycopg_test3 pg15]` for the running version; `[ASSUMED]` for the full support matrix. |
| A2 | `Page` best located in `database.py` (not `base.py`) | Exports | LOW — `paginate*` live on `Database`/`AsyncDatabase` directly, not `QueryMixin`; async_database can import from database.py. Planner may prefer base.py for symmetry. |
| A3 | pandas nullable-int→float64/NaN in `into="dataframe"` is acceptable | INTRO-F01 | LOW — cosmetic; document it. Matches how pandas always handles NULL-containing int columns. |
| A4 | schema.py has no `__all__` to update | Exports | LOW — verified no `__all__` in schema.py imports grep; confirm at edit time. |

## Open Questions

1. **`Page` location — `database.py` vs `base.py`? (RESOLVED: `database.py`, per plan 50-02)**
   - What we know: `paginate*` are defined on `Database`/`AsyncDatabase`, not the shared `QueryMixin`. `RunResult` lives in `etl.py` (its owning module).
   - What's unclear: whether the team prefers all public dataclasses in one place.
   - Recommendation: define `Page` in `database.py`, import into `async_database.py` + `__init__.py` (mirrors `RunResult`'s module-ownership).
   - **Resolved:** plan 50-02 defines `Page` in `database.py` and imports it into `async_database.py` + `__init__.py`, matching this recommendation and the `RunResult` precedent.

2. **`describe(into="dataframe")` — which section?**
   - What we know: D-12 says the **columns** section only (the naturally tabular part).
   - Resolved: `pd.DataFrame(flat["columns"])`. primary_key/foreign_keys/indexes remain reachable via `into="dataclass"` or standalone helpers.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (`pycopg_test3`) | All live integration tests | ✓ | pg15+ (peer/`postgres:postgres`) | none needed |
| psql CLI | matview SQL validation | ✓ | /usr/bin/psql | — |
| pandas | `into="dataframe"` | ✓ | ≥2.0.0 (runtime dep) | — |
| uv | test/lint/build | ✓ | (project env) | — |

**Missing dependencies:** none. PostGIS/TimescaleDB NOT required (Phase 50 is plain PostgreSQL).

## Sources

### Primary (HIGH confidence)
- Live DB `pycopg_test3` — validated matview exclusion from `information_schema` + `pg_matviews`/`pg_attribute` column queries (byte-for-byte TABLE_INFO shape)
- `pycopg/etl.py:738-840` — shipped composite-watermark row-value builder (keyset reference)
- `pycopg/etl.py:462-518` — `RunResult` dataclass precedent
- `pycopg/database.py:975-1478` — delete_where/update_where/exists/count/paginate guard shapes + SQL
- `pycopg/base.py:299-326` — `_build_where_dict`
- `pycopg/schema.py:412-827` — table_info/views/describe + async twins
- `pycopg/queries.py:41-191` — TABLE_INFO/VIEWS constants
- `pycopg/timescale.py:1424-1482` + `pycopg/spatial.py:2239-2313` — `@overload` triplet pattern
- `pycopg/__init__.py:17-154` — export/`__all__` structure
- `tests/test_parity.py` — surface-frozenset + KIND-parity test conventions
- `docs/api-reference.md:85-154` — docs table insertion points

### Secondary (MEDIUM confidence)
- PostgreSQL row-value comparison semantics (SQL standard, index-friendly) — cross-referenced with shipped ETL builder behavior

## Metadata

**Confidence breakdown:**
- Matview SQL (INTRO-F02): HIGH — live-validated on pycopg_test3, byte-for-byte shape match
- Keyset SQL (CRUD-F02): HIGH — reuses shipped, tested ETL builder
- @overload sets (INTRO-F01): HIGH — copies shipped house pattern
- Guards (CRUD-F01): HIGH — read exact existing guard code
- Exports/docs: HIGH — read RunResult precedent end-to-end

**Research date:** 2026-07-03
**Valid until:** 2026-08-02 (stable domain; internal patterns)

## RESEARCH COMPLETE
