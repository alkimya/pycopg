---
phase: 46
slug: mypy-strict-py-typed-gate
status: secured
threats_total: 15
threats_closed: 15
threats_open: 0
register_authored_at_plan_time: true
asvs_level: 1
created: 2026-07-02
---

# SECURITY.md — Phase 46 Audit Record

**Phase:** 46 — mypy-strict-py-typed-gate
**Audit date:** 2026-07-02
**ASVS focus:** Supply-chain integrity (dev stubs), gate/config integrity, annotation-only behavior preservation, KIND-parity regression integrity
**Auditor disposition:** Adversarial — every mitigation assumed absent until grep/read evidence found in the shipped tree
**Register origin:** authored at plan time (7 PLAN files each carry a `<threat_model>` block) → VERIFY declared mitigations exist; not a fresh threat scan

---

## Verdict: SECURED

**Threats Closed:** 15 / 15
**Threats Open:** 0

Phase 46 is a typing/tooling hardening pass: `mypy strict = true` enabled, ~108 `@overload into=` stubs added across accessors (KIND-parity mirrored), 3 dev-only typing stubs, `py.typed` made truthful, CI mypy flipped advisory→blocking. Edits are annotation-only (under `from __future__ import annotations`, non-evaluated strings) plus config/CI. Two latent runtime bugs (`AsyncPooledDatabase.resize()` un-awaited coroutine; etl `steps` `[no-redef]`) were root-caused and FIXED, not silenced. Every declared mitigation was independently confirmed against the live tree.

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-46-01 | Tampering (dev stub supply chain) | mitigate | CLOSED | 3 stubs are dev-only: `pyproject.toml:73-75` (`pandas-stubs>=2.0.0`, `types-geopandas>=0.14.0`, `types-shapely>=2.0.0`) under `[dependency-groups] dev`; NONE in `[project.dependencies]` (L37-43) or `[project.optional-dependencies]` (L45-60). Typeshed/official provenance documented `.planning/research/STACK.md:50-52` + Sources L483-485 (each with PyPI/typeshed URL). Legitimacy install covered by the T-46-SC checkpoint below. |
| T-46-02 | DoS (interrogate/coverage config edit) | accept | CLOSED | Accepted risk — see Accepted Risks Log (AR-46-01). Config-only change; both fail-under bars held at 95 (`pyproject.toml:97` `--cov-fail-under=95`, L133 interrogate `fail-under = 95`); pytest+interrogate smoke in acceptance would catch a broken toml. 46-VERIFICATION.md records live suite 1736 passed @ 96.42% and interrogate `PASSED 100%`. |
| T-46-03 | DoS (`__all__` audit breaks internal import) | mitigate | CLOSED | `__all__` declared across foundation modules: `base.py`, `exceptions.py`, `config.py`, `utils.py`, `logging.py`, `migrations.py`, `admin.py`, `backup.py`, `maint.py` (grep-confirmed). `queries.py` correctly has none (no cross-module re-export need per plan). Import-smoke + `test_parity` are the guard; 46-VERIFICATION.md §Behavioral confirms `import pycopg; from pycopg import Database, AsyncDatabase` → `OK 0.10.1` and parity tests green. |
| T-46-04 | Tampering (annotation edit changing runtime behavior) | mitigate | CLOSED | Annotations are non-evaluated strings under `from __future__ import annotations`. Foundation modules (admin/backup/maint/config/migrations) type-checked to zero and targeted pytest green (46-02-SUMMARY, 46-VERIFICATION). 46-REVIEW.md §5 diffed `validate_identifier` call counts pre-phase vs HEAD across every SQL-building module → identical (no guard dropped). |
| T-46-05 | DoS (spatial @overload sync/async KIND-parity drift) | mitigate | CLOSED | `pycopg/spatial.py` — 96 `@overload` split EXACTLY 48/48 across `SpatialAccessor` (class L2158) and `AsyncSpatialAccessor` (class L4948); `Literal["rows"]`×32 and `Literal["gdf"]`×32 balanced. Guard `tests/test_parity.py:432 test_accessor_parameter_kind_parity` (+ `test_accessor_parity` L36) present and green (15/15 in the `kind_parity or accessor_parity` filter, 46-VERIFICATION). |
| T-46-06 | Tampering (spatial annotation changing SQL/return) | mitigate | CLOSED | `_check_into` runtime validator unchanged at `pycopg/spatial.py:2104` (still called by the polymorphic methods; overloads are the static complement, not a replacement). `from __future__ import annotations` makes stubs non-evaluated. `-k spatial` + parity suite green (46-03-SUMMARY, 46-REVIEW §4 spot-checked `contains()` sync/async against runtime impl). |
| T-46-07 | DoS (timescale @overload sync/async drift) | mitigate | CLOSED | `pycopg/timescale.py` — 12 `@overload` split EXACTLY 6/6 across `TimescaleAccessor` (L329) and `AsyncTimescaleAccessor` (L1475); `Literal["df"]`×4 + `Literal["rows"]`×4 (time_bucket + time_bucket_gapfill triplets × 2 classes). Guarded by `test_accessor_parameter_kind_parity`; green per 46-VERIFICATION. |
| T-46-08 | Tampering (timescale/schema annotation changing behavior) | mitigate | CLOSED | `_check_into` unchanged at `pycopg/timescale.py:161`, still invoked at L1317/L1457. Deferred string annotations; `-k timescale`/`-k schema` pytest green (46-04-SUMMARY). schema.py annotated to zero via D-03, no `into=` polymorphism → no overloads (correct). |
| T-46-09 | Tampering (silencing etl redef/coroutine vs fixing) | mitigate | CLOSED | NO masking: `grep -c 'type: ignore[no-redef]' pycopg/etl.py` = 0 and `type: ignore[unused-coroutine]` = 0. `steps: list[Any]` annotated exactly once per method at `etl.py:1254` (dry-run/normal path) and `:1950` (async to_thread path) — distinct method scopes ~700 lines apart, mutually-exclusive branches (46-REVIEW §2 traced the `dry_run` early-`return`). Root cause recorded in 46-05-SUMMARY. |
| T-46-10 | DoS (pool annotation changing health/resize behavior) | mitigate | CLOSED | Real bug FIXED not silenced: `pycopg/pool.py:578` `async def resize(...)` + `:580 await self._pool.resize(...)` (previously un-awaited coroutine); sync `PooledDatabase.resize()` at `:289` correctly stays `def` (`:299` no await, sync pool API). Regression test moved to async class + upgraded to `AsyncMock`/`assert_awaited_once_with` (46-REVIEW §1, `tests/test_pool.py` 38/38). never-raises `health()` contract asserted by P45 tests. |
| T-46-11 | DoS (sync/async DB-class annotation KIND-parity drift) | mitigate | CLOSED | `Params` alias (`base.py:18`) used 11× in each of `database.py`/`async_database.py` (symmetric). Guarded by `test_accessor_parity` + `test_accessor_parameter_kind_parity` (tests/test_parity.py:36/432), both green (46-06-SUMMARY, 46-VERIFICATION). |
| T-46-12 | Tampering (execute/fetch positional-ness / session change) | mitigate | CLOSED | Annotation-only; D2/D5 positional carve-out preserved (`Params` added as a type only, no kw-only change). `-k execute/fetch/session/transaction` pytest green (46-06-SUMMARY). 8 total `# type: ignore`, ALL code-specific (zero bare ignores, grep-confirmed), each justified at an unstubbed edge (46-REVIEW §7). |
| T-46-SC | Tampering (pandas-stubs/types-geopandas/types-shapely installs) | mitigate | CLOSED | Blocking-human legitimacy checkpoint executed (`46-07-PLAN.md` Task 1, `gate="blocking-human"`); user responded **"approved"** confirming typeshed/official provenance + dev-only placement + lockfile-pinned (`46-07-SUMMARY.md:59`). `uv lock --check` clean (48 packages, no drift). Dev-only placement re-confirmed at `pyproject.toml:73-75`. |
| T-46-13 | DoS (CI flipped blocking before local strict green) | mitigate | CLOSED | `.github/workflows/tests.yml:75-76` — `mypy type check` runs `uv run mypy pycopg/`; `grep -c continue-on-error` = 0 (whole file), `grep -c 'mypy.*--strict'` = 0 (config-driven strict, no CLI flag). Task 3 depended on Task 2 zero-error; 46-VERIFICATION records live `uv run mypy pycopg/` → `Success: no issues found in 18 source files`, exit 0 → gate is green, not red. |
| T-46-14 | DoS (@overload stubs dropping coverage <95%) | mitigate | CLOSED | Overload exclusion wired: `pyproject.toml:120-121` `exclude_lines` includes `@overload` and `@typing.overload`; interrogate `ignore-overloaded-functions = true` (L132). `--cov-fail-under=95` intact (L97). Live full suite (`PGDATABASE=pycopg_test3 uv run pytest`) → 1736 passed, **96.42%** coverage, gate passes (46-VERIFICATION §Behavioral). |

---

## Critical-Path Detail: two latent bugs fixed (not silenced)

The phase's highest-integrity risk was that a strict-mode error would be **masked** with a blanket `# type: ignore` instead of fixed — turning a type-checker into a bug-hider. Both flagged codes were verified as genuine fixes:

1. **`pool.py` `AsyncPooledDatabase.resize()` `[unused-coroutine]`** — `psycopg_pool.AsyncConnectionPool.resize` is a coroutine function; the shipped code called it without `await`, so async pools never actually resized. Fix at `pycopg/pool.py:578-580` makes it `async def` + `await`, matching sibling `check()`/`close()`. Sync `PooledDatabase.resize()` (`:289/:299`) correctly stayed synchronous. A real regression test (`AsyncMock` + `assert_awaited_once_with`) was added — not a mere type-satisfier.

2. **`etl.py` `steps` `[no-redef]`** — the two `steps: list[Any]` bindings (`:1254`, `:1950`) live in separate methods on mutually-exclusive runtime branches (the `dry_run` path `return`s before reaching the second). Annotated exactly once per method; no blanket ignore. `grep` proves 0 `type: ignore[no-redef]` in the file.

Both fixes are the intended posture of T-46-09/T-46-10: strict as a bug-finder, with the mitigation being the fix itself plus the behavioral test, verified present.

---

## Accepted Risks Log

| Risk ID | Threat ID | Rationale |
|---------|-----------|-----------|
| AR-46-01 | T-46-02 | The interrogate/coverage `pyproject.toml` edits (add `ignore-overloaded-functions = true`, add `@overload`/`@typing.overload` to `exclude_lines`) are config-only and cannot lower a gate: both `fail-under` bars remain 95 (`--cov-fail-under=95` at L97; interrogate `fail-under = 95` at L133). A malformed toml would fail-fast at pytest/interrogate collection (smoke-tested in acceptance and confirmed live at 96.42% coverage / 100% docstrings). Residual risk is limited to the config-authoring step itself and is accepted as low-consequence, self-detecting via the existing gates. |

---

## Unregistered Flags

None. No `## Threat Flags` section appears in any of the seven 46-0N-SUMMARY.md files — the executor detected no new attack surface beyond the plan-time register during implementation. The whole-file 46-REVIEW.md (19 files, 0 critical / 0 warning / 1 non-regression info) and 46-VERIFICATION.md (`Anti-Patterns Found: none`) corroborate that no un-mapped surface emerged. The single review Info item (IN-01: package-level deprecated-alias `__getattr__` double-fires a `DeprecationWarning` under `from pycopg import X`) is explicitly pre-existing (reproduced against the pre-phase `75c1895` baseline), not introduced by Phase 46, and is a documentation/test-coverage follow-up, not a security gap.

---

## Scope

This audit covers Phase 46 implementation/evidence files:
- `pyproject.toml` — `[tool.mypy]` strict block (L139-143), 2 external overrides only (geoalchemy2/tenacity, L145-150), coverage `exclude_lines` (L114-122), interrogate config (L124-137), dev stubs (L73-75)
- `.github/workflows/tests.yml` — blocking mypy step (L75-76)
- `pycopg/py.typed` — present, 0-byte PEP 561 marker
- `pycopg/spatial.py` — 96 @overload (48/48), `_check_into` (L2104)
- `pycopg/timescale.py` — 12 @overload (6/6), `_check_into` (L161)
- `pycopg/etl.py` — `steps: list[Any]` (L1254/L1950), 0 masking ignores
- `pycopg/pool.py` — `resize` sync (L289) / async-await fix (L578-580)
- `pycopg/database.py`, `pycopg/async_database.py` — `Params` alias ×11 each
- `pycopg/base.py`, `config.py`, `utils.py`, `exceptions.py`, `logging.py`, `queries.py`, `migrations.py`, `admin.py`, `backup.py`, `maint.py`, `schema.py` — `__all__` audit + annotations
- `tests/test_parity.py` — `test_accessor_parity` (L36), `test_accessor_parameter_kind_parity` (L432)

Implementation files were NOT modified during this audit (read-only). This audit created only this SECURITY.md.
