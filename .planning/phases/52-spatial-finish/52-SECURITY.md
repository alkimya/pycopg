---
phase: 52-spatial-finish
slug: spatial-finish
status: verified
threats_total: 6
threats_closed: 6
threats_open: 0
asvs_level: 1 (default, unset in config)
created: 2026-07-05
audited: 2026-07-05
---

# Phase 52 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (union across 52-01..52-06 PLAN.md `<threat_model>` blocks). This audit **verifies each declared mitigation exists in the implemented code** — it does not scan blindly for new vulnerabilities.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|----------------|
| caller -> pycopg SQL builder | Untrusted table/schema/geom/columns identifiers, `unit=` string, `grid_size` float, and geometry values (point/wkt/geojson/ref/srid) cross into the 10 new SQL builders introduced this phase | identifiers (strings), floats, WKT/GeoJSON payloads |
| pycopg -> PostgreSQL/PostGIS | Built SQL string + bound `%s` params executed server-side | assembled SQL + parameter list |
| docs authoring -> published docs | Static prose, no runtime trust boundary | documentation text |
| dev/CI -> lockfile | Dependency integrity boundary | `uv.lock` / `pyproject.toml` |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-52-01 | Tampering | Identifiers (table/schema/geom/other_geom/columns/ref) in the 10 new builders: `_build_binary_geom_sql`, `build_length_sql`, `build_is_valid_sql`, `build_is_valid_reason_sql`, `build_envelope_sql`, `build_point_on_surface_sql`, `build_overlaps_sql`, `build_touches_sql`, `build_crosses_sql`, `build_disjoint_sql` | mitigate | `validate_identifiers(...)` is the first statement in every builder; the 4 DE-9IM `ref=` builders additionally validate `ref_table`/`ref_col` inside `_resolve_geometry` before interpolation | closed |
| T-52-02 | Tampering | User values: `grid_size` float, geometry values (point coords/WKT/GeoJSON/srid), `unit` string | mitigate | `grid_size` bound as `%s` (never f-string); geometry values bound as `%s` via `_resolve_geometry`; `unit` whitelisted via `_validate_unit` ("m"/"srid" only) | closed |
| T-52-05 | Information Disclosure | Docs omit `disjoint` EXISTS-quantifier footgun / non-indexable perf caveat | mitigate | D-07 footgun warning + D-08 perf note ("does not use indexes" / `NOT ST_Intersects`) present verbatim in `docs/spatial.md`'s `disjoint` section and in the `build_disjoint_sql`/accessor docstrings | closed |
| T-52-SC | Tampering | Dependency/lockfile drift across the 6 plans | mitigate | Zero new deps: `git diff --stat` on `uv.lock`/`pyproject.toml` between the phase's pre-execution commit and HEAD is empty | closed |
| T-52-03 | Tampering | `filter=`/`order_by=` raw SQL fragment (all new predicate/measurement builders inherit `_append_tail`) | accept | Pre-existing documented accepted limitation (T-14-04); `_append_tail` unchanged this phase — no new risk introduced | closed (accepted) |
| T-52-04 | Information Disclosure | `disjoint(ref=...)` EXISTS-quantifier semantics return near-all rows for a sparse reference table (deliberately NOT special-cased into `NOT EXISTS`, D-07) | accept | Semantic footgun, not a security defect; mitigated by the mandatory D-07 docstring warning + a live test (`test_disjoint_ref_existence_quantifier_footgun`) proving the behavior rather than hiding it | closed (accepted) |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Verification Evidence

| Threat ID | Evidence |
|-----------|----------|
| T-52-01 | `pycopg/spatial.py:428` (`build_overlaps_sql`), `:510` (`build_touches_sql`), `:592` (`build_crosses_sql`), `:687` (`build_disjoint_sql`), `:1182` (`build_length_sql`), `:1239` (`build_is_valid_sql`), `:1294` (`build_is_valid_reason_sql`), `:1820` (`_build_binary_geom_sql`), `:2259` (`build_envelope_sql`), `:2316` (`build_point_on_surface_sql`) — `validate_identifiers(...)` is the first executable statement in each. `pycopg/spatial.py:133` — `_resolve_geometry` calls `validate_identifiers(ref_table, ref_col)` before returning the `_REF_SENTINEL` fragment consumed by all 4 DE-9IM `ref=` builders. Live-verified: `PGDATABASE=pycopg_test3 uv run pytest tests/test_spatial.py -k "invalid_table or invalid_column or invalid_geom or invalid_schema or invalid_other_geom or invalid_unit or ref_invalid_identifier or grid_size" -q` → 79 passed, 0 failed (includes `test_overlaps_ref_invalid_identifier`, `test_touches_ref_invalid_identifier`, `test_crosses_ref_invalid_identifier`, `test_disjoint_ref_invalid_identifier`, plus table/schema/geom/column injection tests per builder in `tests/test_spatial.py`). |
| T-52-02 | `pycopg/spatial.py:1823-1828` — `grid_size` branch: `None` → no 3rd arg / `params=[]`; set → `f"{op_func}(t.{geom}, t.{other_geom}, %s)"` / `params=[grid_size]` (never interpolated). `pycopg/spatial.py:118-126` — `_resolve_geometry` binds `point`/`wkt`/`geojson` values as `%s` (only `srid` is `int()`-coerced and interpolated, not a free-form string). `pycopg/spatial.py:52-66` — `_validate_unit` whitelists `("m", "srid")`, raises `ValueError` otherwise; called at `pycopg/spatial.py:1185` in `build_length_sql`. Test evidence: `test_union_grid_size_appends_third_arg`, `test_difference_grid_size_appends_third_arg`, `test_intersection_grid_size_appends_third_arg`, `test_length_invalid_unit` all pass (see 79-test run above). |
| T-52-05 | `docs/spatial.md:392-397` — "the `ref=` form means 'EXISTS a ref row disjoint from t' ... does **not** mean 'disjoint from all'" (D-07). `docs/spatial.md:399-401` — "`ST_Disjoint` does not use indexes ... prefer a negated `NOT ST_Intersects` predicate instead — e.g. via the `filter=` escape hatch" (D-08). Both confirmed present via direct grep of `docs/spatial.md`. |
| T-52-SC | `git diff --stat 024003d..HEAD -- uv.lock pyproject.toml` → empty output (0 lines changed) — verified directly, not taken on faith from SUMMARY prose. `024003d` = "docs(state): record phase 52 context session", the last commit before the first Phase 52 implementation commit (`26b8457`). |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|--------------|------|
| AR-52-01 | T-52-03 | `filter=`/`order_by=` raw SQL fragment is a pre-existing documented accepted limitation (T-14-04, established Phase 14). No new builder in this phase changes `_append_tail`'s behavior — every new builder (predicates, scalars, geometry helpers, overlays) reuses the shared, unmodified tail-assembly function verbatim. Escape-hatch-by-design, not a regression. | User (via plan-time threat register, 52-01..52-05 `<threat_model>`) | 2026-07-04 |
| AR-52-02 | T-52-04 | `disjoint(ref=...)`'s EXISTS-quantifier semantics ("exists a reference row disjoint from this row", not "disjoint from all reference rows") is a deliberate mechanical-uniformity design decision (D-07) — not a code defect. It is disclosed via a mandatory docstring `Warnings` section on both builder and accessor (sync+async, `pycopg/spatial.py`) and proven live by `test_disjoint_ref_existence_quantifier_footgun` in `tests/test_spatial.py` (52-05), which asserts a row genuinely intersecting one reference zone is still returned because a second reference zone is disjoint from it — behavior is surfaced, not hidden. | User (via plan-time threat register, 52-05 `<threat_model>`) | 2026-07-04 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|----------------|--------|------|--------|
| 2026-07-05 | 6 | 6 | 0 | gsd-security-auditor |

---

## Unregistered Flags

None. No `## Threat Flags` section was found in any of the 6 phase summaries (`52-01-SUMMARY.md` through `52-06-SUMMARY.md`) — no new attack surface was flagged by the executor beyond the plan-time threat register.

Note: `_SCALAR_HELPERS` frozenset gained `length`/`is_valid`/`is_valid_reason` (verified at `pycopg/spatial.py:2769-2781`), correctly excluding `envelope`/`point_on_surface` (geometry-valued, gdf-eligible) — this is a routing/UX guard (`_check_into`), not a security control, and does not constitute new attack surface; no threat mapping required.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-05
