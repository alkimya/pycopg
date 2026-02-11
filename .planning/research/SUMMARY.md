# Project Research Summary

**Project:** pycopg v0.3.0 Consolidation
**Domain:** Python Database Library (PostgreSQL/PostGIS/TimescaleDB)
**Researched:** 2026-02-11
**Confidence:** MEDIUM-HIGH

## Executive Summary

pycopg is a high-level Python database library providing DataFrame-first API, native PostGIS/TimescaleDB support, and built-in migrations. Research reveals v0.3.0 consolidation must address critical technical debt: 60% async/sync parity gap, missing resilience features (retry/backoff), and connection lifecycle leaks in session mode. The recommended approach is to achieve full API parity between Database and AsyncDatabase through parallel implementations (not abstraction layers), add production-grade error handling with retry policies, and strengthen test infrastructure with isolation patterns. This consolidation release lays the foundation for production readiness without requiring breaking changes to existing user code.

The key insight from architecture research is that pycopg's parallel sync/async implementation pattern (following psycopg3's design) is correct—the challenge is discipline in maintaining parity across 82+ methods. Testing infrastructure needs containerized PostgreSQL (testcontainers) for reliable integration tests and proper isolation patterns to prevent cascade failures. The biggest risk is incomplete async parity creating silent feature gaps that users discover at runtime—this can be mitigated through automated parity checking, explicit documentation of limitations, and NotImplementedError stubs with helpful messages.

Core recommendation: Structure v0.3.0 around 6 phases focusing on (1) API audit and parity documentation, (2) connection lifecycle robustness, (3) migration reliability, (4) retry/backoff resilience, (5) test infrastructure modernization, and (6) breaking change management. This ordering addresses critical stability issues first while enabling parallel feature development.

## Key Findings

### Recommended Stack

Current stack (psycopg3, SQLAlchemy 2, pandas 2, pytest) is solid for core operations. v0.3.0 consolidation requires incremental additions focused on testing infrastructure and resilience patterns. No major rewrites needed—most additions are non-breaking enhancements.

**Core technologies to add:**
- **testcontainers[postgres] 4.8.2**: Isolated PostgreSQL instances per test suite—industry standard for database integration testing, far superior to pytest-postgresql for complex scenarios
- **tenacity 9.0.0**: Declarative retry with exponential backoff—de facto standard for resilience, cleaner than custom implementations
- **pytest-asyncio 0.24.0**: Async test support with auto mode—required for AsyncDatabase testing, reduces boilerplate
- **pytest-xdist 3.6.1**: Parallel test execution—catches connection pool issues, verifies thread safety
- **mypy 1.13.0**: Static type checking—critical for library code, catches async type errors

**Critical version notes:** All versions from training data (Jan 2025), verify current versions with `pip index versions [package]` before implementation.

### Expected Features

pycopg's value proposition is high-level API without ORM complexity. Users expect production-grade resilience features alongside the unique DataFrame/PostGIS/TimescaleDB integrations.

**Must have (table stakes for v0.3.0):**
- Full async/sync parity (currently 40%, needs 60% more methods in AsyncDatabase)
- Retry policy with exponential backoff for transient connection errors
- Query timeout support (expose PostgreSQL statement_timeout)
- Named parameter support (`:name` syntax like SQLAlchemy, not just `%s`)
- Comprehensive structured logging (connection lifecycle, query execution, errors)
- Session mode robustness (fix cleanup leak at line 352 of database.py)
- Migration gap detection (validate sequence, detect deleted files)
- Extension pre-checks (all PostGIS/TimescaleDB methods validate extension exists)
- Connection health checks (validate pool connections before checkout)
- Error context improvements (migration errors include file path, line number)

**Should have (competitive differentiators):**
- DataFrame-first API (unique strength—expand to async, currently sync-only)
- TimescaleDB first-class support (hypertable, compression as native methods)
- PostGIS first-class support (GeoDataFrame round-trip without type guessing)
- Built-in migration system (zero-config, no Alembic complexity)
- COPY protocol helpers (optimized bulk insert, 10-100x faster than INSERT)
- Transaction isolation levels (SERIALIZABLE, READ COMMITTED control)
- Savepoint support (nested transactions)
- Result streaming for sync (async already has it, sync missing)

**Defer to v0.4.0+ (avoid scope creep):**
- ORM/model layer (duplicates SQLAlchemy, maintenance nightmare)
- Query builder/fluent API (never as good as SQLAlchemy Core)
- Schema diff/auto-migration (complex, error-prone)
- Multi-database support (pycopg is PostgreSQL-specific by design)
- Query result caching (application concern, not library responsibility)

### Architecture Approach

pycopg's architecture is appropriate for its scale: monolithic Database/AsyncDatabase classes with shared mixins for SQL generation. The parallel sync/async implementation pattern (separate classes, duplicated methods) is the correct choice despite code duplication—runtime abstraction layers would add complexity without benefit.

**Major components:**
1. **Database (sync, 2299 lines)** — Complete PostgreSQL operations API using psycopg.Connection
2. **AsyncDatabase (async, 768 lines)** — Async subset (needs ~43 additional methods for parity)
3. **Shared base layer** — DatabaseBase (factory methods), QueryMixin (SQL building), SessionMixin (connection reuse)
4. **Connection layer** — psycopg for DDL/admin, SQLAlchemy engine for DataFrame operations (lazy init)

**Critical architectural patterns:**
- **Parallel implementations over abstraction**: Maintain separate Database and AsyncDatabase, share only non-I/O logic through mixins
- **Connection-level retry**: Retry at connection acquisition, not per-method—keeps business logic clean
- **Session mode for batching**: Connection reuse critical for performance, but cleanup logic needs hardening
- **Three-tier testing**: Unit (mocked), integration (real DB), extension (PostGIS/TimescaleDB optional)

### Critical Pitfalls

Research identified 7 critical pitfalls based on codebase analysis and CONCERNS.md documentation. Top 5 must be addressed in v0.3.0:

1. **Incomplete async parity creates silent feature gaps** — Users discover missing methods at runtime, not import time. 60% of Database methods missing from AsyncDatabase. **Avoid by:** documenting divergence explicitly, adding NotImplementedError stubs with helpful messages, automated parity tests in CI

2. **Connection lifecycle leaks in session mode exception paths** — If `_session_conn.close()` raises exception (line 352), connection stays alive but reference lost. Connections accumulate, exhausting database limits. **Avoid by:** separate state tracking from resource cleanup, wrap close() in try/except that never reraises during cleanup, add connection timeout config

3. **Silent migration file skipping masks configuration errors** — `_get_migrations()` catches MigrationError and continues silently (lines 152-153). User creates `001-create_users.sql` (dash instead of underscore) but migration skipped without warning. **Avoid by:** log skipped files at WARNING level, add validation command, implement strict mode option

4. **Retry/backoff absence amplifies transient network errors** — Single transient connection error (network hiccup, database restart) causes entire operation to fail immediately. Long-running batch operations fail 90% complete. **Avoid by:** categorize exceptions (transient vs permanent), exponential backoff decorator with jitter, operation-level retry config, circuit breaker for permanent failures

5. **Real database testing without isolation causes cascade failures** — Tests against `pycopg_test` database without proper isolation. One test creates table, another assumes it doesn't exist. Parallel execution causes conflicts, CI randomly fails. **Avoid by:** per-test schema isolation with unique names, transaction rollback pattern where possible, fixture-based cleanup verification, parallel execution safety with pytest-xdist

**Additional pitfalls for Phase 6:**
6. **Breaking changes without migration path** — v0.3.0 changes strand users if no deprecation warnings, compatibility shims, or migration guide provided
7. **Mixing sync/async in event loop creates deadlocks** — Users call sync Database.execute() from async functions, thread blocks waiting for connection while callback needs event loop

## Implications for Roadmap

Based on combined research, v0.3.0 consolidation should be structured around **6 sequential phases** that build on each other. This ordering addresses critical stability issues first (async parity, connection leaks) before adding new features (retry, testing). Each phase delivers incremental value while avoiding the pitfall of "big bang" releases.

### Phase 1: API Audit & Async Parity Foundation
**Rationale:** Cannot add features to AsyncDatabase until we know what's missing. Documenting gaps unblocks parallel development of async methods.

**Delivers:**
- Complete API comparison matrix (Database vs AsyncDatabase methods)
- NotImplementedError stubs for all missing async methods with helpful messages
- Automated parity checking in CI (fails if method count diverges)
- Documentation section: "Sync vs Async API Differences"

**Addresses features:** Full async/sync parity (documentation phase), comprehensive logging (identify what needs instrumentation)

**Avoids pitfall:** #1 (Incomplete async parity creating silent feature gaps)

**Research needed:** No—this is audit work, patterns are clear

---

### Phase 2: Connection Lifecycle Robustness
**Rationale:** Connection leaks prevent long-running applications from being production-ready. Must fix before adding pooling or retry (both make leaks worse).

**Delivers:**
- Hardened session mode cleanup (guaranteed state reset even if close() fails)
- Connection timeout configuration (idle_in_transaction_session_timeout)
- Event loop detection in Database methods (warn if called from async context)
- Stress tests for session mode with exception injection
- Connection leak monitoring test utilities

**Addresses features:** Session mode robustness, connection health checks foundation

**Avoids pitfall:** #2 (Connection lifecycle leaks), #7 (Sync/async mixing deadlocks)

**Uses stack:** pytest-xdist for concurrent stress testing

**Research needed:** No—psycopg3 connection patterns are well-documented

---

### Phase 3: AsyncDatabase Method Parity
**Rationale:** With audit complete and connection lifecycle solid, systematically add missing async methods. Longest phase but enables all async use cases.

**Delivers:**
- 43 missing async methods implemented (DataFrame ops, backup/restore, admin, PostGIS, TimescaleDB)
- Async integration tests for all new methods
- DataFrame async patterns documented (workarounds for pandas sync-only limitation)
- All extension methods (PostGIS, TimescaleDB) check for extension existence before operations

**Addresses features:** Full async/sync parity (implementation), async DataFrame methods, async backup methods, extension pre-checks

**Avoids pitfall:** #1 (Complete async parity eliminates feature gaps)

**Uses stack:** pytest-asyncio for async test coverage, QueryMixin for shared SQL building

**Implements architecture:** Parallel async implementations following sync method patterns

**Research needed:** Minimal—each method follows established pattern. May need research for DataFrame async workarounds (pandas is sync-only).

---

### Phase 4: Retry/Backoff Resilience
**Rationale:** Production readiness requires transient error handling. Now that async parity exists, add retry to both Database and AsyncDatabase simultaneously.

**Delivers:**
- pycopg/retry.py module with RetryConfig, with_retry, with_async_retry decorators
- Exception categorization (transient vs permanent errors)
- Exponential backoff with jitter (prevents thundering herd)
- Query timeout support (expose statement_timeout in Config)
- Comprehensive logging integration (retry attempts, connection failures)
- Circuit breaker for repeated permanent failures

**Addresses features:** Retry policy with backoff, query timeout support, comprehensive logging, connection health checks

**Avoids pitfall:** #4 (Retry/backoff absence causing cascading failures from transient errors)

**Uses stack:** tenacity 9.0.0 for declarative retry logic (or custom implementation following researched pattern)

**Research needed:** No—retry patterns are standard. Verify tenacity integration or use custom decorator from STACK.md pattern.

---

### Phase 5: Migration Reliability & Test Infrastructure
**Rationale:** Migrations are critical for production deployments. Testing infrastructure enables confident iteration. Both can develop in parallel.

**Delivers:**
- Migration gap detection (validate sequence, detect deleted files, fail fast)
- Migration validation command (dry-run checker before apply)
- Logging for skipped migration files (WARNING level)
- Strict mode option (invalid filenames raise errors instead of silent skip)
- testcontainers integration for isolated test databases
- Per-test schema isolation fixtures
- Parallel test execution configuration (pytest-xdist)
- Transaction rollback test pattern
- Extension test markers (postgis, timescaledb)

**Addresses features:** Migration gap detection, error context improvements, extension pre-checks validation

**Avoids pitfall:** #3 (Silent migration skipping), #5 (Test isolation failures causing cascade)

**Uses stack:** testcontainers[postgres] for isolated DB, pytest-xdist for parallel execution, pytest-asyncio for async test fixtures

**Research needed:** No—migration validation is straightforward, testcontainers patterns well-documented

---

### Phase 6: Breaking Changes Management & Polish
**Rationale:** v0.3.0 can break APIs, but users need migration path. Final phase ensures upgrade experience is smooth.

**Delivers:**
- Deprecation warnings for any removed APIs (warnings.warn())
- Compatibility shims where feasible (old names as aliases)
- Migration guide in CHANGELOG (before/after examples)
- SRID validation enforcement (error on unknown CRS, never silent default)
- Named parameter support (`:name` syntax converts to `%s` internally)
- Transaction isolation level control
- Savepoint support (nested transactions)
- Sync result streaming (async already exists)

**Addresses features:** Named parameter support, transaction isolation levels, savepoint support, result streaming (sync), SRID validation

**Avoids pitfall:** #6 (Breaking changes without migration path stranding users)

**Uses stack:** Python warnings module, mypy for type hint compatibility checking

**Research needed:** Minimal—named parameter conversion is string manipulation, savepoints are native PostgreSQL

---

### Phase Ordering Rationale

**Why this sequence:**
1. **Audit before implementation**: Cannot fix async parity without knowing what's missing (Phase 1 → Phase 3)
2. **Stability before features**: Connection leaks make retry worse, fix first (Phase 2 before Phase 4)
3. **Parity before resilience**: Retry needs to work in both sync/async, requires parity (Phase 3 before Phase 4)
4. **Infrastructure enables iteration**: Testing improvements accelerate all other phases (Phase 5 can run parallel to Phase 3-4)
5. **Polish last**: Breaking changes and nice-to-haves only after core stability (Phase 6)

**Dependencies identified:**
- Phase 3 depends on Phase 1 (audit reveals what to implement)
- Phase 4 depends on Phase 3 (retry in both sync/async requires parity)
- Phase 5 can develop in parallel to Phase 3-4 (testing infrastructure is independent)
- Phase 6 depends on all previous phases (need stable foundation before API refinements)

**Avoiding pitfalls through ordering:**
- Phases 1-3 address async parity gap (pitfall #1) progressively: document → fix leaks → implement
- Phase 2 addresses connection leaks (pitfall #2) before adding features that worsen leaks
- Phase 5 addresses migration reliability (pitfall #3) and test isolation (pitfall #5) before heavy feature testing
- Phase 4 addresses retry absence (pitfall #4) after async parity complete
- Phase 6 addresses breaking changes (pitfall #6) last, with full context

### Research Flags

**Phases with standard patterns (skip deeper research):**
- **Phase 1:** Audit/documentation work, no implementation research needed
- **Phase 2:** psycopg3 connection patterns well-documented
- **Phase 4:** Retry patterns are standard across database libraries
- **Phase 5:** testcontainers and pytest patterns well-established
- **Phase 6:** Named parameters, savepoints are straightforward PostgreSQL features

**Phases needing targeted research during planning:**
- **Phase 3:** DataFrame async workarounds—pandas is fundamentally synchronous, may need research on async patterns or documentation on limitations. Not blocking, but worth 1-2 hours research.
- **Phase 4:** Verify tenacity library API if used (or validate custom retry implementation against psycopg3 error types)

**Overall research recommendation:** v0.3.0 consolidation does not require `/gsd:research-phase` during roadmap creation. Patterns are well-established, codebase structure is clear, and any uncertainties (DataFrame async) are small enough to handle during implementation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | testcontainers/tenacity recommendations solid, but version numbers from Jan 2025 training data—verify current versions before use |
| Features | HIGH | Feature expectations based on codebase analysis (CONCERNS.md) and established database library patterns (SQLAlchemy, asyncpg) |
| Architecture | HIGH | Direct codebase analysis (database.py, async_database.py), parallel implementation pattern validated by psycopg3 design |
| Pitfalls | HIGH | Based on actual bugs documented in CONCERNS.md plus standard Python async/database pitfalls from training data |

**Overall confidence:** MEDIUM-HIGH

Confidence is high on patterns, architecture, and known bugs. Confidence is medium on specific package versions (need verification) and some edge cases (DataFrame async patterns). All research was completed without web search, so recommendations should be validated against current documentation during implementation.

### Gaps to Address

Areas where research was constrained or needs validation during planning/execution:

- **Package versions**: All versions (testcontainers 4.8.2, tenacity 9.0.0, pytest-asyncio 0.24.0, pytest-xdist 3.6.1, mypy 1.13.0) from Jan 2025 training data. Verify current versions with `pip index versions [package]` before adding to pyproject.toml. Patterns are correct regardless of version.

- **DataFrame async patterns**: pandas and geopandas are synchronous libraries. AsyncDatabase may need to document limitations or use thread pool executor pattern for DataFrame operations. Research this specifically during Phase 3 planning—likely 1-2 hours to determine best approach (document limitation vs. run_in_executor wrapper).

- **PostgreSQL version compatibility**: Research assumes PostgreSQL 12-16. Verify specific feature compatibility (SRID handling, TimescaleDB version requirements) during Phase 3 implementation for PostGIS/TimescaleDB methods.

- **testcontainers CI integration**: Research recommends testcontainers for integration tests. Verify GitHub Actions Docker availability and performance during Phase 5. Fallback: use PostgreSQL service container if testcontainers too slow.

- **Breaking changes inventory**: Phase 6 requires identifying all breaking changes. During Phase 6 planning, audit git history and CONCERNS.md for any planned API changes and add deprecation warnings in advance.

## Sources

### Primary (HIGH confidence)
- **pycopg v0.2.0 codebase**: Direct analysis of database.py (2299 lines), async_database.py (768 lines), base.py (194 lines), migrations.py, pool.py, exceptions.py
- **.planning/codebase/CONCERNS.md**: Documented tech debt, known bugs (session cleanup leak line 352, migration skipping lines 152-153), async parity gaps
- **README.md**: Current feature set, API surface, usage examples
- **Python asyncio patterns**: Training data on async/await semantics, context managers, event loop management

### Secondary (MEDIUM confidence)
- **psycopg3 documentation patterns**: Connection lifecycle, async implementation, connection pooling—from training data, not live verification
- **Database library patterns**: SQLAlchemy 2.0, asyncpg 0.29, encode/databases 0.8 feature comparison—training data on standard resilience patterns (retry, timeout, health checks)
- **pytest-asyncio patterns**: Fixture design, event loop management, async test isolation—training data on testing patterns
- **testcontainers-python**: Docker PostgreSQL container management for integration testing—training data on usage patterns

### Tertiary (LOW confidence—needs verification)
- **Specific package versions**: All version numbers from Jan 2025 training cutoff, may not reflect current stable versions
- **DataFrame async workarounds**: pandas synchronous limitation acknowledged, but optimal async pattern needs validation during implementation
- **CI/CD patterns**: GitHub Actions with testcontainers from training data, actual performance unknown

### Research Constraints
- **No web search/WebFetch available**: All research from training data and codebase analysis
- **No Context7 library access**: Could not verify against external PostgreSQL/psycopg3 documentation
- **Version currency**: Training data cutoff January 2025, current 2026-02-11—package versions and best practices may have evolved

**Validation checklist for roadmap planning:**
1. Verify package versions: `pip index versions testcontainers tenacity pytest-asyncio pytest-xdist mypy`
2. Check psycopg3 docs for connection retry patterns (if available online during planning)
3. Research pandas async alternatives during Phase 3 planning (1-2 hours)
4. Test testcontainers performance in CI during Phase 5 (may need fallback)

---
*Research completed: 2026-02-11*
*Ready for roadmap: yes*
