---
phase: 41-api-homogenization
plan: "04"
subsystem: api-consistency
tags: [freeze-03, kw-only, consistency-audit, d-03, d-04, d-05, d-06]
dependency_graph:
  requires:
    - "41-01 (-W error::DeprecationWarning gate + test scaffold)"
    - "41-02 (exception *Error renames — spatial.py + exceptions.py updated)"
    - "41-03 (filter=/where= shim on all 22 spatial accessor methods)"
  provides:
    - "FREEZE-03 consistency findings table (user-reviewed, D-05 gate)"
    - "kw-only * enforcement across 7 accessors + flat core (Task 3, pending approval)"
    - "TestKwOnlyEnforcement filled test bodies (Task 3, pending approval)"
tech_stack:
  added: []
  patterns:
    - "audit-then-decide (D-05): findings table produced before any fix lands"
    - "per-finding disposition: DEPRECATED (name rename) vs CLEAN BREAK (structural/kw-only/default)"
key_files:
  created:
    - .planning/phases/41-api-homogenization/41-04-SUMMARY.md
  modified: []
decisions:
  - "FREEZE-03 findings table produced — covers 7 accessors + flat core, 7 audit dimensions"
  - "User review gate (D-05) mandatory before Task 3 applies any fix"
metrics:
  duration: "~30 minutes (Task 1 only — stopped at Task 2 checkpoint)"
  completed: "2026-06-28"
  tasks_completed: 1
  tasks_total: 3
  files_created: 1
  files_modified: 0
---

# Phase 41 Plan 04: FREEZE-03 Consistency Audit — Findings Table

**One-liner:** Full FREEZE-03 consistency inventory across 7 accessor families + flat core, covering param names/order, kw-only boundary, into= value-sets, schema= defaults, return shapes, and error types; produced for mandatory user review before any fix lands (D-05).

---

## Task 1: FREEZE-03 Findings Table

### Methodology

Audited every public method on all 7 accessor classes (both sync and async) and the `Database`/`AsyncDatabase` flat core against the 7 RESEARCH §Pattern-3 dimensions:

1. **Param names** — any inconsistency in names for conceptually identical params
2. **Param order** — positional order of args before `*`
3. **`into=` default/value-set** — `"rows"/"gdf"` vs `"df"` vs absent
4. **`schema=` default** — `"public"` vs `None` vs absent
5. **Return shape** — documented return type
6. **kw-only boundary** — position of `*` separator
7. **Error types** — exception classes raised

Fix Type legend:
- `—` : No change needed
- `DEPRECATED` : Name rename → add DeprecationWarning alias + MIGRATION (D-06)
- `CLEAN BREAK` : Structural / default / positional / kw-only change → MIGRATION entry only (D-04/D-06)
- `DECISION` : Flagged for explicit user sign-off (ambiguous or high-impact)

---

### FREEZE-03 Findings Table

#### SPATIAL — SpatialAccessor / AsyncSpatialAccessor

| Accessor | Method | Param | Current | Canonical | Fix Type |
|----------|--------|-------|---------|-----------|----------|
| Spatial | contains | `geom` positional | positional-with-default (pos 2) | keyword-only (`*, geom=`) | CLEAN BREAK |
| Spatial | contains | `schema` positional | positional-with-default (pos 3) | keyword-only (`*, schema=`) | CLEAN BREAK |
| Spatial | intersects | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | intersects | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | dwithin | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | dwithin | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | distance | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | distance | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | nearest | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | nearest | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | area | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | area | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | perimeter | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | perimeter | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | centroid | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | centroid | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | buffer | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | buffer | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | transform | `geom` positional | positional-with-default (pos 2) | keyword-only | CLEAN BREAK |
| Spatial | transform | `schema` positional | positional-with-default (pos 3) | keyword-only | CLEAN BREAK |
| Spatial | **within** | `schema` positional | `(lt, lg, rt, rg, schema="public", *, ...)` — `schema` is pos 5 positional-with-default | 4 identifiers stay positional → `*, schema=` moves to kw-only | **CLEAN BREAK (see note)** |
| Spatial | create_spatial_index | `column` positional | `(table, column="geometry", schema="public", name=None)` — no `*` | `(table, *, column=, schema=, name=)` | CLEAN BREAK |
| Spatial | list_geometry_columns | `schema` positional | `(schema=None)` — no `*` | `(*, schema=None)` | CLEAN BREAK |
| AsyncSpatial | (all 11 methods + 2 utilities) | same as sync | mirror of SpatialAccessor | same kw-only moves | CLEAN BREAK (D-11 parity) |

**Note on `within()` `*`-placement (RESEARCH Q1, flagged):** `within(self, left_table, left_geom, right_table, right_geom, schema="public", *, into=, ...)` — 4 required positional identifiers, then `schema` is currently positional-with-default. Under D-03, `schema` becomes keyword-only: `within(self, left_table, left_geom, right_table, right_geom, *, schema="public", into=, ...)`. This means the `*` moves from after the 4+1 positionals to after the 4 required identifiers only. A caller currently passing `db.spatial.within("lt", "lg", "rt", "rg", "myschema")` positionally will get `TypeError`. REQUIRES USER ACKNOWLEDGMENT.

---

#### SCHEMA — SchemaAccessor / AsyncSchemaAccessor

| Accessor | Method | Param | Current | Canonical | Fix Type |
|----------|--------|-------|---------|-----------|----------|
| Schema | create_database | `owner`, `template` | positional-with-default (no `*`) | `(name, *, owner=, template=)` | CLEAN BREAK |
| Schema | drop_database | `if_exists` | positional-with-default (no `*`) | `(name, *, if_exists=)` | CLEAN BREAK |
| Schema | database_exists | — | `(name)` — required only, no defaulted params | no change needed | — |
| Schema | list_databases | — | `()` — no params | no change needed | — |
| Schema | create_extension | `schema`, `if_not_exists` | positional-with-default (no `*`) | `(name, *, schema=, if_not_exists=)` | CLEAN BREAK |
| Schema | drop_extension | `if_exists`, `cascade` | positional-with-default (no `*`) | `(name, *, if_exists=, cascade=)` | CLEAN BREAK |
| Schema | list_extensions | — | `()` — no params | no change needed | — |
| Schema | has_extension | — | `(name)` — required only | no change needed | — |
| Schema | create_schema | `if_not_exists`, `owner` | positional-with-default (no `*`) | `(name, *, if_not_exists=, owner=)` | CLEAN BREAK |
| Schema | drop_schema | `if_exists`, `cascade` | positional-with-default (no `*`) | `(name, *, if_exists=, cascade=)` | CLEAN BREAK |
| Schema | list_schemas | — | `()` | no change needed | — |
| Schema | schema_exists | — | `(name)` — required only | no change needed | — |
| Schema | list_tables | `schema` | `(schema="public")` — no `*` | `(*, schema="public")` | CLEAN BREAK |
| Schema | table_exists | `schema` | `(name, schema="public")` — no `*` | `(name, *, schema="public")` | CLEAN BREAK |
| Schema | list_columns | `schema` | `(table, schema="public")` — no `*` | `(table, *, schema="public")` | CLEAN BREAK |
| Schema | columns_with_types | `schema` | `(table, schema="public")` — no `*` | `(table, *, schema="public")` | CLEAN BREAK |
| Schema | drop_table | `schema`, `if_exists`, `cascade` | positional-with-default (no `*`) | `(name, *, schema=, if_exists=, cascade=)` | CLEAN BREAK |
| Schema | truncate_table | `schema`, `cascade` | positional-with-default (no `*`) | `(name, *, schema=, cascade=)` | CLEAN BREAK |
| Schema | table_info | `schema` | `(name, schema="public")` — no `*` | `(name, *, schema="public")` | CLEAN BREAK |
| Schema | row_count | `schema` | `(name, schema="public")` — no `*` | `(name, *, schema="public")` | CLEAN BREAK |
| Schema | add_primary_key | `schema`, `name` | `(table, columns, schema=, name=)` — no `*` | `(table, columns, *, schema=, name=)` | CLEAN BREAK |
| Schema | add_foreign_key | `schema`, `ref_schema`, `name`, `on_delete`, `on_update` | positional-with-default (no `*`) | `(table, columns, ref_table, ref_columns, *, schema=, ref_schema=, name=, on_delete=, on_update=)` | CLEAN BREAK |
| Schema | add_unique_constraint | `schema`, `name` | positional-with-default (no `*`) | `(table, columns, *, schema=, name=)` | CLEAN BREAK |
| Schema | create_index | `schema`, `name`, `unique`, `method`, `if_not_exists` | positional-with-default (no `*`) | `(table, columns, *, schema=, name=, unique=, method=, if_not_exists=)` | CLEAN BREAK |
| Schema | drop_index | `schema`, `if_exists` | positional-with-default (no `*`) | `(name, *, schema=, if_exists=)` | CLEAN BREAK |
| Schema | list_indexes | `schema` | `(table, schema="public")` — no `*` | `(table, *, schema="public")` | CLEAN BREAK |
| Schema | list_constraints | `schema` | `(table, schema="public")` — no `*` | `(table, *, schema="public")` | CLEAN BREAK |
| Schema | primary_key | `schema` | `(table, schema="public")` — no `*` | `(table, *, schema="public")` | CLEAN BREAK |
| Schema | foreign_keys | `schema` | `(table, schema="public")` — no `*` | `(table, *, schema="public")` | CLEAN BREAK |
| Schema | sequences | `schema` | `(schema="public")` — no `*` | `(*, schema="public")` | CLEAN BREAK |
| Schema | views | `schema` | `(schema="public")` — no `*` | `(*, schema="public")` | CLEAN BREAK |
| Schema | describe | `schema` | `(table, schema="public")` — no `*` | `(table, *, schema="public")` | CLEAN BREAK |
| AsyncSchema | (all 32 methods) | mirror of sync | same pattern as SchemaAccessor | same kw-only moves | CLEAN BREAK (D-11 parity) |

---

#### TIMESCALE — TimescaleAccessor / AsyncTimescaleAccessor

| Accessor | Method | Param | Current | Canonical | Fix Type |
|----------|--------|-------|---------|-----------|----------|
| Timescale | create_hypertable | `schema`, `chunk_time_interval`, `if_not_exists`, `migrate_data` | positional-with-default (no `*`) | `(table, time_column, *, schema=, chunk_time_interval=, if_not_exists=, migrate_data=)` | CLEAN BREAK |
| Timescale | enable_compression | `segment_by`, `order_by`, `schema` | positional-with-default (no `*`) | `(table, *, segment_by=, order_by=, schema=)` | CLEAN BREAK |
| Timescale | add_compression_policy | `compress_after`, `schema` | positional-with-default (no `*`) | `(table, *, compress_after=, schema=)` | CLEAN BREAK |
| Timescale | add_retention_policy | `schema` | `(table, drop_after, schema="public")` — `schema` after required `drop_after` | `(table, drop_after, *, schema=)` | CLEAN BREAK |
| Timescale | list_hypertables | — | `()` | no change needed | — |
| Timescale | hypertable_info | `schema` | `(table, schema="public")` — no `*` | `(table, *, schema="public")` | CLEAN BREAK |
| Timescale | show_chunks | `older_than`, `newer_than`, `schema` | positional-with-default (no `*`) | `(table, *, older_than=, newer_than=, schema=)` | CLEAN BREAK |
| Timescale | drop_chunks | `older_than`, `newer_than`, `schema`, `dry_run` | positional-with-default (no `*`) | `(table, *, older_than=, newer_than=, schema=, dry_run=)` | CLEAN BREAK |
| Timescale | add_dimension | `partition_type`, `number_partitions`, `chunk_interval`, `schema`, `if_not_exists` | positional-with-default (no `*`) | `(table, column, *, partition_type=, number_partitions=, chunk_interval=, schema=, if_not_exists=)` | CLEAN BREAK |
| Timescale | add_reorder_policy | `schema`, `if_not_exists` | positional-with-default (no `*`) | `(table, index_name, *, schema=, if_not_exists=)` | CLEAN BREAK |
| Timescale | create_continuous_aggregate | `schema`, `materialized_only`, `with_no_data` | positional-with-default (no `*`) | `(view_name, select_sql, *, schema=, materialized_only=, with_no_data=)` | CLEAN BREAK |
| Timescale | refresh_continuous_aggregate | `window_start`, `window_end`, `schema` | positional-with-default (no `*`) | `(view_name, *, window_start=, window_end=, schema=)` | CLEAN BREAK |
| Timescale | add_continuous_aggregate_policy | `schedule_interval`, `schema`, `if_not_exists` | positional-with-default (no `*`) | `(view_name, start_offset, end_offset, *, schedule_interval=, schema=, if_not_exists=)` | CLEAN BREAK |
| Timescale | **time_bucket** | `where` param name | `(table, time_column, bucket_width, aggregates, where=None, schema="public", into="df")` | `where=` here is a raw SQL fragment (structural SQL, NOT a dict-equality filter) — same semantics as spatial `filter=`. DIFFERENT from the CRUD `where=` dict convention. | **DECISION (see note A)** |
| Timescale | **time_bucket** | `into=` default | `into="df"` (pandas DataFrame) | Spatial uses `into="rows"/"gdf"`. Timescale uses `into="df"/"rows"`. Different value-sets, different return types. | **DECISION (see note B)** |
| Timescale | **time_bucket** | param order | `where` before `schema` before `into` (no `*`) | Under D-03: `(table, time_column, bucket_width, aggregates, *, where=, schema=, into=)` | CLEAN BREAK (for kw-only; separate from param-name decision) |
| Timescale | **time_bucket_gapfill** | `where` param name | same raw-SQL fragment semantics as time_bucket `where=` | same DECISION (see note A) | **DECISION (see note A)** |
| Timescale | **time_bucket_gapfill** | `into=` default | `into="df"` | same as time_bucket (see note B) | **DECISION (see note B)** |
| Timescale | time_bucket_gapfill | param order | `(table, tc, bw, start, finish, aggregates, where=, schema=, into=)` — no `*` | `(table, time_column, bucket_width, start, finish, aggregates, *, where=, schema=, into=)` | CLEAN BREAK (for kw-only) |
| AsyncTimescale | (all methods) | mirror of sync | same pattern | same kw-only moves | CLEAN BREAK (D-11 parity) |

**Note A — `time_bucket.where=` param name (FLAGGED FOR USER DECISION):** The `where=` parameter on `time_bucket` and `time_bucket_gapfill` is a **raw SQL fragment** (structural SQL authored by the caller), NOT a dict-equality predicate like the CRUD `where=`. Renaming it to `filter=` would align it with the spatial `filter=` (same semantics: raw SQL fragment), but breaks the existing interface. Two options:
1. **Rename `where=` → `filter=`** (CLEAN BREAK + MIGRATION): consistent with spatial `filter=` semantics; user adjusts code.
2. **Keep `where=`** (no change): leaves a `where=` name that conflicts with the CRUD `where=`-dict convention established in v0.9.0.
Recommended: rename to `filter=` (CLEAN BREAK, consistent with spatial). User must decide.

**Note B — `into=` value-set divergence (FLAGGED FOR USER DECISION):** Spatial methods use `into="rows"` (default) and `into="gdf"` (GeoDataFrame). Timescale query helpers use `into="df"` (default, pandas DataFrame) and `into="rows"`. These are intentionally different because spatial returns geometry data (GeoDataFrame via geopandas) while timescale returns tabular time-series (DataFrame via pandas). The divergence is **semantically intentional** — homogenizing to a single value-set would require either removing GeoDataFrame support or adding it to timescale (out of scope). RECOMMENDATION: leave as-is (no change). User must confirm.

---

#### ETL — ETLAccessor / AsyncETLAccessor

| Accessor | Method | Param | Current | Canonical | Fix Type |
|----------|--------|-------|---------|-----------|----------|
| ETL | init | — | `()` — no params | no change needed | — |
| ETL | history | `limit` | `(name, limit=100)` — no `*` | `(name, *, limit=100)` | CLEAN BREAK |
| ETL | last_run | — | `(name)` — required only | no change needed | — |
| ETL | run | `dry_run` | `(pipeline, dry_run=False)` — no `*` | `(pipeline, *, dry_run=False)` | CLEAN BREAK |
| AsyncETL | (all methods) | mirror of sync | same pattern | same kw-only moves | CLEAN BREAK (D-11 parity) |

**Note on ETL:** The ETL accessor public surface is thin (`init`, `history`, `last_run`, `run`). `schema=` is absent from public methods (handled internally via `Pipeline.schema`). No `into=` on ETL methods.

---

#### ADMIN — AdminAccessor / AsyncAdminAccessor

| Accessor | Method | Param | Current | Canonical | Fix Type |
|----------|--------|-------|---------|-----------|----------|
| Admin | create_role | `password`, `login`, `superuser`, `createdb`, `createrole`, `inherit`, `replication`, `connection_limit`, `valid_until`, `in_roles`, `if_not_exists` | all positional-with-default (no `*`) | `(name, *, password=, login=, superuser=, createdb=, createrole=, inherit=, replication=, connection_limit=, valid_until=, in_roles=, if_not_exists=)` | CLEAN BREAK |
| Admin | drop_role | `if_exists` | `(name, if_exists=True)` — no `*` | `(name, *, if_exists=True)` | CLEAN BREAK |
| Admin | role_exists | — | `(name)` — required only | no change needed | — |
| Admin | list_roles | `include_system` | `(include_system=False)` — no `*` | `(*, include_system=False)` | CLEAN BREAK |
| Admin | alter_role | `password`, `login`, `superuser`, `createdb`, `createrole`, `connection_limit`, `valid_until`, `rename_to` | positional-with-default (no `*`) | `(name, *, password=, login=, superuser=, createdb=, createrole=, connection_limit=, valid_until=, rename_to=)` | CLEAN BREAK |
| Admin | grant_role | `with_admin` | `(role, member, with_admin=False)` — no `*` | `(role, member, *, with_admin=False)` | CLEAN BREAK |
| Admin | revoke_role | — | `(role, member)` — required only | no change needed | — |
| Admin | grant | `object_type`, `schema`, `with_grant_option` | `(privileges, on, to, object_type=, schema=, with_grant_option=)` — no `*` | `(privileges, on, to, *, object_type=, schema=, with_grant_option=)` | CLEAN BREAK |
| Admin | revoke | `object_type`, `schema`, `cascade` | `(privileges, on, from_role, object_type=, schema=, cascade=)` — no `*` | `(privileges, on, from_role, *, object_type=, schema=, cascade=)` | CLEAN BREAK |
| Admin | list_role_members | — | `(role)` — required only | no change needed | — |
| Admin | list_role_grants | — | `(role)` — required only | no change needed | — |
| AsyncAdmin | (all methods) | mirror of sync | same pattern | same kw-only moves | CLEAN BREAK (D-11 parity) |

---

#### MAINT — MaintAccessor / AsyncMaintAccessor

| Accessor | Method | Param | Current | Canonical | Fix Type |
|----------|--------|-------|---------|-----------|----------|
| Maint | size | `pretty` | `(pretty=True)` — no `*` | `(*, pretty=True)` | CLEAN BREAK |
| Maint | table_size | `schema`, `pretty` | `(table, schema="public", pretty=True)` — no `*` | `(table, *, schema=, pretty=)` | CLEAN BREAK |
| Maint | table_sizes | `schema`, `limit` | `(schema="public", limit=20)` — no `*` | `(*, schema=, limit=)` | CLEAN BREAK |
| Maint | vacuum | `table`, `schema`, `analyze`, `full` | `(table=None, schema="public", analyze=True, full=False)` — no `*` | `(*, table=, schema=, analyze=, full=)` | CLEAN BREAK |
| Maint | analyze | `table`, `schema` | `(table=None, schema="public")` — no `*` | `(*, table=, schema=)` | CLEAN BREAK |
| Maint | **explain** | `params`, `analyze`, `format` | `(sql, params=None, analyze=False, format="text")` — no `*`; `params` is positional-with-default | `(sql, *, params=, analyze=, format=)` | CLEAN BREAK |
| AsyncMaint | (all methods) | mirror of sync | same pattern | same kw-only moves | CLEAN BREAK (D-11 parity) |

---

#### BACKUP — BackupAccessor / AsyncBackupAccessor

| Accessor | Method | Param | Current | Canonical | Fix Type |
|----------|--------|-------|---------|-----------|----------|
| Backup | pg_dump | `format`, `schema_only`, `data_only`, `tables`, `exclude_tables`, `schemas`, `compress`, `jobs` | `(output_file, format=, schema_only=, ...)` — no `*` | `(output_file, *, format=, schema_only=, data_only=, tables=, exclude_tables=, schemas=, compress=, jobs=)` | CLEAN BREAK |
| Backup | pg_restore | `clean`, `if_exists`, `create`, `data_only`, `schema_only`, `tables`, `schemas`, `jobs`, `no_owner`, `no_privileges` | `(input_file, clean=, if_exists=, ...)` — no `*` | `(input_file, *, clean=, if_exists=, create=, data_only=, schema_only=, tables=, schemas=, jobs=, no_owner=, no_privileges=)` | CLEAN BREAK |
| Backup | copy_to_csv | `schema`, `columns`, `delimiter`, `header`, `null_string`, `encoding` | `(table, output_file, schema=, columns=, ...)` — no `*` | `(table, output_file, *, schema=, columns=, delimiter=, header=, null_string=, encoding=)` | CLEAN BREAK |
| Backup | copy_from_csv | `schema`, `columns`, `delimiter`, `header`, `null_string`, `encoding` | `(table, input_file, schema=, columns=, ...)` — no `*` | `(table, input_file, *, schema=, columns=, delimiter=, header=, null_string=, encoding=)` | CLEAN BREAK |
| AsyncBackup | (all methods) | mirror of sync | same pattern | same kw-only moves | CLEAN BREAK (D-11 parity) |

---

#### FLAT CORE — Database / AsyncDatabase (public methods not on accessors)

| Accessor | Method | Param | Current | Canonical | Fix Type |
|----------|--------|-------|---------|-----------|----------|
| Database | **execute** | `params`, `autocommit` | `(sql, params=None, autocommit=False)` — no `*`; `params` and `autocommit` positional-with-default | `(sql, *, params=, autocommit=)` | **DECISION (see note C)** |
| Database | execute_many | — | `(sql, params_seq)` — both required, no defaulted params | no change needed | — |
| Database | insert_many | `schema`, `on_conflict` | `(table, rows, schema="public", on_conflict=None)` — no `*` | `(table, rows, *, schema=, on_conflict=)` | CLEAN BREAK |
| Database | upsert_many | `update_columns`, `schema` | `(table, rows, conflict_columns, update_columns=None, schema="public")` — no `*` | `(table, rows, conflict_columns, *, update_columns=, schema=)` | CLEAN BREAK |
| Database | upsert | `update_columns`, `schema` | `(table, row, conflict_columns, update_columns=None, schema="public")` — no `*` | `(table, row, conflict_columns, *, update_columns=, schema=)` | CLEAN BREAK |
| Database | delete_where | `schema` | `(table, where, schema="public")` — no `*` | `(table, where, *, schema=)` | CLEAN BREAK |
| Database | update_where | `schema` | `(table, values, where, schema="public")` — no `*` | `(table, values, where, *, schema=)` | CLEAN BREAK |
| Database | exists | `schema` | `(table, where, schema="public")` — no `*` | `(table, where, *, schema=)` | CLEAN BREAK |
| Database | count | `where`, `schema` | `(table, where=None, schema="public")` — no `*` | `(table, *, where=, schema=)` | CLEAN BREAK |
| Database | stream | `params`, `batch_size` | `(sql, params=None, batch_size=1000)` — no `*` | `(sql, *, params=, batch_size=)` | CLEAN BREAK |
| Database | notify | `payload` | `(channel, payload="")` — no `*` | `(channel, *, payload=)` | CLEAN BREAK |
| Database | insert_batch | `schema`, `on_conflict`, `batch_size` | `(table, rows, schema=, on_conflict=, batch_size=)` — no `*` | `(table, rows, *, schema=, on_conflict=, batch_size=)` | CLEAN BREAK |
| Database | copy_insert | `schema`, `columns` | `(table, rows, schema=, columns=)` — no `*` | `(table, rows, *, schema=, columns=)` | CLEAN BREAK |
| Database | fetch_one | `params` | `(sql, params=None)` — no `*` | `(sql, *, params=)` | CLEAN BREAK |
| Database | fetch_val | `params` | `(sql, params=None)` — no `*` | `(sql, *, params=)` | CLEAN BREAK |
| Database | fetch_all | `params` | `(sql, params=None)` — no `*` | `(sql, *, params=)` | CLEAN BREAK |
| Database | paginate | `offset`, `order_by`, `where`, `descending`, `schema` | `(table, limit, offset=0, order_by=None, where=None, descending=False, schema="public")` — no `*`; `limit` is required but no defaulted params guard | `(table, limit, *, offset=, order_by=, where=, descending=, schema=)` | CLEAN BREAK |
| Database | from_dataframe | `schema`, `if_exists`, `primary_key`, `index`, `dtype` | `(df, table, schema=, if_exists=, primary_key=, index=, dtype=)` — no `*` | `(df, table, *, schema=, if_exists=, primary_key=, index=, dtype=)` | CLEAN BREAK |
| Database | to_dataframe | `schema`, `sql`, `params` | `(table=None, schema=, sql=, params=)` — no `*`; `table` has a default too | `(*, table=, schema=, sql=, params=)` | CLEAN BREAK |
| Database | from_geodataframe | `schema`, `if_exists`, `primary_key`, `spatial_index`, `geometry_column`, `srid` | `(gdf, table, schema=, if_exists=, primary_key=, spatial_index=, geometry_column=, srid=)` — no `*` | `(gdf, table, *, schema=, if_exists=, primary_key=, spatial_index=, geometry_column=, srid=)` | CLEAN BREAK |
| Database | to_geodataframe | `schema`, `sql`, `geometry_column`, `params` | `(table=None, schema=, sql=, geometry_column=, params=)` — no `*` | `(*, table=, schema=, sql=, geometry_column=, params=)` | CLEAN BREAK |
| AsyncDatabase | (all mirrored methods) | mirror of sync | same pattern | same kw-only moves | CLEAN BREAK (D-11 parity) |

**Note C — `Database.execute(sql, params=None, autocommit=False)` kw-only question (FLAGGED FOR EXPLICIT USER SIGN-OFF):**

Making `params` keyword-only on `execute` changes the most-used calling pattern in pycopg:
```python
# CURRENT (positional — very common):
db.execute("SELECT * FROM t WHERE id = %s", [42])

# AFTER (kw-only):
db.execute("SELECT * FROM t WHERE id = %s", params=[42])
```
This affects all direct callers, all internal accessor code that calls `self._db.execute(sql, params)` positionally, and all user code. D-03 says "optional/defaulted params become keyword-only" — `params` has a default of `None` so technically it qualifies. However:
1. Internal accessor code calls `self._db.execute(sql, params)` with positional params extensively (e.g. in schema.py, timescale.py, maint.py — ~30+ internal call sites).
2. `execute` is the most fundamental user-facing API call.
3. Making it kw-only would require updating all internal callers simultaneously (else the test suite breaks under `-W error::DeprecationWarning` gate — internal calls would cause TypeErrors, which is the desired breakage pattern... but these are not deprecation warnings, they are TypeErrors at runtime).

**Recommendation:** Keep `params` (and `autocommit`) as positional-with-default on `execute`, `execute_many`, `fetch_one`, `fetch_val`, `fetch_all`, `stream` (the raw SQL execution methods). These are the primitive I/O layer where `(sql, params)` is the established two-positional convention. Apply kw-only only to higher-level helper methods. REQUIRES EXPLICIT USER DECISION.

Same question applies to:
- `fetch_one(sql, params=None)` → `(sql, *, params=)` ?
- `fetch_val(sql, params=None)` → `(sql, *, params=)` ?
- `fetch_all(sql, params=None)` → `(sql, *, params=)` ?
- `stream(sql, params=None, batch_size=1000)` → `(sql, *, params=, batch_size=)` ?
- `maint.explain(sql, params=None, analyze=False, format="text")` → `(sql, *, params=, analyze=, format=)` ?

---

### Summary: Decisions Required Before Task 3

The following rows are flagged `DECISION` and require explicit user sign-off before Task 3 implements any fix:

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| D1 | `within()` `*`-placement: approve CLEAN BREAK (4 positional identifiers, then `*, schema=`)? | (a) Approve — `schema` becomes kw-only; (b) Keep current (schema stays positional pos 5) | Approve CLEAN BREAK — consistent with D-03 |
| D2 | `Database.execute(sql, params=None, autocommit=False)` — make `params` kw-only? | (a) CLEAN BREAK: `(sql, *, params=, autocommit=)`; (b) Keep positional — D-03 exception for primitive I/O layer | Keep positional (exception for raw-SQL execution primitives) |
| D3 | Raw-SQL `where=` on `time_bucket`/`time_bucket_gapfill` — rename to `filter=`? | (a) CLEAN BREAK: rename to `filter=` (consistent with spatial); (b) Keep `where=` | Rename to `filter=` (aligns spatial and timescale raw-SQL param names) |
| D4 | `into=` value-set divergence (`"rows"/"gdf"` spatial vs `"df"/"rows"` timescale) — homogenize? | (a) Leave as-is (intentional: different return-type semantics); (b) Homogenize | Leave as-is — semantically intentional |
| D5 | `fetch_one`, `fetch_val`, `fetch_all`, `stream`, `explain` — make `params` kw-only? | (a) CLEAN BREAK: `(sql, *, params=, ...)`; (b) Keep positional — same exception as `execute` | Keep positional for all raw-SQL execution primitives |

---

## Task 2: USER REVIEW GATE (D-05)

**Status: APPROVED — 2026-06-28**

The user reviewed the findings table and approved with the following per-row dispositions (these are the authoritative source of truth for Task 3):

| # | Decision | Approved Disposition |
|---|----------|---------------------|
| D1 | `within()` `*`-placement | **APPROVED CLEAN BREAK.** 4 required identifiers (`left_table`, `left_geom`, `right_table`, `right_geom`) stay positional; `*` goes right after them; `schema=` and everything else become keyword-only. |
| D2 | `Database.execute` `params`/`autocommit` kw-only | **KEEP POSITIONAL** — documented carve-out from D-03. Applies to: `Database`/`AsyncDatabase` `execute`, `fetch_one`, `fetch_val`, `fetch_all`, `stream`. `params` and `autocommit` remain positional-with-default on these methods. |
| D3 | `time_bucket`/`time_bucket_gapfill` `where=` rename | **RENAME `where=` → `filter=` WITH ONE-CYCLE DEPRECATION SHIM** — identical pattern to the spatial where→filter shim from Plan 03: `filter=None, where=None`; if `where` supplied emit `DeprecationWarning(stacklevel=2)` + forward to `filter`; if BOTH supplied raise `TypeError`. Add MIGRATION entry. |
| D4 | `into=` value-set divergence | **LEAVE AS-IS.** `"rows"/"gdf"` spatial vs `"df"/"rows"` timescale is intentionally different (different return-type semantics). No change. |
| D5 | `fetch_one`/`fetch_val`/`fetch_all`/`stream`/`maint.explain` `params` kw-only | **KEEP POSITIONAL** — same D-02/D-05 carve-out as `execute`. The `(sql, params)` two-positional convention is kept for all raw-SQL execution primitives. `maint.explain` also keeps `params` positional. |

**D2/D5 carve-out note (recorded for FREEZE-04 Plan 05 stability contract):** The raw-SQL execution primitives — `execute`, `fetch_one`, `fetch_val`, `fetch_all`, `stream` (both sync and async) and `maint.explain` — are intentional, documented exceptions to D-03. These methods form the primitive I/O layer where the `(sql, params)` two-positional convention is established and expected by users. This exception MUST be reflected in the FREEZE-04 stability contract in Plan 05.

**D3 MIGRATION entry (Plan 05 owns MIGRATION.md):** The `where=` → `filter=` rename on `time_bucket` and `time_bucket_gapfill` ships with a one-cycle deprecation shim. Users should update to `filter=` before 2.0. Plan 05 will add this to MIGRATION.md.

---

## Deviations from Plan

None — Task 1 executed exactly as planned. No fixes applied (D-05 compliance).

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This task is a read-only inventory pass — no code modified.

**T-41-09 (validate_identifiers count):** Not applicable for Task 1 — no code changes.
**T-41-10 (D-05 review gate):** HONORED — no fix applied before user review.

## Known Stubs

None — this plan produces a findings table only (Task 1). Task 3 (implementation) is pending user approval.

## Self-Check: PENDING

Self-check will be performed after Task 2 approval and Task 3 completion.
