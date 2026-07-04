# Phase 53: CRUD Symmetry + Introspection Follow-ups - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the small CRUD-read and single-row-insert symmetry gaps in the flat transactional core, and complete the `db.schema.*` existence/size introspection families. Additive-only under the frozen SemVer 1.0 API — no breaking change, full sync/async parity, zero new runtime dependencies.

Delivers (CRUD-F04..F06, INTRO-F03..F04):
- **CRUD-F04** — `select_where` / `find` → `list[dict]` predicate reads (the missing read sibling of `delete_where` / `update_where` / `exists` / `count`)
- **CRUD-F05** — `get` / `find_one` → `dict | None` single-row reads (same predicate surface)
- **CRUD-F06** — `insert` (single row) with `RETURNING *`, the singular twin of `insert_many` / `upsert`
- **INTRO-F03** — `db.schema.column_exists`, completing `table_exists` / `schema_exists` / `database_exists`
- **INTRO-F04** — `db.schema.table_size` (`pg_total_relation_size`), complementing `row_count`

**Not in scope:** any new subsystem; any breaking change to shipped signatures; any new runtime dependency; any change to the predicate mechanics (locked by Phase 50's `_resolve_predicate`, D-01..D-04); a strict "raise on >1 match" mode for `get`/`find_one` (rejected — see D-04).

</domain>

<decisions>
## Implementation Decisions

### CRUD-F04 — `select_where` / `find` read surface
- **D-01:** **Rich single-SELECT shape.** `select_where` accepts the predicate (dict `where` **or** raw `where_sql`/`where_params` via `_resolve_predicate`) PLUS optional keyword-only `columns=` (projection; `None` → `SELECT *`), `order_by=`, `limit=`, `offset=`. Reuse the existing `_build_select_sql` builder ([base.py](../../../pycopg/base.py) ~line 290) which already emits `ORDER BY` / `LIMIT` / `OFFSET` — near-free. Rationale: a read-by-predicate helper that can't order or cap results is frustrating; heavy paged reads still route to the shipped `paginate*`/`fetch_all`, but the common "filter + order + top-N" case must be one call. Returns `list[dict]`.
- **D-02:** **`find` / `find_one` are real delegating twins, NOT aliases.** Ship `find` as a concrete `def find(...)` that forwards to `select_where` with an **identical** signature (and `find_one` → `get`), plus matching `@overload` stubs so `mypy --strict` and the parity gate see them as first-class methods on both accessor classes. These are **intentional twins** — do NOT use the `@deprecated_alias` machinery (hard-removed in v0.7.0) or PEP 562 module aliases. Both names are documented, supported, born-clean (kw-only after the positional predicate, no `where=` shim).
- **D-03:** **Empty predicate is legal for reads → read all.** With no `where`/`where_sql`, `select_where`/`find` emit `SELECT ... FROM t` with no `WHERE` (still honoring `order_by`/`limit`/`offset`) and return all rows. Consistent with `count()`'s no-predicate = count-all, and with `_resolve_predicate` returning an empty fragment as legal for reads. Reads are non-destructive, so NO empty-predicate guard — unlike `delete_where`/`update_where`/`exists`, which reject an empty predicate.

### CRUD-F05 — `get` / `find_one` single-row semantics
- **D-04:** **First match, `LIMIT 1`, no raise on multiple.** On >1 match, append `LIMIT 1` and return the first row as `dict | None` (no exception). Lenient and cheap; uniqueness is the caller's job (UNIQUE constraint, or `exists()`/`count()`). **Rejected:** the strict Django-`.get()` / SQLAlchemy-`.one_or_none()` "raise on >1" mode — it adds a new exception/behavior to a polish release for little gain. With `order_by=` the "first" is deterministic.
- **D-05:** **`get`/`find_one` expose `columns=` and `order_by=` but NOT `limit=`/`offset=`** — they force `LIMIT 1` internally, so exposing a caller `limit`/`offset` would be contradictory. Same predicate surface (dict `where` / `where_sql` / `where_params`) and same empty-predicate-allowed policy as D-03 (no predicate → returns any one row).

### CRUD-F06 — single-row `insert`
- **D-06:** **`insert` carries `on_conflict=` passthrough for full symmetry with `insert_many`.** Signature mirrors the batch twin: `insert(table, row, *, schema="public", on_conflict: str | None = None)`. The `on_conflict` clause (e.g. `"DO NOTHING"`, `"DO UPDATE SET ..."`) is threaded verbatim into the same `_build_insert_sql` path `upsert` uses ([database.py:1007](../../../pycopg/database.py#L1007)), then `+ " RETURNING *"`.
- **D-07:** **Return `dict | None`.** `RETURNING *` returns the inserted row as a `dict`; under `on_conflict="DO NOTHING"` with a pre-existing conflicting row, no row is returned → `None`. Document this `None` path in the docstring (mirrors `upsert`'s documented `dict | None`).

### INTRO-F03 — `column_exists`
- **D-08:** **Mirror `table_exists` mechanically.** Signature `column_exists(table, column, *, schema="public") -> bool`. Add a parametrized SQL constant to `pycopg/queries.py` (against `information_schema.columns`, matching `table_schema`/`table_name`/`column_name`), all three values bound as `%s` (no identifier interpolation — same shape as `TABLE_EXISTS`/`GET_COLUMNS`). Returns `len(result) > 0`.

### INTRO-F04 — `table_size`
- **D-09:** **Guarded, typed, raw-bytes.** `table_size(name, *, schema="public") -> int`. Check `table_exists` first (same guard pattern as [truncate_table](../../../pycopg/schema.py#L438)) and raise the library's `TableNotFoundError` with a clear `'schema.table'` message on a missing table — do NOT leak a raw psycopg `UndefinedTable`, and do NOT silently return 0 (that conflates "empty" with "absent"). On success, run `SELECT pg_total_relation_size(%s)` binding the qualified `'schema.table'` name (regclass-resolved) and return the raw `int` byte count (total size incl. indexes + TOAST). No human-readable/pretty formatting — raw bytes is the primitive.

### Claude's Discretion
- `where` is a **positional-or-keyword** 2nd arg on `select_where`/`get`/`find`/`find_one` (mirroring `delete_where`/`update_where`/`exists`, NOT `count`'s kw-only `where`) — so `select_where("users", {"active": True})` works.
- Exact `@overload` stub shapes for `into=`-free reads (return type is fixed: `list[dict]` for `select_where`/`find`, `dict | None` for `get`/`find_one`), numpydoc wording, injection-test structure, `queries.py` constant names, and `_build_insert_sql`/`_build_select_sql` wiring — standard pattern-following, no user decision needed.
- Whether `table_size` binds the name as `%s::regclass` or resolves `pg_total_relation_size('schema.table')` via a bound text arg — either is fine as long as identifiers are never f-string-interpolated from user input (precedent: Phase 48 per-chunk compress used `%s::regclass`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` — CRUD-F04/F05/F06 + INTRO-F03/F04 definitions and the standing bar (parity, `validate_identifiers`-first, zero new deps, cov ≥95%, `mypy --strict` 0/18, interrogate 100%, Sphinx `-W`). Out-of-scope table prevents scope creep.
- `.planning/ROADMAP.md` §"Phase 53: CRUD Symmetry + Introspection Follow-ups" — goal + 5 success criteria.

### Live pattern source (the shipped code to mirror — mirror BOTH sync and async classes)
- `pycopg/base.py` — the shared `QueryMixin`. **Reuse verbatim:** `_resolve_predicate` (line 329, the D-01..D-04 predicate guard for `where`/`where_sql`/`where_params`), `_build_where_dict` (line 300), `_build_select_sql` (~line 290, already supports `order_by`/`limit`/`offset` — the read builder for D-01).
- `pycopg/database.py` — sync flat core. **Mirror:** `delete_where`/`update_where` (lines 1015/1075, the predicate-consumer template), `exists`/`count` (lines 1144/1204, the read-that-resolves-predicate template), `upsert` (line 952, single-row `RETURNING *` via `_build_insert_sql`), `insert_many` (line 868, the `on_conflict=` shape), `fetch_all`/`fetch_one` (lines 1475/1432, dict-fetch execution).
- `pycopg/async_database.py` — async flat core. Async mirrors of all the above already exist (`_resolve_predicate` call sites at lines 1033/1093/1987/2047 etc.). Every new method MUST be added here too with an identical kw-only signature.
- `pycopg/schema.py` — `db.schema.*` accessor (sync + async). **Mirror:** `table_exists` (line 336) for `column_exists`; `row_count` (line 461) + `truncate_table`'s existence guard (line 438) for `table_size`.
- `pycopg/queries.py` — parametrized SQL constants (`TABLE_EXISTS`, `GET_COLUMNS`, `ROW_COUNT`). Add `COLUMN_EXISTS` and the `table_size` query here.
- `pycopg/exceptions.py` — `TableNotFoundError` (reused by D-09; already raised by `truncate_table`).
- `tests/test_parity.py` — enforces sync/async accessor parity (`test_accessor_parity` / `test_accessor_parameter_kind_parity`); new methods MUST appear on both classes with identical kw-only signatures.

### Docs to update (helper reference)
- `docs/api-reference.md` — API reference surface; the 5 new helpers get documented here.
- `README.md` — the CRUD/introspection usage examples may want the new reads/insert.

### Prior-phase precedent (do not re-litigate)
- `.planning/phases/52-spatial-finish/52-CONTEXT.md` — sibling v1.2.0 phase; the "born clean, no `where=` shim, parity, injection-test-per-helper" conventions apply identically here.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_resolve_predicate` (base.py:329) — the entire `where` / `where_sql` / `where_params` surface for CRUD-F04/F05 is already built and tested (Phase 50, D-01..D-04). Returns `("", [])` for no source, which is exactly the "read all" path (D-03). Reuse verbatim.
- `_build_select_sql` (base.py ~290) — already emits `SELECT {cols} FROM {schema}.{table}` with optional `ORDER BY` / `LIMIT` / `OFFSET`. Extend/reuse for `select_where` (D-01) rather than hand-rolling.
- `_build_insert_sql` + `" RETURNING *"` (the exact `upsert` path, database.py:1007) — reuse for single-row `insert` (D-06/D-07).
- `table_exists` (schema.py:336) + `TABLE_EXISTS` constant — copy shape for `column_exists`; also the existence-guard for `table_size` (schema.py:438 `truncate_table`).

### Established Patterns
- Every flat-core helper = validate_identifiers-first (table/schema/columns), user values bound as `%s`, sync method + async mirror + a dedicated injection test. New 1.0-era methods are "born clean": kw-only after the positional args, NO `where=` deprecated alias.
- `db.schema.*` introspection helpers delegate to `self._db.execute(queries.CONST, [schema, name, ...])` — parametrized, no identifier interpolation, return-shape mapped in Python.
- `mypy --strict` (blocking gate) — reads have a fixed return type (`list[dict]` / `dict | None`), so `@overload` is only needed if a param changes the return type; keep signatures monomorphic where possible.

### Integration Points
- Both `Database` (database.py) and `AsyncDatabase` (async_database.py) gain `select_where`/`find`/`get`/`find_one`/`insert` (parity gate).
- Both `SchemaAccessor` and `AsyncSchemaAccessor` (schema.py) gain `column_exists`/`table_size` (parity gate).
- Coverage ratchet ≥95% (baseline 96.78% after Phase 52) — new helpers need tests; interrogate 100% requires numpydoc docstrings; Sphinx `-W` clean requires the docs surfaces to reference the new methods.

</code_context>

<specifics>
## Specific Ideas

- The whole phase is symmetry-completion: for each new helper there is an already-shipped sibling to mirror mechanically (`select_where`↔`delete_where`/`exists`, `insert`↔`insert_many`/`upsert`, `column_exists`↔`table_exists`, `table_size`↔`row_count`). The mirror IS the spec.
- `get`/`find_one` = `select_where`/`find` + forced `LIMIT 1` + `.fetchone()` return — implement `get` on top of the same builder path rather than a separate SQL builder.
- PostgreSQL function/catalog reference: `information_schema.columns` (column_exists), `pg_total_relation_size(regclass)` → bigint bytes incl. indexes + TOAST (table_size).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (The strict "raise on >1 match" mode for `get`/`find_one` was considered and explicitly rejected in D-04, not deferred; a human-readable `table_size` formatter was considered and rejected in D-09 — raw bytes is the primitive.)

</deferred>

---

*Phase: 53-crud-symmetry-introspection-follow-ups*
*Context gathered: 2026-07-05*
