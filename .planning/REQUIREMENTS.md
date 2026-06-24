# Requirements: pycopg v0.9.0 — CRUD ergonomique + introspection enrichie

**Defined:** 2026-06-24
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

> Additive convenience over the existing API. Low risk. Builder-pur + accessor pattern
> (`validate_identifiers` first, user values as `%s`, pure `(sql, params)` builders), full
> sync/async parity (Core Value), **zero new runtime dependencies**, coverage ratchet held ≥94%.
> Placement locked at cadrage (2026-06-24): CRUD helpers land on the flat transactional core
> next to their analogs (`upsert_many`/`insert_many`/`fetch_one`); introspection helpers extend
> the existing `db.schema.*` accessor — **NO `db.meta.*` carve**.

## v1 Requirements

Requirements for the v0.9.0 release. Each maps to roadmap phases.

### CRUD Ergonomics

Convenience over the existing transactional core. Predicate arguments (`where=`) use a
**dict of equality conditions** (`{col: val, ...}` → AND-ed equality), columns validated via
`validate_identifiers`, values bound as `%s`. Singular ergonomic complements to the existing
`*_many` batch methods.

- [x] **CRUD-01**: User can upsert a single row with `db.upsert(table, row, conflict_columns, ...)` (singular complement to `upsert_many`), returning the affected/returned row
- [x] **CRUD-02**: User can delete rows matching a condition with `db.delete_where(table, where={...})`, returning the number of rows deleted
- [x] **CRUD-03**: User can update rows matching a condition with `db.update_where(table, values={...}, where={...})`, returning the number of rows updated
- [x] **CRUD-04**: User can check row existence with `db.exists(table, where={...}) -> bool` without fetching rows
- [x] **CRUD-05**: User can count rows with `db.count(table, where=None|{...}) -> int`
- [x] **CRUD-06**: User can fetch a page of rows with `db.paginate(table, limit, offset=0, order_by=..., where=None)` returning the page rows
- [ ] **CRUD-07**: User can fetch query results as `list[dict]` (dict-fetch) instead of tuples, for ergonomic row access
- [x] **CRUD-08**: Every new CRUD helper has a working, tested `AsyncDatabase` equivalent with identical signature, enforced by `test_accessor_parity`

### Schema Introspection

Enriched read-only introspection extending the existing `db.schema.*` accessor (which already
has `table_info`, `row_count`, `list_columns`, `columns_with_types`, `list_indexes`,
`list_constraints`). Each helper reads `information_schema` / `pg_catalog`, validates identifiers,
and accepts an optional `schema="public"` argument.

- [ ] **INTRO-01**: User can get a table's primary-key column(s) with `db.schema.primary_key(table, schema="public")`
- [ ] **INTRO-02**: User can get a table's foreign keys with `db.schema.foreign_keys(table, schema="public")`, each entry naming the local column(s), referenced table, and referenced column(s)
- [ ] **INTRO-03**: User can list sequences with `db.schema.sequences(schema="public")`
- [ ] **INTRO-04**: User can list views with `db.schema.views(schema="public")`
- [ ] **INTRO-05**: User can get a consolidated table description with `db.schema.describe(table, schema="public")` (columns + types, primary key, foreign keys, indexes) — the all-in-one introspection helper
- [ ] **INTRO-06**: Every new introspection helper has a working, tested `AsyncDatabase` (`AsyncSchemaAccessor`) equivalent with identical signature, enforced by `test_accessor_parity`

### Release

- [ ] **REL-09**: v0.9.0 released to PyPI via OIDC trusted publishing — version bumped in both sources, CHANGELOG `[0.9.0]` Added-only (purely additive, no MIGRATION needed), docs surfaces updated (README method counts, api-reference, relevant `docs/*.md`), all gates green (coverage ratchet ≥94%, interrogate ≥95, Sphinx `-W` clean, `-W error::DeprecationWarning` green), tagged, clean-venv import smoke confirmed

## v2 Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### CRUD / Introspection follow-ups

- **CRUD-F01**: Raw-SQL escape hatch for `where=` (string + params) alongside the dict form — deferred; dict-of-equality covers the common case for v0.9.0
- **CRUD-F02**: `paginate` keyset/cursor pagination (seek method) in addition to `limit`/`offset`
- **CRUD-F03**: `paginate` returning a page envelope with total count + has_next metadata
- **INTRO-F01**: `describe` output as a rich dataclass / DataFrame rendering
- **INTRO-F02**: `materialized_views()` and per-view column introspection

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| `db.meta.*` accessor carve | Locked at cadrage 2026-06-24 — stay purely additive on `db.schema.*`; no new deprecation cycle on a just-cleaned surface (resolves the v0.6.0 open question) |
| Raw-SQL `where=` strings | Dict-of-equality predicates cover the common case; raw-SQL escape hatch deferred to CRUD-F01 (pushes injection-safety to the caller) |
| ORM / model layer | Standing project boundary — duplicates SQLAlchemy, maintenance nightmare |
| Query builder / fluent API | Standing project boundary — never as good as SQLAlchemy Core |
| New runtime dependencies | Milestone constraint — convenience helpers build on existing psycopg/pandas surface only |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CRUD-01 | Phase 34 | Complete |
| CRUD-02 | Phase 34 | Complete |
| CRUD-03 | Phase 34 | Complete |
| CRUD-04 | Phase 34 | Complete |
| CRUD-05 | Phase 34 | Complete |
| CRUD-06 | Phase 34 | Complete |
| CRUD-07 | Phase 34 | Pending |
| CRUD-08 | Phase 34 | Complete |
| INTRO-01 | Phase 35 | Pending |
| INTRO-02 | Phase 35 | Pending |
| INTRO-03 | Phase 35 | Pending |
| INTRO-04 | Phase 35 | Pending |
| INTRO-05 | Phase 35 | Pending |
| INTRO-06 | Phase 35 | Pending |
| REL-09 | Phase 36 | Pending |

**Coverage:**

- v1 requirements: 15 total
- Mapped to phases: 15 / Unmapped: 0

---
*Requirements defined: 2026-06-24*
*Last updated: 2026-06-24 — traceability filled by roadmapper (Phases 34-36)*
