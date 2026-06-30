# Phase 45: API Completeness Gaps + Structured Logging - Context

**Gathered:** 2026-06-30
**Status:** Ready for planning

<domain>
## Phase Boundary

The flat transactional core (`Database` / `AsyncDatabase`) gains four **purely additive**
capabilities, all sync/async at parity, **zero new runtime dependencies** (psycopg3 ≥3.1 /
psycopg_pool ≥3.2 native + stdlib `logging`):

1. **Transaction control (TXN-01, TXN-02)** — `db.transaction(isolation_level=, savepoint_name=)`,
   `db.session(isolation_level=)`, and a standalone `db.savepoint(name=None)` context manager.
2. **Named params (PARAM-01)** — accept a `dict` of `%(name)s` parameters on
   `execute`/`fetch_one`/`fetch_val`/`fetch_all`/`to_dataframe`. **Annotation + docs only** — psycopg3
   already binds `%(name)s` natively; there is NO `:name` translator.
3. **Health probe (HEALTH-01)** — `db.health()` (sync) / `await db.health()` (async) returning
   `{connected, latency_ms, server_version}`; pooled instances add `pool_stats`.
4. **Structured logging (LOG-01)** — new `pycopg/logging.py` (`get_logger`, `log_operation` context
   manager, `NullHandler` default); coarse instrumentation of key operations.

**In scope (locked by ROADMAP / REQUIREMENTS — not re-litigated):** the 5 requirements above.

**Out of scope (do NOT pull in):**
- `mypy --strict` blocking + `@overload` + py.typed completion (FREEZE-05, **Phase 46**). This phase
  produces clean, annotatable signatures (the new `Params` alias, kw-only params) so Phase 46's
  strict gate has good inputs — but does NOT raise the gate.
- Any Spatial v2 method (Phases 42–44, complete).
- Release mechanics / version bump / CHANGELOG (Phase 47).
- The ~14 deferred 1.x follow-ups (TSDB-F, ETL-INC-F, CRUD-F, INTRO-F) and raster — 1.x additive, not
  this milestone.

This phase is the **last** to add new method signatures before the Phase 46 type freeze, so every
signature here is effectively a 1.0-frozen public name.
</domain>

<decisions>
## Implementation Decisions

### Transaction control — isolation & savepoints (TXN-01, TXN-02)
- **D-01:** **Re-export `pycopg.IsolationLevel`** as a thin alias of psycopg's enum (NOT a copy) and
  export it in `__all__`, so callers do `from pycopg import IsolationLevel`. The kwarg accepts the
  enum value. No string→enum parser to freeze under SemVer (a string-coercion surface was explicitly
  rejected).
- **D-02:** Expose savepoints **two ways**: a standalone `db.savepoint(name=None)` context manager
  (creates a named savepoint, supports partial rollback to it without unwinding the outer txn) AND a
  `transaction(savepoint_name=...)` kwarg. Both delegate to psycopg's native
  `conn.transaction(savepoint_name=...)`. Matches ROADMAP criterion #2 + REQUIREMENTS wording.
- **D-03:** **Isolation × active session:** `session(isolation_level=)` sets the level for the whole
  session connection. Calling `transaction(isolation_level=)` while a `db.session()` is active
  **raises a clear error** (psycopg can only change isolation when no transaction is in progress on
  that connection; silently ignoring the requested level is a footgun). Outside a session,
  `transaction(isolation_level=)` sets it on the fresh per-call connection.
- **D-04:** All new optional params (`isolation_level=`, `savepoint_name=`, savepoint `name=`) are
  **keyword-only** per the Phase 41 Stable API Contract (D-03/D-04) — required args positional, every
  optional/defaulted param keyword-only. Ships as a clean addition at the 0.x→1.0 boundary; no
  positional shim.

### Health probe (HEALTH-01)
- **D-05:** **`health()` never raises.** On a dead/unreachable connection it catches the error and
  returns `{connected: False, latency_ms: None, server_version: None, error: <str>}`. A monitoring
  probe that throws is unusable in a healthcheck loop.
- **D-06:** **`server_version` is a human dotted string** (`'16.1'`), parsed from psycopg's
  `conn.info.server_version` int (`160001`). (If a follow-up wants the raw int it can be added 1.x —
  not now.)
- **D-07:** **`health()` lives on all four classes** — `Database` + `AsyncDatabase`
  (`connected`/`latency_ms`/`server_version`) AND `PooledDatabase` + `AsyncPooledDatabase`, where it
  additionally returns a `pool_stats` key sourced from the **existing** `.stats()`
  (`pool.py:200` sync / `pool.py:423` async). Satisfies "pooled instances include pool stats."

### Structured logging (LOG-01)
- **D-08:** New `pycopg/logging.py` with `get_logger()` (returns the `pycopg` library logger) and a
  `log_operation` context manager. Stdlib `logging` only, **`NullHandler` attached by default** — the
  library is silent unless the application opts in. No structlog / no framework dep (library rule:
  callers own the logging stack).
- **D-09:** **Coarse instrumentation only.** Wrap the meaningful, already-non-trivial operations in
  `log_operation`: `etl.run`, `backup`/`restore`, `migrations`, COPY paths (`from_dataframe` /
  `from_geodataframe`), and `health`. **Do NOT** wrap per-call `execute()` / `fetch_*` in the query
  hot path (no per-query timing cost; no instrumentation site on every query to freeze).
- **D-10:** `log_operation` emits `extra={operation, duration_ms, rows}` — `operation` name +
  elapsed ms always; `rows` (affected/returned) when the wrapped op exposes a count. Records emit at
  **DEBUG**; existing WARNING sites (e.g. session-close-after-commit-failure) stay as-is.

### Named params (PARAM-01)
- **D-11:** Introduce a **shared public type alias `pycopg.Params = Sequence | Mapping[str, Any] |
  None`**, export it in `__all__`, and apply it to `execute`/`fetch_one`/`fetch_val`/`fetch_all`
  **and** widen `to_dataframe` (currently `dict | None`) to it. One frozen symbol, mypy-strict
  friendly, self-documenting.
- **D-12:** **Docs/annotation only — NO parser.** psycopg3 binds `%(name)s` from a `Mapping`
  natively. The deliverable is the widened annotation + docstring examples + tests confirming dict
  params on all five methods. The research's stray `_rewrite_named_params()` (SUMMARY §84)
  **contradicts the locked decision and must NOT be built** (REQUIREMENTS L51, SUMMARY L36/167).

### Claude's Discretion
- Exact `latency_ms` measurement (round-trip of a trivial `SELECT 1`, monotonic clock) — left to
  research/planning, documented + tested.
- Default/auto-generated savepoint `name` when `name=None` (psycopg auto-names if omitted) — pick the
  cleanest psycopg-native behavior.
- Internal mechanism for setting `conn.isolation_level` on the per-call connection vs the session
  connection — provided D-03 semantics hold.
- Precise placement of the `Params` alias definition (likely `base.py` or `utils.py`) and which
  module owns the shared `log_operation` timing helper.
- Exact `pool_stats` dict shape returned by pooled `health()` (reuse `.stats()` verbatim vs subset).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & requirements
- `.planning/REQUIREMENTS.md` §TXN-01, §TXN-02, §PARAM-01, §HEALTH-01, §LOG-01 (lines 46–53) — the
  5 locked requirements this phase satisfies; lines 137–141 traceability rows.
- `.planning/REQUIREMENTS.md` "Explicitly rejected" table — line 108 (`:name` translator rejected →
  native `%(name)s`) + line 110 (structlog/framework dep rejected → stdlib `logging` + `NullHandler`).
  These are the two locks that bound D-08/D-12.
- `.planning/ROADMAP.md` "Phase 45: API Completeness Gaps + Structured Logging" — goal + 5 success
  criteria (the acceptance contract).

### Research (HIGH confidence, this milestone)
- `.planning/research/SUMMARY.md` §"Phase 45" (lines 159–167) + §"Stack" (lines 20–24, 36) +
  §"Architecture/files touched" (lines 84–91) — psycopg ≥3.1 (`IsolationLevel`,
  `transaction(savepoint_name=)`, native `%(name)s`) + psycopg_pool ≥3.2 (`check()`, `get_stats()`)
  cover the entire feature set with zero new runtime deps. **NOTE the internal contradiction:** L84
  mentions `_rewrite_named_params()` but L36/167 (and REQUIREMENTS L51) lock annotation-only/no
  translator — the lock wins (D-12).
- `.planning/research/PITFALLS.md` — "logging before mypy-strict" risk (L197): `extra={}` dict args
  may need annotations Phase 46 will flag → keep `log_operation` cleanly typed now. Also the recurring
  "validate_identifiers silently dropped in a rewrite" lesson (acceptance = per-builder injection
  test) — relevant if any new builder/SQL is introduced (none expected this phase).
- `.planning/research/FEATURES.md`, `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`
  — feature-level + version-floor detail for the four gaps.

### Source to modify (sync + async parity required on every change)
- `pycopg/database.py` — `transaction()` (line ~507), `session()` (line ~528), `in_session` property
  (~584); add `health()`; widen `execute`/`fetch_one`/`fetch_val`/`fetch_all`/`to_dataframe` params.
- `pycopg/async_database.py` — async mirrors: `session()` (~516), `transaction()` (~581),
  `in_session` (~570); add async `health()`; same param widening. `test_accessor_parity` enforces 1:1.
- `pycopg/pool.py` — `PooledDatabase.stats()` (line 200) + `AsyncPooledDatabase.stats()` (line 423)
  are the existing source for the `pool_stats` key; add `health()` to both pooled classes (D-07).
- `pycopg/logging.py` — **NEW** module (`get_logger`, `log_operation`, `NullHandler` default).
- `pycopg/__init__.py` — export `IsolationLevel` (D-01) and `Params` (D-11) in `__all__`; existing
  per-module `logger = logging.getLogger(__name__)` (database.py:40, async_database.py:39,
  migrations.py:18) should be reconciled with the new `get_logger()` convention.
- `pycopg/base.py` / `pycopg/utils.py` — likely home for the shared `Params` alias + timing helper.

### Codebase maps (consult during planning)
- `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/ARCHITECTURE.md`,
  `.planning/codebase/STRUCTURE.md` — flat-core vs accessor split; sync/async mirror convention.

### Prior phase context (mechanism this phase must honor)
- `.planning/phases/41-api-homogenization/41-CONTEXT.md` §D-03/D-04 — the kw-only Stable API Contract
  (required positional / optional keyword-only, clean 0.x→1.0 break) that D-04 above inherits.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PooledDatabase.stats()` / `AsyncPooledDatabase.stats()` (`pool.py:200`, `pool.py:423`) already
  return `{pool_size, pool_available, requests_waiting, requests_num}` from `pool.get_stats()` — reuse
  verbatim as the `pool_stats` value in pooled `health()` (D-07). No new pool plumbing.
- `transaction()` already branches on `self._session_conn` (reuse-session vs fresh-connect) in both
  classes — the natural choke point to add `isolation_level=`/`savepoint_name=` and the
  raise-inside-session guard (D-03).
- Existing per-module `logging.getLogger(__name__)` (database.py:40, async_database.py:39,
  migrations.py:18) — establishes that pycopg already uses stdlib logging; `pycopg/logging.py`
  consolidates this into a single `get_logger()` + the `NullHandler` default.
- `to_dataframe` already accepts `dict | None` params (database.py:1373) — proves `%(name)s` already
  works end-to-end; PARAM-01 is widening the *other* methods to match, not new behavior.

### Established Patterns
- Pure-builder + thin-accessor split; sync `Database` (~database.py) and async `AsyncDatabase`
  (~async_database.py) are 1:1 mirrors enforced by `test_accessor_parity` — every method added here
  lands on both, identical signature.
- kw-only enforcement (Phase 41 D-03): new optional params get `*` in the signature.
- Coverage ratchet ≥95% (measured baseline ~96.18% at Phase 44); `# pragma: no cover` only with an
  em-dash justification.
- `-W error::DeprecationWarning` CI gate is green and must stay green — no internal pycopg code may
  route through a deprecated path (relevant: don't touch the deprecated `where=` spatial alias here).

### Integration Points
- New public symbols `IsolationLevel` + `Params` enter `__all__` and become 1.0-frozen names.
- `pycopg/logging.py` is shared by sync and async paths — `log_operation` must be sync-callable; for
  async ops it wraps the awaited body (timing brackets the `await`), not a per-row inner loop.
- Docs surfaces to update (Phase 47 release-doc territory, but the method docstrings + an `api-reference`
  / guide section land here): named-params `%(name)s` examples, `health()` return shape,
  isolation/savepoint usage, a logging how-to. `interrogate` 100% + Sphinx `-W` gates apply.
</code_context>

<specifics>
## Specific Ideas

- Strong project framing throughout: this is the **last big milestone**, API frozen at 1.0 under
  SemVer — so prefer the smaller, cleaner frozen surface at every fork (re-export over copy, no string
  coercion, no translator, coarse logging over broad).
- The user consistently chose the "honest about the constraint" option (raise on isolation-in-session
  rather than silently ignore) and the "monitoring-friendly" option (health never raises) — apply that
  judgment to the Claude's-Discretion items too.
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Broad per-`execute()` logging instrumentation, a raw-int
`server_version_num` key, and a string→enum isolation coercion were each considered and rejected in
favor of the smaller frozen surface; they remain available as non-breaking 1.x additions if ever
wanted, but are NOT scheduled.)

</deferred>

---

*Phase: 45-API Completeness Gaps + Structured Logging*
*Context gathered: 2026-06-30*
