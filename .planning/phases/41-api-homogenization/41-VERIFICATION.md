---
phase: 41-api-homogenization
verified: 2026-06-28T17:00:00Z
status: passed
score: 10/10
overrides_applied: 1
overrides:
  - must_have: "Old exception names raise DeprecationWarning when imported or caught"
    reason: "D-08 decision recorded in 41-CONTEXT.md: catch-time warning is intentionally NOT implemented (metaclass __instancecheck__/__subclasscheck__ hack would be fragile). Old names warn on import/attribute-access only. Except-time compatibility preserved via same-class-object guarantee (except OldName still catches *Error). Documented in MIGRATION.md and docs/stability.md."
    accepted_by: "loc"
    accepted_at: "2026-06-28T00:00:00Z"
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 41: API Homogenization — Verification Report

**Phase Goal:** The public surface is consistent and homogeneous — `where=` means dict-equality everywhere, `filter=` means raw SQL fragment in spatial, exception names follow N818, and the SemVer stability contract is published.
**Verified:** 2026-06-28T17:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Calling any of the 11 spatial methods (sync or async) with `where=` emits DeprecationWarning pointing at the caller's file, result identical to `filter=` | VERIFIED | `tests/test_deprecations.py::TestWhereDeprecation` — 52 parametrized tests all pass; `w.filename.endswith("test_deprecations.py")` assertion confirmed; stacklevel=2 verified live |
| 2 | Passing both `filter=` and `where=` raises TypeError | VERIFIED | `test_filter_and_where_both_supplied_raises` + 20 parametrized variants (sync+async, all 11 methods, including `within`) all PASS |
| 3 | 11 `build_*_sql` builders and `_append_tail` accept `filter=` only (no `where=`) | VERIFIED | Live check: `build_contains_sql('t', point=(0,0), where='x')` raises `TypeError: got an unexpected keyword argument 'where'`; all 11 builders inspected — `filter` in params, `where` absent |
| 4 | Old exception names emit DeprecationWarning on import/access and resolve to the same class object as `*Error` names | PASSED (override) | Override: D-08 decision — warning fires on import/attribute-access, NOT at catch time (intentional, not a gap; documented in 41-CONTEXT.md D-08, MIGRATION.md, docs/stability.md). Live: `e.InvalidIdentifier is e.InvalidIdentifierError` = True; DeprecationWarning emitted with correct message. `except InvalidIdentifier:` still catches `InvalidIdentifierError` (same object). |
| 5 | No internal pycopg/ code routes through deprecated paths (suite green under -W error::DeprecationWarning) | VERIFIED | Full suite: 1491 passed, 2 skipped, 0 failures; `filterwarnings = ["error::DeprecationWarning", ...]` live in pyproject.toml; ruff check clean; grep of old raise sites returns zero lines |
| 6 | kw-only `*` enforcement across all 7 accessors + flat core; sync/async parity holds (CR-01 fix held) | VERIFIED | `test_accessor_parameter_kind_parity` (7 pairs) + `test_database_core_parameter_kind_parity` — 8/8 PASS; live inspect.signature checks on schema/maint/etl/backup/spatial show zero drift; CR-01 fix commit 92018dd verified in git log |
| 7 | Calling an optional param positionally raises TypeError (clean 1.0 break, no positional shim) | VERIFIED | `test_contains_geom_is_kw_only` + `test_flat_core_kw_only_schema` both PASS; live: `SpatialAccessor.contains('tbl', 'geom_column')` raises `TypeError: takes 2 positional arguments but 3 were given` |
| 8 | `docs/stability.md` exists, in Sphinx toctree, linked from README, builds under Sphinx -W | VERIFIED | File exists; all 5 required sections present (grep returns 5); `uv run sphinx-build -W --keep-going` exits 0 ("La compilation a réussi."); `grep -in stability README.md` returns link; `grep stability docs/index.md` matches |
| 9 | `validate_identifiers` guards preserved through all spatial renames (security) | VERIFIED | `grep -c validate_identifiers pycopg/spatial.py` = 27 (unchanged from pre-phase baseline documented in Plan 02 and Plan 03 threat scans) |
| 10 | MIGRATION.md has complete v0.10.x → 1.0.0 section with before/after for all Phase 41 renames | VERIFIED | All checks pass: `grep -q v0.10.x`, `filter=`, `InvalidIdentifierError`, `keyword-only`; 9 `*Error` name occurrences (≥4 required); D-08 relaxation note present at line 99 |

**Score:** 10/10 truths verified (1 via documented override)

---

### Deferred Items

None.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | filterwarnings = error::DeprecationWarning gate + third-party suppressions | VERIFIED | Line 97: `"error::DeprecationWarning"` is the first entry; 3 defensive ignore entries for psycopg/geopandas/pandas; no `ignore::DeprecationWarning:pycopg` entry (T-41-01 compliant) |
| `tests/test_deprecations.py` | Wave-0 scaffold + filled test bodies for FREEZE-01/02/03 | VERIFIED | 55 tests, all PASS; TestExceptionAliases (3), TestWhereDeprecation (48 including 46 parametrized), TestKwOnlyEnforcement (2), TestTimeBucketWhereDeprecation (4); no xfail markers remaining |
| `pycopg/exceptions.py` | 4 canonical *Error classes + module __getattr__ PEP 562 | VERIFIED | 4 classes at lines 26/32/38/50; `_DEPRECATED_NAMES` map at line 80; `def __getattr__` at line 101; `import warnings as _warnings` at top (E402 compliant); WR-03 fix: single map source |
| `pycopg/__init__.py` | Updated *Error imports + package __getattr__ | VERIFIED | Imports 4 *Error names directly (no old names in import block — Pitfall 2 cleared); `from pycopg.exceptions import _DEPRECATED_NAMES as _DEPRECATED_PACKAGE_ALIASES` (WR-03 fix); `def __getattr__` at line 53; old names kept in `__all__` with deprecation comment |
| `pycopg/spatial.py` | filter= canonical param on 11 builders + _append_tail; filter=/where= shim on 22 accessor methods | VERIFIED | All 11 `build_*_sql` have `filter=` not `where=`; `_append_tail` has `filter` param; all 22 accessor methods have both `filter=` and `where=`; no `where=where` forwarding |
| `docs/stability.md` | SemVer + deprecation policy + support matrix + Stable API Contract + API stability tiers | VERIFIED | 6 sections present; Sphinx -W build clean; PostGIS floor 3.0 hard / 3.2 recommended per D-02; version floors from pyproject.toml; `grep -c 'keyword-only\|positional'` = 5 (≥2 required) |
| `MIGRATION.md` | v0.10.x → 1.0.0 migration section | VERIFIED | Top section; 4 subsections: spatial where=→filter=, exception renames, kw-only enforcement, time_bucket D3; D-08 relaxation note at line 99; upgrade checklist |
| `tests/test_parity.py::test_accessor_parameter_kind_parity` | Structural parity test for all 7 accessor pairs | VERIFIED | Function at line 328; covers all 7 pairs in ACCESSOR_PAIRS; _RAW_SQL_CARVE_OUT documented; 7/7 PASS |
| `tests/test_parity.py::test_database_core_parameter_kind_parity` | Structural parity test for Database/AsyncDatabase | VERIFIED | Function at line 400; PASS |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pycopg/exceptions.py __getattr__` | `globals()[new_name]` (*Error class object) | PEP 562 `_DEPRECATED_NAMES` map | VERIFIED | `_DEPRECATED_NAMES` at line 80; `__getattr__` returns `globals()[new]` — same object guarantee confirmed live |
| `pycopg/__init__.py` | `pycopg.exceptions *Error names` | `from pycopg.exceptions import` | VERIFIED | Direct import of 4 *Error names; no old names imported; `python -c "import pycopg"` exits 0 |
| `SpatialAccessor.<method>` | `build_<method>_sql(..., filter=filter, ...)` | accessor body forwards canonical filter= to clean builder | VERIFIED | grep `filter=where` returns 0; `filter=filter` forwarding confirmed in all 22 methods |
| `where= shim` | `warnings.warn(DeprecationWarning, stacklevel=2)` | per-signature runtime check | VERIFIED | `w.filename.endswith("test_deprecations.py")` assertion passes — stacklevel=2 points to caller |
| `docs/index.md toctree` | `stability` | MyST toctree entry | VERIFIED | `grep stability docs/index.md` matches; Sphinx -W clean (no "not in toctree" warning) |
| `README.md` | `docs/stability.md` (RTD link) | stability link | VERIFIED | Line 10 of README contains RTD link to stability.html |
| `test_accessor_parameter_kind_parity` | all 7 accessor pairs | `inspect.signature` kind comparison | VERIFIED | CR-01 prevention: 8 structural tests PASS; catches future sync/async kw-only drift structurally |

---

### Data-Flow Trace (Level 4)

Not applicable — this phase is a pure API surface refactoring (parameter renames, deprecation shims, signature tightening) with no new data flows. All modified methods are wired to existing DB connections established in prior phases.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `build_contains_sql` rejects old `where=` kwarg | `build_contains_sql('t', point=(0,0), where='x')` raises TypeError | `TypeError: got an unexpected keyword argument 'where'` | PASS |
| `InvalidIdentifier` resolves to same object as `InvalidIdentifierError` | `e.InvalidIdentifier is e.InvalidIdentifierError` | `True` | PASS |
| `filter=` and `where=` both supplied raises TypeError | `accessor.contains('tbl', filter='id>0', where='id>1')` | `TypeError: Cannot specify both 'filter' and 'where'; use 'filter=' only.` | PASS |
| kw-only `geom=` enforcement | `accessor.contains('tbl', 'geom_column')` | `TypeError: SpatialAccessor.contains() takes 2 positional arguments but 3 were given` | PASS |
| `import pycopg` succeeds | `python -c "import pycopg; print('import-ok')"` | `import-ok` | PASS |
| `except OldName:` still catches `*Error` | `except exceptions.InvalidIdentifier: raise InvalidIdentifierError(...)` | Caught — same object guarantee (D-07) | PASS |
| Sphinx -W build clean | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | "La compilation a réussi." | PASS |
| Full suite 1491 passed ≥95% coverage | `PGDATABASE=pycopg_test2 uv run pytest -q` | 1491 passed, 2 skipped, 96.09% coverage | PASS |

---

### Probe Execution

No explicit probe scripts declared for this phase. The PLAN suite specified `uv run pytest` as the primary verification vehicle. See Behavioral Spot-Checks above.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FREEZE-01 | 41-03-PLAN.md | Spatial `where=`→`filter=` rename with DeprecationWarning alias | SATISFIED | 11 builders clean filter= only; 22 accessor methods have filter=/where= shim; 52 parametrized tests PASS; stacklevel=2 verified |
| FREEZE-02 | 41-02-PLAN.md | 4 N818 exception renames with PEP 562 deprecated aliases; internal sites updated | SATISFIED | 4 *Error classes canonical; `def __getattr__` in exceptions.py + __init__.py; 0 old raise sites (grep check); N818 suppression gone; ruff clean |
| FREEZE-03 | 41-04-PLAN.md | Public API consistency pass + Stable API Contract (positional vs kw-only) | SATISFIED | FREEZE-03 findings table in 41-04-SUMMARY.md (D-05 user review gate honored); kw-only `*` on all 7 accessor families + flat core; D2/D5 carve-out documented; CR-01 async parity fix applied + structural test prevents recurrence; 8 parity tests PASS |
| FREEZE-04 | 41-05-PLAN.md | `docs/stability.md` SemVer + deprecation policy + supported versions | SATISFIED | docs/stability.md has all 6 sections; Sphinx -W clean; toctree linked; README linked; MIGRATION.md complete v0.10.x → 1.0.0 section |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | Scan clean: no TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER in any phase-41 modified file |

---

### CR-01 BLOCKER Fix — Verification Detail

The REVIEW.md identified CR-01 as a BLOCKER: `d2eee0d` (Plan 04 kw-only commit) only moved the `*` boundary on sync accessor methods, leaving async classes in `schema.py`, `maint.py`, `etl.py`, and `backup.py` with the old positional signatures.

**Fix commit:** `92018dd` — "fix(41): apply kw-only * boundary to async accessor methods (CR-01)"

**Verification outcome:**
- `test_accessor_parameter_kind_parity[SchemaAccessor-AsyncSchemaAccessor]` PASS
- `test_accessor_parameter_kind_parity[MaintAccessor-AsyncMaintAccessor]` PASS
- `test_accessor_parameter_kind_parity[ETLAccessor-AsyncETLAccessor]` PASS
- `test_accessor_parameter_kind_parity[BackupAccessor-AsyncBackupAccessor]` PASS
- Live inspect.signature checks for schema (17 methods), maint (5+explain), etl (2), backup (4) — zero drift detected

The structural test `test_accessor_parameter_kind_parity` now prevents any future recurrence of this class of sync/async kw-only divergence.

**Other REVIEW findings resolved:**
- WR-03 (duplicate alias map): `__init__.py` now imports `_DEPRECATED_NAMES` from `exceptions.py` — single source of truth, commit `a42ad16`
- IN-01 (docstring Raises used deprecated names): numpydoc Raises blocks updated to `*Error` canonical names, commit `e9dc3da`
- WR-01 (validate_identifiers None-skip): deferred with documented justification — behavior change at SQL boundary, not a Phase 41 regression
- WR-02 (nearest missing order_by/limit): deferred — no code change required, doc suggestion only

---

### Human Verification Required

None — all required behaviors were verified programmatically.

---

### Gaps Summary

No gaps. All 10 must-have truths are VERIFIED (9 directly, 1 via documented override for D-08 which was pre-decided and recorded in 41-CONTEXT.md before implementation began). The CR-01 BLOCKER found during code review was fixed and verified to hold. The full test suite passes at 96.09% coverage under the `-W error::DeprecationWarning` gate.

---

_Verified: 2026-06-28T17:00:00Z_
_Verifier: Claude (gsd-verifier)_
