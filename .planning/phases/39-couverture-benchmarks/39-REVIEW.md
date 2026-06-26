---
phase: 39-couverture-benchmarks
reviewed: 2026-06-26T19:16:11Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - tests/test_async_database.py
  - tests/test_etl_accessor.py
  - pycopg/database.py
  - pycopg/config.py
  - pycopg/__init__.py
  - pycopg/backup.py
  - benchmarks/__init__.py
  - benchmarks/__main__.py
  - benchmarks/README.md
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 39: Code Review Report

**Reviewed:** 2026-06-26T19:16:11Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 39 (COV-01 + PERF-04) was reviewed adversarially. The production-code diff
is genuinely pragma-only: four `# pragma: no cover` annotations were added to
`__init__.py`, `config.py`, `backup.py`, and `database.py`, each carrying an
em-dash justification and each landing on a defensive branch that is in fact
unreachable in the test environment. I verified every pragma matches the
`exclude_lines = ["pragma: no cover", ...]` substring rule in `pyproject.toml`,
so coverage tooling will honor them. No logic changes were introduced in
production code, and I found no bugs in the pragma placements.

The new tests are correct, deterministic, and trace to real branches:
- `TestAsyncInsertBatch` (4 live-DB tests) — UUID-suffixed tables, teardown
  fixtures, valid `insert_batch` signature/return semantics (verified
  `cur.rowcount` accumulation gives `0` for `ON CONFLICT DO NOTHING`, so the
  `n == 0` assertion is sound, not flaky).
- 5 sync + 4 async ETL `dry_run` watermark/transform tests — I traced
  `etl.py` L1215/L1224/L1226/L1241/L1248-49 (and the async L1900/L1902/L1916-19/
  L1922-25 mirrors) and confirmed each test exercises the claimed branch.
  `watermark_recorded` is set from `dry_raw_watermark`, so the `isinstance(...,
  str)`/`isinstance(..., datetime)` assertions are correct. All ETL tests carry
  `cleanup_pipeline_runs`/`cleanup_async_pipeline_runs` teardown, so
  pytest-randomly ordering is safe. All required imports
  (`uuid`, `datetime`, `ETLError`, `ETLTransformError`, `AsyncDatabase`) and
  fixtures (`etl_table`, `async_etl_table`, `db_config`) are present.

The benchmark package is functional and correctly scoped out of `testpaths`
and the coverage gate (`omit = [..., "benchmarks/*"]`). Per D-03 there are
deliberately no timing assertions — that is by design and is NOT flagged. The
issues below are confined to the benchmark module: one real lint failure that
escapes the documented lint command, plus quality nits.

## Warnings

### WR-01: Benchmark module fails `ruff check .` (I001) but escapes the documented lint command

**File:** `benchmarks/__main__.py:30-32`
**Issue:** `ruff check benchmarks` reports `I001 Import block is un-sorted or
un-formatted` — there is a double blank line between the import block (ending
L30 `from pycopg.etl import Pipeline`) and the first `# ---` comment banner.
The project's documented lint command (CLAUDE.md) is
`uv run ruff check pycopg tests`, which does **not** include `benchmarks/`,
and `[tool.ruff]` in `pyproject.toml` declares no `exclude`. So this lint
failure ships green under the documented workflow but trips any
`ruff check .` / pre-commit / CI invocation that lints the whole tree. Ruff
selects `I` (isort) in `[tool.ruff.lint]`, so this is an enforced rule, not a
preference.
**Fix:** Collapse to a single blank line after the imports:
```python
from pycopg import Database
from pycopg.etl import Pipeline


# ---------------------------------------------------------------------------
# Data helpers
```
→
```python
from pycopg import Database
from pycopg.etl import Pipeline

# ---------------------------------------------------------------------------
# Data helpers
```
Run `uv run ruff check --fix benchmarks` to apply. Consider also adding
`benchmarks` to the documented lint command so future drift is caught.

### WR-02: Silent bare-`except Exception: pass` can mask real failures in the ETL benchmark teardown

**File:** `benchmarks/__main__.py:205-208`
**Issue:** The `pipeline_runs` truncate in `_bench_etl_run`'s `finally` swallows
*every* exception with `pass`. The comment claims the only expected failure is
"pipeline_runs may not exist", but a broad `except Exception` also hides a dead
connection, a permissions error, or a genuinely broken `TRUNCATE` — any of which
would silently leave `pipeline_runs` rows accumulating across runs and skew the
human-read numbers the whole suite exists to produce. This is dev tooling so it
is a WARNING, not a BLOCKER, but the swallow is wider than the documented intent.
**Fix:** Narrow the catch to the real "table absent" case, or at minimum surface
the error:
```python
try:
    _truncate_pipeline_runs(db)
except psycopg.errors.UndefinedTable:
    pass  # pipeline_runs never created (ETL never ran)
```
(or log `exc` before `pass` if you want to keep the broad catch).

## Info

### IN-01: Benchmark table SQL is unquoted / not schema-qualified, diverging from the codebase convention

**File:** `benchmarks/__main__.py:96-104, 127, 147` (and `_create_bench_table`/`_drop_table` callers)
**Issue:** `_create_bench_table` / `_drop_table` / the inline `TRUNCATE` build SQL
via `f"CREATE TABLE IF NOT EXISTS {table} ..."` with a bare, unquoted,
non-schema-qualified identifier, whereas the rest of the codebase (and every
test fixture in this phase) uses `public."{tbl}"`. Names come from
`_fresh_name` (`base_<uuid-hex>`, lowercase alphanumerics + underscore), so this
is safe today and not an injection risk — but it is an inconsistent pattern that
will surprise a maintainer who later parametrizes `base` from user input.
**Fix:** Quote and qualify for consistency, e.g.
`f'CREATE TABLE IF NOT EXISTS public."{table}" (...)'`, and likewise in
`_drop_table`. Low priority for dev-only tooling.

### IN-02: README documents `make bench` ratios but the suite never asserts them

**File:** `benchmarks/README.md:104-126`
**Issue:** The "Regression Protocol" prose names a concrete ~5x threshold as the
investigate-before-release signal, but nothing enforces it (correct per D-03 — no
timing assertion). The numeric thresholds in the README (~5x, ±20%, 30-60k rows/s)
are unversioned magic numbers that will silently rot as hardware/Postgres config
changes. Not a defect — just flagging that these are documentation-only guard
numbers a reader may mistake for enforced bounds.
**Fix:** No code change required. Optionally add one sentence clarifying the
numbers are illustrative of one reference machine, not committed SLOs.

### IN-03: Four `pragma: no cover` justifications are accurate, but two are environment-coupled rather than structurally unreachable

**File:** `pycopg/backup.py:192-194, 222-224, 571-573`
**Issue:** The three `backup.py` pragmas justify exclusion as "requires
pg_restore/psql subprocess failure; environment-dependent". These branches are
genuinely *reachable* (a subprocess can fail); they are merely hard to trigger
deterministically in CI. That is a legitimate use of `pragma: no cover`, but it
differs in kind from the `__init__.py`/`config.py`/`database.py` pragmas, which
guard branches that are structurally impossible in the installed test env. No
action needed — the justifications are honest — but a future reviewer should know
these three lines hide a real, testable error path (a faked non-zero
`returncode` via a patched `subprocess.run`/`proc` would cover them if coverage
on the restore-failure path is ever wanted).
**Fix:** None required. If COV-01 follow-up wants these lines covered, mock the
subprocess result with `returncode != 0` and assert `RuntimeError` is raised.

---

_Reviewed: 2026-06-26T19:16:11Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
