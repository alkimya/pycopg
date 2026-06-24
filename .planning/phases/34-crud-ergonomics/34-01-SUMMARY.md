---
phase: 34-crud-ergonomics
plan: "01"
subsystem: base
tags: [crud, builder, sql-safety, query-mixin]
dependency_graph:
  requires: []
  provides: [_build_where_dict on QueryMixin]
  affects: [pycopg/base.py, tests/test_base.py]
tech_stack:
  added: []
  patterns: [validate_identifiers-first, pure-(sql,params)-builder, numpydoc-shallow-docstring]
key_files:
  created: []
  modified:
    - pycopg/base.py
    - tests/test_base.py
decisions:
  - "_build_where_dict placed directly after _build_select_sql in QueryMixin — consistent with sibling builders"
  - "validate_identifiers(*where.keys()) runs before any string build — T-34-01 mitigation"
  - "Values returned as positional params list, never interpolated — T-34-02 mitigation"
  - "Empty-dict guard explicitly excluded from the builder — caller responsibility (D-04/D-12)"
metrics:
  duration: "56s"
  completed: "2026-06-24T15:40:51Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 34 Plan 01: _build_where_dict Pure Builder Summary

**One-liner:** Added `_build_where_dict` pure staticmethod on `QueryMixin` — converts a dict of equality conditions to an AND-ed `col = %s` fragment with validated column keys and positionally-bound params.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add _build_where_dict pure builder to QueryMixin | 20caa52 | pycopg/base.py |
| 2 | Unit-test _build_where_dict in test_base.py | 34c63ee | tests/test_base.py |

## What Was Built

### `_build_where_dict(where: dict) -> tuple[str, list]` on `QueryMixin`

A pure `@staticmethod` in `pycopg/base.py` that:

1. Calls `validate_identifiers(*where.keys())` first — raises `InvalidIdentifier` for any malformed column name before any string construction (T-34-01 mitigation).
2. Builds the SQL fragment as `" AND ".join(f"{col} = %s" for col in where)` — dict-insertion order, `%s` placeholders only.
3. Returns `(fragment, list(where.values()))` — values are never interpolated into the SQL string (T-34-02 mitigation).

Contract: caller must pass a non-empty dict. Empty dict would yield `("", [])` producing a malformed `WHERE ` — this path is excluded by callers (`delete_where`/`update_where` raise `ValueError` on empty where; `count`/`paginate` route around the builder when `where is None`).

### Unit Tests in `TestQueryMixin`

Three new test methods in `tests/test_base.py`:
- `test_build_where_dict_basic` — single-key dict → `("id = %s", [1])`; asserts raw value not in fragment.
- `test_build_where_dict_multi_key` — `{"active": True, "kind": "x"}` → `("active = %s AND kind = %s", [True, "x"])`; params in insertion order.
- `test_build_where_dict_validates_identifiers` — `{"bad;col": 1}` raises `InvalidIdentifier`.

All 65 tests in `test_base.py` pass; no DB connection required.

## Verification

```
uv run ruff check pycopg/base.py tests/test_base.py  → All checks passed (clean)
uv run pytest tests/test_base.py -o addopts="" -q    → 65 passed in 0.18s
```

Manual sanity: fragment contains only `col = %s` and `AND`; all values are in the params list.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Model Coverage

| Threat | Mitigation | Status |
|--------|------------|--------|
| T-34-01 Identifier injection via column key | `validate_identifiers(*where.keys())` runs first | Implemented + tested |
| T-34-02 Value injection | Values returned as `%s` params, never interpolated | Implemented + tested |
| T-34-SC No new runtime dependencies | No installs in this plan | Confirmed |

## Known Stubs

None — this is a pure builder with no UI/data-rendering surface.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- [x] `pycopg/base.py` contains `def _build_where_dict(` as `@staticmethod` on `QueryMixin`
- [x] Commit 20caa52 exists (Task 1)
- [x] Commit 34c63ee exists (Task 2)
- [x] `tests/test_base.py` contains `test_build_where_dict_basic`, `test_build_where_dict_multi_key`, `test_build_where_dict_validates_identifiers`
- [x] All 65 tests pass, ruff clean
