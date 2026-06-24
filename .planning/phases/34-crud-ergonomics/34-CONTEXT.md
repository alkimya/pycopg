# Phase 34: CRUD Ergonomics - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Add ergonomic single-row and predicate-driven CRUD helpers to the **flat transactional
core** of `Database` and `AsyncDatabase`, sitting next to their existing batch analogs
(`upsert_many`, `insert_many`, `fetch_one`/`fetch_val`), with full sync/async parity:

- `upsert(table, row, conflict_columns, ...)` — singular complement to `upsert_many` (CRUD-01)
- `delete_where(table, where={...})` (CRUD-02)
- `update_where(table, values={...}, where={...})` (CRUD-03)
- `exists(table, where={...})` / `count(table, where=None|{...})` (CRUD-04, CRUD-05)
- `paginate(table, limit, offset, order_by, where)` (CRUD-06)
- dict-fetch / `fetch_all` (CRUD-07)
- async parity for every helper, enforced by `test_accessor_parity` (CRUD-08)

**Locked at milestone cadrage (2026-06-24) — NOT re-litigated here:**
- Placement is the **flat transactional core**, not a new accessor. No `db.meta.*` / `db.crud.*` carve.
- `where=` is a **dict of equality conditions** (`{col: val, ...}` → AND-ed equality); columns
  validated via `validate_identifiers`, values bound as `%s`. (Raw-SQL `where=` is deferred — CRUD-F01.)
- **Builder-pur convention**: `validate_identifiers` first, user values as `%s`, pure `(sql, params)`
  builders (mirroring `_build_insert_sql` / `_build_select_sql` in `base.py`), sync/async parity.
- **Zero new runtime dependencies**; coverage ratchet held ≥94% (baseline 95.11%).

**Out of scope (deferred — do NOT add):** raw-SQL `where=` strings (CRUD-F01), keyset/cursor
pagination (CRUD-F02), page-envelope with total-count/has_next (CRUD-F03), ORM/query-builder.

</domain>

<decisions>
## Implementation Decisions

### `upsert` (CRUD-01) — single-row upsert
- **D-01:** Return shape is `dict | None`. Build `INSERT ... ON CONFLICT (conflict_columns)
  DO UPDATE SET ... RETURNING *` and return the single affected row as a dict. On a no-op /
  `DO NOTHING` / no row affected, return `None`.
- **D-02:** `conflict_columns` is **required** (a positional arg), matching `upsert_many`'s
  signature. `update_columns` may stay optional (default = all non-conflict columns, same rule
  as `upsert_many`).
- **D-03:** Reuse `upsert_many`'s `EXCLUDED.<col>` SET-clause construction; this is the singular
  form, so a single `row: dict` (not `rows: list[dict]`). Append `RETURNING *` and `fetchone()`.

### Destructive predicate guard (CRUD-02, CRUD-03)
- **D-04:** `delete_where` and `update_where` **require a non-empty `where` dict**. An empty `{}`
  (or omitted/`None`) raises `ValueError` **before any DB round-trip** — never silently emit a
  WHERE-less DELETE/UPDATE that wipes/overwrites the whole table. "Affect everything" must go
  through the explicit `truncate_table`. (This guard applies ONLY to the destructive ops;
  `count`/`exists` still accept `where=None`.)

### Read / predicate return types (CRUD-02..05)
- **D-05:** `exists(table, where) -> bool`, implemented as `SELECT EXISTS(SELECT 1 FROM ... WHERE ...)`
  so it never materializes rows.
- **D-06:** `count(table, where=None|{...}) -> int` via `SELECT COUNT(*)`. `where=None` counts all rows.
- **D-07:** `delete_where(...) -> int` (rows deleted, `cur.rowcount`); `update_where(...) -> int`
  (rows updated, `cur.rowcount`). Consistent with `insert_many`/`upsert_many` returning affected counts.

### dict-fetch (CRUD-07)
- **D-08:** The transactional core **already returns dicts** — `execute() -> list[dict]` and
  `fetch_one() -> dict | None` (the pool sets psycopg's `dict_row` row factory). So CRUD-07 is
  **largely already satisfied by existing behavior**. The deliverable is: (a) document this
  dicts-by-default behavior, and (b) add a thin, explicitly-named `fetch_all(sql, params) -> list[dict]`
  for discoverability/symmetry with `fetch_one`. **Do NOT** add an `into='dicts'|'tuples'` toggle
  or a tuples path (scope creep over dicts-by-default).
- **D-09:** `paginate(...)` returns `list[dict]` (the page rows), consistent with `execute`/`fetch_all`.

### `paginate` ordering (CRUD-06)
- **D-10:** `order_by` is **optional**, accepts a **column name `str` or `list[str]`** of column
  names, each run through `validate_identifiers` (NOT raw SQL strings). If omitted, no `ORDER BY`
  (caller accepts non-determinism). Whole-clause direction is controlled by a separate
  **`descending: bool` parameter** (default `False` = ASC) applied to all order columns — e.g.
  `paginate('t', limit=20, offset=40, order_by=['created_at','id'], descending=True)` →
  `ORDER BY created_at, id DESC`. Per-column direction (mixed ASC/DESC) is **deferred** — do not
  build a tuple/`'col DESC'`-parsing form in v0.9.0.
- **D-11:** Signature `paginate(table, limit, offset=0, order_by=None, where=None, schema="public")`.
  `limit`/`offset` cast to `int` in the builder (as `_build_select_sql` already does). `where=None`
  is allowed for paginate (read-only — the destructive guard in D-04 does NOT apply here).

### Builder reuse
- **D-12:** Introduce a shared pure helper that turns a `where` dict into a `(sql_fragment, params)`
  pair (AND-ed `col = %s`, columns validated) — used by `delete_where`, `update_where`, `exists`,
  `count`, and `paginate`. Note: the existing `_build_select_sql(where: str)` takes a **raw SQL
  string**; the new dict-based path is a *separate, safer* mechanism — extend/add a builder rather
  than overloading the existing `where: str` param. Final builder shape is the planner's call;
  the dict→`%s` convention is locked.

### Claude's Discretion
- Exact private builder names/locations (`base.py` vs `database.py`), how the where-dict builder
  is factored, and whether `paginate` composes `_build_select_sql` or a new builder — planner's call,
  as long as builders stay pure and identifiers are validated before interpolation.
- Docstring wording (numpydoc shallow, no Examples — per project convention).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & requirements (locked decisions)
- `.planning/REQUIREMENTS.md` — CRUD-01..08 (the phase requirements), the dict-of-equality
  `where=` convention, the "flat core, no `db.meta.*` carve" placement lock, and the v2/Out-of-Scope
  deferrals (CRUD-F01 raw-SQL where, CRUD-F02 keyset, CRUD-F03 page envelope).
- `.planning/PROJECT.md` §"Current Milestone: v0.9.0" — locked cadrage decisions (both families,
  builder-pur + parity, zero new deps, coverage ≥94%).
- `.planning/ROADMAP.md` §"Phase 34: CRUD Ergonomics" — goal + 6 success criteria.

### Code conventions
- `.planning/codebase/CONVENTIONS.md` — naming (snake_case methods, `has_`/`is_`/`exists_`
  predicate prefixes, `_build_*` private builders), type-hint style, error handling
  (`validate_identifier(s)` before interpolation, `InvalidIdentifier`).

### Closest existing analogs in source (read before implementing)
- `pycopg/database.py:602-645` — `upsert_many` (EXCLUDED SET-clause construction, `conflict_columns`
  required, returns affected count). Singular `upsert` reuses this shape + `RETURNING *`.
- `pycopg/database.py:518-541` — `execute()` already returns `list[dict]` (dicts-by-default proof).
- `pycopg/database.py:815-852` — `fetch_one()` (`dict | None`) and `fetch_val()` — symmetry target for `fetch_all`.
- `pycopg/base.py:80-208` — `_build_insert_sql`, `_build_batch_insert_sql`, `_build_select_sql`
  (note: existing `where` is a RAW SQL string; the new dict-where path is separate and safer).
- `pycopg/utils.py:107-122` — `validate_identifiers(*names)`.
- `pycopg/pool.py` (`row_factory=dict_row`) — why the core already returns dicts.
- `tests/test_parity.py:121` — `TestParityMethods::test_all_database_public_methods_exist_in_async`
  auto-enumerates all public methods → new flat CRUD methods are covered by parity automatically
  once added to both classes (CRUD-08).

No new external specs/ADRs introduced in this discussion — decisions are fully captured above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `upsert_many` (`database.py:602`) — singular `upsert` is the same EXCLUDED-SET shape over one
  row, plus `RETURNING *`/`fetchone()`.
- `_build_select_sql` (`base.py:159`) — paginate's `LIMIT`/`OFFSET`/`ORDER BY`/`SELECT *`
  scaffolding already exists; the only new piece is the validated dict-`where` → `%s` path
  and the `descending` flag.
- `validate_identifiers` (`utils.py:107`) — the identifier guard every builder calls first.
- `execute`/`fetch_one`/`fetch_val` already use `dict_row` (via `pool.py`) — dict-fetch is mostly free.

### Established Patterns
- **Builder-pur**: pure `_build_*` staticmethods return `(sql, params)` (or `sql`); the public
  method opens a cursor and executes. Mirror this for every new helper.
- **Parity**: flat-core public methods are auto-checked by `test_parity.py`'s public-method
  enumeration — add each method to BOTH `Database` and `AsyncDatabase` (async via `await`/`to_thread`
  where relevant) and parity is enforced without a hand-written pair list.
- **Affected-count returns**: existing write methods (`insert_many`, `upsert_many`, `execute_many`)
  return `cur.rowcount` as `int` — D-07 follows this.

### Integration Points
- New methods live on `Database` (`pycopg/database.py`) and `AsyncDatabase` (`pycopg/async_database.py`);
  shared pure builders in `pycopg/base.py` (inherited by both).
- `__init__.py` exports unchanged (methods are on existing classes, not new symbols), unless a new
  exception is warranted (none anticipated — `ValueError` for the empty-where guard, `InvalidIdentifier`
  from validation; no new exception class expected).

</code_context>

<specifics>
## Specific Ideas

- `upsert` example contract: `db.upsert('users', {'id':1,'name':'a'}, ['id'])` →
  `{'id':1,'name':'a', ...}` (full row via `RETURNING *`), `None` on no-op.
- `paginate` example: `db.paginate('t', limit=20, offset=40, order_by=['created_at','id'], descending=True, where={'active': True})`.
- Safety posture is the throughline: the empty-where guard (D-04) and dict→`%s` binding (D-12) are
  the deliberate "ergonomic but not a foot-gun" decisions of this phase.

</specifics>

<deferred>
## Deferred Ideas

- **Raw-SQL `where=` escape hatch** (string + params alongside the dict form) — CRUD-F01, deferred.
- **Per-column ORDER BY direction** (mixed ASC/DESC via tuples or `'col DESC'` parsing) — beyond
  v0.9.0's `descending: bool`; deferred follow-up.
- **`into='dicts'|'tuples'` row-format toggle** and a tuples fetch path — explicitly rejected for
  v0.9.0 (dicts-by-default); would be its own small feature if ever wanted.
- **Keyset/cursor pagination** (CRUD-F02) and **page-envelope metadata** (total count, has_next —
  CRUD-F03) — deferred to a future release.

None of these are in Phase 34 scope — discussion stayed within the phase boundary.

</deferred>

---

*Phase: 34-crud-ergonomics*
*Context gathered: 2026-06-24*
