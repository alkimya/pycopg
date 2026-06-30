---
phase: 44
slug: spatial-v2-serialization-mvt
status: secured
threats_total: 9
threats_closed: 9
threats_open: 0
register_authored_at_plan_time: true
asvs_level: 1
created: 2026-06-30
---

# SECURITY.md — Phase 44 Audit Record

**Phase:** 44 — spatial-v2-serialization-mvt
**Audit date:** 2026-06-30
**ASVS focus:** Input validation / SQL injection (V5), parity-regression integrity
**Auditor disposition:** Adversarial — every mitigation assumed absent until grep evidence found

---

## Verdict: SECURED

**Threats Closed:** 9 / 9
**Threats Open:** 0

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-44-01 | Tampering (SQLi via identifiers) | mitigate | CLOSED | `pycopg/spatial.py:849` — `validate_identifiers(table, schema, geom)` is the first statement of `build_geojson_sql`; `validate_identifiers(*columns)` at line 851. Injection tests in `tests/test_spatial.py:1885-1898` assert `InvalidIdentifierError` for malicious table, geom, and columns entries. Same guard in `build_text_sql` at lines 915/917. |
| T-44-01b | Tampering (numeric/options injection) | mitigate | CLOSED | `pycopg/spatial.py:852` — `options = (1 if include_bbox else 0) \| (2 if include_crs else 0)` is a computed `int` from two bools. Lines 855-859 pass `max_decimal_digits` and `options` as `%s` bind params (`return sql, [max_decimal_digits, options]`). No caller string reaches SQL text. |
| T-44-01c | Information disclosure via `filter=` raw fragment | accept | CLOSED | Accepted risk. `filter=` is documented as a raw-SQL escape hatch consistent with the full spatial surface (pre-existing pattern on all spatial builders). No identifier path bypasses the line-1 guard. Rationale recorded below. |
| T-44-02 | Tampering (SQLi via identifiers in build_mvt_sql) | mitigate | CLOSED | `pycopg/spatial.py:1054` — `validate_identifiers(table, schema, geom)` is the first statement (comment annotated "LINE 1: security invariant T-44-02"). `validate_identifiers(*columns)` at line 1056; `validate_identifiers(feature_id_column)` at line 1058 — both BEFORE `feature_id_column` is interpolated as a literal identifier at line 1082. The interpolation at line 1082 is therefore unreachable unless the guard at line 1058 passed. Injection tests in `tests/test_spatial.py:2029-2061` cover all four identifier paths (table, geom, columns entry, feature_id_column). |
| T-44-02b | Tampering (numeric injection via tile/extent/srid) | mitigate | CLOSED | `pycopg/spatial.py:1062` — `z, x, y, ext = int(tile_z), int(tile_x), int(tile_y), int(extent)` coerces all four before SQL assembly. `srid` coerced at line 1066 (`int(srid)`). Non-integer input raises `ValueError`/`TypeError` before any SQL text is built. `layer_name` is a `%s` bind (line 1086 `[layer_name, ext]`). SQL-shape test at line 2104 asserts `params == [layer_name, extent]` and `sql.count("%s") == 2`. |
| T-44-02c | Information disclosure via `filter=` raw fragment | accept | CLOSED | Accepted risk. Same rationale as T-44-01c — documented escape hatch consistent with the spatial surface. Recorded below. |
| T-44-02d | Denial of service (pathological tile / huge extent) | accept | CLOSED | Accepted risk. `int()` prevents non-numeric abuse; PostGIS bounds the execution cost; tile servers gate z/x/y at the HTTP layer (out of library scope). Recorded below. |
| T-44-03 | Tampering (parity/regression — method silently dropped) | mitigate | CLOSED | `tests/test_parity.py:202-236` — `test_spatial_serialization_surface` asserts `frozenset({"as_geojson", "as_text", "as_mvt"})` is a subset of the public members of both `SpatialAccessor` and `AsyncSpatialAccessor`. Auto-extending `test_accessor_parity` (line 36) and `test_accessor_parameter_kind_parity` (line 432) enforce bidirectional set-diff and KIND parity. Full suite at 96.18% coverage (gate ≥95%) keeps injection tests from Plans 01-02 continuously exercised. |
| T-44-03b | Information disclosure (stale docs with `where=` on new methods) | mitigate | CLOSED | `docs/api-reference.md:219-221` — all three P44 rows (`as_geojson`, `as_text`, `as_mvt`) use `filter=`; none carry `where=`. `docs/stability.md:118-120` — same. No new `where=` token on any P44 method row in any doc surface. |

---

## Critical-Path Detail: build_mvt_sql feature_id_column

This was the highest-risk path per the audit brief — `feature_id_column` is interpolated as a literal SQL identifier (not a `%s` bind) at `pycopg/spatial.py:1082`:

```
f"ST_AsMVT(q.*, %s, %s, 'geom_mvt', '{feature_id_column}')"
```

Verification confirms the guard at line 1058 (`validate_identifiers(feature_id_column)`) executes **before** the f-string at line 1082. The call sequence is:

1. Line 1054: `validate_identifiers(table, schema, geom)` — raises `InvalidIdentifierError` on bad table/schema/geom
2. Line 1056: `validate_identifiers(*columns)` — raises on bad column
3. Line 1058: `validate_identifiers(feature_id_column)` — raises on bad feature_id_column
4. Lines 1062-1086: SQL assembly (only reached if all guards above pass)

The injection test at `tests/test_spatial.py:2052-2061` passes `feature_id_column="'; DROP TABLE foo; --"` and asserts `InvalidIdentifierError` is raised — confirming the guard fires before any SQL is constructed.

---

## Accepted Risks Log

| Risk ID | Threat ID | Rationale |
|---------|-----------|-----------|
| AR-44-01 | T-44-01c | `filter=` on `as_geojson`/`as_text` is a documented raw-SQL escape hatch. Callers own the fragment. The line-1 `validate_identifiers` guard on all table/schema/geom/columns identifiers cannot be bypassed via `filter=`. This pattern is consistent across the entire spatial surface (P42, P43, P44) and is the accepted posture for the library. |
| AR-44-02 | T-44-02c | `filter=` on `as_mvt` (inner subquery placement). Same rationale as AR-44-01. The inner-subquery placement is architecturally correct — the outer `WHERE q.geom_mvt IS NOT NULL` remains structural and cannot be overridden by `filter=`. |
| AR-44-03 | T-44-02d | Pathological tile coordinates / huge extent are a DoS concern handled at the HTTP/tile-server layer, not in the library. `int()` coercion prevents non-numeric strings from reaching SQL. PostGIS itself bounds execution cost at the database layer. |

---

## Unregistered Flags

None. No new attack surface was detected during this audit that lacks a threat mapping. The SUMMARY.md threat surface scans for all three plans explicitly state "No new security-relevant surface beyond what the plan's threat model covers."

---

## Scope

This audit covers Phase 44 implementation files only:
- `pycopg/spatial.py` — `build_geojson_sql` (L787), `build_text_sql` (L862), `build_mvt_sql` (L929), `SpatialAccessor._run_mvt` (L2209), `SpatialAccessor.as_geojson/as_text/as_mvt` (L3018/3096/3167), `_SCALAR_HELPERS` (L2086), `AsyncSpatialAccessor._arun_mvt` (L4244), `AsyncSpatialAccessor.as_geojson/as_text/as_mvt` (L5079/5160/5234)
- `tests/test_spatial.py` — `TestBuildGeojsonSql` (L1882), `TestBuildTextSql` (L1958), `TestBuildMvtSql` (L2026), `TestMvtRouting` (L2186)
- `tests/test_parity.py` — `test_spatial_serialization_surface` (L202)
- `docs/api-reference.md` — P44 rows (L219-221)
- `docs/stability.md` — P44 rows (L118-120)

Implementation files were not modified during this audit.
