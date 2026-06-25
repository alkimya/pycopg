# Phase 36 — Release v0.9.0 — Context (discuss-phase, inline)

**Date:** 2026-06-25
**Mode:** light inline discuss (no skill) — release phase, well-bounded by ROADMAP + v0.8.0 precedent
**Goal (ROADMAP):** v0.9.0 published to PyPI with all quality gates green, docs updated, clean-venv smoke confirming the new surface is importable and functional.
**Requirements:** REL-09

---

## New surface to release (Phases 34 + 35 — verified delivered)

**CRUD ergonomics (Phase 34) — flat on `Database` / `AsyncDatabase`, 7 methods × 2:**
`upsert`, `delete_where`, `update_where`, `exists`, `count`, `paginate`, `fetch_all`
(grep-anchored: `pycopg/database.py:647,702,742,792,833,1077,1114`; async twins in `async_database.py`).

**Introspection (Phase 35) — on `db.schema.*` (`SchemaAccessor`/`AsyncSchemaAccessor`), 5 methods × 2:**
`primary_key`, `foreign_keys`, `sequences`, `views`, `describe`
(grep-anchored: `pycopg/schema.py:676,701,741,759,777` + async twins at `1457,1482,1522,1540,1558`).

**Total new public surface: 12 methods, each with sync + async parity (verified by `test_accessor_parity` / flat-class parity).**

---

## Decisions locked (this discuss)

### D-36-01 — Version: ONE canonical source (corrects ROADMAP criterion #1)
`__version__` is derived dynamically from package metadata
(`pycopg/__init__.py:42` → `importlib.metadata.version("pycopg")`), NOT hardcoded.
**Bump `pyproject.toml` `version = "0.8.0"` → `"0.9.0"` ONLY.** Do NOT add a hardcoded
`__version__ = "0.9.0"` — it would shadow the dynamic resolution and is a regression.
The ROADMAP criterion #1 wording ("both canonical sources") is INACCURATE for this repo;
treat pyproject as the single source. Smoke verifies `pycopg.__version__ == "0.9.0"` resolves
correctly post-build.

### D-36-02 — Plan split: 2 plans (mirrors v0.8.0 Phase 33)
- **36-01 (content):** bump `pyproject.toml`; create CHANGELOG `[0.9.0]` Added-only section
  (under `[Unreleased]`); document the 12 new methods in docs; refresh README method counts
  (`db.schema.*` 27 → 32; add CRUD flat methods note/row); cosmetic-debt cleanup (see D-36-04).
- **36-02 (release):** confirm all 4 gates green; tag `v0.9.0`; PyPI publish via OIDC trusted
  publishing — **human-gated at the irreversible publish step**; clean-venv
  `pip install pycopg==0.9.0` smoke prints `0.9.0`.

### D-36-03 — CHANGELOG signature-drift guard
v0.8.0 ship review caught **4 CHANGELOG signature-drift warnings** (see memory
`phase33-v080-shipped`). Every method signature in the CHANGELOG `[0.9.0]` block MUST match
the actual code signature exactly (param names, defaults, return types). Added-only — no
Changed/Removed/Deprecated (v0.9.0 is purely additive; no MIGRATION guide needed per cadrage lock).

### D-36-04 — Cosmetic debt SOLDERED in this phase (user choice)
Clean up within Phase 36 (was carried in Deferred Items):
- `CLAUDE.md:13` "Version" line reads `v0.5.0` (stale since v0.6.0) → bump to `v0.9.0`.
- Stale `pycopg.aliases` Sphinx xref in accessor docstrings (IN-01/IN-02; `aliases.py` deleted v0.7.0).
- v0.8.0 advisory review warnings WR-01 (case-sensitive `time_bucket(` guard), WR-03
  (INTERVAL-literal-vs-`%s`) — fold in if low-risk; defer any that touch behavior.
Assign to 36-01 as docs/housekeeping tasks; keep them OUT of the release-step plan (36-02).

---

## Gates (baseline = v0.8.0 ship; measure current at plan start)

| Gate | v0.8.0 measured | Target |
| ---- | --------------- | ------ |
| Coverage ratchet | 95.11% | ≥94% |
| interrogate | 100% | ≥95 |
| Sphinx `-W` | clean | clean |
| `-W error::DeprecationWarning` | green | green |

Current-state smoke (2026-06-25): all 12 methods present on both sync+async classes;
`test_parity.py` 26/26 green; `__version__` currently `0.8.0` (auto-updates after pyproject bump).
Run full-suite coverage + interrogate + Sphinx at 36-01 start to confirm starting point.

## Test conventions (carry into plans)
- Default `pycopg_test` DB is BROKEN → run live-DB/parity tests with `PGDATABASE=pycopg_test2`.
- Use `-o addopts=""` for targeted runs.
- 2-3 pre-existing flaky full-suite DB tests (fixture-isolation, not v0.9.0 code) — not blocking.

## Docs surfaces to touch (no new page needed)
`README.md` (counts), `docs/api-reference.md` (per-method rows), `docs/database.md` +
`docs/async-database.md` (CRUD), `docs/index.md`. `docs/api-autodoc.md` regenerates from docstrings.

## Out of scope (deferred, confirmed at cadrage)
CRUD-F01/F02/F03 (raw-SQL where escape hatch, keyset pagination, page-envelope);
INTRO-F01/F02 (describe rich rendering, materialized_views/per-view columns). All v2.
