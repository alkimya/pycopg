# Phase 35: Schema Introspection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 35-schema-introspection
**Areas discussed:** Return shapes, describe() shape, SQL source, Edge cases

---

## Return shapes — `primary_key` (INTRO-01)

| Option | Description | Selected |
|--------|-------------|----------|
| list[str] of columns | `['id']` / `['org_id','user_id']`; `[]` if no PK; mirrors `list_columns` | |
| dict (name + columns) | `{'constraint_name','columns':[...]}` or `None` if no PK; mirrors `table_info`/`list_constraints` | ✓ |

**User's choice:** dict (name + columns)
**Notes:** Distinguishes "no PK" as `None`, names the constraint, composite-safe via the `columns` list.

---

## Return shapes — `foreign_keys` (INTRO-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Core fields only | `{'constraint_name','columns','referenced_table','referenced_columns'}` — exactly the REQUIREMENTS contract | ✓ |
| Core + referential actions | adds `on_delete`/`on_update`/`referenced_schema` | |

**User's choice:** Core fields only
**Notes:** ON DELETE/UPDATE actions deferred (can be added later without breaking the shape). Empty list `[]` when no FKs.

---

## Return shapes — `sequences` & `views` (INTRO-03, INTRO-04)

| Option | Description | Selected |
|--------|-------------|----------|
| list[str] of names | just object names; mirrors `list_tables`/`list_columns` | ✓ |
| list[dict] with metadata | sequence data_type/start_value; view definition SQL | |

**User's choice:** list[str] of names
**Notes:** Consistent with the existing name-list precedent; schema-level (not consumed by `describe`).

---

## describe() shape (INTRO-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Flat dict composing helpers | `{'columns','primary_key','foreign_keys','indexes'}`, each sub-value the standalone helper's exact shape; composes `table_info`/new helpers/`list_indexes` | ✓ |
| Flat dict, own queries | same keys but describe runs its own SQL — risks shape drift, duplicate SQL | |

**User's choice:** Flat dict composing helpers
**Notes:** Minimal new SQL, guaranteed-consistent shapes, no drift. Sub-values exactly match the standalone helpers.

---

## SQL source

| Option | Description | Selected |
|--------|-------------|----------|
| Per-helper, correctness-first | pick best source per helper (matches existing mixed precedent); pg_catalog for PK/FK ordering, information_schema for sequences, matview-excluding views | ✓ |
| information_schema only | ANSI portability, but composite key ordering is fiddly | |
| pg_catalog only | Postgres-native, but sequences/views less natural; hand-rolled matview exclusion | |

**User's choice:** Per-helper, correctness-first
**Notes:** Continues the existing accessor's mixed-source approach. Planner picks exact source per helper.

---

## Edge cases — empty / missing table

| Option | Description | Selected |
|--------|-------------|----------|
| Empty result, no pre-check | no PK→`None`, no FKs→`[]`, missing table→same empty/None; matches existing `list_columns` | ✓ |
| Raise on missing table | pre-check + raise; extra round-trip, diverges from existing helpers, new error decision | |

**User's choice:** Empty result, no pre-check
**Notes:** Cheapest, consistent with existing helpers, no new exception class.

---

## Edge cases — object filtering (`sequences` / `views`)

| Option | Description | Selected |
|--------|-------------|----------|
| Scope to the given schema only | schema-arg filter; sequences include SERIAL/identity seqs; views exclude matviews | ✓ |
| Include matviews in views() | regular + materialized views (relkind 'v','m') | |

**User's choice:** Scope to the given schema only
**Notes:** Predictable, matches `list_tables` scoping; excluding matviews keeps the deferred INTRO-F02 `materialized_views()` helper meaningful.

---

## Claude's Discretion

- Exact SQL text of each new `queries.py` constant (column-ordering joins, relkind filters).
- Whether `describe` calls the public methods or shares private builders (shapes must match standalone helpers exactly).
- Docstring wording (numpydoc, shallow, no Examples — project convention).
- Whether to add an optional named-surface frozenset test for the 5 new methods.

## Deferred Ideas

- ON DELETE / ON UPDATE referential actions (+ `referenced_schema`) on `foreign_keys` — not v0.9.0.
- `materialized_views()` + per-view column introspection — INTRO-F02, v2.
- `describe` as a rich dataclass / DataFrame rendering — INTRO-F01, v2.
