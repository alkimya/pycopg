---
phase: 26-incremental-etl-pure-layer
verified: 2026-06-20T12:05:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
---

# Phase 26: Incremental ETL — Pure Layer Verification Report

**Phase Goal:** The pure foundation of incremental ETL exists and is DB-free unit-testable — `Pipeline` accepts and validates `incremental_column`, pure SQL builders produce correct WHERE-clause SQL and subquery wraps, and the encode/decode functions for the JSONB watermark envelope are verified for all supported types.
**Verified:** 2026-06-20T12:05:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `Pipeline(incremental_column='updated_at', load_mode='upsert', ...)` constructs without error and stores the field | ✓ VERIFIED | `etl.py:204` field; spot-check constructed instance, `p.incremental_column == 'updated_at'`; test `test_incremental_column_stored_with_upsert` (test_etl.py:136) |
| 2 | `Pipeline(incremental_column='col', load_mode='append'\|'replace', ...)` raises `ValueError` at construction | ✓ VERIFIED | `_validate_incremental` raises at `etl.py:101-106`; spot-check both modes raised ValueError; tests `test_incremental_column_append_raises_valueerror`/`_replace_` (test_etl.py:148,159) |
| 3 | An invalid `incremental_column` identifier raises `InvalidIdentifier` at construction | ✓ VERIFIED | `validate_identifiers(incremental_column)` at `etl.py:107`; test `test_incremental_column_bad_identifier_raises` (test_etl.py:170) |
| 4 | `_build_incremental_extract_sql` wraps a SQL-string source as `SELECT * FROM (<sql>) _pycopg_inc WHERE col > %s` with `[watermark]` params | ✓ VERIFIED | `etl.py:566-571`; spot-check produced exact string `SELECT * FROM (SELECT a,b FROM t) _pycopg_inc WHERE id > %s`, params `[99]`, watermark not interpolated; test `test_sql_source_with_watermark_wraps_subquery` (test_etl.py:554) |
| 5 | `_build_incremental_extract_sql` appends `WHERE col > %s` to a table source with `[watermark]` params | ✓ VERIFIED | `etl.py:572-573`; spot-check produced `SELECT * FROM public.raw WHERE updated_at > %s`, params `[5]`; test `test_table_source_with_watermark` (test_etl.py:545) |
| 6 | `watermark=None` returns a full unfiltered SELECT and `[]` params | ✓ VERIFIED | `etl.py:561-565`; tests `test_table_source_watermark_none_full_select` / `test_sql_source_watermark_none_full_select` (test_etl.py:575,583) assert no WHERE, no `%s`, `[]` params |
| 7 | `_encode_watermark`/`_decode_watermark` round-trip `datetime` (tz-aware, microseconds + offset), `int`, `str` without type drift | ✓ VERIFIED | `etl.py:580-655`; spot-check round-trip equality for all 3 types incl. `+02:00`/`.123456` datetime; tests `test_roundtrip_datetime`/`_int`/`_str` (test_etl.py:677-696) |
| 8 | `_encode_watermark` raises `ETLError` naming the unsupported type for `bool`, `float`, etc. | ✓ VERIFIED | `bool` guard at `etl.py:612-616` (before int branch), fallthrough raise at `etl.py:623-626`; tests `test_encode_bool_raises_etlerror`/`test_encode_float_raises_etlerror` (test_etl.py:664,672) |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/etl.py` | `incremental_column` field + `_validate_incremental`, `_build_incremental_extract_sql`, `_encode_watermark`, `_decode_watermark` | ✓ VERIFIED | All 5 symbols present (grep confirms lines 76, 204, 512, 580, 629); `_validate_incremental` contained; substantive implementations, not stubs; wired into `__post_init__` and self-contained pure builders |
| `tests/test_etl.py` | DB-free tests for validation, SQL builder, encode/decode round-trip | ✓ VERIFIED | `TestValidateIncremental`, `TestBuildIncrementalExtractSql`, `TestEncodeDecodeWatermark` classes present + field cases in `TestPipeline`; 92 tests pass, exit 0 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `Pipeline.__post_init__` | `_validate_incremental` | call after `_validate_load_mode`, before upsert check | ✓ WIRED | `etl.py:235` — exact call present; ordering proven: load_mode at line 232, incremental at 235, upsert check at 237 (D-17 honored); `test_garbage_load_mode_reported_before_incremental` passes |
| `_build_incremental_extract_sql` | `_is_sql_source` | source-kind dispatch | ✓ WIRED | `etl.py:562,566` — dispatches on `_is_sql_source(source)` for both watermark=None and watermark-set branches (D-11) |
| `_build_incremental_extract_sql` | `validate_identifiers` | column/source/schema validation before f-string interpolation | ✓ WIRED | `etl.py:560` (column, always first), `:564` and `:572` (source/schema, table branch) — identifiers validated before any interpolation (T-26-02) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SQL-source wrap + watermark-as-param | `_build_incremental_extract_sql('SELECT a,b FROM t','id','public',99)` | `SELECT * FROM (SELECT a,b FROM t) _pycopg_inc WHERE id > %s`, params `[99]`, `99` absent from SQL | ✓ PASS |
| Table-source WHERE append | `_build_incremental_extract_sql('raw','updated_at','public',5)` | `SELECT * FROM public.raw WHERE updated_at > %s`, params `[5]` | ✓ PASS |
| Round-trip all 3 types | `_decode_watermark(_encode_watermark(x))` for tz-datetime/int/str | Equal to original, no type/offset/microsecond drift | ✓ PASS |
| Construction + forbidden combos | `Pipeline(... incremental_column ...)` upsert OK, append/replace ValueError | upsert stores field; append/replace raise | ✓ PASS |
| DB-free test suite | `uv run pytest tests/test_etl.py -q -o addopts=""` | `92 passed in 0.11s`, exit 0 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ETL-INC-01 | 26-01-PLAN.md | Declare `Pipeline(incremental_column=...)`; identifier validated; `ValueError` for append/replace (incremental requires upsert) | ✓ SATISFIED | REQUIREMENTS.md:33 (marked `[x]`), traceability row REQUIREMENTS.md:88 (Phase 26, Complete); truths 1-3 verified; no orphaned requirements for this phase |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None | — | No debt markers (TODO/FIXME/XXX/TBD/HACK) in either changed file. "placeholder" grep hits are SQL `%s` placeholder docstrings, not stubs. No `Jsonb` wrap present (correct per D-05). |

### Scope Compliance

`git diff --name-only 6bfd7ca..HEAD -- pycopg tests` returns ONLY `pycopg/etl.py` and `tests/test_etl.py` (211 insertions in etl.py, 286 in test_etl.py, 5 deletions). No `queries.py`, no async/run wiring, no docs — out-of-scope Phase 27/28 work was correctly NOT pulled forward. `interrogate pycopg` = 100% (≥95 gate met).

### Quality Gates

| Gate | Result |
|------|--------|
| `uv run pytest tests/test_etl.py -q -o addopts=""` | 92 passed, exit 0 |
| All 5 new symbols present (grep) | ✓ confirmed |
| `uv run interrogate pycopg` | PASSED, 100.0% (≥95) |
| `git diff` scope (only etl.py + test_etl.py) | ✓ confirmed |

### Human Verification Required

None. This is a pure, DB-free code layer with no visual, real-time, or external-service surface. All behaviors are deterministically verifiable via unit tests and direct invocation, which were executed in-process during this verification.

### Gaps Summary

No gaps. All four ROADMAP Success Criteria and all eight PLAN must-have truths are observably true in the codebase, backed by passing DB-free unit tests and in-process spot-checks. The three key links are wired with the exact D-17 call ordering. Requirement ETL-INC-01 is satisfied and traced. The change set is confined to the two intended files with no out-of-scope leakage.

**Observations (non-blocking, per 26-REVIEW.md — forward-looking hardening for Phases 27/28, NOT this phase's contract):**
- Encode-strict / decode-permissive asymmetry: `_decode_watermark` does not validate the `type` tag against the allowlist (unknown tag falls through to `str(value)`). Acceptable for a pure layer whose only producer is `_encode_watermark`.
- Trailing-`;` SQL hygiene is best-effort (single `rstrip(";")`, no SQL parser) — documented in D-08 as the caller's responsibility for line-comments.
These were explicitly excluded from the phase success criteria and must_haves; they do not affect the goal.

---

_Verified: 2026-06-20T12:05:00Z_
_Verifier: Claude (gsd-verifier)_
