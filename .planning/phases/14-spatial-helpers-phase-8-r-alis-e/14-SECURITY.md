---
phase: 14
slug: spatial-helpers-phase-8-r-alis-e
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-12
---

# Phase 14 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| caller → spatial builder | Untrusted table/schema/column/geom identifiers and geometry values cross into generated SQL | identifiers, WKT/GeoJSON, coordinates, distances, SRIDs |
| caller → accessor method | Untrusted identifiers/values cross into builders, then into executed SQL against the live DB | identifiers, geometry values, `into=` selector, `where=` fragment |
| accessor → database | Generated SQL + params executed via existing `execute` / `to_geodataframe` infrastructure | parameterized SQL, bind values |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-14-01 | Tampering | identifiers (table, schema, geom, columns, ref) in every builder | mitigate | `validate_identifiers` called as first statement in every builder before any string interpolation: spatial.py lines 127, 246, 326, 395, 473, 559, 633, 695, 757, 815, 880, 943 (12 call-sites). Rejects via `InvalidIdentifier`. | closed |
| T-14-02 | Tampering | geometry values (coordinates, WKT, GeoJSON, distance, k) | mitigate | All values appended to params list as `%s` placeholders; `build_transform_sql` returns `sql, [to_srid]` (line 952). No user value appears inside an f-string. | closed |
| T-14-03 | Tampering | SRID / to_srid integers | mitigate | `int(srid)` coercion in `_resolve_geometry` (lines 118, 121, 124); `int(limit)` in `_append_tail` (line 183); `to_srid` parameterized via `%s`. | closed |
| T-14-04 | Tampering | `where=` raw SQL fragment (builders) | accept | Documented limitation in module docstring (spatial.py line 23): "values inside `where=` are the caller's responsibility (T-14-04 accepted limitation)". Convention traced to `_build_select_sql`; `where_params=` deferred (D-11). | closed |
| T-14-05 | Tampering | accessor method inputs (table, geom, columns, geometry values) | mitigate | All 11 `SpatialAccessor` + 11 `AsyncSpatialAccessor` methods delegate SQL assembly entirely to 14-01 builders; no SQL string construction in accessor bodies; `_check_into` enforced before each `build_*_sql` call. | closed |
| T-14-06 | Information Disclosure / Elevation | spatial query on a DB without PostGIS | mitigate | Sync: `SpatialAccessor.__init__` calls `db.has_extension("postgis")` and raises `ExtensionNotAvailable` (spatial.py lines 1047–1048). Async: `_check_postgis()` awaited as first line of all 11 async methods (lines 1982, 2055, 2132, 2219, 2304, 2381, 2450, 2517, 2582, 2650, 2718). | closed |
| T-14-07 | Tampering | `into=` value | mitigate | `_check_into()` validates against `_VALID_INTO = ("rows", "gdf")` (line 961); scalar helpers (`_SCALAR_HELPERS`, line 957) reject `into="gdf"` with `ValueError` before any SQL runs. Called in all 22 public methods. | closed |
| T-14-08 | Tampering | `where=` raw fragment passed through to executed SQL (accessors) | accept | Covered by the same module-level documentation as T-14-04 (spatial.py line 23); accessors pass `where=` through to builders without adding SQL. | closed |
| T-14-09 | Tampering | 08-DESIGN.md content drift vs locked decisions | mitigate | 08-DESIGN.md contains all 12 decision IDs D-01..D-12; "Points à TRANCHER" heading absent; status line reads "Design validé et réalisé en Phase 14 (D-01..D-12)"; §9 states "Aucune. Toutes les décisions ont été tranchées en Phase 14." | closed |
| T-14-10 | Repudiation | coverage gate frozen above achieved value | mitigate | pyproject.toml line 90: `--cov-fail-under=94`; SUMMARY-04 records measured 94.09%; gate set at floor below achieved value — cliquet rule satisfied. Only pyproject.toml change in phase 14 was this value (verified via git diff). | closed |
| T-14-SC | Tampering | npm/pip/cargo supply chain | accept | Git diff across all 7 phase-14 commits (d8a5609, 2d9c3cb, e06ffea, 4e3667d, ebf7375, 8d3cfff, 5835dc2) shows only the `--cov-fail-under` line changed in pyproject.toml; zero packages installed. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-14-01 | T-14-04 | `where=` is a raw SQL fragment; values inside it are the caller's responsibility. Matches existing `_build_select_sql` convention; `where_params=` deferred to D-11 / ETL milestone. Documented at spatial.py line 23. | plan 14-01 threat register (plan-time) | 2026-06-12 |
| AR-14-02 | T-14-08 | Same limitation as T-14-04 at the accessor delegation layer; accessors pass `where=` through unchanged; documented at module entry point. | plan 14-02 threat register (plan-time) | 2026-06-12 |
| AR-14-03 | T-14-SC | Phase 14 installs zero packages; config + test changes only (verified via git diff across phase 14 commits). | plan-time register (all plans) | 2026-06-12 |

*Accepted risks do not resurface in future audit runs.*

---

## Audit Notes

- The `_to_named_binds()` adapter (spatial.py lines 994–1020), bridging psycopg `%s` params to SQLAlchemy `text()` named binds for the `gdf` path, rewrites placeholders by index position over the already-sanitized params list and generates `:p0`..`:pN` names deterministically — no new injection surface; no unregistered flag.
- `_append_tail` interpolates `order_by` directly into SQL (line 181). Same accepted-risk pattern as `where=` — falls under the T-14-04/T-14-08 envelope and the existing `_build_select_sql` convention. Not a blocker at ASVS L1.
- No `## Threat Flags` section was present in any of the four SUMMARY files; no unregistered threats surfaced.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-12 | 11 | 11 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
