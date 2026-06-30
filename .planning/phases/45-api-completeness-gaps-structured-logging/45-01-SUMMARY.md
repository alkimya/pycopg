---
phase: 45-api-completeness-gaps-structured-logging
plan: "01"
subsystem: logging-and-types
tags: [logging, types, stdlib, base, exports]
dependency_graph:
  requires: []
  provides:
    - pycopg.logging (get_logger, log_operation)
    - pycopg.base.Params
    - pycopg.base._decode_server_version
    - pycopg.IsolationLevel
    - pycopg.Params
  affects:
    - pycopg/__init__.py (__all__ extended)
    - pycopg/base.py (new symbols)
tech_stack:
  added:
    - pycopg/logging.py (new module, stdlib logging + contextlib only)
  patterns:
    - NullHandler-by-default library logging pattern (D-08)
    - contextmanager with Generator[None, None, None] return type for mypy-strict (D-10)
    - Thin re-export via `from psycopg import IsolationLevel` (D-01)
    - Union type alias `Sequence[Any] | Mapping[str, Any] | None` in base.py (D-11)
key_files:
  created:
    - pycopg/logging.py
    - tests/test_logging_module.py
  modified:
    - pycopg/base.py
    - pycopg/__init__.py
decisions:
  - "D-08 enforced: NullHandler attached at module import; logging.basicConfig() never called; verified by AST-walk test"
  - "D-10: log_operation uses Generator[None, None, None] return type (not Iterator[None]) for mypy-strict @contextmanager compatibility"
  - "D-11: Params alias lives in base.py (no circular import risk); exported via __all__ in __init__.py"
  - "D-01: IsolationLevel is a thin re-export (from psycopg import IsolationLevel), not a copy of the enum"
  - "D-06: _decode_server_version placed in base.py (shared by Plans 03+ without duplication)"
  - "test_no_basicconfig_call uses AST walk not string search — avoids false positive from docstring mention"
metrics:
  duration: "6 minutes"
  completed: "2026-06-30"
  tasks_completed: 2
  files_created: 2
  files_modified: 2
---

# Phase 45 Plan 01: Logging Module + Type Foundation Summary

Silent-by-default `pycopg/logging.py` with `get_logger()`+`log_operation()` CM; `Params` union alias and `_decode_server_version` in `base.py`; `IsolationLevel`+`Params` frozen public exports in `__all__`.

## What Was Built

### Task 1 — `pycopg/logging.py` + `tests/test_logging_module.py`

TDD (RED→GREEN→REFACTOR). New module providing the structured-logging substrate for all of Phase 45.

- `get_logger() -> logging.Logger` — returns `logging.getLogger("pycopg")`, the library logger
- `_logger.addHandler(logging.NullHandler())` at module import — library is silent by default (D-08)
- `log_operation(operation: str, *, rows: int | None = None) -> Generator[None, None, None]` — `@contextmanager` that emits one `DEBUG` record via `_logger.debug(...)` with `extra={"operation": ..., "duration_ms": ..., ["rows": ...]}`. `rows` is keyword-only (D-04). Never calls `logging.basicConfig()`.
- Return type explicitly annotated as `Generator[None, None, None]` (not `Iterator`) for Phase 46 mypy-strict (D-10)
- `extra: dict[str, Any]` explicitly annotated (avoids `--disallow-any-generics` failure at Phase 46)

Test suite (`tests/test_logging_module.py`, 10 tests, 3 classes):
- `TestGetLogger`: identity check, name, NullHandler presence
- `TestLogOperation`: DEBUG level, `operation`/`duration_ms`/`rows` extra fields, keyword-only enforcement, no-`basicConfig` AST guard
- `TestNullHandlerSilence`: NullHandler-only isolation, module-level AST scan

### Task 2 — `pycopg/base.py` + `pycopg/__init__.py`

- `base.py` — added `from collections.abc import Mapping, Sequence`; defined `Params = Sequence[Any] | Mapping[str, Any] | None` (D-11, single source of truth); defined `_decode_server_version(v: int) -> str` with two-part (PG≥10) and three-part (pre-10) arithmetic
- `__init__.py` — `from psycopg import IsolationLevel` thin re-export (D-01); `from pycopg.base import Params`; both added to `__all__` under `# Types` group

## Verification

| Check | Result |
|---|---|
| `pytest tests/test_logging_module.py -x -q -o addopts=""` | 10 passed |
| `python -c "from pycopg import IsolationLevel, Params"` | OK |
| `python -c "from pycopg.base import _decode_server_version; assert _decode_server_version(160001)=='16.1'"` | OK |
| `_decode_server_version(90605) == '9.6.5'` | OK |
| `pycopg.IsolationLevel is psycopg.IsolationLevel` | OK (thin re-export) |
| `ruff check pycopg tests` | clean |
| `black --check pycopg tests` | clean |
| `pytest tests/test_parity.py` (PGDATABASE=pycopg_test2) | 37 passed |
| Full suite `uv run pytest` | 1700 passed, 2 skipped — 96.08% coverage |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_no_basicconfig_call` string-search false positive**
- **Found during:** Task 1 GREEN phase
- **Issue:** Test checked `assert "basicConfig" not in source` — this matched the docstring line "never calls `logging.basicConfig()`" causing a spurious failure
- **Fix:** Replaced string search with AST walk (`ast.walk(tree)`) that checks only actual `ast.Call` nodes, not docstring text
- **Files modified:** `tests/test_logging_module.py`
- **Commit:** included in GREEN feat commit + REFACTOR commit

**2. [Rule 3 - Blocking] Unused import and sort order in `__init__.py`**
- **Found during:** Task 2 post-commit ruff check
- **Issue:** `import psycopg` was unused (only `from psycopg import IsolationLevel` needed); ruff I001 sort violation
- **Fix:** Removed bare `import psycopg`; the `from psycopg import IsolationLevel` line is already correctly placed as a third-party import before first-party `from pycopg` imports
- **Files modified:** `pycopg/__init__.py`
- **Commit:** included in Task 2 feat commit

**3. [Rule 3 - Blocking] Ruff import-sort violations in test file**
- **Found during:** Final verification pass
- **Issue:** `import ast/inspect` inside method bodies triggering I001; unused `import pytest` (F401)
- **Fix:** Hoisted all stdlib imports to module level; removed `import pytest`
- **Files modified:** `tests/test_logging_module.py`
- **Commit:** `refactor(45-01)` separate commit

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes. Both threat items from the plan's STRIDE register are addressed:
- T-45-01: `log_operation` `extra` contains only `operation` (caller constant), `duration_ms` (float), and optional `rows` (int) — no SQL text, params, DSNs, or credentials. Verified by `test_log_operation_extra`.
- T-45-02: Module attaches ONLY `NullHandler`, never calls `basicConfig()`. Verified by `test_module_does_not_call_basicconfig` (AST-walk scan).

## Known Stubs

None.

## Self-Check: PASSED

Files created/modified:
- `pycopg/logging.py` — FOUND
- `tests/test_logging_module.py` — FOUND
- `pycopg/base.py` — FOUND (Params + _decode_server_version added)
- `pycopg/__init__.py` — FOUND (IsolationLevel + Params in __all__)

Commits:
- `74ee1ac` — test(45-01): RED phase (failing tests)
- `27400b0` — feat(45-01): GREEN phase (logging.py implementation)
- `659a581` — feat(45-01): base.py + __init__.py additions
- `159fe67` — refactor(45-01): test file ruff cleanup
