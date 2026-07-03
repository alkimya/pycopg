---
phase: 50
slug: crud-introspection-follow-ups
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-03
plans_mapped: 2026-07-03
---

# Phase 50 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `50-RESEARCH.md` § Validation Architecture. Task IDs are assigned at planning; rows below map by requirement + builder path.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + pytest-cov |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`; `addopts` carries `--cov-fail-under=95`) |
| **Quick run command** | `PGDATABASE=pycopg_test3 uv run pytest tests/test_database.py tests/test_parity.py -x -q -o addopts=""` |
| **Full suite command** | `PGDATABASE=pycopg_test3 uv run pytest` |
| **Estimated runtime** | ~90–180 seconds (full suite); quick mock+parity ~5–15s |

> **Env gotcha (project memory):** default `pycopg_test`/`pycopg_test2` are broken by TimescaleDB `.so` drift → `UndefinedFile`. **ALWAYS run DB/parity/coverage tests with `PGDATABASE=pycopg_test3`.** Phase 50 is plain PostgreSQL — no PostGIS/TSL gating. Targeted runs use `-o addopts=""` to drop the coverage gate (flaky fixture isolation, project memory).

---

## Sampling Rate

- **After every task commit:** `PGDATABASE=pycopg_test3 uv run pytest tests/test_database.py tests/test_parity.py -x -q -o addopts=""` (fast mock + parity)
- **After every plan wave:** `PGDATABASE=pycopg_test3 uv run pytest tests/ -q -o addopts=""`
- **Before `/gsd-verify-work`:** `PGDATABASE=pycopg_test3 uv run pytest` (full suite + coverage ≥95%) **AND** `uv run mypy pycopg` (0 errors) **AND** `interrogate` 100% **AND** Sphinx `-W` clean
- **Max feedback latency:** ~15 seconds (quick), ~180 seconds (full gate)

---

## Per-Task Verification Map

Plan/Wave columns filled from the committed plan set (50-01..50-04). Task ID is plan-scoped (`50-{plan}-*` — tasks are named "Task N" within each plan). Each row is a required verification signal keyed to its requirement + builder path.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 50-01-* | 50-01 | 1 | CRUD-F01 | T-50-01 | `where_sql`+`where_params` on 5 helpers, mock SQL shape (sync+async) | unit | `PGDATABASE=pycopg_test3 pytest tests/test_database.py -k where_sql -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-01-* | 50-01 | 1 | CRUD-F01 | T-50-02 | Guards: dict/where_sql mutual-exclusion, empty-fragment reject, param-desync, destructive-still-raises (before DB round-trip) | unit | `PGDATABASE=pycopg_test3 pytest tests/test_database.py -k where_sql_guard -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-01-* | 50-01 | 1 | CRUD-F01 | T-50-03 | Injection: `where_params` bound `%s`, fragment passthrough verbatim, no interpolation | injection | `PGDATABASE=pycopg_test3 pytest tests/test_sql_injection.py -k where_sql -o addopts=""` | ❌ W0 (extend) | ⬜ pending |
| 50-01-* | 50-01 | 1 | CRUD-F01 | — | Live: raw predicate returns correct rows (sync+async) | integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k where_sql -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-02-* | 50-02 | 2 | CRUD-F02 | T-50-04 | Keyset SQL shape `(c1,c2) > (%s,%s)`, `<`-flip on `descending`, `LIMIT+1`, mock | unit | `PGDATABASE=pycopg_test3 pytest tests/test_database.py -k paginate_keyset -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-02-* | 50-02 | 2 | CRUD-F02 | T-50-05 | Injection: keyset binds `after` values, `validate_identifiers` on `order_by` cols | injection | `PGDATABASE=pycopg_test3 pytest tests/test_sql_injection.py -k keyset -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-02-* | 50-02 | 2 | CRUD-F02 | — | Live: stable deep pagination, forward-only monotonic progress, `after=None` first page | integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k paginate_keyset -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-02-* | 50-02 | 2 | CRUD-F03 | — | `Page` fields; `has_next` `limit+1` trim; `with_total` COUNT vs `None` | unit + integration | `PGDATABASE=pycopg_test3 pytest tests/test_database.py -k paginate_page -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-04-* | 50-04 | 4 | INTRO-F01 | — | `describe(into=...)` returns dict/dataclass/DataFrame; default byte-identical; `@overload` resolves | unit | `PGDATABASE=pycopg_test3 pytest tests/test_database.py -k describe_into -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-04-* | 50-04 | 4 | INTRO-F01 | — | Live: dataclass/DataFrame sub-values equal the dict (no shape drift) | integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k describe_into -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-03-* | 50-03 | 3 | INTRO-F02 | T-50-06 | `materialized_views` + `materialized_view_columns` mock SQL-const shape | unit | `PGDATABASE=pycopg_test3 pytest tests/test_database.py -k materialized_view -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-03-* | 50-03 | 3 | INTRO-F02 | T-50-07 | Injection: name/schema handling in matview-columns builder | injection | `PGDATABASE=pycopg_test3 pytest tests/test_sql_injection.py -k materialized_view -o addopts=""` | ❌ W0 | ⬜ pending |
| 50-03-* | 50-03 | 3 | INTRO-F02 | — | Live: create matview in pycopg_test3, columns match `table_info` shape byte-for-byte | integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k materialized_view -o addopts=""` | ❌ W0 | ⬜ pending |
| ALL-* | 50-01..04 | 1–4 | ALL | — | Parity: new methods/params registered, KIND-parity holds | unit | `PGDATABASE=pycopg_test3 pytest tests/test_parity.py -o addopts=""` | ✅ (extend frozensets) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_parity.py` — add `test_crud_v110_surface` frozenset `{paginate_page, paginate_keyset}` and `test_schema_v110_surface` frozenset `{materialized_views, materialized_view_columns}` (mirror `test_schema_v090_surface`). No change to `ACCESSOR_PAIRS`; KIND-parity auto-covers new params.
- [ ] `tests/test_database.py` — new mock-SQL unit tests: `where_sql` (5 helpers), `paginate_page`, `paginate_keyset`, `describe_into`, `materialized_view*` (mirror `test_describe_composes_four_helpers`, `test_table_info`).
- [ ] `tests/test_database_integration.py` — new live tests (mirror `test_paginate_*`, `test_describe_*`); add a matview fixture (`CREATE MATERIALIZED VIEW` / `DROP` on teardown).
- [ ] `tests/test_async_database.py` — async twins (mirror `test_paginate_async`, `test_describe_async`).
- [ ] `tests/test_sql_injection.py` — extend with `where_sql` passthrough + param-binding, keyset tuple compare, matview name/schema tests (mirror existing `_build_*` import + `EVIL_IDENTIFIERS` payloads).
- [ ] No framework install needed — pytest/cov/asyncio already configured.

---

## Manual-Only Verifications

All phase behaviors have automated verification. Every new method/param/return type is exercised by mock SQL-shape unit tests (both accessors), live-DB integration on `pycopg_test3`, and — for each new builder path — a dedicated injection test.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (confirmed by gsd-plan-checker — every task across 50-01..04 carries an `<automated>` command)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test stubs enumerated above; written during execution)
- [x] No watch-mode flags
- [x] Feedback latency < 180s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-03 (plan set 50-01..04 verified PASSED by gsd-plan-checker; `wave_0_complete` flips true once the Wave 0 test stubs land during execution)
