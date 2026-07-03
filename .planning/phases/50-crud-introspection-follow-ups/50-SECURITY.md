---
phase: 50
slug: crud-introspection-follow-ups
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-04
---

# Phase 50 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|----------------|
| caller → `Database`/`AsyncDatabase` API (predicate helpers) | `table`/`schema` identifiers, dict `where` values, raw `where_sql` fragment + `where_params` cross into `delete_where`/`update_where`/`exists`/`count`/`paginate` | untrusted identifiers (validated) + untrusted SQL text (accepted escape hatch) + untrusted bound values |
| caller → `Database`/`AsyncDatabase` API (pagination) | `order_by` identifiers, `after` cursor values, optional `where`/`where_sql`+`where_params` cross into `paginate_page`/`paginate_keyset` | untrusted identifiers (validated) + untrusted bound values |
| caller → `SchemaAccessor`/`AsyncSchemaAccessor` API (matview introspection) | matview `name`/`schema` identifiers cross into `materialized_views`/`materialized_view_columns` as pg_catalog query inputs | untrusted identifiers (validated + bound) |
| caller → `SchemaAccessor`/`AsyncSchemaAccessor` API (describe) | table/schema identifiers (reused, pre-existing bound helpers) + `into` output-selector literal | untrusted identifiers (bound, no new SQL) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-50-01 | Tampering | raw `where_sql` fragment (plan 01) | accept | Intentional escape hatch: fragment passed verbatim, never run through `validate_identifiers`; `where_params` bound `%s`; docstring states the trust model on every touched method. Verified: `pycopg/base.py` `_resolve_predicate` (:378-388) returns `where_sql` unmodified; `grep -c "validate_identifiers(where_sql" pycopg/base.py` = 0. | closed |
| T-50-02 | Tampering | `where_params` binding | mitigate | Values bound as `%s` positional params in `_resolve_predicate`, never interpolated. Verified: `pycopg/base.py:385` `return where_sql, list(where_params or [])`; params flow to `cur.execute(sql, pred_params)` / `self.fetch_val(sql, pred_params)` in all 5 helpers (`pycopg/database.py:1063-1072,1141,1201-1202,1259`; async mirrors `pycopg/async_database.py`). Injection test `TestWhereSqlValueInjection` (`tests/test_sql_injection.py:262-311`) — 50 param cases, all pass live (`PGDATABASE=pycopg_test3`). Independently re-verified live with a `; DROP TABLE` payload via `where_params` — no injection, only an expected non-existent-table error. | closed |
| T-50-03 | Tampering / DoS | unpredicated `delete_where`/`update_where` | mitigate | Destructive guard raises `ValueError` when `not frag` (neither dict nor `where_sql` present) before `validate_identifiers` and before any cursor is opened. Verified: `pycopg/database.py:1063-1068` (`delete_where`), `:1128-1134` (`update_where`); async mirrors `pycopg/async_database.py:2035-2040,2100-2106`. Live-verified: `db.delete_where("nonexistent_table")` raises `ValueError` (never reaches the DB) — table doesn't exist so a DB round-trip would otherwise surface a different error class. | closed |
| T-50-04 | Tampering | keyset `order_by` columns | mitigate | `_build_keyset_where` calls `validate_identifiers(*order_cols)` as line 1. Verified: `pycopg/base.py:434`; injection test `test_keyset_order_by_validated` in `TestKeysetInjection` (`tests/test_sql_injection.py:313-334`), passes live. Independently re-verified live: `QueryMixin._build_keyset_where(["id; DROP TABLE users; --"], (1,), False)` raises `InvalidIdentifierError`. | closed |
| T-50-05 | Tampering | keyset `after` values in row-value RHS | mitigate | `after` values bound as `%s` placeholders (`list(after)`), never interpolated. Verified: `pycopg/base.py:438`; consumed via `params.extend(keyset_params)` then `cur.execute(sql, params)` in `paginate_keyset` (`pycopg/database.py:1855-1887`, async mirror `pycopg/async_database.py`). Injection test in `TestKeysetInjection` asserts bound, not interpolated. | closed |
| T-50-06 | Tampering | raw `where_sql` composed onto page query | accept | Inherits plan-01 escape-hatch posture — caller owns the fragment, `where_params` bound `%s`, resolved via `_resolve_predicate`. Verified: `paginate_page`/`paginate_keyset` both call `self._resolve_predicate(where, where_sql, where_params)` (`pycopg/database.py:1695,1856`; async mirrors present) — same resolver as T-50-01/02, no separate/weaker code path. | closed |
| T-50-07 | Tampering | matview `name`/`schema` in `materialized_view_columns`/`materialized_views` | mitigate | `validate_identifiers(name, schema)` as line 1 AND name/schema passed only as bound `%s` params to the pg_catalog query, never interpolated. Verified: `pycopg/schema.py:848-850` (`materialized_views`), `:881-882` (`materialized_view_columns`); async mirrors `:1752,1786`; SQL constants use `%s` placeholders only (`pycopg/queries.py:197-231`, no f-string interpolation). Injection test `TestMaterializedViewIdentifierInjection` (`tests/test_sql_injection.py:336-374`), passes live. Independently re-verified live: `db.schema.materialized_view_columns("mv; DROP TABLE users; --")` raises `InvalidIdentifierError`. | closed |
| T-50-08 | Tampering | `describe` table/schema identifiers | mitigate | `describe` reuses existing standalone helpers (`table_info`/`primary_key`/`foreign_keys`/`list_indexes`) which pass name/schema as bound `%s`; `into=` introduces no new SQL (pure Python reshape of already-fetched output). Verified: `pycopg/schema.py:944-958` — `flat` dict built entirely from calls to the four pre-existing helpers; `into` dispatch (`:950-958`) only wraps/reshapes `flat`, no new `self._db.execute` call. `table_info` itself binds `[schema, name]` as `%s` (`pycopg/schema.py:459`). | closed |
| T-50-09 | Information disclosure | `into="dataframe"` output | accept | Reshapes only the already-authorized `columns` section; no new data surfaced beyond what `table_info` already returns (wrap, don't reshape). Verified: `pycopg/schema.py:955` `return pd.DataFrame(flat["columns"])` — sourced solely from `flat["columns"]` (= `table_info()` output), no additional query or field added. | closed |
| T-50-SC | Tampering (supply chain) | package installs | accept | Zero new packages this phase; pandas already a runtime dependency (used by plan 04's `describe(into="dataframe")`). Verified: `git log --oneline <phase-50-commit-range> -- pyproject.toml uv.lock` returns no commits — neither file was touched anywhere in Phase 50 (plans 01-04); `pyproject.toml` `dependencies` unchanged (`psycopg`, `psycopg_pool`, `sqlalchemy`, `pandas`, `tenacity`). | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Unregistered Flags

None. No `## Threat Flags` section present in any of `50-01-SUMMARY.md` through `50-04-SUMMARY.md` (grep confirmed) — no new attack surface was flagged by the executor beyond the plan-time register, and no gap was found during independent verification either.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|--------------|------|
| AR-50-01 | T-50-01 | `where_sql` is a documented, intentional raw-SQL escape hatch (C-02) for predicates the dict `where` form cannot express (e.g. `age > %s AND status = ANY(%s)`). The caller owns the SQL text; only `where_params` are treated as untrusted and are always bound `%s`. Trust model documented in the docstring of every touched method (`delete_where`/`update_where`/`exists`/`count`/`paginate`, both classes). Same posture as the pre-existing spatial `filter=` escape hatch. | Phase 50 plan (50-01-PLAN.md `<threat_model>`) | 2026-07-03 |
| AR-50-02 | T-50-06 | `paginate_page`/`paginate_keyset` compose the same `where_sql` escape hatch onto the page query via the identical `_resolve_predicate` resolver used by T-50-01 — no new/weaker code path is introduced for pagination. | Phase 50 plan (50-02-PLAN.md `<threat_model>`) | 2026-07-03 |
| AR-50-03 | T-50-09 | `describe(into="dataframe")` reshapes only the `columns` section already returned by `table_info()` (and therefore already returned by the frozen v0.9.0 `describe(into="dict")` default) into a `pandas.DataFrame`. No new SQL, no new fields, no data beyond what a caller could already retrieve. | Phase 50 plan (50-04-PLAN.md `<threat_model>`) | 2026-07-04 |
| AR-50-04 | T-50-SC | Zero new packages added across all 4 plans of Phase 50; `pandas` (used by `describe(into="dataframe")`) was already a hard runtime dependency prior to this phase. Confirmed via `git log` — `pyproject.toml`/`uv.lock` untouched by any Phase 50 commit. | Phase 50 plans (all 4, `<threat_model>`) | 2026-07-03/04 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|-----------------|--------|------|--------|
| 2026-07-04 | 10 | 10 | 0 | gsd-security-auditor |

**Verification method:** Every `mitigate` threat verified by locating the actual guard/validation call in the cited implementation file (not inferred from code structure), cross-checked with the corresponding injection test executed live against `PGDATABASE=pycopg_test3` (`tests/test_sql_injection.py -k "where_sql or keyset or materialized_view"` — 50 passed), plus independent ad-hoc live probes (evil-payload `delete_where`, `_build_keyset_where`, `materialized_view_columns` calls) reproducing the guard failures outside the test suite. Every `accept` threat verified by confirming the accepted-risk rationale is truthful against the actual source (fragment passed verbatim / dataframe sourced only from `table_info` / no new deps via `git log` on `pyproject.toml`+`uv.lock`) and recorded in the Accepted Risks Log above. Both `Database`/`SchemaAccessor` and their async twins were checked for every threat (sync/async parity, C-01) — no threat closed on sync-only evidence.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-04
