# Phase 53: CRUD Symmetry + Introspection Follow-ups - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-05
**Phase:** 53-crud-symmetry-introspection-follow-ups
**Areas discussed:** Read helper richness, Single-row match semantics, insert conflict handling, Introspection behavior

---

## Read helper richness (select_where / find / get / find_one)

### Q1 — How rich should the read surface be?

| Option | Description | Selected |
|--------|-------------|----------|
| SELECT * + order_by/limit/offset | Predicate + optional columns=, order_by=, limit=, offset=; reuse base.py._build_select_sql | ✓ |
| SELECT * + columns= only | Projection but no ordering/limit; push paged reads to paginate*/fetch_all | |
| Pure SELECT * predicate-only | Exact mirror of delete_where/exists; always SELECT * | |

**User's choice:** SELECT * + order_by/limit/offset (Recommended)
**Notes:** A read-by-predicate helper that can't order or cap is frustrating; the builder support already exists → near-free. Captured as D-01.

### Q2 — How do find/find_one relate to select_where/get?

| Option | Description | Selected |
|--------|-------------|----------|
| find/find_one delegate | Real thin methods forwarding to select_where/get, identical signatures + overloads, parity-visible | ✓ |
| One canonical, drop the second | Ship only select_where + get (or find + get) | |
| find/find_one primary, select_where/get secondary | Make find the documented canonical name | |

**User's choice:** find/find_one delegate (Recommended)
**Notes:** Intentional twins, NOT @deprecated_alias machinery (hard-removed v0.7.0). Both first-class, mypy-clean, born-clean. Captured as D-02.

### Q3 — Empty-predicate policy

| Option | Description | Selected |
|--------|-------------|----------|
| Allow — read all | No predicate → return all rows (SELECT * no WHERE) / any one row; consistent with count() | ✓ |
| Require a predicate | Reject empty predicate with ValueError, mirroring delete_where/update_where/exists | |

**User's choice:** Allow — read all (Recommended)
**Notes:** Reads are non-destructive → no guard, unlike the destructive helpers. Captured as D-03/D-05.

---

## Single-row match semantics (get / find_one)

### Q1 — Behavior when >1 row matches

| Option | Description | Selected |
|--------|-------------|----------|
| Return first, LIMIT 1 | Append LIMIT 1, return first row as dict \| None; never raises | ✓ |
| Raise on >1 match | Fetch up to 2, raise if >1 (Django .get() / SQLAlchemy .one_or_none() style) | |

**User's choice:** Return first, LIMIT 1 (Recommended)
**Notes:** Lenient/cheap; uniqueness is the caller's job (UNIQUE constraint / exists()/count()). Strict mode explicitly rejected — no new exception in a polish release. Captured as D-04.

---

## insert conflict handling (single-row insert)

### Q1 — Conflict handling on the singular insert

| Option | Description | Selected |
|--------|-------------|----------|
| Accept on_conflict= passthrough | Mirror insert_many's on_conflict: str \| None = None; verbatim clause; RETURNING * → dict \| None | ✓ |
| Pure insert, no conflict param | RETURNING * only; conflicts raise; upsert() is the documented conflict path | |

**User's choice:** Accept on_conflict= passthrough (Recommended)
**Notes:** Maximal symmetry with insert_many. Under DO NOTHING with a pre-existing row, RETURNING * yields no row → None (documented). Captured as D-06/D-07.

---

## Introspection behavior (column_exists / table_size)

### Q1 — table_size on a missing table

| Option | Description | Selected |
|--------|-------------|----------|
| Guard → raise TableNotFoundError | Check table_exists first (like truncate_table); raise the library's typed error | ✓ |
| Return None/0 for missing table | Mirror row_count's lenient missing→0 behavior | |
| Let pg error propagate | No guard; leak raw psycopg UndefinedTable | |

**User's choice:** Guard → raise TableNotFoundError (Recommended)
**Notes:** Consistent, typed, testable; don't conflate "empty" with "absent". column_exists mirrors table_exists via information_schema.columns. Captured as D-08/D-09.

---

## Claude's Discretion

- `where` as positional-or-keyword 2nd arg on the read helpers (mirror delete_where/update_where/exists, not count's kw-only where).
- get/find_one expose columns=/order_by= but not limit=/offset= (they force LIMIT 1).
- table_size returns raw int bytes (no human-readable formatting); exact %s::regclass vs bound-text binding of the qualified name.
- @overload stub shapes (return types are fixed), numpydoc wording, injection-test structure, queries.py constant names, builder wiring — standard pattern-following.

## Deferred Ideas

None — discussion stayed within phase scope. (Strict "raise on >1 match" for get/find_one and a human-readable table_size formatter were considered and explicitly rejected in D-04/D-09, not deferred.)
