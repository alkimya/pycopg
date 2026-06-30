---
phase: 43
slug: spatial-v2-spatial-aggregates
status: secured
threats_total: 5
threats_closed: 5
threats_open: 0
register_authored_at_plan_time: true
asvs_level: 1
created: 2026-06-29
---

# Security Audit — Phase 43: Spatial Aggregates

**Verdict: SECURED** — 5/5 threats closed, 0 open, 0 blockers.

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-43-01 | Tampering / Elevation (SQL identifier injection — table/schema/geom/group_by) | mitigate | CLOSED | See below |
| T-43-02 | Tampering (security guard regression slips through green suite) | mitigate | CLOSED | See below |
| T-43-03 | Tampering (SRID injection via gdf cast) | mitigate | CLOSED | See below |
| T-43-04 | Information disclosure (docs drift — where=/columns= on new aggregate methods) | mitigate | CLOSED | See below |
| T-43-SC | Tampering (supply chain — npm/pip/cargo installs) | accept | CLOSED | See accepted risks log |

---

## Per-Threat Verification Detail

### T-43-01 — SQL Identifier Injection (table/schema/geom/group_by)

**Declared mitigation:** `validate_identifiers(table, schema, geom)` as line 1 of `_build_agg_geom_sql`; `validate_identifiers(*group_by)` before any group-column f-string assembly. Equivalent guards on `build_extent_sql`. Per-builder injection tests (malicious table, geom, group_by) assert `InvalidIdentifierError` before SQL is produced.

**Verification:**

`_build_agg_geom_sql` (shared helper for collect_geometries + union_aggregate):
- `pycopg/spatial.py:1810` — `validate_identifiers(table, schema, geom)  # LINE 1 — security invariant`
- `pycopg/spatial.py:1811-1812` — `if group_by: validate_identifiers(*group_by)` executes before the f-string `group_cols = [f"t.{col}" for col in group_by]` at line 1813.
- The group column string is not interpolated into SQL until after validation passes.

`build_extent_sql`:
- `pycopg/spatial.py:2067` — `validate_identifiers(table, schema, geom)  # LINE 1 — security invariant (T-43-01)`
- `pycopg/spatial.py:2068-2069` — `if group_by: validate_identifiers(*group_by)` before `group_cols = [f"t.{col}" for col in group_by]` at line 2070.

Injection tests in `tests/test_spatial.py` (all within `class TestAggregateBuilders`):
- `test_collect_geometries_invalid_table` (line 2321) — malicious table raises `InvalidIdentifierError`
- `test_collect_geometries_invalid_geom` (line 2326) — malicious geom raises `InvalidIdentifierError`
- `test_collect_geometries_invalid_group_by` (line 2331) — `group_by=["region; DROP TABLE users; --"]` raises `InvalidIdentifierError`
- `test_union_aggregate_invalid_table` (line 2380) — malicious table raises `InvalidIdentifierError`
- `test_union_aggregate_invalid_geom` (line 2385) — malicious geom raises `InvalidIdentifierError`
- `test_union_aggregate_invalid_group_by` (line 2390) — `group_by=["region; DROP TABLE users; --"]` raises `InvalidIdentifierError`
- `test_extent_invalid_table` (line 2447) — malicious table raises `InvalidIdentifierError`
- `test_extent_invalid_geom` (line 2452) — malicious geom raises `InvalidIdentifierError`
- `test_extent_invalid_group_by` (line 2457) — `group_by=["region; DROP TABLE users; --"]` raises `InvalidIdentifierError`

All 9 injection tests confirm `InvalidIdentifierError` is raised before any SQL is produced. The ordering invariant — validation before f-string interpolation — is confirmed at the source level for all three builders.

**CLOSED.**

---

### T-43-02 — Security Guard Regression (validate_identifiers dropped, suite stays green)

**Declared mitigation:** Per-builder injection tests in `TestAggregateBuilders` are the tripwire; full suite + coverage gate >= 95% exercises every new branch.

**Verification:**

- 9 per-builder injection tests across 3 builders (table, geom, group_by per builder) are present in `tests/test_spatial.py::TestAggregateBuilders` (lines 2321-2460). If any `validate_identifiers` call were removed, these tests would fail loudly.
- 43-03-SUMMARY.md records the full-suite result: 1623 passed, 96.10% coverage (above the 95% ratchet). The summary confirms "TestAggregateBuilders injection tests: All 23 passed (9 inject + 14 SQL-shape tests) — T-43-01/T-43-02 tripwires green."
- Coverage at 96.10% confirms the validate-first branches are exercised under the full run.

**CLOSED.**

---

### T-43-03 — SRID Injection via gdf Cast

**Declared mitigation:** `srid` interpolated via `int(srid)` in the gdf branch of `build_extent_sql`; non-integer raises `ValueError`/`TypeError` before SQL assembly. `test_extent_custom_srid` confirms the integer reaches the cast.

**Verification:**

- `pycopg/spatial.py:2072` — gdf branch: `agg_expr = f"ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent"`. The `int(srid)` coercion is inline in the f-string, meaning any non-integer srid raises `ValueError` (e.g. `int("3857; DROP")`) or `TypeError` (e.g. `int(None)`) before the string is assembled and returned.
- `tests/test_spatial.py:2414-2419` — `test_extent_custom_srid`: `build_extent_sql("zones", into="gdf", srid=3857)` produces SQL containing `", 3857) AS extent"`, confirming the integer value is correctly interpolated.
- `tests/test_spatial.py:2407-2412` — `test_extent_gdf_branch`: confirms default srid=4326 reaches the cast as `ST_SetSRID(ST_Extent(t.geometry)::geometry, 4326) AS extent`.

**CLOSED.**

---

### T-43-04 — Information Disclosure via Docs Drift (where=/columns= in new aggregate method docs)

**Declared mitigation:** The 3 new doc rows in `docs/stability.md` and `docs/api-reference.md` must use `filter=` (not `where=`) and must omit `columns=`. Acceptance criterion: grep confirms no `where=` in the new aggregate rows.

**Verification:**

`docs/stability.md` (lines 115-117):
- `collect_geometries` row: `geom`, `schema`, `group_by`, `filter`, `into`, `order_by`, `limit` — `filter=` used, no `where=`, no `columns=`.
- `union_aggregate` row: same set — `filter=` used, no `where=`, no `columns=`.
- `extent` row: `geom`, `schema`, `group_by`, `srid`, `filter`, `into`, `order_by`, `limit` — `filter=` used, no `where=`, no `columns=`.
- Note at lines 122-126 documents the `extent` dual-branch (box2d text / SRID-tagged geometry) and explicitly states "No `columns=` parameter on the aggregate methods."

`docs/api-reference.md` (lines 216-218):
- `collect_geometries`: `table, *, geom="geometry", schema="public", group_by=None, filter=None, into="rows", order_by=None, limit=None` — `filter=`, no `where=`, no `columns=`.
- `union_aggregate`: same set — `filter=`, no `where=`, no `columns=`.
- `extent`: `table, *, geom="geometry", schema="public", group_by=None, srid=4326, filter=None, into="rows", order_by=None, limit=None` — `filter=`, no `where=`, no `columns=`.

All 3 new doc rows in both files use `filter=` exclusively. No `where=` or `columns=` drift detected.

Note: `README.md` line 89 shows "(25 methods)" rather than the planned "(22 methods)" — this is because Phase 44 (serialization + MVT) was completed after Phase 43 and updated the count further. The discrepancy does not affect Phase 43's security posture. The three method names (`collect_geometries`, `extent`) and the method count bump are present in the README.

**CLOSED.**

---

## Accepted Risks Log

| Threat ID | Category | Rationale | Evidence |
|-----------|----------|-----------|----------|
| T-43-SC | Supply chain (npm/pip/cargo installs) | Phase 43 (all 3 plans) installs zero new packages. The implementation is pure code on existing dependencies: `pycopg/spatial.py` and `tests/test_spatial.py` only. No `pyproject.toml` or `uv.lock` changes in any Phase 43 commit. | `git show --stat` across all 14 Phase 43 commits (0d0ae0e through e283219) shows no changes to `pyproject.toml` or `uv.lock`. |

---

## Unregistered Flags

The SUMMARY files document no threat flags beyond the registered threat register. No unregistered attack surface was introduced.

The one structural note (not a security flag): `_append_tail` explicitly does NOT call `validate_identifiers` itself — its docstring (`pycopg/spatial.py:169`) states "this function does not call `validate_identifiers` — that is the builder's responsibility." This is by design: the builder pre-validates and passes an already-validated string. The builder-level validation (confirmed above for T-43-01) covers this delegation.

---

## Scope

Files audited:
- `/home/loc/workspace/pycopg/pycopg/spatial.py` — `_append_tail` (line 149), `_build_agg_geom_sql` (line 1757), `build_collect_geometries_sql` (line 1823), `build_union_aggregate_sql` (line 1900), `build_extent_sql` (line 1977), `_SCALAR_HELPERS` (line 2086), `SpatialAccessor.collect_geometries` (line 3850), `SpatialAccessor.union_aggregate` (line 3936), `SpatialAccessor.extent` (line 4023), `AsyncSpatialAccessor.collect_geometries` (line 5926), `AsyncSpatialAccessor.union_aggregate` (line 5998), `AsyncSpatialAccessor.extent` (line 6070)
- `/home/loc/workspace/pycopg/tests/test_spatial.py` — `class TestAggregateBuilders` (line 2267), injection tests (lines 2321-2460), `class TestAggregateAccessorGuards` (line 2463)
- `/home/loc/workspace/pycopg/tests/test_parity.py` — `test_spatial_aggregates_surface` (line 170)
- `/home/loc/workspace/pycopg/docs/stability.md` — lines 115-126
- `/home/loc/workspace/pycopg/docs/api-reference.md` — lines 216-218

ASVS Level: 1 (identifier-injection and docs-drift checks aligned with ASVS V5 input validation).
