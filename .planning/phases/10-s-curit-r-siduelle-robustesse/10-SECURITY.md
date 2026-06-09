---
status: secure
phase: 10
threats_total: 10
threats_closed: 10
threats_open: 0
audited: 2026-06-09
---

# Phase 10 — Sécurité Résiduelle & Robustesse: Security Audit Report

**Auditor:** Claude (gsd-security-auditor), claude-sonnet-4-6
**Audited:** 2026-06-09
**ASVS Level:** 2
**Phase Goal:** Close residual security/correctness bugs B1/B2/B3/B5 + coverage ratchet to 80.

---

## Threat Verification Table

| Threat ID | Category | Component | Disposition | Status | Evidence |
|-----------|----------|-----------|-------------|--------|----------|
| T-10-01 | Tampering/Repudiation | PooledDatabase.execute / AsyncPooledDatabase.execute (B1) | mitigate | CLOSED | pool.py:155-157 (sync): `rows = cur.fetchall() if cur.description else []` then `conn.commit()` then `return rows` — correct fetch-then-commit-then-return order confirmed by direct read. pool.py:353-355 (async): `rows = await cur.fetchall() if cur.description else []` then `await conn.commit()` then `return rows`. Tests: tests/test_pool_commit.py asserts INSERT...RETURNING persistence across a separate pool checkout. |
| T-10-02 | Tampering (Injection) | utils.validate_* call sites + async create_role (SEC-05) | mitigate | CLOSED | 17-item D-01 audit (.planning/phases/10-s-curit-r-siduelle-robustesse/10-AUDIT-D01.md) confirms all validate_* call sites present. async_database.py:1078 `validate_identifier(name)` and async_database.py:1106 `if valid_until: validate_timestamp(valid_until)` confirmed by direct read. tests/test_sql_injection.py: 64 parametrized tests, all passing. |
| T-10-03 | Tampering (Integrity) | Migrator._apply / Migrator.rollback (B3) | mitigate | CLOSED | migrations.py:233 `with self.db.transaction() as conn:` wraps `cur.execute(up_sql)` + INSERT version row. migrations.py:292 `with self.db.transaction() as conn:` wraps `cur.execute(down_sql)` + DELETE version row. Both confirmed by direct read. Test: tests/test_migration_atomicity.py. |
| T-10-03-DoS | Denial of Service | Migrator partial-failure state | accept | CLOSED | See Accepted Risks Log. |
| T-10-04 | Denial of Service (Availability) | pg_dump / pg_restore / _psql_restore env (B5) | mitigate | CLOSED | database.py:10 `import os` present. Three subprocess sites confirmed by direct read: database.py:2191 (`pg_dump`), database.py:2286 (`pg_restore`), database.py:2305 (`_psql_restore`) — all use `env={**os.environ, **env}`. `grep -rn "subprocess\.os" pycopg/` returns zero matches. Test: tests/test_subprocess_env.py. |
| T-10-04-IE | Information Disclosure | PGPASSWORD in child env | accept | CLOSED | See Accepted Risks Log. |
| T-10-05 | Denial of Service (Resource exhaustion) | Database.session / AsyncDatabase.session (B2 residual) | mitigate | CLOSED | database.py:390-414: nested try/finally confirmed by direct read — `commit_exc` captured before re-raise; `close()` in inner `finally` wrapped in try/except; if `commit_exc is not None` close errors logged via `logger.warning()` not re-raised; `_session_conn = None` in outer `finally`. async_database.py:224-248: identical structure for async path. WR-01 follow-up (commit 6b507b0) present and verified — close exception suppression when commit already failed is implemented. Test: tests/test_session_leak.py (18 tests: 5 sync + 5 async base + edge cases). |
| T-10-05-EoP | Elevation/Repudiation | masked original exception (SEC-02 core) | accept | CLOSED | See Accepted Risks Log. |
| T-10-06 | Repudiation (Process integrity) | coverage ratchet (D-07) | mitigate | CLOSED | pyproject.toml:88 `--cov-fail-under=80` confirmed by direct read. No `--cov-fail-under=70` present (grep returns zero matches). Gate was flipped only after measured coverage reached 80.71% with 574 passed / 2 skipped / 6 pre-existing integration failures deselected. |
| T-10-06-FT | Tampering (Test reliability) | coverage-fill tests | mitigate | CLOSED | tests/test_pool.py class `TestAsyncPooledDatabaseMethods` (8 tests) — each asserts return values, call counts, and awaited operations (e.g., `assert result == [{"col1": 1, "col2": 2}]`, `mock_cursor.execute.assert_called_once_with(...)`). tests/test_database.py classes `TestDatabaseGrantRevoke` (13 tests) and `TestDatabaseRoleAdminBranches` (12 tests) assert SQL string content (`assert "SELECT, INSERT" in call_sql`) and call counts — not instantiation-only. |

---

## Accepted Risks Log

### T-10-03-DoS — Migrator partial-failure state (Denial of Service)

**Disposition:** accept

**Rationale:** A migration that fails mid-execution rolls back atomically via `with self.db.transaction()` (confirmed present for both `_apply` and `rollback` in T-10-03 verification). Because the transaction rolls back entirely, no partial schema change or orphaned version row can occur. A failed migration is therefore fully re-runnable — there is no locked or half-applied state that would prevent subsequent execution. The only availability concern is that the operator must diagnose and correct the migration SQL before re-running, which is inherent to any migration system and not addressable at the library level.

**Status:** CLOSED — rationale is sound; the atomicity mitigation in T-10-03 eliminates the half-state scenario that would make this a genuine DoS risk.

---

### T-10-04-IE — PGPASSWORD in child process environment (Information Disclosure)

**Disposition:** accept

**Rationale:** Passing credentials via environment variable (`PGPASSWORD`) rather than command-line arguments (`-W`, `--password=`) is the standard libpq-recommended approach. Environment variables are not visible in `/proc/<pid>/cmdline` (which is world-readable on Linux), whereas argv is. The risk of environment exposure (e.g., via `/proc/<pid>/environ`) requires either root access or the same UID as the child process, making it a significantly higher bar than cmdline exposure. The alternative — using a `.pgpass` file or connection service file — would require additional file management outside the library's scope. This risk is accepted as it follows the established PostgreSQL ecosystem convention and is not worsened by this phase.

**Status:** CLOSED — standard libpq practice; env-not-argv is the correct mitigation for this class of credential exposure.

---

### T-10-05-EoP — Masked original exception (SEC-02 core)

**Disposition:** accept

**Rationale:** This acceptance covers the pre-phase state where cursor status handling and re-raise were already in place, and the plan adds no new masking. The B2 fix in phase 10 actually strengthens this: the WR-01 follow-up (commit 6b507b0) adds explicit `commit_exc` capture so that when `close()` also raises after a `commit()` failure, the close error is logged as a warning rather than replacing the commit exception. The original commit exception therefore always propagates to the caller. The residual accepted risk is that a logged close warning may go unnoticed in environments without log monitoring — this is inherent to any resource-cleanup path and does not represent an elevation-of-privilege scenario. The exception propagation chain is preserved.

**Status:** CLOSED — original exception propagation is verified present; close-error suppression is logged not silenced.

---

## Unregistered Flags

No threat flags from SUMMARY.md `## Threat Flags` sections introduced new unregistered attack surface. The WR-01 follow-up noted in the threat register was verified as implemented (commit 6b507b0 present in database.py and async_database.py).

---

## Summary

All 10 threats in the register are CLOSED. 7 mitigate threats have confirmed code-level evidence; 3 accept threats have sound rationales documented above. No implementation gaps found. Phase 10 may ship.

---

_Audit performed by: Claude (gsd-security-auditor), claude-sonnet-4-6_
_Date: 2026-06-09_
