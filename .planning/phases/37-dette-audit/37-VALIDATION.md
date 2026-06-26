---
phase: 37
slug: dette-audit
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-26
---

# Phase 37 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio 0.23+ (`asyncio_mode = "auto"`); pytest-randomly added in Wave 1 (Plan 01) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`--cov-fail-under=94`, unchanged this phase) + `[tool.ruff.lint]` (migrated in Plan 01) |
| **Quick run command** | `PGDATABASE=pycopg_test2 uv run pytest tests/ -x -q -o addopts=""` |
| **Full suite command** | `PGDATABASE=pycopg_test2 uv run pytest` |
| **Randomized determinism** | `PGDATABASE=pycopg_test2 uv run pytest -p randomly --randomly-seed=random` |
| **Lint gate** | `uv run ruff check pycopg tests` (must exit 0) |
| **Dead-code gate** | `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80` |
| **Estimated runtime** | ~120-180 seconds (full DB suite) |

> Note: the default `pycopg_test` DB is broken since 2026-06-24 (TSDB catalog mismatch) — all
> DB/parity tests MUST set `PGDATABASE=pycopg_test2`. conftest honors the env var.

---

## Sampling Rate

- **After every task commit:** `uv run ruff check pycopg tests` + `PGDATABASE=pycopg_test2 uv run pytest tests/ -x -q -o addopts=""`
- **After every plan wave:** `PGDATABASE=pycopg_test2 uv run pytest` (full suite); from Wave 2 on, also `-p randomly --randomly-seed=random`
- **Before `/gsd-verify-work`:** Full suite green + `uv run ruff check pycopg tests` returns 0 + `uv run vulture ...` reports no unexplained dead code
- **Max feedback latency:** ~180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 37-01-01 | 01 | 1 | AUDIT-02 | T-37-SC | Package legitimacy confirmed before install (no typosquat) | manual (blocking-human) | Human confirms vulture + pytest-randomly on pypi.org | ✅ checkpoint | ⬜ pending |
| 37-01-02 | 01 | 1 | DEBT-02, AUDIT-02 | T-37-SC | N/A (lint config + dev-group install) | static | `uv run ruff check pycopg` (exit 0, no N818/deprecation) | ✅ existing tool | ⬜ pending |
| 37-01-03 | 01 | 1 | AUDIT-02 | — | N/A | static | `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80` (parses) | ❌ W0: create `vulture_whitelist.py` | ⬜ pending |
| 37-02-01 | 02 | 1 | DEBT-02 | — | N/A (mechanical lint) | static | `uv run ruff check tests` (exit 0) | ✅ existing tool | ⬜ pending |
| 37-02-02 | 02 | 1 | DEBT-04 | — | SQL-injection coverage preserved (live patch kept) | unit | `PGDATABASE=pycopg_test2 uv run pytest tests/test_sql_injection.py -x -q -o addopts=""` | ✅ existing | ⬜ pending |
| 37-03-01 | 03 | 2 | DEBT-01 | — | No cross-test state leak (UUID table, app_name reset) | regression | `PGDATABASE=pycopg_test2 uv run pytest tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter -v -o addopts=""` | ✅ existing — fix them | ⬜ pending |
| 37-03-02 | 03 | 2 | DEBT-01 | — | Mock-call-order deterministic; randomized suite green | regression | `PGDATABASE=pycopg_test2 uv run pytest -k "watermark_as_bound_param" -p randomly --randomly-seed=random -q` then full `PGDATABASE=pycopg_test2 uv run pytest -p randomly --randomly-seed=random` | ✅ existing — fix them | ⬜ pending |
| 37-04-01 | 04 | 2 | DEBT-05 | T-37-04-01, T-37-04-02 | TableNotFound message leaks only caller identifier; validate_identifiers first | unit | `PGDATABASE=pycopg_test2 uv run pytest tests/test_database_integration.py -k "truncate_table_missing or describe_missing_table" tests/test_async_database.py -k truncate -v -o addopts=""` | ❌ W0: add `test_truncate_table_missing_raises_TableNotFound` (sync + async) | ⬜ pending |
| 37-04-02 | 04 | 2 | DEBT-03 | — | WR-01 guard broadened (still rejects no-time_bucket SQL) | unit/static | `uv run pytest tests/test_timescale.py -k time_bucket -x -o addopts="" && uv run interrogate -f 95 pycopg/database.py && PGDATABASE=pycopg_test2 uv run pytest tests/test_async_database.py::TestAsyncSchemaIntrospection::test_sequences_async -v -o addopts=""` | ✅ existing — fix assertion | ⬜ pending |
| 37-05-01 | 05 | 3 | AUDIT-02 | T-37-05-01 | No public `__all__` symbol deleted; surface intact | static | `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80` + `uv run python -c "import pycopg; from pycopg import TableNotFound, ExtensionNotAvailable, InvalidIdentifier, DatabaseExists"` | ❌ W0: refine allowlist | ⬜ pending |
| 37-05-02 | 05 | 3 | AUDIT-01 | (review instrument) | Any HIGH security finding fixed in-phase | manual (blocking-human) | `/gsd-code-review pycopg/` → `37-REVIEW.md` exists; HIGH fixed; MEDIUM dispositioned | ❌ W0: run review | ⬜ pending |
| 37-05-03 | 05 | 3 | NYQ-01 | — | N/A (planning-doc sign-off) | static | `grep -q 'overall: compliant' .planning/milestones/v0.6.0-MILESTONE-AUDIT.md && grep -A1 compliant_phases ... \| grep -q 24` | ❌ W0: edit milestone audit | ⬜ pending |
| 37-05-04 | 05 | 3 | DEBT-03, NYQ-01 | — | N/A (decisions journal) | static | `test -f .planning/phases/37-dette-audit/37-DECISIONS.md && grep -q NYQ-01 ... && grep -q WR-03 ... && grep -q IN-03 ...` | ❌ W0: create `37-DECISIONS.md` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `vulture_whitelist.py` — create at project root (Plan 01 Task 3; covers AUDIT-02 scan harness)
- [ ] `tests/test_database_integration.py` — add `test_truncate_table_missing_raises_TableNotFound` (sync) (Plan 04 Task 1; covers DEBT-05)
- [ ] `tests/test_async_database.py` — add async twin truncate-raise assertion (Plan 04 Task 1; covers DEBT-05 parity)
- [ ] `.planning/phases/37-dette-audit/37-REVIEW.md` — produced by `/gsd-code-review` (Plan 05 Task 2; covers AUDIT-01)
- [ ] `.planning/phases/37-dette-audit/37-DECISIONS.md` — create (Plan 05 Task 4; covers D-09 / DEBT-03b / NYQ-01 rationale / AUDIT MEDIUM dispositions)

> All other phase requirements (DEBT-01, DEBT-02, DEBT-03a, DEBT-04, NYQ-01 edit) are covered by
> existing test/tool infrastructure — no new framework install beyond pytest-randomly + vulture (Plan 01).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| vulture + pytest-randomly are legitimate, non-typosquat packages | AUDIT-02 | Package-legitimacy gate for [ASSUMED] packages — not auto-approvable | Open https://pypi.org/project/vulture/ and https://pypi.org/project/pytest-randomly/; confirm canonical authors + recent releases before install |
| `/gsd-code-review` findings triaged per the D-06 disposition bar | AUDIT-01 | The review run + MEDIUM fix-or-defer decision requires operator judgment | Run `/gsd-code-review` on `pycopg/`; capture to `37-REVIEW.md`; fix every HIGH; record every MEDIUM disposition + LOW in `37-DECISIONS.md` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify OR a Wave 0 dependency (the two manual checkpoints are package-legitimacy and the human-gated code-review per D-06/D-07; both are documented above)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every wave has automated lint/test gates between any manual checkpoints)
- [x] Wave 0 covers all MISSING references (vulture_whitelist.py, truncate-raise tests, 37-REVIEW.md, 37-DECISIONS.md)
- [x] No watch-mode flags (all commands are single-run; `-o addopts=""` only disables coverage/verbose noise for targeted runs)
- [x] Feedback latency < 180s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-26
