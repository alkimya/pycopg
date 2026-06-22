# Phase 30: Chunk Management & Partitioning - Context

**Gathered:** 2026-06-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver four TimescaleDB 2.x management methods on **both** `db.timescale.*` (sync) and
`async_db.timescale.*` (async), using the established pure-builder + `validate_identifiers` +
`%s`-params + lazy-accessor + sync/async-parity contract:

- `show_chunks(table, older_than=None, newer_than=None, schema="public")` → `list[str]`
- `drop_chunks(table, older_than=None, newer_than=None, schema="public", dry_run=False)` → `list[str]`
- `add_dimension(table, column, partition_type="hash", number_partitions=None, chunk_interval=None, schema="public", if_not_exists=True)`
- `add_reorder_policy(table, index_name, schema="public", if_not_exists=True)`

These are the four pure-builder methods of the milestone — **no autocommit seam, no new connection
management** (that's Phase 31's CAGG work). All use the standard `self._db.execute()` path.

**In scope:** the 4 methods (sync+async), their guards/validation, `dry_run` preview, the
`ValueError`/`TimescaleError` safety raises, and `test_accessor_parity` coverage.

**Out of scope (other phases / deferred):** continuous aggregates (Phase 31), `time_bucket`/
`time_bucket_gapfill` query helpers (Phase 32), and the deferred TSDB-F01–F04 follow-ups
(per-chunk compress/decompress, `created_before`/`created_after` physical-time filters,
`time_bucket origin/offset`).
</domain>

<decisions>
## Implementation Decisions

### Chunk bound value types (`older_than` / `newer_than`)
- **D-01:** Accept **`str | datetime | None`** for both `older_than` and `newer_than` on
  `show_chunks` and `drop_chunks`. A `str` is treated as a relative interval (`"30 days"`); a
  `datetime`/`date` is treated as an absolute cutoff. Matches native TimescaleDB behavior
  (both forms are valid for `show_chunks`/`drop_chunks`). Type hint: `str | datetime | None`.
- **D-02:** The pure builder **branches on Python type to choose the SQL cast** so TimescaleDB
  receives the correctly-typed argument:
  - `str` bound → emit `%s::interval` (a plain `%s` interval string arrives as `text` and errors)
  - `datetime` bound → emit bare `%s` (psycopg 3 adapts `datetime` to `timestamptz`)
  Each **non-None** bound contributes exactly one `%s` arg + its cast; `None` bounds are omitted
  from the call entirely. Both-`None` is allowed for `show_chunks` (lists all chunks) but **forbidden
  for `drop_chunks`** — see D-03.

### Chunk return shape & ordering
- **D-03 (safety, from REQ TS-ADV-05):** `drop_chunks` raises **`ValueError` when both bounds are
  `None`** — *before any DB round-trip* (prevents full-table wipe). `dry_run=True` previews via
  `show_chunks` (or the same builder) and returns the would-be-dropped list **without deleting**.
  Docstring Notes mark `drop_chunks` **DESTRUCTIVE / IRREVERSIBLE**.
- **D-04:** Both methods return a **`list[str]` of fully-qualified chunk names**
  (`_timescaledb_internal._hyper_1_2_chunk`), schema-qualified and copy-paste usable in raw SQL.
  `drop_chunks` (and its `dry_run` preview) returns the **identical shape** to `show_chunks`.
- **D-05:** The returned list is **sorted oldest-first by chunk time range** (ascending
  `range_start`), not by native function order and not lexicographically (`_hyper_1_10` must not
  sort before `_hyper_1_2`). This likely means `show_chunks` cannot rely on the bare
  `show_chunks()` SRF output alone — it must order by the chunk's range. **Researcher: confirm the
  exact mechanism** (e.g. wrap/join against `timescaledb_information.chunks` for `range_start`, or
  order the SRF output by a range expression) and the precise regclass→text rendering on TSDB 2.28.

### `add_dimension` form & non-empty-hypertable error
- **D-06:** Local/CI TimescaleDB is **2.28.0** (verified: `SELECT extversion FROM pg_extension
  WHERE extname='timescaledb'` → `2.28.0`; available default also `2.28.0`). This is **well above
  2.13**, so `add_dimension` uses the **modern `by_hash` / `by_range` form** — exactly what REQ
  TS-ADV-08 specifies. No pre-2.13 positional-keyword fallback is needed. The pre-2.13 form is
  explicitly NOT supported (per milestone "2.x floor, 1.x shims out of scope").
- **D-07:** Construction-time **`ValueError`** enforces hash↔`number_partitions` /
  range↔`chunk_interval` mutual exclusivity (`partition_type="hash"` requires `number_partitions`,
  forbids `chunk_interval`; `partition_type="range"` requires `chunk_interval`, forbids
  `number_partitions`) — raised before any DB round-trip.
- **D-08:** On a **non-empty hypertable**, `add_dimension` surfaces a **clear pycopg-domain error**
  (REQ TS-ADV-08 success criterion). Approach: **attempt the DDL, catch psycopg's failure,
  re-raise as `TimescaleError`** — no extra pre-check round-trip.
- **D-09:** Add **`class TimescaleError(PycopgError)`** to `pycopg/exceptions.py` — a **milestone-wide**
  TimescaleDB-domain error intended for reuse across Phases 31–32 (cagg lifecycle, etc.), not a
  single-use `HypertableNotEmpty`. This means **Phase 30 touches a third file**: `exceptions.py`
  (in addition to `timescale.py` + `queries.py`). Note this is an intentional, expected addition —
  the milestone plan's "only timescale.py + queries.py" assumption is superseded by this decision.

### Test placement & fixtures
- **D-10:** Create a **new `tests/test_timescale.py`** to host all v0.8.0 advanced-TSDB live-DB
  integration tests (sync + async), porting the **`ts_db` skip-fixture** pattern from
  `tests/test_database_integration.py::TestDatabaseTimescaleCoverage` (create-extension-or-skip).
  Phases 31–32 extend the same file. The existing v0.6.0 basic-TSDB tests stay where they are
  (do not move them).
- **D-11:** Two test layers already exist and both continue: **mock-based SQL-shape unit tests**
  (async, `mock_schema.has_extension` style as in `tests/test_async_database.py`) assert generated
  SQL without a live DB; **live-DB integration tests** (gated by the `ts_db`/async-equivalent skip
  fixture) confirm real chunk listing/dropping, dimension registration, and the reorder-policy job
  row. `asyncio_mode = "auto"` is already set, so async tests need no per-test marker.

### Claude's Discretion
- Exact `queries.py` constant names (research SUMMARY suggests `TSDB_SHOW_CHUNKS`,
  `TSDB_DROP_CHUNKS`) and whether `drop_chunks`' preview re-invokes `show_chunks` vs shares an
  internal builder — planner's call, as long as D-04/D-05 shapes hold.
- The precise `TimescaleError` message wording for the non-empty-hypertable case.
- Whether `add_reorder_policy` / `add_dimension` need any `validate_interval` on `chunk_interval`
  (consistent with existing `validate_interval` usage on intervals elsewhere in `timescale.py`).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` — TS-ADV-04/05/08/09 verbatim signatures + the baked safety
  criteria (drop_chunks dry_run/ValueError; add_dimension `by_hash`/`by_range` + mutual-exclusivity)
- `.planning/ROADMAP.md` §"Phase 30: Chunk Management & Partitioning" — goal + 5 success criteria

### Research (project-level, HIGH confidence, already done)
- `.planning/research/SUMMARY.md` — 9-method overview; Phase 30 = "Pure-builder chunk + partitioning"
  (§"Phase 30"); confirms no autocommit seam, async-guard `await` audit, `dry_run` guard
- `.planning/research/PITFALLS.md` — pitfalls 3 (drop_chunks destructive), 4 (add_dimension empty
  hypertable + version), 5 (async guard `await` omission), 6 (policy tests use `CALL run_job()`,
  no sleep)
- `.planning/research/FEATURES.md`, `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`

### Codebase patterns to mirror
- `pycopg/timescale.py` — existing `TimescaleAccessor`/`AsyncTimescaleAccessor`; mirror the
  per-method `has_extension("timescaledb")` guard (**async must `await`** it), `validate_identifiers`,
  and the `self._db.execute(...)` pure-builder body
- `pycopg/queries.py` — where the new SQL constants go (alongside `LIST_HYPERTABLES`,
  `HYPERTABLE_INFO`)
- `pycopg/exceptions.py` — `PycopgError` base + existing subclasses; add `TimescaleError` here (D-09)
- `pycopg/utils.py` — `validate_identifier`/`validate_identifiers`/`validate_interval` (lines 78/107/125)
- `tests/test_parity.py` §`ACCESSOR_PAIRS` (line 24) — `(TimescaleAccessor, AsyncTimescaleAccessor)`
  already registered; `test_accessor_parity` (line 35) enforces TS-ADV-10 with **no registry change**
- `tests/test_database_integration.py::TestDatabaseTimescaleCoverage` (line 836) — `ts_db`
  skip-fixture (line 839) + live-DB test pattern to port into the new `tests/test_timescale.py`
- `tests/test_async_database.py` (line ~2334) — mock-`has_extension` SQL-shape async unit-test pattern
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`validate_identifiers` / `validate_interval` (`pycopg/utils.py`):** validate `table`, `schema`,
  `column`, `index_name`; validate `chunk_interval` interval strings.
- **`ts_db` skip-fixture (`tests/test_database_integration.py:839`):** create-extension-or-skip
  guard to port into `tests/test_timescale.py`.
- **`ACCESSOR_PAIRS` + `test_accessor_parity` (`tests/test_parity.py`):** timescale pair already
  registered — adding the 4 methods to both classes auto-satisfies TS-ADV-10 parity.
- **`self._db.execute(sql, params)` path:** standard execute with `%s` params (no `connect()`
  autocommit seam needed for any Phase 30 method).

### Established Patterns
- **Per-method extension guard** raising `ExtensionNotAvailable` (sync) / `await ... ExtensionNotAvailable`
  (async). The async `await` omission is the recurring Phase 23 gotcha — audit every async method.
- **Pure-builder:** identifiers validated + interpolated; runtime VALUES bound as `%s`. Phase 30's
  twist: `older_than`/`newer_than` need a **type-driven cast** (`%s::interval` vs bare `%s`) — D-02.
- **`exceptions.py` PycopgError hierarchy:** `TimescaleError(PycopgError)` slots in alongside
  `ExtensionNotAvailable`, `TableNotFound`, etc.

### Integration Points
- New SQL constants → `pycopg/queries.py`; new methods → both classes in `pycopg/timescale.py`;
  new exception → `pycopg/exceptions.py`; new tests → `tests/test_timescale.py`. No other files.
- `db.timescale` / `async_db.timescale` lazy accessors already wired (v0.6.0) — methods just appear.
</code_context>

<specifics>
## Specific Ideas

- `show_chunks`/`drop_chunks` return value must be **sorted oldest-first** and **fully-qualified**
  so a user can `show_chunks` → inspect → feed names straight into raw SQL or reasoning about
  retention. Tests should assert this ordering, not just membership.
- `add_dimension` should feel like the modern TSDB API (`by_hash`/`by_range`), not the legacy
  positional form — local server is 2.28.0 so there's no reason to hedge.
</specifics>

<deferred>
## Deferred Ideas

- **`show_chunks` `created_before` / `created_after`** physical-time filters → TSDB-F04 (deferred,
  rarely needed). Phase 30 only does `older_than`/`newer_than` partition-range filters.
- **Per-chunk `compress_chunk` / `decompress_chunk`** → TSDB-F03 (deferred, advanced operational).
- **Continuous-aggregate lifecycle, `time_bucket`/`gapfill` helpers** → Phases 31/32 (in milestone,
  not this phase).

None of these came up as scope-creep requests — listed only to mark the boundary explicitly.
</deferred>

---

*Phase: 30-Chunk Management & Partitioning*
*Context gathered: 2026-06-22*
