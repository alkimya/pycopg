# Phase 35: Schema Introspection - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Add five enriched **read-only** schema-introspection helpers to the **existing
`db.schema.*` accessor** (`SchemaAccessor` / `AsyncSchemaAccessor`), sitting next to
the existing introspection methods (`table_info`, `row_count`, `list_columns`,
`columns_with_types`, `list_indexes`, `list_constraints`), with full sync/async parity:

- `primary_key(table, schema="public")` (INTRO-01)
- `foreign_keys(table, schema="public")` (INTRO-02)
- `sequences(schema="public")` (INTRO-03)
- `views(schema="public")` (INTRO-04)
- `describe(table, schema="public")` — all-in-one consolidation (INTRO-05)
- async parity for every helper, enforced by `test_accessor_parity` (INTRO-06)

**Locked at milestone cadrage (2026-06-24) — NOT re-litigated here:**
- Placement is the **existing `db.schema.*` accessor**, NOT a new accessor.
  **No `db.meta.*` carve** (resolves the v0.6.0 open question; stay purely additive,
  no second deprecation cycle on a just-cleaned surface).
- Each helper reads `information_schema` / `pg_catalog`, validates identifiers
  (`validate_identifiers`), and accepts an optional `schema="public"` argument.
- **Builder-pur convention** (same as Phase 34 / spatial / etl / timescale):
  `validate_identifiers` first, user values as `%s`, SQL held as named constants in
  `pycopg/queries.py`, called via `self._db.execute(CONSTANT, [schema, table])`.
- **Zero new runtime dependencies**; coverage ratchet held ≥94% (baseline 95.11%).
- Read-only — no DDL, no destructive-predicate guard concerns (this is introspection).

**Out of scope (deferred — do NOT add):** `materialized_views()` and per-view column
introspection (INTRO-F02); `describe` as a rich dataclass / DataFrame rendering
(INTRO-F01); ON DELETE/UPDATE referential actions on FKs (see D-02 rationale);
ORM / query-builder.

</domain>

<decisions>
## Implementation Decisions

### `primary_key` return shape (INTRO-01)
- **D-01:** Returns a **`dict | None`**: `{'constraint_name': 'users_pkey', 'columns': ['id']}`
  (or `['org_id', 'user_id']` for a composite PK, columns in key order). Returns **`None`**
  when the table has no primary key. Distinguishing "no PK" as `None` (vs an empty list) and
  naming the constraint mirrors the `table_info`/`list_constraints` dict style. Composite-safe
  via the `columns` list.

### `foreign_keys` return shape (INTRO-02)
- **D-02:** Returns **`list[dict]`**, each entry the **core fields only**:
  `{'constraint_name', 'columns': [local...], 'referenced_table', 'referenced_columns': [...]}`.
  Exactly the REQUIREMENTS contract — composite-safe (column lists in key order).
  **No `on_delete`/`on_update`/`referenced_schema`** — referential actions are deferred
  (rarely needed for introspection display; can be added later without breaking the shape).
  Empty list `[]` when the table has no foreign keys.

### `sequences` / `views` return shape (INTRO-03, INTRO-04)
- **D-03:** Both return **`list[str]` of object names** (e.g. `sequences → ['users_id_seq', ...]`,
  `views → ['active_users', ...]`), consistent with the existing `list_tables` / `list_columns`
  name-list precedent. Lightweight; matches the "list" verb. (These are schema-level, not
  table-level, so `describe()` does not consume them.)

### `describe` consolidation shape (INTRO-05)
- **D-04:** Returns **one flat dict** that **composes the existing + new helpers** — it does
  NOT run its own consolidated SQL:
  ```
  {
    'columns':      table_info(table, schema),     # list[dict] (cols + types, per existing helper)
    'primary_key':  primary_key(table, schema),    # dict | None (D-01 shape)
    'foreign_keys': foreign_keys(table, schema),   # list[dict] (D-02 shape)
    'indexes':      list_indexes(table, schema),   # list[dict] (existing helper shape)
  }
  ```
  Each sub-value is **exactly** the shape its standalone helper returns. Minimal new SQL,
  guaranteed-consistent shapes, no drift. (Planner's call: whether `describe` calls the public
  methods directly or shares the same private builders — as long as the shapes match the
  standalone helpers exactly.)

### SQL source policy (all helpers)
- **D-05:** **Per-helper, correctness-first** — pick whichever source makes each helper correct
  and simple, matching the existing mixed precedent (`table_info`/`GET_COLUMNS` =
  `information_schema`; `list_indexes`/`list_constraints`/`row_count` = `pg_catalog`). Guidance
  for the planner (exact SQL is the planner/researcher's call):
  - `primary_key` + `foreign_keys` → **`pg_catalog`** (`pg_constraint` with `conkey`/`confkey`
    arrays) for **reliable composite-column ORDERING** — information_schema's
    `key_column_usage` ordinal handling for multi-column keys is notoriously fiddly.
  - `sequences` → **`information_schema.sequences`** (clean, scoped to the schema arg).
  - `views` → source that **excludes materialized views** — `information_schema.views` naturally
    omits matviews, or `pg_catalog` with `relkind = 'v'`.

### Edge-case behavior (all helpers)
- **D-06:** **Empty result, no table-existence pre-check** — consistent with existing helpers
  (`list_columns` returns `[]` today without pre-checking). No PK → `primary_key` returns `None`;
  no FKs → `foreign_keys` returns `[]`. A **nonexistent table** yields the same empty/`None`
  (the catalog query simply matches nothing) — **no extra round-trip, no new error class**.
  `describe()` on a missing table → a dict with empty/`None` sections.
- **D-07:** **Schema-scoped, matviews excluded** — `sequences`/`views` filter strictly by the
  `schema` arg (default `"public"`), so system schemas (`pg_catalog`, `information_schema`) are
  naturally excluded. `sequences` **includes** SERIAL/identity-backed sequences (they are real
  sequences in the schema). `views` returns **regular views only, excluding materialized views**
  (keeps the deferred INTRO-F02 `materialized_views()` helper meaningful).

### Parity (INTRO-06)
- **D-08:** Parity is enforced **automatically** by `test_accessor_parity`
  (`tests/test_parity.py:36`), which bidirectionally set-diffs the public members of
  `SchemaAccessor` vs `AsyncSchemaAccessor` (the pair is already registered in `ACCESSOR_PAIRS`
  at line 31). Adding each new method to BOTH classes is sufficient — no hand-written pair list
  to update. (A named-surface assertion like `test_timescale_v080_surface` for the 5 new methods
  is the planner's option, not required.)

### Claude's Discretion
- Exact SQL text of each new `queries.py` constant (column ordering joins, relkind filters),
  and whether `describe` calls the public methods or shares private builders — researcher/planner's
  call, as long as identifiers are validated, values bound as `%s`, and the documented return
  shapes (D-01..D-04) hold exactly.
- Docstring wording (numpydoc, shallow, no Examples — per project convention).
- Whether to add a named-surface frozenset test for the 5 new methods (optional belt-and-suspenders).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & requirements (locked decisions)
- `.planning/REQUIREMENTS.md` — INTRO-01..06 (the phase requirements with exact signatures),
  the "extend `db.schema.*`, no `db.meta.*` carve" placement lock, the optional `schema="public"`
  convention, and the v2/Out-of-Scope deferrals (INTRO-F01 rich dataclass, INTRO-F02 matviews).
- `.planning/PROJECT.md` §"Current Milestone: v0.9.0" — locked cadrage decisions (both families,
  builder-pur + parity, zero new deps, coverage ≥94%).
- `.planning/ROADMAP.md` §"Phase 35: Schema Introspection" — goal + success criteria.
- `.planning/phases/34-crud-ergonomics/34-CONTEXT.md` — sibling phase; the builder-pur /
  validate-identifiers-first / parity-via-auto-enumeration conventions established there carry
  directly into Phase 35.

### Code conventions
- `.planning/codebase/CONVENTIONS.md` — naming (snake_case methods, `_build_*`/UPPER_SNAKE SQL
  constants, modern `str | None` type hints), error handling (`validate_identifier(s)` before
  interpolation, `InvalidIdentifier`).

### Closest existing analogs in source (read before implementing)
- `pycopg/schema.py:321-337` — `list_columns` (the `execute(queries.GET_COLUMNS, [schema, table])`
  → reshape pattern; `list[str]` precedent for `sequences`/`views` D-03).
- `pycopg/schema.py:402-418` — `table_info` (`list[dict]` of columns+types; consumed by
  `describe`'s `'columns'` key, D-04).
- `pycopg/schema.py:642-674` — `list_indexes` + `list_constraints` (the `pg_catalog`-sourced
  `list[dict]` pattern; `list_indexes` is consumed by `describe`'s `'indexes'` key; the dict
  style is the model for `primary_key`/`foreign_keys`).
- `pycopg/schema.py:677-680` — `AsyncSchemaAccessor` class header (mirror every new method here
  with `await`).
- `pycopg/queries.py` — SQL constants module. New `PRIMARY_KEY`, `FOREIGN_KEYS`, `SEQUENCES`,
  `VIEWS` constants live here (see `TABLE_INFO` :41, `LIST_INDEXES` :111, `LIST_CONSTRAINTS` :129
  for the established style; existing pg_catalog joins to copy from for PK/FK).
- `pycopg/utils.py:107-122` — `validate_identifiers(*names)` — the identifier guard every helper
  calls first.
- `tests/test_parity.py:24-61` — `ACCESSOR_PAIRS` (SchemaAccessor pair already at line 31) +
  `test_accessor_parity` (auto-enumeration → INTRO-06 enforced once methods land on both classes).

No new external specs/ADRs introduced in this discussion — decisions are fully captured above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SchemaAccessor` / `AsyncSchemaAccessor` (`pycopg/schema.py:33` / `:677`) — the new methods are
  appended to these existing classes; no new class/accessor.
- The `execute(queries.CONSTANT, [schema, table]) → list[dict]` introspection pattern
  (`table_info`, `list_indexes`, `list_constraints`, `list_columns`) — every new helper follows it.
- `table_info` / `list_indexes` — composed verbatim by `describe()` (D-04); their existing dict
  shapes ARE the `describe` `'columns'` / `'indexes'` sub-shapes.
- `validate_identifiers` (`pycopg/utils.py:107`) — the guard every helper calls before binding.
- `queries.py` existing `pg_catalog` joins (`LIST_INDEXES`, `LIST_CONSTRAINTS`, `ROW_COUNT`) —
  the join/namespace-filter scaffolding to copy for the new `pg_catalog`-sourced PK/FK queries.

### Established Patterns
- **SQL-as-named-constant**: all introspection SQL is a `UPPER_SNAKE` constant in `queries.py`,
  parameterized with `%s` on `[schema, table]`. Mirror this for the 4 new constants.
- **Mixed source by correctness**: existing accessor already splits information_schema vs
  pg_catalog per-query (D-05 continues this) — no need to force a single source.
- **Parity by auto-enumeration**: `test_accessor_parity` set-diffs the two classes' public
  members — add each method to BOTH `SchemaAccessor` and `AsyncSchemaAccessor` and parity passes
  without touching any pair list (INTRO-06, D-08).
- **Async mirror**: async helpers mirror sync 1:1 with `await self._db.execute(...)` (see existing
  `async def list_indexes` at `schema.py:1292`).

### Integration Points
- New methods land on `SchemaAccessor` (`pycopg/schema.py`) and `AsyncSchemaAccessor` (same file).
- New SQL constants land in `pycopg/queries.py`.
- No `__init__.py` export changes (methods on existing accessor classes, no new symbols); no new
  exception class (D-06 — empty/None, no pre-check).

</code_context>

<specifics>
## Specific Ideas

- `primary_key('users')` → `{'constraint_name': 'users_pkey', 'columns': ['id']}`; `None` if no PK;
  composite → `{'constraint_name': '...', 'columns': ['org_id', 'user_id']}` (key order).
- `foreign_keys('orders')` → `[{'constraint_name': 'orders_user_id_fkey', 'columns': ['user_id'],
  'referenced_table': 'users', 'referenced_columns': ['id']}]`; `[]` if none.
- `describe('users')` → `{'columns': [...], 'primary_key': {...}|None, 'foreign_keys': [...],
  'indexes': [...]}` — a one-call snapshot composing the standalone helpers (D-04).
- Throughline: introspection is **read-only and consistent** — the new helpers reuse the existing
  helpers' exact return shapes so `describe` is just an assembly, and the SQL source is chosen for
  correctness (composite-key ordering) not dogma.

</specifics>

<deferred>
## Deferred Ideas

- **ON DELETE / ON UPDATE referential actions** (+ `referenced_schema`) on `foreign_keys` — D-02
  keeps core fields only; actions can be added later without breaking the shape. (Surfaced in
  discussion; not in v0.9.0 scope.)
- **`materialized_views()` helper** and **per-view column introspection** — INTRO-F02, deferred
  to v2. `views()` excluding matviews (D-07) deliberately preserves room for this.
- **`describe` as a rich dataclass / DataFrame rendering** — INTRO-F01, deferred to v2.

None of these are in Phase 35 scope — discussion stayed within the phase boundary.

</deferred>

---

*Phase: 35-schema-introspection*
*Context gathered: 2026-06-24*
