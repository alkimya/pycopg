---
phase: 41
slug: api-homogenization
status: secured
threats_total: 14
threats_closed: 14
threats_open: 0
register_authored_at_plan_time: true
asvs_level: 1
created: 2026-06-30
---

# Security Audit — Phase 41: API Homogenization

## Verdict: SECURED

All 14 threats verified. Zero open blockers. Every declared `mitigate` mitigation is present
in the implemented code at the cited location. Every `accept` rationale is grounded in
documented phase decisions. The phase may ship.

---

## Per-Threat Verification Table

| Threat ID | Category | Disposition | Status | Evidence (file:line / command) |
|-----------|----------|-------------|--------|-------------------------------|
| T-41-01 | Tampering | mitigate | CLOSED | `grep 'ignore::DeprecationWarning:pycopg' pyproject.toml` → 0 matches (exit 1). filterwarnings list at `pyproject.toml:96-104` has only third-party suppressions for `psycopg`, `geopandas`, `pandas`. No pycopg-scoped suppression present. |
| T-41-02 | Repudiation | accept | CLOSED | Accepted at plan time (41-01-PLAN.md threat register): discovery sweep is re-runnable; a new third-party emitter would surface as a red suite and be added then. No PII, config-only change. |
| T-41-03 | Tampering | mitigate | CLOSED | `grep -c 'validate_identifiers' pycopg/spatial.py` = 51. The Plan 02 summary records the count as 27 after the 2 exception-raise edits in spatial.py; it grew to 51 after Phases 42/43 added new builders. The Phase 41 kw-only move in Plan 04 explicitly recorded "count = 27 (confirmed unchanged)" before Phase 42 additions. `validate_identifiers` is the first call in every `build_*_sql` body as confirmed by inspection of `build_contains_sql` at `pycopg/spatial.py:262`. |
| T-41-04 | Elevation | mitigate | CLOSED | (a) `pycopg/exceptions.py:114` — `__getattr__` returns `globals()[new]` (the canonical `*Error` class object); `python3 -c "import warnings; import pycopg.exceptions as e; warnings.simplefilter('ignore'); assert e.InvalidIdentifier is e.InvalidIdentifierError"` exits 0. (b) `-W error::DeprecationWarning` gate live at `pyproject.toml:97`; full-suite-green confirmed in Plan 04 summary (1483 passed). (c) No internal pycopg/ code routes through deprecated alias: `grep -rn 'raise.*\b(ExtensionNotAvailable|TableNotFound|InvalidIdentifier|DatabaseExists)\b' pycopg/ | grep -v Error` → 0 lines. |
| T-41-05 | DoS | mitigate | CLOSED | `python3 -c "import pycopg; print('import-ok')"` → prints `import-ok` (exit 0). `pycopg/__init__.py:14-27` imports only `*Error` canonical names; old names absent from the direct import block (Pitfall 2 cleared). |
| T-41-06 | Tampering | mitigate | CLOSED | `_append_tail` uses `filter` parameter (not `where`) throughout its body at `pycopg/spatial.py:148-201`. All 11 `build_*_sql` builders forward `filter=filter` to `_append_tail`. `validate_identifiers` confirmed first call in every builder (e.g., `pycopg/spatial.py:262`). `grep -n 'where=where' pycopg/spatial.py` → 0 matches. |
| T-41-07 | Elevation | mitigate | CLOSED | `grep -c 'where=where' pycopg/spatial.py` = 0. Internal accessor bodies forward `filter=filter` (confirmed at lines 1359, 1425, 1491, 1894, 1971, 2321, 2403, 2495, 2596, 2691 etc. in `pycopg/spatial.py`). Full suite green under `-W error::DeprecationWarning` gate (no internal caller triggers the shim). |
| T-41-08 | Info disclosure | mitigate | CLOSED | `pycopg/spatial.py` — every accessor `where=` shim block uses `stacklevel=2` (confirmed at lines 2307, 2392, 2481, 2580, 2677, 2766, 2847, 2926, 3003, 3331). `tests/test_deprecations.py:95-97` — `test_where_deprecation_points_to_caller` asserts `w.filename.endswith("test_deprecations.py")`. This test passes (Plan 03 summary: 28 passed in TestWhereDeprecation). |
| T-41-09 | Tampering | mitigate | CLOSED | `grep -c 'validate_identifiers' pycopg/spatial.py` = 51 (plan 04 confirmed 27 before Phase 42 additions; the `within()` kw-only `*` move in Plan 04 Task 3 did not disturb any injection guard). Spatial injection tests passed under full suite. Plan 04 summary explicitly states "security invariant: grep -c validate_identifiers pycopg/spatial.py = 27 (confirmed unchanged)." |
| T-41-10 | Repudiation | mitigate | CLOSED | `41-04-SUMMARY.md:325` — "Task 2: USER REVIEW GATE (D-05) — Status: APPROVED — 2026-06-28". The findings table and per-row D1-D5 dispositions are recorded with explicit user approval before Task 3 applied any fix. Plan 04 is `autonomous: false` with `checkpoint:human-verify` Task 2. Only approved-table dispositions were applied (documented D2/D5 carve-out). |
| T-41-11 | Info disclosure | mitigate | CLOSED | Audit-surfaced rename: `time_bucket`/`time_bucket_gapfill` `where=`→`filter=` shim (D3 approved). `pycopg/timescale.py:1267` — `stacklevel=2`. `tests/test_deprecations.py:222-225` — `TestTimeBucketWhereDeprecation.test_time_bucket_where_warns` asserts `w.filename.endswith("test_deprecations.py")`. Async mirror at `pycopg/timescale.py:2291` also uses `stacklevel=2`. |
| T-41-12 | Tampering | mitigate | CLOSED | `docs/stability.md:260` — PostGIS row: "3.0 (hard floor)" and "3.2+ (`ST_MakeValid method=structure` requires PostGIS 3.2, per D-02)". Version floors grounded in `pyproject.toml` actuals: `requires-python = ">=3.11"`, `psycopg>=3.1.0`, `psycopg_pool>=3.2.0`, `pandas>=2.0.0`, `geopandas>=0.14.0` (Plan 05 summary, Task 1 acceptance criteria confirmed). |
| T-41-13 | Repudiation | mitigate | CLOSED | `MIGRATION.md:1` — section `# Migration Guide: v0.10.x → 1.0.0` present. `grep -c 'InvalidIdentifierError\|ExtensionNotAvailableError\|TableNotFoundError\|DatabaseExistsError' MIGRATION.md` = 9 (≥ 4 required). `grep -q 'filter=' MIGRATION.md` matches. `grep -qi 'keyword-only' MIGRATION.md` matches. All 4 Phase 41 renames documented with before/after. |
| T-41-SC | Tampering | accept | CLOSED | Accepted across all 5 plans (41-01-PLAN.md, 41-02-PLAN.md, 41-03-PLAN.md, 41-04-PLAN.md, 41-05-PLAN.md threat registers): no new packages installed in any plan. Pure Python refactor, docs-only final plan. No `uv add` or `pip install` in any plan execution. |

---

## Accepted Risks Log

| Risk ID | Threat | Rationale | Authority |
|---------|--------|-----------|-----------|
| T-41-02 | Repudiation — discovery sweep completeness | The filterwarnings discovery sweep was run once on 2026-06-28 and produced zero third-party DeprecationWarning hits at the current dep versions. Three defensive suppression entries were added for `psycopg`, `geopandas`, and `pandas` as known upstream emitters. If a new dep version introduces a new warning source, the suite will go red and the suppressions will be updated then. The risk is operationally low: no PII, no persistent state, config-only change. | 41-01-PLAN.md threat register |
| T-41-SC | Tampering — supply chain | No new packages were installed across all 5 plans. The existing locked `uv.lock` dependency set was used. No npm, pip install, or cargo commands were executed. | 41-01 through 41-05 PLAN.md threat registers |

---

## Unregistered Flags

None. The `## Threat Flags` sections in the five SUMMARY files report no net-new attack surface:
all changes are Python parameter renames, deprecation shim additions, kw-only boundary moves,
and docs-only additions. No new network endpoints, auth paths, file access patterns, or schema
changes were introduced in any plan.

---

## Notes on validate_identifiers Count

The Phase 41 threat register (T-41-03, T-41-06, T-41-09) tracks `validate_identifiers` guard
preservation using a count assertion. The count was 27 at the end of Plan 02 and remained 27
through Plans 03 and 04 (explicitly confirmed in each SUMMARY). The current count of 51 reflects
additions from Phases 42 and 43 (new spatial aggregate builders), which are out of scope for this
Phase 41 audit. The Phase 41 kw-only move (`within()` schema= → kw-only) did not touch any
injection guard, as confirmed by the Plan 04 "security invariant" note.

---

## Scope

This audit covers Phase 41 (api-homogenization) only. Implementation files audited:

- `pycopg/exceptions.py` — 4 `*Error` renames + PEP 562 `__getattr__`
- `pycopg/__init__.py` — updated imports + package `__getattr__`
- `pycopg/spatial.py` — `filter=` rename on builders + `_append_tail`; `filter=/where=` shim on 22 accessor methods; kw-only `*` moves
- `pycopg/timescale.py` — `filter=/where=` shim on `time_bucket`/`time_bucket_gapfill`; kw-only `*` moves
- `pyproject.toml` — `filterwarnings` gate; N818 suppression removed
- `tests/test_deprecations.py` — stacklevel assertions; alias identity tests; kw-only enforcement tests
- `tests/test_parity.py` — `test_accessor_parameter_kind_parity` KIND-parity guard
- `docs/stability.md` — SemVer contract + support matrix
- `MIGRATION.md` — v0.10.x → 1.0.0 section

Implementation files are read-only for this audit. No implementation changes were made.
