---
phase: 25
slug: alias-removal
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-19
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `25-RESEARCH.md` → "## Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (`uv run pytest`) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, coverage ratchet `--cov-fail-under=94`) |
| **Quick run command** | `uv run pytest tests/ -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` (coverage gate ≥94) |
| **Estimated runtime** | ~60–120 seconds (DB-backed suite) |

> Note: 2–4 pre-existing flaky DB tests in the local env (documented in memory). Use
> `-o addopts=""` for targeted runs to bypass the coverage gate during iteration; the
> coverage gate is asserted once at end-of-phase on the full suite.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -o addopts=""` (scoped to touched files where possible)
- **After every plan wave:** Run the full suite `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite green AND `uv run pytest -W error::DeprecationWarning tests/` green
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

| Task (illustrative) | Requirement | Test Type | Automated Command | Pass Assertion |
|---------------------|-------------|-----------|-------------------|----------------|
| Remove 56 stubs from `database.py` | ALIAS-RM-01 | source | `grep -c deprecated_alias pycopg/database.py` | output is `0` |
| Remove 56 stubs from `async_database.py` | ALIAS-RM-01 | source | `grep -c deprecated_alias pycopg/async_database.py` | output is `0` |
| Delete `pycopg/aliases.py` | ALIAS-RM-01 | source | `test ! -f pycopg/aliases.py && ! grep -rq deprecated_alias pycopg/` | file gone, no importers |
| Removed flat names raise AttributeError | ALIAS-RM-02 | behavior | `uv run pytest tests/test_alias_removal.py -q -o addopts=""` | new test green; `getattr(db,"create_hypertable")` → `AttributeError` |
| Delete 6 `test_*_aliases.py` | ALIAS-RM-02 | source | `ls tests/test_*_aliases.py 2>/dev/null \| wc -l` | output is `0` |
| Parity stays green | ALIAS-RM-02 | behavior | `uv run pytest tests/test_parity.py -q -o addopts=""` | all pass, `test_parity.py` unmodified |
| No DeprecationWarning fires | ALIAS-RM-02 | gate | `uv run pytest -W error::DeprecationWarning tests/` | exit 0 |
| MIGRATION v0.6→v0.7 table (56 names) | ALIAS-RM-03 | doc | `grep -c 'v0.6.0 → v0.7.0\|v0.6→v0.7' MIGRATION.md` ; count rows | section present; 56-row 1:1 table |
| CHANGELOG `[0.7.0]` Breaking | ALIAS-RM-03 | doc | `grep -A3 '\[0.7.0\]' CHANGELOG.md \| grep -i Breaking` | Breaking entry pointing to MIGRATION |
| WR-01: no `*args/**kwargs` stub on surface | ALIAS-RM-04 | source/behavior | `grep -c '\*args, \*\*kwargs' pycopg/database.py pycopg/async_database.py` | `0` for alias stubs (real varargs methods, if any, justified) |
| IN-02: 15 stale flat-name error strings fixed | ALIAS-RM-04 | source | `grep -rn "db.create_extension(" pycopg/` (error strings) | zero flat `db.create_extension(` in guard messages; all use `db.schema.create_extension(` |
| Coverage ratchet holds | (gate) | gate | `uv run pytest` | `--cov-fail-under=94` passes (baseline 95.64%) |

---

## Wave 0 Requirements

- [ ] `tests/test_alias_removal.py` — NEW test asserting removed flat names raise `AttributeError`
      on both `Database` and `AsyncDatabase` (positive proof for ALIAS-RM-02). The planner
      should treat this as a TDD-style deliverable: it must FAIL while stubs still exist (the
      names resolve) and PASS once they are removed.

*Existing infrastructure (pytest + coverage + `-W` gate) covers all other phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IDE autocomplete shows only accessor methods (no `*args/**kwargs` stubs) | ALIAS-RM-04 (WR-01) | True IDE behavior is editor-dependent; the source-level `grep` for `*args, **kwargs` + the absence of stubs is the automatable proxy | In an editor with Pylance/Jedi on a `py.typed` install, type `db.` and confirm no removed flat names appear and accessor methods carry real signatures. Automatable proxy: the WR-01 source assertion above. |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have an automated verify command or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers the one MISSING reference (`tests/test_alias_removal.py`)
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter once plans are written

**Approval:** pending
