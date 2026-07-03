# Phase 50: CRUD + Introspection Follow-ups - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Richer, production-ready query ergonomics on the flat transactional CRUD core plus deeper
structural visibility via `db.schema.*` — five additive, keyword-only, sync/async-parity
follow-ups (CRUD-F01..F03, INTRO-F01..F02) on the shipped v0.9.0 CRUD helpers + `db.schema.*`
surface. **All non-breaking under the frozen SemVer 1.0 API** (no existing signature or return
type changes), zero new runtime dependencies. Every new knob defaults to today's exact behavior.

1. **CRUD-F01** — raw-SQL WHERE escape hatch (`where_sql` + `where_params`) on the predicate
   helpers, for conditions the dict `where` can't express.
2. **CRUD-F02** — keyset/seek pagination (`paginate_keyset()`) for stable, index-friendly deep
   pagination.
3. **CRUD-F03** — a `Page` envelope carrying `total` + `has_next` alongside the rows.
4. **INTRO-F01** — `describe()` output as a structured dataclass and/or DataFrame, not only a dict.
5. **INTRO-F02** — materialized-view introspection (`materialized_views()` + per-view columns).

**NOT in scope** (roadmap-fixed, don't add): any breaking change to an existing signature/return
type; bidirectional (`before=`) keyset paging; opaque cursor tokens; AND-composition of dict
`where` + raw `where_sql`; auto-PK tiebreaker for keyset; matview metadata beyond names+columns
(`ispopulated`/`definition`/size); per-column dataclass nesting. SPAT-F01 (gridSize) and RASTER-F01
remain deferred to future cycles.
</domain>

<decisions>
## Implementation Decisions

### Carried forward — house pattern (LOCKED, do not reopen)
- **C-01:** Full **sync/async parity** — every new field/param/method on BOTH the sync class
  ([database.py](../../../pycopg/database.py) / [schema.py](../../../pycopg/schema.py) `SchemaAccessor`)
  and the async class ([async_database.py](../../../pycopg/async_database.py) / `AsyncSchemaAccessor`),
  edited in the **same commit** and registered in [tests/test_parity.py](../../../tests/test_parity.py)
  (`test_accessor_parity` + `test_accessor_parameter_kind_parity` — the v1.0.0 Phase 41 KIND-parity lesson).
- **C-02:** Builder-pur — `validate_identifiers` line 1 of every new/extended SQL builder; user values
  bound `%s`, never interpolated. **Exception by design:** the raw `where_sql` fragment (D-01) is user-
  authored SQL passed through verbatim — that IS the escape hatch — but its `where_params` are still
  bound `%s`, and the fragment is NOT run through `validate_identifiers`.
- **C-03:** Additive/non-breaking under **frozen SemVer 1.0** — all new params keyword-only, no
  `DeprecationWarning`, defaults reproduce current behavior byte-identically. Existing returns are
  frozen: `paginate()` stays `list[dict]` ([database.py:1400](../../../pycopg/database.py#L1400)),
  `describe()` stays a flat dict ([schema.py:799](../../../pycopg/schema.py#L799)) → new outputs are opt-in.
- **C-04:** Zero new runtime deps; `mypy --strict` 0 errors (blocking gate — add `@overload` stubs where
  a param switches the return type: `describe(into=...)`, `paginate_page` vs `paginate`); `interrogate`
  100%; coverage ratchet ≥95% (baseline 96.29% at Phase 49); Sphinx `-W` clean.

### CRUD-F01 — raw-SQL WHERE escape hatch
- **D-01:** **Two keyword-only args** `where_sql: str | None = None` + `where_params: Sequence[Any] | None = None`
  on `delete_where` / `update_where` / `count` / `exists` / `paginate` (and, for consistency, the new
  `paginate_page` / `paginate_keyset` — D-06/D-05). Shape mirrors the library's pervasive
  `execute(sql, params)` idiom. NOT a `(fragment, params)` tuple. Example:
  `db.count("users", where_sql="age > %s AND status = ANY(%s)", where_params=[30, ["a", "b"]])`.
- **D-02:** **`where` (dict) and `where_sql` are mutually exclusive.** Passing both → `ValueError`
  (guard before any DB round-trip). Restrictive-first: AND-composition can be added later
  non-breakingly; a frozen-API narrowing cannot. NO precedence rules to lock in now.
- **D-03:** **Destructive-guard interaction.** On the helpers that require a predicate
  (`delete_where`/`update_where`/`exists`), a non-empty `where_sql` **satisfies** the existing
  "non-empty `where` required" guard — i.e. the guard becomes "exactly one predicate source present
  and non-empty". Reject an empty/whitespace-only `where_sql` (same shape of `ValueError`). The escape
  hatch is explicit user SQL, so a deliberate `where_sql="1=1"` is the caller's responsibility (matches
  the intent that the guard blocks *accidental* unpredicated deletes, not deliberate ones).
- **D-04:** **`where_params` without `where_sql` is an error** (and vice-versa) — `ValueError` guard,
  so the two never desync silently. `where_params=None` with a `where_sql` that has no placeholders is fine.

### CRUD-F02 — keyset / seek pagination
- **D-05:** **New method `paginate_keyset()`** parallel to `paginate()`, both accessors. NOT a `method=`
  mode on `paginate()` (offset= is meaningless under keyset; two models in one signature is more to
  freeze). It returns the `Page` envelope natively (D-08).
- **D-06:** **Explicit `after=` tuple cursor** keyed positionally to `order_by` columns — transparent,
  no encode/decode machinery, no wire format to freeze under 1.0. NOT an opaque base64 token. The
  envelope's `next_cursor` (D-08) is simply the last returned row's `order_by`-key tuple, fed back as
  the next call's `after=`.
- **D-07:** **`order_by` is mandatory** for `paginate_keyset()`; the user owns a unique/total order
  (docstring: append a unique column such as the PK as a tiebreaker). NO hidden PK-introspection
  round-trip. The SQL uses a **row-value comparison** `(c1, c2) > (%s, %s)` (Postgres lexicographic
  tuple compare) — the exact pattern used by the ETL composite watermark
  ([49-CONTEXT D-10](../49-incremental-etl-follow-ups/49-CONTEXT.md)). `descending=True` flips the
  operator to `<`. **Forward-only** for this release; `before=`/backward paging deferred (addable
  non-breakingly later).

### CRUD-F03 — page envelope
- **D-08:** **Frozen `Page` dataclass** — fields `rows: list[dict]`, `total: int | None`,
  `has_next: bool`, `next_cursor: tuple | None`. Attribute access, typed, mypy-friendly; mirrors the
  existing `RunResult` dataclass precedent ([etl.py:273](../../../pycopg/etl.py#L273)). Exported from
  `pycopg/__init__.py` (public type). NOT a plain dict / TypedDict.
- **D-09:** **New sibling `paginate_page()`** returns `Page` for **offset** pagination; the existing
  `paginate()` is left untouched (`list[dict]`, frozen). Three methods total — `paginate` (offset,
  list) / `paginate_page` (offset, Page) / `paginate_keyset` (keyset, Page) — each unambiguous. NOT an
  `envelope=True` return-type-switching flag on `paginate()`.
- **D-10:** **`with_total` opt-in** (`with_total: bool = False`). `has_next` is **always** computed
  cheaply — fetch `limit + 1` rows, set `has_next = len > limit`, trim the extra row before returning.
  `total` runs a separate `COUNT(*)` (same WHERE/`where_sql`) **only** when `with_total=True`;
  `Page.total is None` otherwise. Avoids a surprise `COUNT` on deep/keyset pages.

### INTRO-F01 — structured describe()
- **D-11:** **`into=` param on `describe()`** — `describe(table, into="dict" | "dataclass" | "dataframe")`,
  default `"dict"` (byte-identical back-compat). `@overload` selects the return type per literal.
  Matches the house `into=` convention already used by spatial/aggregate helpers. NOT separate
  `describe_dataclass()`/`describe_dataframe()` methods.
- **D-12:** **Offer both structured forms.** `into="dataclass"` → a `TableDescription` dataclass with
  typed fields mirroring the four dict keys 1:1 (`columns`, `primary_key`, `foreign_keys`, `indexes`);
  **sub-values keep their current shapes** (`columns` stays `list[dict]`, etc.) — a typed wrapper only,
  zero shape drift from the standalone helpers (preserves describe's D-04 "shapes can never drift"
  invariant). `into="dataframe"` → the **columns** section as a one-row-per-column DataFrame (the only
  naturally tabular part; `primary_key`/`foreign_keys`/`indexes` remain reachable via the dataclass or
  standalone helpers). NOT per-column dataclass nesting. `TableDescription` exported from `pycopg/__init__.py`.

### INTRO-F02 — materialized-view introspection
- **D-13:** **Two parallel methods**, both accessors: `materialized_views(*, schema="public")` → `list[str]`
  of names (mirrors `views()` at [schema.py:781](../../../pycopg/schema.py#L781)); and
  `materialized_view_columns(name, *, schema="public")` → `list[dict]` in the **same shape as
  `table_info`**. NOT a single rich object bundling name+columns.
- **D-14:** **Dedicated `pg_catalog` query — CONFIRMED REQUIRED.** `information_schema.columns` (used by
  `TABLE_INFO`, [queries.py:41](../../../pycopg/queries.py#L41)) **excludes materialized views** per the
  SQL standard, so `table_info` cannot be reused for matview columns. New query const via
  `pg_catalog.pg_attribute` + `pg_class` (`relkind = 'm'`), following the existing `queries.*` style;
  `materialized_views()` lists via `pg_matviews` (or `pg_class relkind='m'`). Regular `views()` already
  excludes matviews — leave it unchanged.
- **D-15:** **Names + columns only.** `ispopulated`, view `definition`, and size are deferred as future
  additive helpers — keep the frozen surface minimal and parallel to the table-introspection surface.

### Claude's Discretion (resolve during research/planning against the live DB)
- Exact new `queries.*` constant names/placement (raw-fragment path reuses the caller's SQL; keyset
  row-value builder; matview list + matview-columns pg_catalog queries) — follow existing style.
- The precise `@overload` stub set for `describe(into=...)` and the `Page`-returning methods (mypy-strict).
- Whether the keyset row-value builder is a fresh local helper or extends an existing WHERE builder —
  any approach that emits `(c1, c2) [> | <] (%s, %s)` with each value bound satisfies D-07. Reuse the
  ETL composite tuple-compare shape as the reference.
- `has_next` limit+1 trim mechanics and where `Page`/`TableDescription` slot into `pycopg/__init__.py`
  exports + `docs/api-reference`.
- Test layering: mock SQL-shape unit tests (both accessors) + live-DB integration; a dedicated
  injection test per new builder path (raw-fragment param binding, keyset tuple compare, matview
  columns). Run DB/parity/coverage tests with `PGDATABASE=pycopg_test3` (project memory: default
  `pycopg_test`/`pycopg_test2` broken by TSDB `.so` drift). These are plain PostgreSQL (no TSL gating).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 50 goal + 5 success criteria (the scope anchor); milestone standing bar
- `.planning/REQUIREMENTS.md` — CRUD-F01..F03 + INTRO-F01..F02 wording + cross-cutting acceptance criteria

### Code to extend (edit sync + async in one commit)
- `pycopg/base.py` — `_build_where_dict` ([:300](../../../pycopg/base.py#L300)): the shared equality-WHERE
  builder; the raw escape hatch (D-01) routes around it when `where_sql` is given. `validate_identifiers` here.
- `pycopg/database.py` — sync CRUD helpers: `delete_where` ([:975](../../../pycopg/database.py#L975)),
  `update_where` ([:1016](../../../pycopg/database.py#L1016)), `exists` ([:1067](../../../pycopg/database.py#L1067)),
  `count` ([:1109](../../../pycopg/database.py#L1109)), `paginate` ([:1400](../../../pycopg/database.py#L1400)) —
  add `where_sql`/`where_params` (D-01..D-04); add `paginate_page` (D-09) + `paginate_keyset` (D-05..D-07);
  define/export `Page` (D-08).
- `pycopg/async_database.py` — async mirrors: `exists` (:1032), `count` (:1074), `paginate` (:1112),
  `delete_where` (:1637), `update_where` (:1678) — same additions, `await` every DB call.
- `pycopg/schema.py` — `views` ([:781](../../../pycopg/schema.py#L781)) / `describe`
  ([:799](../../../pycopg/schema.py#L799)) / `table_info` ([:412](../../../pycopg/schema.py#L412)) and their
  async twins (:1584 / :1602 / :1162): add `into=` to `describe` (D-11/D-12), `TableDescription` dataclass,
  `materialized_views` + `materialized_view_columns` (D-13/D-14).
- `pycopg/queries.py` — `TABLE_INFO` ([:41](../../../pycopg/queries.py#L41), `information_schema.columns` — the
  reason matviews need a new query), `VIEWS` (:186). Add matview list + matview-columns `pg_catalog` constants.
- `pycopg/validators.py` — `validate_identifiers` (line-1 of every builder; NOT applied to raw `where_sql`).
- `pycopg/exceptions.py` — `ValueError` guards are plain Python; no new exception type anticipated.
- `pycopg/__init__.py` — export the new public `Page` and `TableDescription` types.

### Test patterns
- `tests/test_parity.py` — register every new method/param (both accessors)
- Existing CRUD + schema test modules — mock SQL-shape unit tests, injection-test conventions, live-DB integration

### Prior-phase decisions (locked, carry forward — do not re-derive)
- `.planning/phases/49-incremental-etl-follow-ups/49-CONTEXT.md` — **D-10 row-value tuple compare
  `(c1,c2) > (%s,%s)`** is the reference pattern for keyset (D-07); same house pattern (guards before
  DB round-trip, keyword-only additive params, both-accessors-same-commit, sequential-on-main).
- `.planning/phases/48-timescaledb-follow-ups/48-CONTEXT.md` — immediate-prior follow-up phase; keyword-only
  additive params + `@overload` KIND-parity precedent.
- `.planning/milestones/v1.0.0-*` (freeze) — SemVer 1.0 freeze: named params native `%(name)s`, `*Error`
  names, no breaking signature/return changes. The frozen-return constraint (C-03) descends from here.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_build_where_dict` ([base.py:300](../../../pycopg/base.py#L300)): the single equality-WHERE builder shared
  by all five predicate helpers. The raw escape hatch (D-01) is a sibling branch — when `where_sql` is set,
  skip this builder and use the user fragment + `where_params` directly.
- `RunResult` frozen dataclass ([etl.py:273](../../../pycopg/etl.py#L273)): the precedent shape/style for the
  new `Page` (D-08) and `TableDescription` (D-12) dataclasses.
- ETL composite watermark row-value compare (49-CONTEXT D-10): the exact `(c1,c2) > (%s,%s)` SQL shape and
  binding discipline the keyset builder (D-07) reuses.
- `describe()` compose-from-helpers pattern ([schema.py:799](../../../pycopg/schema.py#L799)): its D-04
  "no shape drift" contract carries into the dataclass/DataFrame wrappers (D-12) — wrap, don't reshape.
- `views()` ([schema.py:781](../../../pycopg/schema.py#L781)): the names-only mirror `materialized_views()`
  follows (D-13); `table_info()` ([:412](../../../pycopg/schema.py#L412)) is the return-shape template for
  `materialized_view_columns()`.

### Established Patterns
- Guards fire **before any DB round-trip** — construction/entry-time `ValueError` (D-02/D-03/D-04). Matches
  Phase 48 D-07 and the v0.7.0 incremental guards.
- `into=` is the house convention for output-shape toggles (spatial/aggregate helpers) — D-11 reuses it.
- `@overload` stubs kept in sync+async KIND-parity for mypy-strict (v1.0.0 Phase 46) — required where a
  param switches the return type (`describe(into=...)`, and each `Page`-returning method).
- Both sync and async accessors edited in the same file/commit; new params registered in `test_parity`.

### Integration Points
- The three pagination methods form a family: `paginate` (offset→list, frozen) / `paginate_page`
  (offset→`Page`) / `paginate_keyset` (keyset→`Page`). `paginate_page` and `paginate_keyset` share the
  `Page` envelope (D-08) and the `with_total` COUNT + limit+1 `has_next` mechanics (D-10).
- The raw escape hatch (D-01) composes onto every read/predicate helper including the two new pagination
  methods → `where`/`where_sql` mutual-exclusion (D-02) is one guard reused across all of them.
- INTRO-F02 is self-contained (new `pg_catalog` queries + two methods); INTRO-F01 wraps existing describe
  output. Neither touches the CRUD surface — the two halves of the phase are independently plannable.
- Local test env (project memory): `PGDATABASE=pycopg_test3`; all Phase 50 work is plain PostgreSQL
  (no PostGIS/TSL gating).
</code_context>

<specifics>
## Specific Ideas

- Raw escape hatch call: `db.count("users", where_sql="age > %s AND status = ANY(%s)", where_params=[30, ["a","b"]])`;
  `db.delete_where("logs", where_sql="created_at < now() - %s::interval", where_params=["30 days"])`.
- Keyset: `db.paginate_keyset("events", 50, order_by=["created_at", "id"], after=(last_ts, last_id))` →
  `Page(rows=[...], has_next=True, next_cursor=(ts_n, id_n), total=None)`; SQL `WHERE (created_at, id) > (%s, %s)`.
- Envelope: `paginate_page("t", 20, offset=40, with_total=True)` → `Page(rows, total=1234, has_next=True, next_cursor=None)`.
- describe: `db.schema.describe("orders", into="dataclass")` → `TableDescription(columns=[...], primary_key=..., foreign_keys=[...], indexes=[...])`;
  `into="dataframe"` → one-row-per-column DataFrame.
- Matviews: `db.schema.materialized_views()` → `["mv_daily", ...]`; `db.schema.materialized_view_columns("mv_daily")` →
  same list[dict] shape as `table_info`.
</specifics>

<deferred>
## Deferred Ideas

- **AND-composition of dict `where` + raw `where_sql`** — D-02 ships mutual-exclusion; ANDing both is a clean
  future additive widening if a concrete need appears.
- **Opaque/encoded keyset cursor token** — D-06 ships explicit `after=` tuples; a base64 token layer can be
  added over them later without breaking the tuple form.
- **Bidirectional keyset (`before=` / backward paging)** — D-07 ships forward-only; addable non-breakingly.
- **Matview-specific metadata** (`ispopulated`, `definition`, size) and per-column dataclass nesting for
  describe — deferred (D-15/D-12) to keep the frozen 1.x surface minimal.
- **Auto-PK tiebreaker for keyset** — rejected (D-07) to avoid a hidden introspection round-trip; user owns
  the total order.
- Milestone-level deferrals already recorded (don't re-litigate): SPAT-F01 (gridSize), RASTER-F01 (raster),
  ETL-INC-F05 (CDC).

*None raised during discussion that aren't already tracked above.*
</deferred>

---

*Phase: 50-crud-introspection-follow-ups*
*Context gathered: 2026-07-03*
