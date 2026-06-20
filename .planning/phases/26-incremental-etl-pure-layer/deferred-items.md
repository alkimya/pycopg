# Phase 26 — Deferred / Out-of-Scope Items

Discoveries logged during execution that are **out of scope** for this plan
(pre-existing, in unrelated files) and were deliberately NOT fixed (SCOPE BOUNDARY).

## Pre-existing lint/format debt (unrelated files)

The plan's verification ran `uv run ruff check pycopg tests` and
`uv run black --check pycopg tests` across the whole tree. Both report
failures that **pre-date this plan** and live in files this plan did not touch:

### ruff (35 errors, all pre-existing on base commit 6bfd7ca)
- `pycopg/exceptions.py` — N818 (exception names without `Error` suffix:
  `ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`).
- `tests/setup_test_db.py` — W291 trailing whitespace.
- `tests/test_async_database.py`, `tests/test_database.py`, `tests/test_pool.py`,
  `tests/test_pool_stress.py`, `tests/test_postgis_errors.py`,
  `tests/test_session_edge_cases.py` — F841 unused locals, E722 bare except.

### black (pre-existing on base commit 6bfd7ca)
- `pycopg/etl.py:1415` (base numbering) — the async `AsyncETLAccessor.run`
  `exists = await self._db.schema.table_exists(pipeline.target, pipeline.schema)`
  line exceeds the wrap width under the newer black; committed as-is in history.
- Two other files in the tree (`tests/`-area) also flagged by the whole-tree run.

**Verification done for this plan instead:** ran ruff + black scoped to the two
files this plan modifies (`pycopg/etl.py`, `tests/test_etl.py`) — both clean
(my new code passes; the only residual `etl.py` black hunk is the untouched
pre-existing async line above). `interrogate pycopg` = 100% (≥95 gate).

These are tracked here, not fixed, per the executor SCOPE BOUNDARY rule
(only auto-fix issues directly caused by the current task's changes).
