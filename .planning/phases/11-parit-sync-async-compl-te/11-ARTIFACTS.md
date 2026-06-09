# Phase 11 — Artifacts This Phase Produces

This phase is a **parity / mechanical-mirror** phase. Every symbol below is NEWLY created (or signature-extended) in Phase 11 — the source-grounding / drift pass MUST exclude these from "missing twin" or "unexpected new symbol" drift checks, because their twins already exist on the opposite class.

## New async methods on `AsyncDatabase` (pycopg/async_database.py) — 9 (PAR-01/02)

| Symbol | Plan | Mirror of (sync) |
|--------|------|------------------|
| `async add_primary_key(self, table, columns, schema="public", name=None)` | 11-03 | `Database.add_primary_key` |
| `async add_foreign_key(self, table, columns, ref_table, ref_columns, schema="public", ref_schema="public", name=None, on_delete="NO ACTION", on_update="NO ACTION")` | 11-03 | `Database.add_foreign_key` |
| `async add_unique_constraint(self, table, columns, schema="public", name=None)` | 11-03 | `Database.add_unique_constraint` |
| `async truncate_table(self, name, schema="public", cascade=False)` | 11-03 | `Database.truncate_table` |
| `async drop_extension(self, name, if_exists=True, cascade=False)` | 11-04 | `Database.drop_extension` |
| `async database_exists(self, name) -> bool` | 11-04 | `Database.database_exists` |
| `async list_databases(self) -> list[str]` | 11-04 | `Database.list_databases` |
| `@classmethod async create(cls, name, host, port, user, password, owner, template, if_not_exists)` | 11-04 | `Database.create` (D-02) |
| `@classmethod async create_from_env(cls, name, owner, template, if_not_exists, dotenv_path)` | 11-04 | `Database.create_from_env` (D-02) |

## New sync methods on `Database` (pycopg/database.py) — 4 (PAR-03)

| Symbol | Plan | Mirror of (async) |
|--------|------|-------------------|
| `insert_many(self, table, rows, schema="public", on_conflict=None) -> int` | 11-02 | `AsyncDatabase.insert_many` |
| `upsert_many(self, table, rows, conflict_columns, update_columns=None, schema="public") -> int` | 11-02 | `AsyncDatabase.upsert_many` |
| `stream(self, sql, params=None, batch_size=1000) -> Iterator[dict]` | 11-02 | `AsyncDatabase.stream` |
| `notify(self, channel, payload="") -> None` | 11-02 | `AsyncDatabase.notify` |

> `listen` is deliberately NOT mirrored to sync (D-06) — remains async-only by design.

## New / changed on `Config` (pycopg/config.py)

| Symbol | Plan | Notes |
|--------|------|-------|
| `Config.async_url` (property) → `postgresql+psycopg_async://...` | 11-01 | NEW (D-04). `Config.url` UNCHANGED (`+psycopg`). |

## Behavioral fixes (no new symbol, changed behavior) — async_database.py

| Change | Plan | Requirement |
|--------|------|-------------|
| `async_engine` now built from `config.async_url` | 11-01 | C3 / PAR-06 |
| `from_dataframe` / `from_geodataframe` now call `await self.add_primary_key(...)` (warning removed) | 11-05 | C1 / PAR-04 |
| `async close()` now disposes `self._async_engine` (was `pass`) | 11-05 | C2 / PAR-05 |

## Signature/semantics extensions (async catches up to sync — D-07) — async_database.py

| Symbol | Plan | Change |
|--------|------|--------|
| `async create_extension` | 11-05 | gains `schema=None` + SCHEMA clause |
| `async create_schema` | 11-05 | gains `owner=None` + AUTHORIZATION clause |
| `async table_info` | 11-05 | return fields aligned to sync |
| `async list_roles` | 11-05 | return fields aligned to sync |

## New test helpers / fixtures (tests/)

| Helper | Plan | Notes |
|--------|------|-------|
| Async real-DB fixture (AsyncDatabase against `pycopg_test`) in test_parity.py | 11-06 | mirrors `db`/`cleanup_table` pattern from test_database_integration.py |
| Integration parity test cases (sync==async) for the 13 mirrored methods + C1 + 4 PAR-07 methods | 11-06 | D-03 |
| Per-method tests for all new sync/async methods | 11-06 | |
| Targeted coverage gap-fill tests | 11-07 | only if measured coverage < 90 |

## Test-config / allow-list edits

| File | Plan | Change |
|------|------|--------|
| `tests/test_parity.py` SYNC_ONLY_METHODS | 11-06 | remove the 9 now-mirrored sync methods (keep `engine`) |
| `tests/test_parity.py` ASYNC_ONLY_METHODS | 11-06 | remove insert_many/upsert_many/stream/notify (keep `async_engine`, keep `listen` + comment) |
| `tests/test_parity.py` KNOWN_SIGNATURE_MISMATCHES | 11-06 | remove create_schema, create_extension |
| `pyproject.toml` addopts | 11-07 | `--cov-fail-under` 80 → 90 (PAR-09, gated on measured ≥90) |
