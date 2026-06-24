# Phase 34: CRUD Ergonomics - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 34-crud-ergonomics
**Areas discussed:** upsert return shape, empty-where guard, dict-fetch (CRUD-07), paginate ordering, order direction, predicate return types

---

## upsert return shape (CRUD-01)

| Option | Description | Selected |
|--------|-------------|----------|
| RETURNING * → dict, None on no-op | `INSERT ... ON CONFLICT DO UPDATE ... RETURNING *`, return dict; None on DO NOTHING / no row; `conflict_columns` required | ✓ |
| RETURNING * → dict, always a row | Always DO UPDATE so a row always returns; return type is `dict` not `dict\|None` | |
| Return affected count (int) | Mirror `upsert_many`'s int return; loses generated/defaulted columns | |

**User's choice:** RETURNING * → dict, None on no-op
**Notes:** Most informative; mirrors `upsert_many` (conflict_columns required). The singular form's value is precisely the returned/defaulted columns, so the row (not a count) is returned.

---

## Empty-where guard (CRUD-02, CRUD-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Empty where → raise (guard) | `delete_where`/`update_where` require non-empty `where`; `{}`/None raises `ValueError` pre-round-trip; count/exists still allow `where=None` | ✓ |
| Empty where → affect all rows | Empty/omitted `where` = no WHERE clause (all rows), consistent with raw SQL but a foot-gun | |

**User's choice:** Empty where → raise (guard)
**Notes:** Prevents an accidental full-table wipe/overwrite from an unintentionally-empty dict. "Affect everything" routes through the explicit `truncate_table`. Guard applies only to the destructive ops.

---

## Dict-fetch (CRUD-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Treat as satisfied + add fetch_all alias | Document dicts-by-default (`execute`/`fetch_one` already return dicts); add explicit `fetch_all(sql, params) -> list[dict]`; paginate returns dicts | ✓ |
| Add into='dicts'\|'tuples' option | Row-format toggle exposing a tuples path; scope creep over dicts-by-default | |
| No new method — document only | Mark satisfied by existing behavior; no `fetch_all`, no symmetry with `fetch_one` | |

**User's choice:** Treat as satisfied + add fetch_all alias
**Notes:** Codebase finding surfaced during discussion — the transactional core already uses psycopg's `dict_row` factory (`execute -> list[dict]`, `fetch_one -> dict|None`), so CRUD-07 is largely already met. Deliverable narrows to documenting it + a thin `fetch_all` for discoverability/symmetry.

---

## Paginate ordering (CRUD-06)

| Option | Description | Selected |
|--------|-------------|----------|
| order_by optional str\|list, validated cols | Column name or list of validated identifiers, optional; default ASC | ✓ |
| order_by required (str\|list) | Mandatory order — pagination without stable order is a bug | |
| order_by optional, supports direction tuples | `('col','DESC')` tuples / per-column direction; more surface to design now | |

**User's choice:** order_by optional str|list, validated cols
**Notes:** Validated identifiers (not raw SQL), optional. Default ASC. See "Order direction" below for how DESC is expressed.

---

## Order direction (follow-up to paginate ordering)

| Option | Description | Selected |
|--------|-------------|----------|
| Add a descending: bool param | Whole-clause direction via `descending=False` default; columns stay pure identifiers | ✓ |
| Allow 'col DESC' via split-and-validate | Parse `'created_at DESC'`, validate column, whitelist ASC/DESC; per-column direction + parsing logic | |
| ASC only for v0.9.0 | Ascending only; descending deferred — limiting for 'newest first' | |

**User's choice:** Add a descending: bool param
**Notes:** Columns remain pure validated identifiers; direction is a separate boolean applied to the whole ORDER BY. Per-column mixed direction deferred.

---

## Predicate return types (CRUD-02..05)

| Option | Description | Selected |
|--------|-------------|----------|
| Standard: bool / int / int / int | `exists -> bool` (via `SELECT EXISTS(...)`), `count -> int`, `delete_where -> int`, `update_where -> int` (rowcount) | ✓ |
| Let me adjust one of these | Different return for any of the four (e.g. delete_where returning RETURNING rows) | |

**User's choice:** Standard: bool / int / int / int
**Notes:** Consistent with `insert_many`/`upsert_many` returning affected counts; `exists` implemented as `SELECT EXISTS(SELECT 1 ...)` so it never fetches rows.

---

## Claude's Discretion

- Exact private builder names/locations and how the where-dict → `(sql, params)` helper is factored (`base.py` vs `database.py`); whether `paginate` composes `_build_select_sql` or a new builder — as long as builders stay pure and validate identifiers before interpolation.
- Numpydoc docstring wording (shallow, no Examples — project convention).

## Deferred Ideas

- Raw-SQL `where=` escape hatch (CRUD-F01).
- Per-column ORDER BY direction (mixed ASC/DESC).
- `into='dicts'|'tuples'` row-format toggle / tuples fetch path (explicitly rejected for v0.9.0).
- Keyset/cursor pagination (CRUD-F02); page-envelope metadata — total count, has_next (CRUD-F03).
