---
phase: 41-api-homogenization
plan: "05"
subsystem: docs
tags: [freeze-04, stability-doc, migration, semver, deprecation-policy, support-matrix]
dependency_graph:
  requires:
    - "41-04 (FREEZE-03 reviewed audit — Stable API Contract source of truth)"
    - "41-03 (spatial where=→filter= rename details for MIGRATION)"
    - "41-02 (4 exception renames for MIGRATION)"
  provides:
    - "docs/stability.md — SemVer contract, deprecation policy, support matrix, Stable API Contract, API stability tiers"
    - "Sphinx toctree entry `stability` in docs/index.md"
    - "README API Stability link"
    - "MIGRATION.md v0.10.x → 1.0.0 section — all Phase 41 renames with before/after"
  affects:
    - "docs/stability.md (new file)"
    - "docs/index.md (toctree update)"
    - "README.md (stability link)"
    - "MIGRATION.md (new top section)"
tech_stack:
  added: []
  patterns:
    - "MyST Markdown docs flat layout (docs/<page>.md, conf.py in docs/)"
    - "Sphinx -W gate: docs must be in toctree or build fails"
    - "D2/D5 carve-out documented in stability contract (execute/fetch_* keep params positional)"
    - "D-08 relaxation documented (deprecation warning at import/access, not catch-time)"
key_files:
  created:
    - docs/stability.md
  modified:
    - docs/index.md
    - README.md
    - MIGRATION.md
decisions:
  - "docs/stability.md placed at docs/stability.md (flat docs/ layout, not docs/source/) matching actual repo layout"
  - "Stable API Contract table sourced from 41-04-SUMMARY.md reviewed FREEZE-03 audit — not regenerated"
  - "D2/D5 carve-out documented as named exception in stability.md contract table"
  - "D-08 relaxation note added to both stability.md deprecation policy and MIGRATION.md section 2"
metrics:
  duration: "~30 minutes"
  completed: "2026-06-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 3
---

# Phase 41 Plan 05: FREEZE-04 Stability Doc + MIGRATION Section Summary

**One-liner:** `docs/stability.md` published with SemVer contract, deprecation policy (D-01 remove-in-2.0), support matrix grounded in pyproject.toml, Stable API Contract table from FREEZE-03 audit, and API tier table; MIGRATION.md adds complete v0.10.x → 1.0.0 section with before/after for every Phase 41 rename; Sphinx -W gate clean.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write docs/stability.md, add to toctree, link from README | cada69d | docs/stability.md, docs/index.md, README.md |
| 2 | Add MIGRATION.md v0.10.x → 1.0.0 section | 12b33a5 | MIGRATION.md |

---

## What Was Built

### Task 1: docs/stability.md + toctree + README link

**`docs/stability.md`** — 6 sections:

1. **Intro + SemVer Contract** — pycopg follows SemVer 2.0.0; API frozen at 1.0.0.
2. **Breaking vs Non-Breaking Changes table** — 7 rows covering method removal, param
   rename, adding optional param, changing default, changing return type, changing exception
   type, behaviour-changing bug fix.
3. **Deprecation Policy** — deprecated names kept through all of 1.x, removed only in 2.0;
   list of names deprecated in 1.0.0; D-08 relaxation note (warning at import/access, not
   catch-time — intentional, not a gap).
4. **Stable API Contract** — per-method positional-vs-keyword-only boundary table for all
   7 accessor families + flat core (sourced from 41-04-SUMMARY.md FREEZE-03 reviewed audit);
   D2/D5 carve-out documented (`execute`, `fetch_one`, `fetch_val`, `fetch_all`, `stream`,
   `maint.explain` keep params positional); D1 `within()` 4-positional-identifier note.
5. **Supported Versions** — support matrix grounded in pyproject.toml actual values:
   Python ≥ 3.11, PostgreSQL 13+, PostGIS 3.0 hard / 3.2 recommended (ST_MakeValid per D-02),
   TimescaleDB 2.0+, psycopg ≥ 3.1.0, psycopg_pool ≥ 3.2.0, pandas ≥ 2.0.0,
   geopandas ≥ 0.14.0. No invented numbers.
6. **API Stability Tiers** — all 7 accessor namespaces + flat core + builders +
   `*Error` exception names marked Stable; internal `_*` names marked Private.

**`docs/index.md`** — `stability` added to the Sphinx toctree block after `api-autodoc`.

**`README.md`** — stability link added after the badge block (before ## Installation):
`See [API Stability](...) for the SemVer contract, deprecation policy, supported version matrix, and the full Stable API Contract table.`

**Sphinx build:** `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` → "La compilation a réussi." (clean under -W).

### Task 2: MIGRATION.md v0.10.x → 1.0.0 section

Added as the new top section of `MIGRATION.md`, above the existing v0.6.0→v0.7.0 section.

**4 subsections covering every Phase 41 rename:**

1. **Spatial `where=`→`filter=` (FREEZE-01)** — before/after for all 11 accessor methods
   + 11 `build_*_sql` builders; notes that builders are a clean break (TypeError on `where=`)
   while accessors emit DeprecationWarning through 1.x; `filter=` is a raw SQL fragment.

2. **Exception renames (FREEZE-02)** — 4-row rename table; before/after import; notes same-
   object guarantee (`except OldName:` still works); D-08 relaxation note (warning at import/
   access, not catch-time — PEP 562 `__getattr__` semantics, intentional).

3. **Keyword-only enforcement (FREEZE-03)** — clean-break before/after examples across all 7
   accessor families + flat core; D2/D5 carve-out listed (execute/fetch_one/fetch_val/
   fetch_all/stream/maint.explain — `(sql, params)` convention kept positional); D1 within()
   4-positional-identifier boundary; upgrade-to-keyword examples for every accessor family.

4. **time_bucket / time_bucket_gapfill `where=`→`filter=` (D3)** — before/after for both
   methods; notes one-cycle DeprecationWarning shim (same pattern as spatial); raw SQL fragment
   semantics.

**Upgrade checklist** with actionable bullet points + link to stability doc.

**Verification:**

```
grep -q 'v0.10.x' MIGRATION.md                              → OK
grep -q 'filter=' MIGRATION.md                              → OK
grep -q 'InvalidIdentifierError' MIGRATION.md               → OK
grep -qi 'keyword-only' MIGRATION.md                        → OK
grep -c '*Error names' MIGRATION.md                         → 9 (≥ 4 required)
```

---

## Deviations from Plan

None — plan executed exactly as written. The PATTERNS.md reference to `docs/source/stability.md`
was correctly adapted to the actual flat `docs/stability.md` layout per the plan's read_first note.

---

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes. This plan is
docs-only.

**T-41-12 (support matrix version numbers):** VERIFIED — all version floors sourced from
`pyproject.toml` actual values (`requires-python = ">=3.11"`, `psycopg>=3.1.0`,
`psycopg_pool>=3.2.0`, `pandas>=2.0.0`, `geopandas>=0.14.0`). PostGIS 3.0/3.2 per D-02
(not in pyproject.toml — comes from research/context; documented in stability.md).

**T-41-13 (undocumented breaking rename):** VERIFIED — all 4 `*Error` names in MIGRATION.md
(count=9); `filter=` documented; `keyword-only` keyword present; D-08 relaxation documented.

---

## Known Stubs

None.

---

## Self-Check

**Files exist:**

- `docs/stability.md` — FOUND
- `docs/index.md` (updated) — FOUND
- `README.md` (updated) — FOUND
- `MIGRATION.md` (updated) — FOUND

**Commits exist:**

- `cada69d` — docs(41-05): add docs/stability.md
- `12b33a5` — docs(41-05): add MIGRATION.md v0.10.x → 1.0.0 section

**Acceptance criteria:**

- `docs/stability.md` contains "Semantic Versioning" → YES
- `docs/stability.md` contains "Deprecation Policy" → YES
- `docs/stability.md` contains "Stable API Contract" → YES
- `docs/stability.md` contains "Supported Versions" → YES
- `docs/stability.md` contains "API Stability Tiers" → YES
- `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` exits 0 → YES ("La compilation a réussi.")
- `grep -in 'stability' README.md` returns link → YES
- PostGIS row states 3.0 hard / 3.2 recommended → YES
- `grep -c 'keyword-only\|positional' docs/stability.md` ≥ 2 → YES (count=5)
- `MIGRATION.md` has `v0.10.x → 1.0.0` section → YES
- Before/after for spatial where=→filter= → YES
- Before/after for 4 exception renames → YES
- Before/after for keyword-only enforcement → YES
- D-08 relaxation note present → YES
- `grep -c '*Error names' MIGRATION.md` ≥ 4 → YES (count=9)

## Self-Check: PASSED
