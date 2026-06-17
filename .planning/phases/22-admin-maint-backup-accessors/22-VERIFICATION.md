---
phase: 22-admin-maint-backup-accessors
verified: 2026-06-17T17:55:33Z
status: passed
score: 17/17
overrides_applied: 0
---

# Phase 22: Admin, Maint & Backup Accessors — Verification Report

**Phase Goal:** Users can access `db.admin.*`, `db.maint.*`, and `db.backup.*` with all methods working, and the 22 legacy flat names on `db.*` all warn and delegate — three accessors delivered in one phase using the pattern already validated in Phase 21
**Verified:** 2026-06-17T17:55:33Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| T-01 | `db.admin.*` / `async_db.admin.*` exposes 11 methods via `AdminAccessor` / `AsyncAdminAccessor` | VERIFIED | `python -c "...inspect.getmembers(AdminAccessor)..."` → 11 public methods each: `alter_role, create_role, drop_role, grant, grant_role, list_role_grants, list_role_members, list_roles, revoke, revoke_role, role_exists` |
| T-02 | `db.maint.*` / `async_db.maint.*` exposes 6 methods via `MaintAccessor` / `AsyncMaintAccessor` | VERIFIED | Introspection → 6 public methods each: `analyze, explain, size, table_size, table_sizes, vacuum` |
| T-03 | `db.backup.*` / `async_db.backup.*` exposes 4 public methods + `_psql_restore` via `BackupAccessor` / `AsyncBackupAccessor` | VERIFIED | Introspection → 4 public methods each: `copy_from_csv, copy_to_csv, pg_dump, pg_restore`; `hasattr(..., '_psql_restore')` passes on both classes |
| T-04 | `create_role` sibling calls route through `self._db.admin.*` (not flat `self._db.role_exists`/`self._db.grant_role`) | VERIFIED | `grep -nE 'self\._db\.(role_exists\|grant_role)\(' admin.py` returns nothing; `grep -c 'self\._db\.admin\.(role_exists\|grant_role)'` returns 2 each |
| T-05 | `db.admin` / `db.maint` / `db.backup` are lazily-cached properties on `Database` | VERIFIED | `grep -c '    def admin(self)'` returns 1 each in `database.py`; `grep -c 'AdminAccessor(self)'` / `MaintAccessor(self)` / `BackupAccessor(self)` each return 1 |
| T-06 | `async_db.admin` / `async_db.maint` / `async_db.backup` are lazily-cached properties on `AsyncDatabase` | VERIFIED | Same checks on `async_database.py` → 1 each for `AsyncAdminAccessor(self)` / `AsyncMaintAccessor(self)` / `AsyncBackupAccessor(self)` |
| T-07 | Exactly 21 `@deprecated_alias` stubs on `Database` (11 admin + 6 maint + 4 backup) | VERIFIED | `grep -c '@deprecated_alias("admin\.'` returns 11; `"maint\.` returns 6; `"backup\.` returns 4 (total 21 new Phase 22 stubs; 27 total including 6 Phase 21 timescale stubs) |
| T-08 | Exactly 21 `@deprecated_alias` stubs on `AsyncDatabase` | VERIFIED | Same grep counts on `async_database.py` → 11 + 6 + 4 = 21 |
| T-09 | `_psql_restore` is NOT exposed as a flat stub on `Database` or `AsyncDatabase` | VERIFIED | `grep -c '_psql_restore' database.py` returns 0; same for `async_database.py` |
| T-10 | 6 new accessor classes exported from `pycopg.__init__` and in `__all__` | VERIFIED | `python -c "import pycopg; assert all(n in pycopg.__all__ for n in ['AdminAccessor','AsyncAdminAccessor','MaintAccessor','AsyncMaintAccessor','BackupAccessor','AsyncBackupAccessor']); print('exports OK')"` exits 0 |
| T-11 | SQL injection validators travel with moved bodies (no regression) | VERIFIED | `admin.py`: `grep -c 'validate_identifier'` returns 34, `'validate_identifiers'` returns 9; `maint.py`: `validate_identifiers` present; `tests/test_sql_injection.py` passes 102 tests |
| T-12 | No `shell=True` in `backup.py`; `asyncio` imported at module level | VERIFIED | `grep -nE 'shell\s*=\s*True' backup.py` returns nothing; `grep -nE '^import asyncio' backup.py` returns line 16 |
| T-13 | Each of the 21 flat aliases warns (correct message + stacklevel=2) and delegates, proven DB-free | VERIFIED | `uv run pytest tests/test_admin_aliases.py tests/test_maint_aliases.py tests/test_backup_aliases.py -q -o addopts=""` → 22 passed (11 sync + 11 async admin = 22 per file, 3 files); total 47 alias+parity tests pass |
| T-14 | `test_parity` passes with `AdminAccessor`, `MaintAccessor`, `BackupAccessor` pairs registered | VERIFIED | `pytest tests/test_parity.py::test_accessor_parity -v` → 5 pairs all pass: Timescale, ETL, Admin, Maint, Backup |
| T-15 | Existing call-sites migrated; main suite emits no internal `DeprecationWarning` | VERIFIED | `pytest tests/test_database.py tests/test_async_database.py tests/test_sql_injection.py tests/test_subprocess_env.py -q -o addopts="" -W error::DeprecationWarning -k "not alias"` → 384 passed |
| T-16 | Full suite green with coverage >= 94% | VERIFIED | `uv run pytest` → 1049 passed, 2 pre-existing failures (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`); coverage 95.42% ≥ 94% gate |
| T-17 | Alias tests isolate warnings; `-W error::DeprecationWarning` does not break | VERIFIED | `pytest tests/test_*_aliases.py tests/test_parity.py -q -o addopts="" -W error::DeprecationWarning` → 64 passed; no filterwarnings added globally (`grep -c 'filterwarnings' test_*_aliases.py` returns 0 each) |

**Score:** 17/17 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/admin.py` | `AdminAccessor` + `AsyncAdminAccessor`, 11 public methods each | VERIFIED | 543+ lines; imports `validate_identifier`, `validate_identifiers`, `validate_object_type`, `validate_privileges`, `validate_timestamp`, `build_role_options`; `TYPE_CHECKING` guard pattern; no circular import |
| `pycopg/maint.py` | `MaintAccessor` + `AsyncMaintAccessor`, 6 public methods each | VERIFIED | `self._db.config.database` rewrites present (4 occurrences); no bare `self.execute` or `self.config` calls remain |
| `pycopg/backup.py` | `BackupAccessor` + `AsyncBackupAccessor`, 4 public + `_psql_restore` | VERIFIED | `import asyncio` at module level; `build_pg_dump_cmd`/`build_pg_restore_cmd` imported; 5 `_psql_restore` occurrences (2 defs + 2 calls + 1 docstring ref); no `shell=True`; 33 `self._db.config.*` rewrites |
| `pycopg/database.py` | Cache fields, 3 lazy properties, 21 stubs; `_psql_restore` removed | VERIFIED | `_admin`/`_maint`/`_backup: ... | None = None` cache fields confirmed; 3 properties confirmed; 27 total stubs (6 timescale + 21 new); `_psql_restore` count = 0 |
| `pycopg/async_database.py` | Async equivalents; `_psql_restore` removed | VERIFIED | Same checks pass; `_psql_restore` count = 0 |
| `pycopg/__init__.py` | 6 new accessor classes in imports + `__all__` | VERIFIED | 3 import lines present (note: backup and maint lines use reversed class order vs plan template wording, but both classes are correctly imported and in `__all__`) |
| `tests/test_admin_aliases.py` | 11 sync + 11 async admin alias tests | VERIFIED | `_SYNC_ALIAS_ARGS` has 11 keys; `class TestAdminAliases` confirmed; MagicMock injection via `db._admin`; per-test `catch_warnings` isolation |
| `tests/test_maint_aliases.py` | 6 sync + 6 async maint alias tests | VERIFIED | `_SYNC_ALIAS_ARGS` has 6 keys; injection via `db._maint` |
| `tests/test_backup_aliases.py` | 4 sync + 4 async backup alias tests | VERIFIED | `_SYNC_ALIAS_ARGS` has 4 keys; injection via `db._backup`; `_psql_restore` not tested (private, correct) |
| `tests/test_parity.py` | 3 appended `ACCESSOR_PAIRS` entries | VERIFIED | `(AdminAccessor, AsyncAdminAccessor)`, `(MaintAccessor, AsyncMaintAccessor)`, `(BackupAccessor, AsyncBackupAccessor)` each confirmed with `grep -c` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `admin.py::AdminAccessor.create_role` | `self._db.admin.role_exists` / `self._db.admin.grant_role` | sibling-accessor delegation (D-02) | VERIFIED | `grep -c 'self\._db\.admin\.role_exists'` = 2 (sync+async); same for `grant_role` = 2; `grep -nE 'self\._db\.(role_exists\|grant_role)\('` returns nothing |
| `backup.py::BackupAccessor.pg_restore` | `self._psql_restore` | private companion call | VERIFIED | `grep -n '_psql_restore' backup.py` shows call at line 160 (sync `pg_restore`) and line 494 (async `pg_restore`) |
| `database.py::Database.admin` (property) | `pycopg.admin.AdminAccessor` | lazy construct + cache on `self._admin` | VERIFIED | `grep -c 'AdminAccessor(self)' database.py` = 1; property body confirms conditional instantiation pattern |
| `database.py` flat stubs | `db.<accessor>.<method>` | `@deprecated_alias` decorator | VERIFIED | 21 stubs confirmed; alias tests prove warn+delegate for all 21 |
| `tests/test_*_aliases.py` | `db._admin` / `db._maint` / `db._backup` | MagicMock injection into cache field | VERIFIED | Lines confirmed: `db._admin = mock_accessor` (line 79, 149), `db._maint = mock_accessor` (lines 69, 139), `db._backup = mock_accessor` (lines 66, 136) |
| `tests/test_parity.py::ACCESSOR_PAIRS` | `test_accessor_parity` | parametrized registry | VERIFIED | `(AdminAccessor, AsyncAdminAccessor)` present; 5 pairs all pass |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 3 accessor modules importable, no circular import | `python -c "import pycopg.admin, pycopg.maint, pycopg.backup"` | exit 0 | PASS |
| AdminAccessor 11 public methods (sync + async) | introspection assert | exit 0 | PASS |
| MaintAccessor 6 public methods (sync + async) | introspection assert | exit 0 | PASS |
| BackupAccessor 4 public + `_psql_restore` (sync + async) | introspection assert | exit 0 | PASS |
| 6 exports in `pycopg.__all__` | `python -c "import pycopg; assert all(n in pycopg.__all__ ...)"` | exit 0 | PASS |
| 21 stubs on Database (all accessor combinations) | source inspection assert | exit 0 | PASS |
| 21 stubs on AsyncDatabase + `_psql_restore` absent | source inspection assert | exit 0 | PASS |
| Alias tests + parity pass DB-free | `pytest test_*_aliases.py test_parity.py::test_accessor_parity` | 47 passed | PASS |
| `-W error::DeprecationWarning` clean on alias + parity | `pytest ... -W error::DeprecationWarning` | 64 passed | PASS |
| Migrated suite clean under `-W error::DeprecationWarning` | `pytest test_database.py test_async_database.py test_sql_injection.py test_subprocess_env.py -W error::DeprecationWarning -k "not alias"` | 384 passed | PASS |
| Full suite coverage gate | `uv run pytest` | 95.42% ≥ 94%, 1049 passed, 2 pre-existing failures | PASS |
| interrogate ≥ 95% | `uv run interrogate pycopg -f 95` | 100% | PASS |
| ruff on new accessor files | `uv run ruff check pycopg/admin.py pycopg/maint.py pycopg/backup.py` | All checks passed | PASS |
| black format on new + modified files | `uv run black --check pycopg/admin.py pycopg/maint.py pycopg/backup.py pycopg/database.py pycopg/async_database.py pycopg/__init__.py` | All unchanged | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ADM-01 | 22-01/02/03-PLAN.md | `db.admin.*` / `async_db.admin.*` exposes 11 role & permission methods; flat `db.*` names remain as deprecated aliases | SATISFIED | `AdminAccessor` + `AsyncAdminAccessor` with 11 public methods each; 11 `@deprecated_alias("admin.*")` stubs on both `Database` and `AsyncDatabase`; alias tests prove warn+delegate |
| MNT-01 | 22-01/02/03-PLAN.md | `db.maint.*` / `async_db.maint.*` exposes 6 maintenance/size methods; flat names remain as deprecated aliases | SATISFIED | `MaintAccessor` + `AsyncMaintAccessor` with 6 public methods each; 6 `@deprecated_alias("maint.*")` stubs on both database classes; alias tests prove warn+delegate |
| BKP-01 | 22-01/02/03-PLAN.md | `db.backup.*` / `async_db.backup.*` exposes 4 dump/restore/CSV methods; flat names remain as deprecated aliases | SATISFIED | `BackupAccessor` + `AsyncBackupAccessor` with 4 public methods each; 4 `@deprecated_alias("backup.*")` stubs on both database classes; `_psql_restore` private companion correctly present on accessors only; alias tests prove warn+delegate |

Note on ADM-01 wording: REQUIREMENTS.md ADM-01 text says "12 role & permission methods" but lists only 11 (documented off-by-one in CONTEXT.md D-01). The real authoritative count is 11 — verified implemented. This is a stale REQUIREMENTS.md cosmetic issue, not an implementation gap.

---

### Anti-Patterns Found

No TBD, FIXME, or XXX markers found in any Phase 22 new/modified file.
No PLACEHOLDER, HACK, or TODO debt markers found.
No `shell=True` subprocess calls (security: list-form subprocess preserved verbatim from source).
No global `filterwarnings` added to test files.
No `--cov-fail-under` threshold lowered (still 94%).

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | — | — | — |

---

### Pre-Existing Test Failures (Confirmed Not Phase 22 Regressions)

Two tests fail in the full suite but are documented pre-existing environmental failures:

1. `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — `psycopg.ProgrammingError: Explicit commit() forbidden within a Transaction context`; present before Phase 22 (documented in `pycopg-flaky-db-tests.md` and `phase19-shipped.md` memory notes, traced to session-context commit quirk).

2. `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — `UndefinedTable`; present before Phase 22 (fixture-isolation ordering, documented same memory notes).

Neither failure is in any file modified by Phase 22. The Phase 22 accessor changes do not touch the spatial index or async transaction code paths.

---

### Human Verification Required

None. All observable truths are verifiable programmatically. The phase delivers a pure refactor (verbatim body moves + alias wiring) — no new behavior to validate via UI or external service.

---

## Gaps Summary

No gaps. All 17 truths verified, all artifacts substantive and wired, all key links confirmed.

ROADMAP success criteria status:
- SC-1 (accessor methods return same results as old flat calls): SATISFIED — bodies moved verbatim (D-06); 384-test migrated suite passes with -W error confirming call paths work
- SC-2 (22 legacy flat names warn and delegate): SATISFIED — 21 actual flat names (ROADMAP has documented off-by-one stale count of 22; real count is 21); all 21 stubs verified; alias tests prove warn+delegate for all
- SC-3 (`test_parity` with 3 new accessor pairs): SATISFIED — 5 total pairs all pass
- SC-4 (coverage ≥ 94%): SATISFIED — 95.42%

---

_Verified: 2026-06-17T17:55:33Z_
_Verifier: Claude (gsd-verifier)_
