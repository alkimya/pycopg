# Phase 1: Bug Fixes & Foundation - Context

**Gathered:** 2026-02-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix 5 critical bugs (BUG-01 through BUG-05) in connection lifecycle, migration parsing, extension validation, and SRID inference. These bugs block async parity work in later phases. No new features — strictly fixing broken behavior and hardening existing code.

</domain>

<decisions>
## Implementation Decisions

### Error behavior
- SRID inference failure, extension-not-found errors, cleanup failures, transaction detection issues — Claude has full discretion on exception types, error messages, and whether to use custom exceptions vs standard ones
- Error message tone: Claude decides (technical vs approachable) based on what fits pycopg's existing patterns
- Cleanup error handling in session mode (original error vs chained): Claude's discretion

### Logging strategy
- Migration parser silent-skip → WARNING is required by roadmap
- Whether to audit and fix other silent-failure patterns: Claude's discretion
- Cleanup failure log level: Claude's discretion
- Extension validation happy-path logging: Claude's discretion
- Follow whatever logging pattern already exists in the codebase (investigate during research)

### Backwards compatibility
- v0.3.0 is a consolidation release — breaking changes are allowed
- User may have code depending on buggy behavior (e.g., SRID=4326 default) but hasn't checked — assume clean breaks are acceptable
- Claude decides per-fix whether to hard break, deprecation-warn, or provide migration path — evaluate each case individually
- Where to document behavior changes (code docstrings vs CHANGELOG only): Claude's discretion

### Validation scope
- TimescaleDB extension validation is required by roadmap
- Whether to also add PostGIS validation in this phase: Claude's discretion (evaluate scope fit)
- Validation timing (per-call vs cached): Claude's discretion
- Version checking vs existence-only: Claude's discretion
- Session mode transaction fix scope (just TransactionStatus vs also connection liveness): Claude's discretion

### Claude's Discretion
The user granted maximum autonomy across all four discussion areas. Claude has flexibility on:
- Exception types and error message design
- Logging levels and scope of logging fixes
- Breaking change strategy per bug fix
- Validation depth and timing
- Whether to extend fixes beyond the strict 5-bug scope when the same pattern applies

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. User trusts Claude's judgment on all implementation details for this phase.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-bug-fixes-foundation*
*Context gathered: 2026-02-11*
