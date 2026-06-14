---
phase: 16-pure-etl-layer
reviewed: 2026-06-14T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - pycopg/exceptions.py
  - pycopg/queries.py
  - pycopg/__init__.py
  - pycopg/etl.py
  - tests/test_etl.py
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 16: Code Review Report

**Reviewed:** 2026-06-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the Phase 16 "Pure ETL Layer" diff (base `d7c3362^`): the ETL
exception hierarchy (`exceptions.py`), 5 ETL SQL constants (`queries.py`),
top-level exception re-exports (`__init__.py`), the new `pycopg/etl.py`
(`Pipeline` frozen dataclass + pure SQL builders), and DB-free unit tests
(`tests/test_etl.py`).

Overall the security posture is sound: `build_truncate_sql` validates both
identifiers via `validate_identifiers` before interpolation, the regex in
`validate_identifier` restricts to `[a-zA-Z_][a-zA-Z0-9_]*` (no injection
surface), all SQL value placeholders in `queries.py` use `%s`, and the DDL
constant is static. No Critical issues found.

The findings below are all correctness/robustness/quality concerns. The most
important is the silent per-character explosion when `conflict_columns` is
passed as a bare string (WR-01), and a test whose docstring claims coverage
it does not provide (WR-03).

## Warnings

### WR-01: `conflict_columns` passed as a bare string is silently exploded into per-character tuple

**File:** `pycopg/etl.py:157-158`
**Issue:** The normalization `tuple(self.conflict_columns)` treats any
non-tuple iterable uniformly. A bare `str` is iterable, so
`Pipeline(..., load_mode="upsert", conflict_columns="user_id")` does not
raise — it stores `('u','s','e','r','_','i','d')`. The non-empty check at
line 162 then passes, and Phase 18 would emit an `ON CONFLICT
(u, s, e, r, _, i, d)` clause referencing seven non-existent columns. This
is a silent data-correctness trap: a very natural call-site mistake produces
no error at construction and a confusing failure far downstream.
**Fix:** Reject strings explicitly before normalizing:
```python
if isinstance(self.conflict_columns, str):
    raise ValueError(
        "conflict_columns must be a sequence of column names, not a "
        f"single string; got {self.conflict_columns!r} (did you mean "
        f"[{self.conflict_columns!r}]?)"
    )
if not isinstance(self.conflict_columns, tuple):
    object.__setattr__(self, "conflict_columns", tuple(self.conflict_columns))
```

### WR-02: `extract_limit` accepts `bool` values silently

**File:** `pycopg/etl.py:167-170`
**Issue:** The guard `self.extract_limit is not None and self.extract_limit <= 0`
does not reject `bool`, which is a subclass of `int`. `extract_limit=True`
passes (`True <= 0` is `False`) and is stored as `True`; `extract_limit=False`
is rejected with a message claiming it is not "a positive integer" even
though the value printed is `False`. Phase 18 wires this as `LIMIT %s`, so a
stored `True` would render as `LIMIT true`/`LIMIT 1` depending on the driver
— a surprising, hard-to-trace outcome from a boolean typo.
**Fix:** Tighten the type check (the docstring already says "positive
integer"):
```python
if self.extract_limit is not None:
    if isinstance(self.extract_limit, bool) or not isinstance(self.extract_limit, int):
        raise ValueError(
            f"extract_limit must be a positive integer or None, got "
            f"{self.extract_limit!r}"
        )
    if self.extract_limit <= 0:
        raise ValueError(
            f"extract_limit must be a positive integer, got {self.extract_limit!r}"
        )
```

### WR-03: `test_all_load_modes_valid` docstring claims three modes but only tests two

**File:** `tests/test_etl.py:126-130`
**Issue:** The test name and docstring state "All three public load_mode
values construct successfully", but the loop iterates only
`("append", "replace")`. The third public mode, `"upsert"`, is silently
omitted (correctly, because it needs `conflict_columns`). The result is a
test that misrepresents its own coverage — a future reader will believe
`upsert` construction is exercised here when it is not, and a regression in
`upsert` happy-path construction would not be caught by this test. (The
dedicated `test_upsert_with_conflict_columns_ok` does cover it, so this is a
test-clarity/maintainability defect, not a coverage gap per se.)
**Fix:** Either fix the docstring to say "two modes that need no extra
fields", or rename to `test_append_and_replace_modes_valid`. Do not add
`"upsert"` to the bare loop — it would fail without `conflict_columns`.

## Info

### IN-01: Unused re-export imports in `etl.py` rely on `# noqa: F401` instead of `__all__`

**File:** `pycopg/etl.py:31`
**Issue:** `ETLTargetNotFoundError` and `ETLTransformError` are imported only
to be re-exported for Phase 18, suppressed with `# noqa: F401`. They are not
referenced in this module and not listed in any `__all__` (the module has no
`__all__`). The intent ("staging for Phase 18") is invisible to a reader and
the suppression hides a genuine "unused import" signal.
**Fix:** Add an explicit `__all__` that documents the public surface, e.g.
`__all__ = ["Pipeline", "build_init_sql", "build_truncate_sql", "ETLTargetNotFoundError", "ETLTransformError"]`,
which both documents intent and lets you drop the `# noqa`. Alternatively
defer the import to Phase 18 when it is actually used.

### IN-02: `build_truncate_sql` interpolates identifiers without quoting

**File:** `pycopg/etl.py:229`
**Issue:** `f"TRUNCATE TABLE {schema}.{table}"` interpolates validated
identifiers unquoted. This is injection-safe (the validator regex forbids any
metacharacter), but a valid-by-regex identifier that is also a reserved word
or contains uppercase-needing-quoting (PG folds unquoted identifiers to
lower case) would produce SQL that targets the wrong/nonexistent relation
rather than the user's intent. Not a security issue; a correctness sharp edge.
**Fix:** Consider `psycopg.sql.Identifier`/quoting at the Phase 18 execution
boundary, or document that identifiers must be lower-case unquoted names.
Acceptable to defer, but worth a note in the builder docstring.

### IN-03: `Pipeline.transform` type is not validated at construction

**File:** `pycopg/etl.py:142,145-170`
**Issue:** `transform` is typed `Callable | list[Callable] | None` but
`__post_init__` performs no validation. A non-callable (e.g. a string or int)
is accepted silently and will only fail when Phase 18 attempts to invoke it.
The module otherwise validates every field eagerly (load_mode, conflict_columns,
extract_limit), so this is an inconsistency in the validation discipline.
**Fix:** Optional given the "Phase 18 invokes these" boundary, but for
fail-fast consistency consider validating that `transform` is `None`, a
callable, or a list of callables in `__post_init__`.

### IN-04: `_is_sql_source` calls `source.strip()` twice

**File:** `pycopg/etl.py:193-197`
**Issue:** `stripped = source.strip().upper()` is computed, then line 197
recomputes `source.strip()` for the whitespace check. Minor duplication; also
the whitespace heuristic checks the *stripped* string, so an internal-only
space is detected but the recompute is redundant.
**Fix:**
```python
stripped = source.strip()
upper = stripped.upper()
if upper.startswith(("SELECT", "WITH")):
    return True
return " " in stripped
```

---

_Reviewed: 2026-06-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
