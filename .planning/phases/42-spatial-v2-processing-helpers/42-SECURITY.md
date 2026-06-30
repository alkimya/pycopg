---
phase: 42
slug: spatial-v2-processing-helpers
status: secured
threats_total: 11
threats_closed: 11
threats_open: 0
register_authored_at_plan_time: true
asvs_level: 1
created: 2026-06-29
---

# Security Audit — Phase 42: Spatial v2 Processing Helpers

## Verdict

SECURED. All 11 threats in the register (across plans 42-01, 42-02, 42-03) verified as closed.
Zero OPEN_THREATS. No unregistered threat flags in any SUMMARY.md.

---

## Threat Verification Table

| Threat ID | Category | Disposition | Status | Evidence (file:line) |
|-----------|----------|-------------|--------|----------------------|
| T-42-01 | Tampering — identifier injection (binary builders: table/schema/geom/other_geom) | mitigate | CLOSED | `spatial.py:1287` — `validate_identifiers(table, schema, geom, other_geom)` is the first executable statement of `_build_binary_geom_sql`; shared by all 3 binary builders. Injection tests at `test_spatial.py:576–652` (6 tests: `test_union_invalid_table`, `test_union_invalid_other_geom`, `test_difference_invalid_table`, `test_difference_invalid_other_geom`, `test_intersection_invalid_table`, `test_intersection_invalid_other_geom`) all assert `InvalidIdentifierError`. |
| T-42-02 | Tampering — columns injection (binary builders via `_cols_str`) | mitigate | CLOSED | `spatial.py:1288–1289` — `if columns: validate_identifiers(*columns)` immediately after line 1 in `_build_binary_geom_sql`. Columns-injection tests at `test_spatial.py:1851–1864` (`test_union_columns_validated`, `test_difference_columns_validated`, `test_intersection_columns_validated`). |
| T-42-03 | Tampering — value injection (binary trio: params always `[]`) | accept | CLOSED | `spatial.py:1296` — `return sql, []`; the binary builders emit no `%s` values. `filter=`/`order_by=` are documented as raw-SQL caller responsibility (pre-existing contract identical to `buffer`/`transform`). Rationale confirmed reasonable: no user values exist to bind; the identifiers are fully validated. |
| T-42-04 | Tampering — identifier injection (unary builders: build_simplify_sql/build_convex_hull_sql/build_make_valid_sql) | mitigate | CLOSED | `spatial.py:1568` — `validate_identifiers(table, schema, geom)` is the first executable statement of `build_simplify_sql` (comment `# LINE 1 — security invariant`). Same at `spatial.py:1634` for `build_convex_hull_sql` and `spatial.py:1717` for `build_make_valid_sql`. Per-builder injection tests at `test_spatial.py:699` (`test_simplify_invalid_table`), `test_spatial.py:732` (`test_convex_hull_invalid_table`), `test_spatial.py:796` (`test_make_valid_invalid_table`), all asserting `InvalidIdentifierError`. |
| T-42-05 | Tampering — columns injection (unary builders via `_cols_str`) | mitigate | CLOSED | `spatial.py:1569–1570`, `1635–1636`, `1718–1719` — `if columns: validate_identifiers(*columns)` immediately after `validate_identifiers(table, schema, geom)` in each unary builder. Columns-injection tests at `test_spatial.py:1866–1879` (`test_simplify_columns_validated`, `test_convex_hull_columns_validated`, `test_make_valid_columns_validated`). Additional `TestBuilders`-class injection tests at `test_spatial.py:699–804` include `test_simplify_invalid_columns`, `test_convex_hull_invalid_columns`, `test_make_valid_invalid_columns`. |
| T-42-06 | Tampering — value injection via numeric tolerance in `build_simplify_sql` | mitigate | CLOSED | `spatial.py:1578–1582` — both branches use `%s` exclusively: `ST_SimplifyPreserveTopology(t.{geom}, %s)` with `params=[tolerance]` and `ST_Simplify(t.{geom}, %s, %s)` with `params=[tolerance, preserve_collapsed]`. No `int()` shortcut or f-string interpolation of the tolerance value. SQL-shape test at `test_spatial.py:656–664` asserts `params == [0.5]` and `sql.count("%s") == len(params)`. |
| T-42-07 | Tampering — value injection via make_valid method/params string | mitigate | CLOSED | `spatial.py:1721–1726` — whitelist guard `if method not in _VALID_MAKE_VALID_METHODS: raise ValueError(...)` placed after `validate_identifiers` (line 1717), before any SQL construction. `_VALID_MAKE_VALID_METHODS = {None, "linework", "structure"}` at `spatial.py:1498`. The params string at `spatial.py:1739–1746` is assembled exclusively from programmer-controlled string literals (`"method=linework"`, `"method=structure"`, `"method=structure keepcollapsed=true"`, `"method=structure keepcollapsed=false"`) — never f-string-interpolated from caller input. The `geom` identifier interpolated at `spatial.py:1734` and `1747` is already validated at line 1717. `expr = f"ST_MakeValid(t.{geom}, %s)"` at line 1747 — `%s` receives the programmer-assembled literal, not user input. Tripwire test at `test_spatial.py:781–784` (`test_make_valid_invalid_method`, asserts `ValueError` with message `"method must be one of"`). Params-string tests at `test_spatial.py:753–779` cover all four combinations (linework, structure+None, structure+True, structure+False). Contradictory-arg guard tests at `test_spatial.py:786–794`. |
| T-42-08 | DoS/correctness — `make_valid(method="structure")` on PostGIS < 3.2 | accept | CLOSED | Accepted per D-04. Disposition: native PostGIS error passthrough; no server-version round-trip. Documented in `spatial.py:1670–1676` (docstring) and `docs/stability.md:274–276` (explicit D-04 version note: "On older servers, passing `method="structure"` raises a native PostGIS error — pycopg does not pre-check the server version"). The rationale is reasonable: adding a pre-check round-trip would be a performance and complexity cost for a stable PostGIS version deployed since 2020; users on older servers receive a clear native error. |
| T-42-09 | Information disclosure — docs drift (`where=` on new methods) | mitigate | CLOSED | `docs/api-reference.md:210–215` — all 6 new Spatial Helpers rows use `filter=None`, not `where=`. Grep of those rows shows no `where=` occurrence among the new method entries. `docs/stability.md:109–114` — 6 new rows in Stable API Contract table, all list `filter` (not `where`). |
| T-42-10 | Tampering — security guard regression slips through green suite (v0.10.0 COPY lesson) | mitigate | CLOSED | Per `42-03-SUMMARY.md` verification table: full suite ran 1567 passed at 96.18% coverage (gate >= 95%). Per-builder injection tests from plans 42-01/42-02 are part of that suite. Named surface test `test_spatial_v1_processing_surface` at `test_parity.py:135–167` asserts both accessors expose all 6 methods. Routing-registry parametrized tests in `_HELPER_CALLS` (`test_spatial.py:1667–1689`) and `_GDF_CALLS` (`test_spatial.py:1692–1708`) include all 6 new methods, exercising them through the parametrized `TestAccessorRouting` tests. |
| T-42-SC | Tampering — supply chain (npm/pip/cargo installs) | accept | CLOSED | Accepted across all three plan runs. Plans 42-01, 42-02, 42-03 each declare no packages installed (source modification and docs only). SUMMARY files for all three plans confirm `tech_stack.added: []`. Rationale is reasonable: this phase adds no runtime dependencies. |

---

## Accepted Risks Log

| Threat ID | Rationale | Reference |
|-----------|-----------|-----------|
| T-42-03 | Binary trio builders return `params=[]`; no user values are bound. `filter=`/`order_by=` are documented raw-SQL caller responsibility — a pre-existing API contract on `buffer`/`transform`, unchanged for the new methods. | `spatial.py:1296`; `42-01-PLAN.md` threat register |
| T-42-08 | `make_valid(method="structure")` on PostGIS < 3.2 raises a native server error (no pre-check). The accepted posture avoids a per-call round-trip to check PostGIS version; the server error is clear and actionable for callers. Documented in docstring and stability.md. | `spatial.py:1670–1676`; `docs/stability.md:274–276` |
| T-42-SC | No packages installed in any of the three Phase 42 plans; supply-chain risk is zero for this phase. | `42-01-SUMMARY.md`, `42-02-SUMMARY.md`, `42-03-SUMMARY.md` — `tech_stack.added: []` |

---

## Unregistered Threat Flags

None. All three SUMMARY.md files (`42-01-SUMMARY.md`, `42-02-SUMMARY.md`, `42-03-SUMMARY.md`) declare no new security surface beyond the registered threat model. No unregistered flags to log.

---

## Audit Scope

**Files audited (implementation, read-only):**
- `/home/loc/workspace/pycopg/pycopg/spatial.py` — builders `_build_binary_geom_sql` (line 1273), `build_union_sql` (1299), `build_difference_sql` (1365), `build_intersection_sql` (1431), `build_simplify_sql` (1501), `build_convex_hull_sql` (1591), `build_make_valid_sql` (1645); `_VALID_MAKE_VALID_METHODS` (1498); sync accessor methods `union/difference/intersection/simplify/convex_hull/make_valid` (3427–3848); async mirrors (5491–5924)
- `/home/loc/workspace/pycopg/tests/test_spatial.py` — injection tests, SQL-shape tests, ValueError-guard tests, columns-injection tests, routing registry `_HELPER_CALLS`/`_GDF_CALLS`
- `/home/loc/workspace/pycopg/tests/test_parity.py` — `test_spatial_v1_processing_surface` (line 135)
- `/home/loc/workspace/pycopg/docs/stability.md` — 6 new method rows + D-04 version note
- `/home/loc/workspace/pycopg/docs/api-reference.md` — 6 new Spatial Helpers rows

**Plans and summaries read:**
- `.planning/phases/42-spatial-v2-processing-helpers/42-01-PLAN.md`, `42-02-PLAN.md`, `42-03-PLAN.md`
- `.planning/phases/42-spatial-v2-processing-helpers/42-01-SUMMARY.md`, `42-02-SUMMARY.md`, `42-03-SUMMARY.md`

**ASVS Level:** 1 (default per config)
**Block criteria:** critical / open threats
**Audited:** 2026-06-30
