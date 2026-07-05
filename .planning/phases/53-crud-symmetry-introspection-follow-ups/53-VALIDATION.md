---
phase: 53
slug: crud-symmetry-introspection-follow-ups
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-05
---

# Phase 53 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `53-RESEARCH.md` § Validation Architecture (HIGH confidence, all mirror targets read from live code).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via `uv sync --all-extras --dev`), `pytest-cov` for coverage |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `--cov=pycopg --cov-fail-under=95`) |
| **Quick run command** | `uv run pytest tests/test_database.py tests/test_async_database.py tests/test_sql_injection.py -x -q -o addopts=""` |
| **Full suite command** | `PGDATABASE=pycopg_test3 uv run pytest` |
| **Estimated runtime** | ~60–120 seconds (full suite) |

> **DB note (project convention):** any test touching a real connection MUST run under `PGDATABASE=pycopg_test3` — the default `pycopg_test`/`pycopg_test2` DBs are broken by TimescaleDB `.so` drift.

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/test_database.py tests/test_async_database.py tests/test_sql_injection.py -x -q -o addopts=""` (fast, mocked-DB subset)
- **After every plan wave:** `PGDATABASE=pycopg_test3 uv run pytest tests/test_database_integration.py tests/test_parity.py -x -q -o addopts=""` (live-DB + parity gates)
- **Before `/gsd-verify-work`:** `PGDATABASE=pycopg_test3 uv run pytest` full suite green (cov ≥95%, 96.78% baseline)
- **Max feedback latency:** ~30 seconds (quick subset)

---

## Per-Task Verification Map

> Requirement-level map below; per-task rows (`53-0N-0M`) are filled once plans exist. Every task in a PLAN.md must map to one of these requirement rows.

| Requirement | Behavior to verify | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|--------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| CRUD-F04 | `select_where`/`find` → `list[dict]` filtered by dict `where` + `where_sql`/`where_params`; honor `columns`/`order_by`/`limit`/`offset`; empty predicate = read-all | T-53 injection | identifiers `validate_identifiers`-first, values bound `%s` | unit + injection + integration | `PGDATABASE=pycopg_test3 pytest tests/test_database.py tests/test_sql_injection.py tests/test_database_integration.py -k select_where -x` | ❌ W0 | ⬜ pending |
| CRUD-F05 | `get`/`find_one` → `dict \| None`, forced `LIMIT 1` on >1 match, no raise; same predicate surface | T-53 injection | same guard as F04 | unit + integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k "test_get or test_find_one" -x` | ❌ W0 | ⬜ pending |
| CRUD-F06 | `insert` single row → `RETURNING *` dict; `on_conflict="DO NOTHING"` + pre-existing conflict → `None` | T-53 injection | row keys/table/schema validated, values bound `%s`; `on_conflict` verbatim (documented raw-SQL escape hatch) | integration (needs real UNIQUE constraint) | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k test_insert -x` | ❌ W0 | ⬜ pending |
| INTRO-F03 | `column_exists` → `bool` (true for existing, false for missing) | T-53 injection | 3 values bound `%s` vs `information_schema.columns`, no identifier interpolation | unit + integration | `PGDATABASE=pycopg_test3 pytest tests/test_database.py tests/test_database_integration.py -k column_exists -x` | ❌ W0 | ⬜ pending |
| INTRO-F04 | `table_size` raises `TableNotFoundError` on missing table; returns `int` bytes on success | T-53 injection | existence guard before size query; name bound (regclass), never f-string | unit (guard) + integration (bytes>0) | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k table_size -x` | ❌ W0 | ⬜ pending |
| (all) | sync/async parity — every new method on BOTH classes, identical kw-only signature | — | N/A | automated gate | `pytest tests/test_parity.py -x` | ✅ auto-extends | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_database.py` — mocked-DB unit tests for `select_where`/`find`/`get`/`find_one`/`insert`/`column_exists` (param-shape + empty-predicate-read-all)
- [ ] `tests/test_async_database.py` — async mirrors of the above
- [ ] `tests/test_database_integration.py` (+ async section) — live-DB behavior: predicate filtering, `order_by`/`limit`/`offset` correctness, `RETURNING *` shape, `on_conflict="DO NOTHING"`→`None`, `column_exists` true/false, `table_size` guard + real byte count
- [ ] `tests/test_sql_injection.py` — parametrized injection tests for all new identifier-accepting call sites (extend `TestSyncIdentifierInjection`/`TestAsyncIdentifierInjection`/`TestWhereSqlValueInjection`), sync + async
- [ ] `pycopg/queries.py` — add `COLUMN_EXISTS` constant (reuse existing `TABLE_SIZE` for `table_size`)

*Framework itself is fully present — pytest + coverage + parity harness require no new install.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
