---
phase: 11
slug: parit-sync-async-compl-te
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-09
---

# Phase 11 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Phase 11 mirrored 13 methods across the sync/async boundary and aligned signatures.
The dominant security concern is **SQL injection via identifier interpolation** — new
DDL/admin methods build SQL with f-strings, so every interpolated identifier must pass a
`validate_*` helper (the controls established in Phase 10) before reaching the database.
Secondary concerns: credential leakage through the new `Config.async_url`, resource/credential
leak from the async engine lifecycle, and false-assurance from the coverage ratchet.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Config → SQLAlchemy URL | host/port/db/user/password assembled into `Config.async_url` for the async engine | DB credentials |
| Config object → logs/repr | `__repr__`/logging must not leak credentials | DB credentials |
| caller → SQL identifiers | `table`/`schema`/columns/`channel` interpolated into sync batch/notify SQL | identifiers (untrusted) |
| caller → DDL identifiers | table/schema/columns/ref_table/constraint/ON DELETE-UPDATE action interpolated into async ALTER/TRUNCATE/FK SQL | identifiers + FK action (untrusted) |
| caller → DB/extension/owner/template names | interpolated into async CREATE/DROP DATABASE, CREATE/DROP EXTENSION, CREATE SCHEMA SQL | identifiers (untrusted) |
| admin connection to `postgres` | elevated-privilege connection used for DB creation | admin DB session |
| async engine lifecycle | engine holds pooled connections/credentials until disposed | DB credentials |
| test code → `pycopg_test` DB | tests create/drop temp tables/databases on the real test instance | test DB objects |
| CI gate → merge protection | coverage floor in `pyproject.toml`/`tests.yml` governs what merges | merge assurance |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-11-01 | Information Disclosure | `Config.async_url` (credentials in URL) | mitigate | Built on demand; password not in `__repr__`/logging — `config.py:297-298` excludes password from repr; `async_url` at `config.py:215-238` not persisted. | closed |
| T-11-02 | Tampering | async driver scheme | accept | Hardcoded literal `postgresql+psycopg_async://`; no caller input flows into the scheme (`async_database.py:89` via `config.async_url`). | closed |
| T-11-03 | Tampering (SQL injection) | sync `insert_many`/`upsert_many`/`notify` identifiers | mitigate | `validate_identifiers(table, schema)` + `validate_identifiers(*columns)` before f-string (`database.py:500,503,550-551`); `validate_identifier(channel)` before `pg_notify` (`database.py:600`); row VALUES via `%s`. | closed |
| T-11-04 | Tampering | `stream` sql passthrough | accept | Forwards caller-supplied SQL verbatim — same contract as `execute`; caller owns query text. No new injection surface. | closed |
| T-11-05 | Tampering (SQL injection) | async `add_primary_key`/`add_unique_constraint`/`add_foreign_key`/`truncate_table` identifiers | mitigate | `validate_identifiers(...)` before f-string: `async_database.py:814` (ALTER), `:858-860` (FK), `:909` (UNIQUE), `:785` (TRUNCATE). | closed |
| T-11-06 | Tampering | FK `on_delete`/`on_update` action string | mitigate | `valid_actions` allow-set check; `ValueError` before SQL (`async_database.py:865-873`). | closed |
| T-11-07 | Tampering (SQL injection) | async + sync `create`/`create_from_env`/`drop_extension` identifiers | mitigate | `validate_extension_name(name)` now first line of both `AsyncDatabase.drop_extension` (`async_database.py:1088`) and `Database.drop_extension` (`database.py:881`); `create`/`create_from_env` identifiers validated; existence check via `%s`. **Closed during this audit** (gap found and fixed — see audit trail). | closed |
| T-11-08 | Elevation of Privilege | admin connect to `postgres` with autocommit | accept | Same posture as established sync `create`/`create_database`; credentials from caller's own Config (no new secret source); DB creation inherently needs admin rights. | closed |
| T-11-09 | Tampering (SQL injection) | async `create_extension` `schema`, `create_schema` `owner` | mitigate | `validate_identifier(name)` + `if owner: validate_identifier(owner)` (`async_database.py:636-638`); `validate_extension_name(name)` + `if schema: validate_identifier(schema)` (`async_database.py:1061-1063`). | closed |
| T-11-10 | Information Disclosure / resource leak | async engine not disposed (was no-op close) | mitigate | `async close()` disposes engine and nulls reference (`async_database.py:2773-2775`), mirroring sync `close()`. | closed |
| T-11-11 | Tampering | C1 `add_primary_key` call in `from_dataframe`/`from_geodataframe` | mitigate | `await self.add_primary_key(...)` (`async_database.py:1910-1911`, `:2028-2029`); `add_primary_key` validates via `validate_identifiers` (`:814`). | closed |
| T-11-12 | Tampering | test fixtures leaving residue | mitigate | Unique temp names via `uuid4` (`tests/test_parity.py:176-179`); throwaway databases dropped in `finally` (`:461-462`) → idempotent reruns. | closed |
| T-11-SC | Tampering | test deps (pytest/pytest-asyncio) | accept | No new package installs — existing test stack from `pyproject.toml`/`uv.lock`; no Package Legitimacy Gate triggered. | closed |
| T-11-13 | Repudiation / false assurance | coverage gate set above actual coverage | mitigate | `--cov-fail-under=90` (`pyproject.toml:88`) raised only after measured coverage hit 91.61% (11-07-SUMMARY; D-08 ordering honored). | closed |
| T-11-14 | Tampering | coverage gate lowered | accept | Ratchet policy documented (never lowered); 80 → 90 is the only change; no mechanism here lowers it. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-11-01 | T-11-02 | Async driver scheme is a hardcoded literal (`postgresql+psycopg_async://`); no caller input reaches the scheme. | Phase 11 plan (11-01) | 2026-06-09 |
| AR-11-02 | T-11-04 | `stream` forwards caller-supplied SQL verbatim — identical contract to `execute`; the caller owns query text. No new injection surface vs existing API. | Phase 11 plan (11-02) | 2026-06-09 |
| AR-11-03 | T-11-08 | Admin connect to `postgres` with autocommit is inherent to DB creation; same posture as established sync path; credentials come from the caller's own Config. | Phase 11 plan (11-04) | 2026-06-09 |
| AR-11-04 | T-11-SC | No new runtime or test dependencies introduced; existing stack only. | Phase 11 plan (11-06) | 2026-06-09 |
| AR-11-05 | T-11-14 | Coverage ratchet is documented as never-lowered; the only change is 80 → 90. No code path lowers the gate. | Phase 11 plan (11-07) | 2026-06-09 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-09 | 14 | 14 | 0 | gsd-security-auditor (sonnet) + orchestrator |

**Audit notes (2026-06-09):** Initial audit returned 13/14 closed with **T-11-07 OPEN** —
both `AsyncDatabase.drop_extension` (`async_database.py:1079-1093`) and
`Database.drop_extension` (`database.py:872-886`) interpolated the extension `name` into
`DROP EXTENSION "{name}"` with only double-quoting and **no** `validate_extension_name(name)`
call, despite the T-11-07 mitigation plan explicitly naming this method (its twin
`create_extension` already validated). A pre-existing gap that Phase 11 mirrored without
adding the declared control. User chose **fix the mitigation**: `validate_extension_name(name)`
added as the first line of both methods (import already present). Lint clean; 289
parity/sync/async tests pass; malicious-name rejection confirmed. T-11-07 → **closed**.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-09
