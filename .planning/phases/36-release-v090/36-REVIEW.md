---
phase: 36-release-v090
reviewed: 2026-06-25T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - pycopg/schema.py
  - pycopg/maint.py
  - pycopg/admin.py
  - pycopg/backup.py
  - pycopg/timescale.py
  - pycopg/database.py
  - pycopg/async_database.py
  - tests/test_async_database.py
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 36: Code Review Report

**Reviewed:** 2026-06-25
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 36 is the v0.9.0 release phase. The non-test source changes are entirely
cosmetic docstring edits, and they hold up under adversarial review:

- The dangling `:mod:\`pycopg.aliases\`` Sphinx cross-references were removed from
  all five accessor modules (schema/maint/admin/backup/timescale). I confirmed
  via grep that **no** `pycopg.aliases` reference remains anywhere in `pycopg/` or
  `docs/`, and that `pycopg/aliases.py` genuinely does not exist (removed v0.7.0).
  The edits also correctly updated the version-context prose ("removed in v0.7.0").
- The `RETURNING *` RST-markup fixes in `database.py:670` and
  `async_database.py:1251` wrap the previously-bare `*` in double-backticks,
  eliminating the stray RST-emphasis token that would otherwise trip Sphinx `-W`.
  Both edits are pure markup; the documented behavior is unchanged.
- The accessor-count updates in `schema.py` (27→32) and `timescale.py` (6→15)
  match the actual method inventory.

The substantive change is the new `TestAsyncSchemaIntrospection` class (~117 lines)
in `tests/test_async_database.py`. I traced every assertion against the real
`AsyncSchemaAccessor` implementations (`schema.py:1458-1587`) and the underlying
SQL (`queries.py:141-191`). The return-shape assertions are correct: queries emit
**unqualified** names (`relname`, `table_name`, `sequence_name`), so the
`referenced_table == parent` and `view_name in views` checks are valid. The class
correctly uses the `db_config` real-DB fixture and the class-level
`@pytest.mark.asyncio` marker, consistent with the 23 sibling DB test classes.

One test (`test_sequences_async`) has a weak assertion that undermines its
coverage intent, plus two minor consistency nits. No critical issues.

## Warnings

### WR-01: `test_sequences_async` assertion cannot detect a broken `sequences()`

**File:** `tests/test_async_database.py:3271-3284`
**Issue:** The test creates a table with a `SERIAL` column (which produces a
sequence named `<table>_id_seq`) and then asserts only:

```python
seqs = await db.schema.sequences("public")
assert isinstance(seqs, list)
assert len(seqs) >= 1
```

The `len(seqs) >= 1` check does not verify that the **created** sequence is in the
result. The `public` schema in the shared `pycopg_test` database frequently
contains leftover sequences from other tests (the suite has documented
fixture-isolation issues — see `pycopg-flaky-db-tests`), so this assertion can pass
even if `sequences()` returned an unrelated, stale list and never saw the new
SERIAL sequence at all. As written the test would still pass if the query were
silently broken, defeating its purpose as a coverage/regression guard.

**Fix:** Assert on the specific sequence the test created (SERIAL sequences are
named `<table>_<column>_seq`):

```python
seqs = await db.schema.sequences("public")
assert isinstance(seqs, list)
assert f"{t}_id_seq" in seqs
```

## Info

### IN-01: Class-level `@pytest.mark.asyncio` is redundant under `asyncio_mode = "auto"`

**File:** `tests/test_async_database.py:3219`
**Issue:** `pyproject.toml:91` sets `asyncio_mode = "auto"`, so pytest-asyncio
already treats every `async def test_*` as an asyncio test; the explicit
`@pytest.mark.asyncio` decorator is not required. This is harmless and matches the
existing convention across the other 23 async test classes in this file, so it is
noted for consistency context only — not a defect.

**Fix:** No action required; keep as-is for stylistic consistency with the rest of
the file.

### IN-02: `_t()` imports `uuid` inside the method body

**File:** `tests/test_async_database.py:3223-3226`
**Issue:** The unique-name helper imports `uuid` lazily inside `_t()` rather than
at module scope. It works correctly, but a single module-level `import uuid`
alongside the other top-of-file imports would be cleaner and avoids re-running the
import lookup on every table-name generation.

**Fix:** Move `import uuid` to the module import block (top of file) and drop the
in-method import.

---

_Reviewed: 2026-06-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
