"""Documented false-positive allowlist for the vulture dead-code scanner.

Run:
    uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80

This file is a *false-positive allowlist* (the term AUDIT-02 uses): each reference
below marks a name that vulture would otherwise report as unused, but which is
intentionally part of the public surface or otherwise reachable via dynamic access.

This is the SEED allowlist. Plan 05 refines it against the live vulture scan — do
NOT add any entry here that is not a confirmed false positive; the scan-driven
refinement is owned by Plan 05.
"""

import pycopg.exceptions

# Public exceptions — exported in pycopg.__all__ for user-facing `except` clauses.
# vulture flags them as unused because they have no internal raise site, but they
# are part of the documented public API and may be caught by library consumers.
#
# Note: `TableNotFound` gains an internal raise site in Plan 04 (DEBT-05, in
# SchemaAccessor.truncate_table); the other three remain user-facing-only by design.
pycopg.exceptions.ExtensionNotAvailable
pycopg.exceptions.TableNotFound
pycopg.exceptions.InvalidIdentifier
pycopg.exceptions.DatabaseExists
