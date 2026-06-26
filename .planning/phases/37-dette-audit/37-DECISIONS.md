---
phase: 37-dette-audit
plan: 05
decision: D-09
created: 2026-06-26
purpose: Single consolidated decisions journal for every justified closure, audit disposition, and sign-off in Phase 37.
covers:
  - DEBT-03b behavioral closures (deferred to v1.0.0)
  - AUDIT-01 code-review dispositions (5 BLOCKERS fixed, 5 warnings fixed, 1 deferred)
  - NYQ-01 formal Nyquist sign-off for phases 22-24
  - DEBT-05 raise-site note (truncate_table used; __all__-removal fallback unused)
  - AUDIT-02 vulture allowlist rationale
  - Plan 03 isolation finding (none surfaced)
---

# Phase 37 — Consolidated Decisions Journal (D-09)

This is the single authority document (D-09) recording every "closed-with-justification"
disposition, audit triage outcome, and formal sign-off produced by Phase 37
(Dette & Audit). The verifier checks the ROADMAP success criteria against this file.

> ## ⚠ ID-collision warning (read first)
>
> Two unrelated `WR-0x` warning-ID series appear in this phase and MUST NOT be conflated:
>
> - **v0.8.0:WR-xx** — historical findings from the v0.8.0 code review, tracked under
>   **DEBT-03b** (this journal, §1). `v0.8.0:WR-03` = INTERVAL-literal-vs-`%s`.
> - **37-REVIEW:WR-0x** — findings LOCAL to the Phase 37 AUDIT-01 code review
>   (`37-REVIEW.md`), tracked in §2. `37-REVIEW:WR-03` = `copy_insert()` session bypass.
>
> They collide by number but are entirely different findings. Throughout this file each
> ID is qualified with its source prefix.

---

## §1 — DEBT-03b: Behavioral closures (deferred to v1.0.0 with justification)

Per D-03b, the following three behavioral-hardening items are **closed with justification**
and the actual behavioral change is **deferred to the v1.0.0 API-freeze milestone**. None is
an active vulnerability; each is guarded or is accepted caller-responsibility UX.

### §1.1 — v0.8.0:WR-03 — INTERVAL literal vs `%s` bind

- **Location:** `pycopg/timescale.py:393` — `chunk_time_interval => INTERVAL '{chunk_time_interval}'`
  (RESEARCH §"DEBT-03 → D-03b", file:line evidence at 37-RESEARCH.md:443-445).
- **Finding:** the `chunk_time_interval` value is interpolated as an INTERVAL literal rather
  than passed as a `%s` bound parameter.
- **Why it is safe today:** a `validate_interval()` guard at `timescale.py:387` runs first and
  only admits safe interval literals (the `_INTERVAL_PATTERN` whitelist:
  `<number> <unit>`). No injection surface remains.
- **Why deferred:** converting to `%s` would require TimescaleDB to accept a bound parameter
  in the `chunk_time_interval =>` named-argument position of `create_hypertable`, which its
  function-call syntax may not support. This is a behavioral change with real regression risk.
- **Disposition:** **CLOSED — deferred to v1.0.0.** Guarded by `validate_interval`; revisit
  under the API-freeze milestone.

### §1.2 — `%`/`%s` in caller-supplied structural SQL (`aggregates` / `where`)

- **Location:** `time_bucket` builder at `pycopg/timescale.py:255` — the `_to_named_binds`
  renaming path (37-RESEARCH.md:447-449).
- **Finding:** if a caller passes structural SQL (`aggregates` or `where`) that itself contains
  `%s`/`%`, the named-binds renaming path can misbehave.
- **Why it is accepted:** `aggregates`/`where` are **structural SQL fragments authored by the
  caller**, not data values. A caller embedding stray `%s` in their own structural SQL is a
  caller error surfaced as a clear failure, not an injection vector (the values bound by pycopg
  remain parameterized). This is accepted caller-responsibility UX.
- **Disposition:** **CLOSED — accepted (caller-error UX, not injection).** No change in v0.10.0;
  any ergonomics improvement deferred to v1.0.0.

### §1.3 — IN-03 — fragile `chunk_seq` test helper

- **Location:** inline `chunk_seq` helper at `tests/test_timescale.py:468` and `:589`
  (37-RESEARCH.md:451-453).
- **Finding:** the helper parses the internal TimescaleDB chunk-name format
  (`_hyper_X_N_chunk`) to extract a sequence number; this could break on a TSDB version change.
- **Why it is accepted:** it is **test-only** code; the fragility is documented at the helper
  site. It does not affect the shipped library.
- **Disposition:** **CLOSED — deferred to v1.0.0.** Test-only; document-and-defer.

---

## §2 — AUDIT-01: Code-review dispositions (D-06 disposition bar)

Source report: `.planning/phases/37-dette-audit/37-REVIEW.md` (5 critical / 6 warning / 0 info).
The Task 2 human checkpoint was **APPROVED** with the dispositions below. Every HIGH (BLOCKER)
is fixed in-phase; every MEDIUM (WARNING) is fixed in-phase except one, which is deferred to
v1.0.0 with justification. No INFO/LOW findings surfaced.

> IDs in this section are **37-REVIEW:** local IDs — distinct from the v0.8.0:WR-xx series in §1.

### §2.1 — BLOCKERS (HIGH) — all 5 FIXED in-phase

| ID | Fix | File(s) | Test | Commit |
|----|-----|---------|------|--------|
| CR-01 | Whitelist `explain()` `format` against `{text,json,xml,yaml}` (case-insensitive); raise `ValueError` before building EXPLAIN SQL — sync + async | `pycopg/maint.py` | `TestCR01ExplainFormatWhitelist` (9 cases) | `0321b85` |
| CR-02 | Add `validate_identifiers(table, schema)` before `df.to_sql()` in `from_dataframe()` — sync + async | `pycopg/database.py`, `pycopg/async_database.py` | `TestCR02FromDataframeValidation` (4 cases) | `1118a60` |
| CR-03 | Add `validate_identifiers(table, schema)` after the PostGIS gate, before `gdf.to_postgis()` in `from_geodataframe()` — sync + async | `pycopg/database.py`, `pycopg/async_database.py` | `TestCR03FromGeoDataframeValidation` (4 cases) | `1118a60` |
| CR-04 | New `_validate_cli_pattern()` guard rejecting values starting with `-` (flag injection) or containing control chars, applied to all `-t`/`-T`/`-n` expansions in `build_pg_dump_cmd` + `build_pg_restore_cmd` (wildcards/`schema.table` patterns still accepted) | `pycopg/base.py` | `TestCR04CLIFlagInjectionGuard` (8 cases) | `6dc326b` |
| CR-05 | Separate `.sql`→psql routing from existence check; non-`.sql` + missing file now raises `FileNotFoundError` instead of misrouting binary content to psql — sync + async | `pycopg/backup.py` | `TestCR05PgRestoreMissingFile` (3 cases) | `ede7210` |

### §2.2 — WARNINGS (MEDIUM) — 5 FIXED in-phase, 1 DEFERRED

| ID | Disposition | Fix / Justification | File(s) | Test | Commit |
|----|-------------|---------------------|---------|------|--------|
| 37-REVIEW:WR-01 | **FIXED** | `isinstance(bool)`/`isinstance(int)` runtime guard on `connection_limit` in `build_role_options()`, consistent with `number_partitions` in timescale.py | `pycopg/base.py` | `TestWR01ConnectionLimitIntGuard` (5 cases) | `6dc326b` |
| 37-REVIEW:WR-02 | **FIXED** | `AsyncDatabase.stream()` switched from `self.connect()` to session-aware `self.cursor()` — restores sync/async parity for session-mode streaming | `pycopg/async_database.py` | `TestWR02AsyncStreamSessionParity` (2 cases) | `1118a60` |
| 37-REVIEW:WR-03 | **DEFERRED to v1.0.0** | See justification below | `pycopg/database.py`, `pycopg/async_database.py` | — | — |
| 37-REVIEW:WR-04 | **FIXED** | `_validate_libpq_option()` rejects unsafe option keys (non-GUC-identifier) and values (space/quote/backslash) before interpolation into the libpq `options` string; applied in `Config.dsn` + `Config.connect_params()` | `pycopg/config.py` | `TestWR04ConfigOptionSanitization` (8 cases) | `e46ab2d` |
| 37-REVIEW:WR-05 | **FIXED** | Export `TimescaleError` from `pycopg/__init__.py` import block + `__all__` | `pycopg/__init__.py` | `TestWR05TimescaleErrorExported` (4 cases) | `b9bed80` |
| 37-REVIEW:WR-06 | **FIXED** | `_decode_watermark()` adds explicit `str` branch and raises `ETLError` (with envelope in message) for unknown type tags instead of silent `str()` fallthrough | `pycopg/etl.py` | `TestWR06DecodeWatermarkUnknownTag` (6 cases) | `a081b0e` |

#### 37-REVIEW:WR-03 deferral justification (`copy_insert()` session bypass)

- **Finding:** `Database.copy_insert()` (`pycopg/database.py:1037`) and
  `AsyncDatabase.copy_insert()` (`pycopg/async_database.py:678`) both open their own connection
  via `self.connect()`, so a COPY runs and commits on an independent connection even when the
  caller is inside a `db.session()` block — the COPY does not participate in the surrounding
  transaction.
- **Why deferred (not fixed):** the two paths are **consistent** (sync and async behave
  identically), so this is the current **intentional semantics**: COPY-as-its-own-transaction.
  Making `copy_insert()` join the active `db.session()` connection is a **behavioral change** to
  transaction/atomicity semantics that needs design review (interaction with the run-log
  autocommit isolation seam, COPY error handling within an open transaction, and the documented
  contract). That design work belongs in the v1.0.0 API-freeze milestone, not in this bounded
  dette phase.
- **Disposition:** **CLOSED — deferred to v1.0.0** with the above justification. Per the Task 2
  approval, `copy_insert` was explicitly left untouched (no code change, no test).

### §2.3 — INFO / LOW

**None surfaced.** The AUDIT-01 report (`37-REVIEW.md`) classified 0 INFO findings.

### §2.4 — Bar-satisfaction summary

- Every **HIGH (BLOCKER)** is fixed in-phase (CR-01..CR-05).
- Every **MEDIUM (WARNING)** is fixed in-phase except **37-REVIEW:WR-03**, which is
  deferred-to-v1.0.0 with written justification.
- **0 LOW/INFO** findings to log.
- After all fixes: `uv run ruff check pycopg tests` exits 0; `PGDATABASE=pycopg_test2 uv run
  pytest` is green except the 3 known pre-existing PostGIS-env failures. 53 new regression tests
  in `tests/test_audit_37_fixes.py` (≥1 per fixed finding).

---

## §3 — NYQ-01: Formal Nyquist sign-off (phases 22-24)

### Surviving evidence

The per-phase `VALIDATION.md` / `VERIFICATION.md` artifacts for phases 22, 23, and 24 **no
longer exist on disk** — the v0.6.0 phase directories were not archived with their per-phase
artifacts (only Phase 21 was archived with its `VALIDATION.md`, and only `v0.5.0-phases` retained
the full per-phase set). [VERIFIED: `find .planning/phases/2[234]-* -name '*VALIDATION*'` returns
nothing, 2026-06-26.]

The **surviving authority document** is `.planning/milestones/v0.6.0-MILESTONE-AUDIT.md`, which
records: all 11 v0.6.0 requirements SATISFIED (3-source cross-reference), all 4 phases verified
PASSED, full-suite coverage 95.64% at Phase 23, and the explicit note that the only open item was
a **"missing formal Nyquist sign-off, not a coverage gap."**

### Sign-off mechanism (D-08)

Rather than fabricate backdated `draft` `VALIDATION.md` files for 22-24 (rejected as false
history — D-08), the **legitimate sign-off** is to flip the nyquist block in the surviving
milestone-audit document and record the rationale here. Applied 2026-06-26:

- `v0.6.0-MILESTONE-AUDIT.md` frontmatter: `compliant_phases: ["21","22","23","24"]`,
  `partial_phases: []`, `overall: compliant` (was `compliant: ["21"]`, `partial: ["22","23","24"]`,
  `overall: partial`). Committed `18a958f`.
- Body Nyquist-Compliance section + Tech-Debt row updated to reflect closure and reference this
  journal.

### Spot-check: the five v0.6.0 accessor requirements still hold in v0.9.0 code

[VERIFIED: live grep 2026-06-26]

| Req | Class / method | File:line | Status |
|-----|----------------|-----------|--------|
| ADM-01 | `AdminAccessor` / `AsyncAdminAccessor` | `pycopg/admin.py:33,424` | EXISTS |
| MNT-01 | `MaintAccessor` / `AsyncMaintAccessor` | `pycopg/maint.py:28,203` | EXISTS |
| BKP-01 | `BackupAccessor` / `AsyncBackupAccessor` | `pycopg/backup.py:29,365` | EXISTS |
| SCH-01 | `SchemaAccessor` / `AsyncSchemaAccessor` | `pycopg/schema.py:35,817` | EXISTS |
| SCH-02 | `create_spatial_index` / `list_geometry_columns` on `SpatialAccessor` | `pycopg/spatial.py:1859,1888` (+ async `2782,2812`) | EXISTS |

Smoke: `uv run python -c "import pycopg; from pycopg import admin, maint, backup, schema, spatial"`
exits 0.

### Success-criterion wording reconciliation

The ROADMAP success criterion reads: *"the VALIDATION.md of phases 22-24 are at
`nyquist_compliant: true` (PASSED)."* The literal artifact ("a VALIDATION.md file per phase at
`nyquist_compliant: true`") cannot be produced honestly because those files were never archived.
The **artifact reality** is that `v0.6.0-MILESTONE-AUDIT.md` is the authoritative nyquist
compliance record for the milestone; promoting its nyquist block from `partial` to `compliant`
**is** the legitimate `nyquist_compliant: true` sign-off for 22-24. The criterion is satisfied in
substance (formal sign-off recorded against surviving evidence) without fabricating backdated
per-phase files.

**Formal sign-off statement:** *Phases 22, 23 and 24 are retroactively promoted to
`nyquist_compliant: true` as of 2026-06-26, based on the v0.6.0 milestone-audit evidence (all
reqs SATISFIED, all phases PASSED, coverage 95.64%) and a live spot-check confirming all five
v0.6.0 accessor requirements still hold in v0.9.0 code.*

---

## §4 — DEBT-05: TableNotFound raise-site note

DEBT-05 was resolved in **Plan 37-04** using the **recommended** raise site:
`SchemaAccessor.truncate_table` and `AsyncSchemaAccessor.truncate_table` now raise
`TableNotFound` when the target table is absent (additive guard before the `TRUNCATE` DDL,
symmetric sync/async). The **fallback option** (removing `TableNotFound` from `__all__` and
documenting it as a public-surface change) was **NOT needed** — the truncate_table raise site
landed cleanly with no existing-test breakage. Recorded here for the D-09 consolidation per D-09's
"DEBT-05 fallback (unused — the truncate_table site landed)" requirement.

---

## §5 — AUDIT-02: vulture allowlist rationale

Per D-07, `vulture` (+ `pytest-randomly`) were added to the dev-group and a live scan was run:

```
uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80
```

**Result: no confirmed dead code at `--min-confidence 80`.** The scan produced 13 findings, all
confirmed false positives and documented in `vulture_whitelist.py`:

1. **4 public exceptions** (`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`,
   `DatabaseExists`) — exported in `pycopg.__all__` for user-facing `except` clauses; rarely the
   sole internal raise/catch point but are documented public API. Allowlisted, never deleted
   (non-breaking constraint).
2. **3 context-manager protocol parameters × 4 sites** (`exc_type`, `exc_val`, `exc_tb`) — required
   by the PEP 343 / PEP 492 `__exit__`/`__aexit__` signatures on `Database`, `AsyncDatabase`,
   `PooledDatabase`, `AsyncPooledDatabase`; the bodies just call `close()` so vulture flags them at
   100% confidence. Cannot be removed (protocol violation).
3. **1 python-dotenv fallback-stub parameter** (`override`) — the no-op `load_dotenv` stub in
   `config.py`'s `except ImportError` branch mirrors the real python-dotenv API so
   `load_dotenv(override=True)` works when dotenv is absent; the stub body is `pass`, so vulture
   flags `override` as unused. Must exist to preserve the API contract.

No public-API symbol (anything in a module `__all__`) was deleted — public-but-internally-unused
names are allowlisted, never removed (non-breaking constraint, T-37-05-01 mitigation).

---

## §6 — Plan 03 isolation finding (pytest-randomly)

Plan 37-03 (fixture-isolation de-flake) ran the suite under `pytest-randomly`. Per its SUMMARY,
the watermark bound-param tests passed across **8+ random seeds** (1, 100, 999, 5000, 7777, 12345,
31337, 54321, 78901, 98765) and the full suite was stable (1332 passed, 11 skipped, 3 known
PostGIS-env failures) across seeds including `--randomly-seed=42`.

**No new isolation bug surfaced.** The randomization confirmed determinism for the three known
DEBT-01 flaky tests (now root-cause fixed) and surfaced no additional latent isolation finding to
disposition under D-05. The only residual failures are the 3 pre-existing PostGIS-env failures in
`tests/test_postgis_errors.py` (PostGIS absent in `pycopg_test2`) — an environment limitation, not
a test-isolation bug, and not introduced by Phase 37.

---

_Consolidated 2026-06-26 — Phase 37 Plan 05 (D-09). This file is the single authority for all
Phase 37 closed-with-justification dispositions and sign-offs._
