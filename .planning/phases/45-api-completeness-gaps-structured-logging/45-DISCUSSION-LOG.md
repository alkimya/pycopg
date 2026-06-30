# Phase 45: API Completeness Gaps + Structured Logging - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-30
**Phase:** 45-API Completeness Gaps + Structured Logging
**Areas discussed:** Transaction/savepoint surface, health() semantics, Logging depth, Named-params shape

---

## Transaction / savepoint / isolation surface (TXN-01, TXN-02)

### IsolationLevel exposure

| Option | Description | Selected |
|--------|-------------|----------|
| Re-export under `pycopg.*` | Thin alias of psycopg's enum; `from pycopg import IsolationLevel`; accept the enum value | ✓ |
| Enum + case-insensitive string | Also accept `'serializable'` etc.; adds a string→enum mapping to freeze | |
| Pass psycopg enum through only | No re-export; leaks `from psycopg import IsolationLevel` onto callers | |

**User's choice:** Re-export under `pycopg.*`
**Notes:** Smallest frozen surface, zero new dep, no string-parsing to maintain under SemVer.

### Savepoint exposure

| Option | Description | Selected |
|--------|-------------|----------|
| Both: `savepoint()` CM + `transaction(savepoint_name=)` | Standalone CM AND kwarg; both delegate to native `conn.transaction(savepoint_name=)` | ✓ |
| Only standalone `db.savepoint()` | Drops the `transaction(savepoint_name=)` kwarg | |
| Only `transaction(savepoint_name=)` | No separate method; less discoverable | |

**User's choice:** Both — matches ROADMAP criterion #2 + REQUIREMENTS wording.

### isolation_level inside an active session

| Option | Description | Selected |
|--------|-------------|----------|
| `session()` sets it; `transaction(isolation_level=)` raises inside a session | Honest about psycopg's "no change mid-transaction" constraint | ✓ |
| `transaction(isolation_level=)` silently ignored in a session | No-op when session conn reused — a footgun | |
| You decide | Defer to research/planning | |

**User's choice:** Raise inside a session. **Notes:** Prefers an explicit error over silently dropping a requested isolation level.

---

## health() semantics (HEALTH-01)

### Failure behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Return `{connected: False, ...}`, never raise | Probe-friendly; usable in a healthcheck loop | ✓ |
| Raise on failure | Callers must wrap every call in try/except | |
| You decide | Defer | |

**User's choice:** Never raise.

### server_version format

| Option | Description | Selected |
|--------|-------------|----------|
| Human string `'16.1'` | Parsed from the int; readable in logs/dashboards | ✓ |
| Raw int `160001` | psycopg verbatim; callers decode MMmmpp | |
| Both keys | `server_version` + `server_version_num`; wider dict | |

**User's choice:** Human string `'16.1'`.

### Placement

| Option | Description | Selected |
|--------|-------------|----------|
| On all four classes; pooled variants add `pool_stats` | Database/AsyncDatabase + PooledDatabase/AsyncPooledDatabase (reuse `.stats()`) | ✓ |
| Only on Database/AsyncDatabase | "pool stats when pooled" criterion unmet | |
| You decide | Defer | |

**User's choice:** All four classes; pooled variants add `pool_stats`.

---

## Logging depth (LOG-01)

### Instrumentation depth

| Option | Description | Selected |
|--------|-------------|----------|
| Coarse ops only | `etl.run`, backup/restore, migrations, COPY/`from_dataframe`, `health` — NOT per-call `execute()`/fetch | ✓ |
| Broad, incl. `execute()`/`fetch_*` at DEBUG | Every query emits a record; per-call timing cost | |
| Opt-in helper only | Module exists, internals stay silent | |

**User's choice:** Coarse ops only — honors "key methods instrumented" without a query-path perf footprint.

### Standard extra={} fields

| Option | Description | Selected |
|--------|-------------|----------|
| `operation, duration_ms, rows` (when known) | Latency + volume without overcommitting the schema | ✓ |
| `operation, duration_ms` only | Minimal generic envelope | |
| `operation, duration_ms, rows, + status/error` | Wider field contract frozen at 1.0 | |

**User's choice:** `operation, duration_ms, rows`.

### Default level

| Option | Description | Selected |
|--------|-------------|----------|
| DEBUG (quiet by default) | Silent under NullHandler unless app opts in | ✓ |
| INFO | Louder by default — potential noise | |
| You decide | Defer | |

**User's choice:** DEBUG; existing WARNING sites stay.

---

## Named-params shape (PARAM-01)

### Annotation mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Shared public `pycopg.Params` alias | `Sequence \| Mapping[str, Any] \| None`, exported, applied across all five methods | ✓ |
| Inline-widen, no named alias | Union repeated ~5×, can drift | |
| You decide | Defer | |

**User's choice:** Shared public `pycopg.Params` alias.

### to_dataframe alignment

| Option | Description | Selected |
|--------|-------------|----------|
| Widen to the shared `Params` alias | Uniform surface; sequence params valid for SELECT too | ✓ |
| Keep `dict \| None` | Odd one out but already supports named params | |

**User's choice:** Widen `to_dataframe` to the shared `Params` alias.

---

## Claude's Discretion

- `latency_ms` measurement method (trivial `SELECT 1` round-trip, monotonic clock).
- Auto-generated savepoint `name` when `name=None` (psycopg auto-names).
- Internal mechanism for setting `conn.isolation_level` (per-call vs session connection), provided the raise-inside-session semantics hold.
- Placement of the `Params` alias + shared `log_operation` timing helper (`base.py`/`utils.py`).
- Exact `pool_stats` dict shape returned by pooled `health()`.

## Deferred Ideas

None — discussion stayed within phase scope. Broad per-`execute()` logging, a raw-int `server_version_num` key, and string→enum isolation coercion were considered and rejected in favor of the smaller frozen surface (available as non-breaking 1.x additions if ever wanted).
