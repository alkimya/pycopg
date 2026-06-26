"""Documented false-positive allowlist for the vulture dead-code scanner.

Run:
    uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80

This file is a *false-positive allowlist* (the term AUDIT-02 uses): each reference
below marks a name that vulture would otherwise report as unused, but which is
intentionally part of the public surface or otherwise reachable via dynamic access.

AUDIT-02 refinement (Phase 37 Plan 05): live scan ran against pycopg/ at
--min-confidence 80 and produced 13 findings, all confirmed false positives. Each
entry below documents why. No confirmed dead code was found — every finding is a
protocol-required or API-contract parameter.

Vulture processes this file via ast.parse() (not exec), so bare Name nodes here
are treated as "uses" of those names by the scanner.
"""

import pycopg.exceptions

# ── Public exceptions ──────────────────────────────────────────────────────────
# Exported in pycopg.__all__ for user-facing `except` clauses. vulture flags them
# as unused because they are rarely the *only* raise/catch point inside the library,
# but they are documented public API that library consumers catch.
#
# - ExtensionNotAvailable: raised by SpatialAccessor / TimescaleAccessor when the
#   required DB extension is absent.
# - TableNotFound: raised by SchemaAccessor.truncate_table (raise site added in
#   Plan 04, DEBT-05); and by AsyncSchemaAccessor.truncate_table.
# - InvalidIdentifier: raised by validate_identifiers() throughout the library.
# - DatabaseExists: raised by AdminAccessor.create_database.
pycopg.exceptions.ExtensionNotAvailable
pycopg.exceptions.TableNotFound
pycopg.exceptions.InvalidIdentifier
pycopg.exceptions.DatabaseExists

# ── Context-manager protocol parameters: exc_type, exc_val, exc_tb ────────────
# Python's context-manager protocol (PEP 343 / PEP 492) requires `__exit__` and
# `__aexit__` to accept exactly three exception-info arguments: exc_type, exc_val,
# exc_tb. The implementations in Database, AsyncDatabase, PooledDatabase, and
# AsyncPooledDatabase simply call close() and do not inspect the exception, so
# vulture flags the parameters as "unused variable" at 100% confidence. They cannot
# be removed (protocol violation) and renaming to `_*` is a style change not
# warranted here. Affected sites:
#   pycopg/database.py:1417      Database.__exit__
#   pycopg/async_database.py:1476  AsyncDatabase.__aexit__
#   pycopg/pool.py:250           PooledDatabase.__exit__
#   pycopg/pool.py:449           AsyncPooledDatabase.__aexit__
exc_type
exc_val
exc_tb

# ── load_dotenv fallback stub parameter: override ─────────────────────────────
# config.py defines a no-op `load_dotenv(dotenv_path=None, *, override: bool = False,
# **kwargs)` in the `except ImportError` branch when python-dotenv is absent. The
# `override` keyword argument mirrors the real python-dotenv API so callers using
# `load_dotenv(override=True)` work without error when dotenv is absent. The stub
# body is `pass`, so vulture flags `override` as unused at 100% confidence. The
# parameter must exist to preserve the API contract.
#   pycopg/config.py:20  load_dotenv fallback stub
override
