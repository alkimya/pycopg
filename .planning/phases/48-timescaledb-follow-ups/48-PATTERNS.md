# Phase 48: TimescaleDB Follow-ups - Pattern Map

**Mapped:** 2026-07-02
**Files analyzed:** 3 modified (no new files) — `pycopg/timescale.py`, `tests/test_timescale.py`, `tests/test_parity.py`
**Analogs found:** 5 / 5 surfaces

This phase is pure additive-by-analogy: every new method/param has a direct, shipped exemplar
already in `pycopg/timescale.py`. Both sync (`TimescaleAccessor`, from line 329) and async
(`AsyncTimescaleAccessor`, from line 1475) classes must be edited in the same commit — the async
class mirrors the sync class 1268 lines later with `async def` / `await` added (verify by
grepping the same method name at `+1268` offset before considering a method "done").

## File Classification

| Surface (all land in existing files) | Role | Data Flow | Closest Analog | Match Quality |
|---------------------------------------|------|-----------|-----------------|----------------|
| `drop_continuous_aggregate` (new method, both classes) | service/accessor method | request-response (DDL) | `add_reorder_policy` (timescale.py:879) for plain-execute+guard shape; `drop_chunks` (timescale.py:646) for IF EXISTS/destructive-op idiom | exact (role+flow) |
| `remove_continuous_aggregate_policy` (new method, both classes) | service/accessor method | request-response (SELECT function call) | `add_continuous_aggregate_policy` (timescale.py:1094) — naming/pairing sibling, identical plain-execute pattern | exact |
| `time_bucket` origin/offset params (extend existing method + builder) | service/accessor method (param extension) | request-response (CRUD query) | `_build_time_bucket_sql` (timescale.py:214) itself — extend in place; guard style from `drop_chunks` both-None guard (timescale.py:701) | exact (same function) |
| `compress_chunk` / `decompress_chunk` (new methods, both classes) | service/accessor method | request-response (SELECT function call, bound value) | `enable_compression` (timescale.py:400) for None-return + guard convention; `add_compression_policy` (timescale.py:455) for plain execute | exact |
| F04 `newer_than`-datetime test (optional, symmetry-only) | test | — | `test_show_chunks_sql_shape_datetime_older_than` (tests/test_timescale.py:159) | exact (mirror, swap field) |
| `TestDropContinuousAggregateMock` / `TestRemoveContinuousAggregatePolicyMock` / `TestCompressChunkMock` / `TestDecompressChunkMock` (new test classes) | test | mock SQL-shape | `TestShowChunksMock` (tests/test_timescale.py:115) + `TestDropChunksMock` (tests/test_timescale.py:273) | exact |
| `test_timescale_v110_surface` (new frozenset test) | test | — | `test_timescale_v080_surface` (tests/test_parity.py:64) | exact |

## Pattern Assignments

### `drop_continuous_aggregate(view_name, *, cascade=False, if_exists=False, schema="public")` (new, both classes)

**Analog:** `pycopg/timescale.py:879-925` (`add_reorder_policy`) for the guard-order + plain-execute
shape, `pycopg/timescale.py:646-741` (`drop_chunks`) for the destructive-op / IF-EXISTS idiom.

**Imports** — already present at module top (timescale.py:14-30); no new imports needed:
```python
from pycopg.exceptions import ExtensionNotAvailableError, TimescaleError
from pycopg.utils import validate_identifier, validate_identifiers, validate_interval
```

**Guard order pattern** (mirror `add_reorder_policy`, timescale.py:914-920):
```python
if not self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailableError(
        "TimescaleDB extension not installed. "
        "Run db.schema.create_extension('timescaledb')"
    )

validate_identifiers(table, schema, index_name)
```
Note: research (RESEARCH.md D-05 resolution) directs `validate_identifiers` line-1-of-builder
per the standing bar — since `has_extension` is itself a metadata round-trip (not the gated
call), either guard-then-validate or validate-then-guard order is acceptable; existing
`add_reorder_policy` does extension-check first, `drop_chunks` does the ValueError guard first
then extension-check then `validate_identifiers`. Follow `drop_chunks`'s ordering for
`drop_continuous_aggregate` since it is also destructive: no Python-level guard needed here
(no both-None case), so: `validate_identifiers` → `has_extension` check → build+execute.

**Core plain-execute + flag-literal pattern** (mirror `add_reorder_policy`, timescale.py:922-925):
```python
ne = ", if_not_exists => true" if if_not_exists else ""
self._db.execute(
    f"SELECT add_reorder_policy('{schema}.{table}', '{index_name}'{ne}) AS job_id"
)
```
Apply identically for the DROP DDL (per RESEARCH.md Code Examples §F01, confirmed plain
transaction-safe — NOT the autocommit seam):
```python
ie = "IF EXISTS " if if_exists else ""
cas = " CASCADE" if cascade else ""
self._db.execute(f"DROP MATERIALIZED VIEW {ie}{schema}.{view_name}{cas}")
```

**Docstring convention** — mirror `drop_chunks`'s `Notes` section (timescale.py:695-699) for the
`.. note::`-style DESTRUCTIVE callout, and `add_reorder_policy`'s `Raises` block (timescale.py:905-912)
for the `ExtensionNotAvailableError` / `FeatureNotSupported` dual-raise documentation (F01's DROP
itself is NOT license-gated per research D-05, but the accompanying `remove_continuous_aggregate_policy`
and any pre-existing cagg on the target view could still surface license errors from other
operations — keep the standard `Raises` shape for consistency even if this particular DDL is
Apache-safe).

**Async mirror location:** `pycopg/timescale.py` async `AsyncTimescaleAccessor` class starts at
line 1475; `add_reorder_policy` async twin is at line 2018 (offset +1139 from sync at 879). Add
`drop_continuous_aggregate`/`remove_continuous_aggregate_policy` as `async def` with `await
self._db.schema.has_extension(...)` and `await self._db.execute(...)` — same body shape, only
`async`/`await` added.

---

### `remove_continuous_aggregate_policy(view_name, *, if_exists=True, schema="public")` (new, both classes)

**Analog:** `pycopg/timescale.py:1094-1178` (`add_continuous_aggregate_policy`) — direct naming
pair, identical plain-execute pattern (confirmed transaction-safe by RESEARCH.md D-01 doc-comment
at timescale.py:1108-1110).

**Core pattern** (mirror the docstring's own note at timescale.py:1107-1110):
```python
# "Uses a plain self._db.execute call (D-01 — transaction-safe, like
#  add_reorder_policy / add_compression_policy / add_retention_policy; NOT the autocommit seam.)"
```
Apply the identical idiom for the new method (per RESEARCH.md D-11-resolved SQL, using the
CURRENT `if_exists` param name — NOT the deprecated `if_not_exists`):
```python
ie = "true" if if_exists else "false"
self._db.execute(
    f"SELECT remove_continuous_aggregate_policy("
    f"'{schema}.{view_name}', if_exists => {ie})"
)
```
**Critical pitfall (RESEARCH.md Pitfall 1):** bind by name, never positionally; assert
`"if_exists =>"` in generated SQL, never `"if_not_exists =>"` — the latter is the deprecated
TSDB pre-2.8 parameter name still accepted for back-compat but wrong for new code.

---

### `time_bucket` — `origin`/`offset` extension (extend `_build_time_bucket_sql`, both classes)

**Analog:** `pycopg/timescale.py:214-262` (`_build_time_bucket_sql`) — extend the SAME function in
place (not a new builder). Guard style mirrors `drop_chunks`'s both-None ValueError
(timescale.py:701-706).

**Current builder to extend** (timescale.py:214-262, full text already in context above):
```python
def _build_time_bucket_sql(
    table: str,
    time_column: str,
    bucket_width: str,
    aggregates: str,
    where: str | None = None,
    schema: str = "public",
) -> tuple[str, list[Any]]:
    validate_identifiers(table, schema, time_column)
    sql = (
        f"SELECT time_bucket(%s, {time_column}) AS bucket, {aggregates} "
        f"FROM {schema}.{table}"
    )
    if where is not None:
        sql += f" WHERE {where}"
    sql += " GROUP BY bucket ORDER BY bucket"
    return sql, [bucket_width]
```

**Guard-before-DB pattern to mirror** (`drop_chunks`, timescale.py:701-706):
```python
if older_than is None and newer_than is None:
    raise ValueError(
        "drop_chunks requires at least one of older_than or newer_than. "
        "Passing both as None would drop ALL chunks — use show_chunks() "
        "to inspect first, or pass an explicit bound."
    )
```
Apply identically for the new mutual-exclusion guard (per CONTEXT.md D-07 / RESEARCH.md §3,
confirmed at the SQL-overload level — TimescaleDB has no 4-arg `time_bucket` accepting both):
```python
if origin is not None and offset is not None:
    raise ValueError(
        "time_bucket: 'origin' and 'offset' are mutually exclusive "
        "(TimescaleDB has no time_bucket overload accepting both); pass one or neither."
    )
```
Place this guard inside `_build_time_bucket_sql` itself (builder-testable in isolation) per
RESEARCH.md's recommended placement — NOT in the public `time_bucket()` accessor method.

**Type-dispatch idiom to mirror** (`_build_chunk_bound_fragments`, timescale.py:58-70) — same
"distinct SQL fragment + param per type" shape, but F02's dispatch is param-presence (not
str-vs-datetime on ONE param) — `origin` is always datetime-or-None, `offset` is always
str-or-None:
```python
bucket_expr = f"time_bucket(%s, {time_column}"
if origin is not None:
    bucket_expr += ", origin => %s"
    params.append(origin)
elif offset is not None:
    bucket_expr += ', "offset" => %s::interval'
    params.append(offset)
bucket_expr += ")"
```

**`@overload` KIND-parity block to preserve** (timescale.py:1207-1246, sync; async twin at
timescale.py:2323-2362, offset +1116): the three `@overload` stubs (`into="df"` / `into="rows"` /
`into=str`) plus the implementation signature must ALL receive the new `origin`/`offset`
keyword-only params, in both sync and async — this is the v1.0.0 Phase 46 mypy-strict KIND-parity
convention (CONTEXT.md D-08). Add `origin: datetime | None = None, offset: str | None = None,`
after `where` in every one of the 4 signatures (3 overloads + 1 impl) per class, ×2 classes = 8
signature edits total.

**Deprecated-`where=`-vs-`filter=` handling already present** (timescale.py:1303-1316) — DO NOT
touch this block; it is orthogonal to F02 and must be preserved as-is.

**Call-site wiring** — the implementation body (timescale.py:1317-1325) passes through to the
builder; extend the `_build_time_bucket_sql(...)` call to forward `origin=origin, offset=offset`:
```python
sql, params = _build_time_bucket_sql(
    table, time_column, bucket_width, aggregates, where=filter, schema=schema,
    origin=origin, offset=offset,
)
```

---

### `compress_chunk(chunk, *, if_not_compressed=True)` / `decompress_chunk(chunk, *, if_compressed=True)` (new, both classes, return `None`)

**Analog:** `pycopg/timescale.py:400-453` (`enable_compression`) for the `None`-return +
`ExtensionNotAvailableError`-guard convention; `pycopg/timescale.py:455-491`
(`add_compression_policy`) for the plain-execute sibling in the same compression family.

**Guard + None-return pattern** (mirror `enable_compression`, timescale.py:426-432):
```python
if not self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailableError(
        "TimescaleDB extension not installed. "
        "Run db.schema.create_extension('timescaledb')"
    )

validate_identifiers(table, schema)
```
**Important deviation for this pair:** unlike `enable_compression`/`add_compression_policy`,
`compress_chunk`/`decompress_chunk` take NO schema/table identifier arguments — `chunk` is a
fully-qualified value returned by `show_chunks()`, bound as `%s::regclass`, not a bare
identifier. Per RESEARCH.md's explicit note (Code Examples §F03): **do NOT call
`validate_identifiers` inside these two methods** — there is no identifier argument to validate;
injection safety comes entirely from parameter binding (`%s::regclass`), which is the security
control, documented in RESEARCH.md's Security Domain / V5 Input Validation row.

**Core bound-value execute pattern** (RESEARCH.md D-10/D-11-confirmed exact SQL, mirroring
`add_compression_policy`'s plain-execute shape at timescale.py:486-491 but with bound params
instead of f-string interpolation for the boolean — since chunk is now a genuine bound value, not
an identifier):
```python
self._db.execute(
    "SELECT compress_chunk(%s::regclass, if_not_compressed => %s)",
    [chunk, if_not_compressed],
)
```
```python
self._db.execute(
    "SELECT decompress_chunk(%s::regclass, if_compressed => %s)",
    [chunk, if_compressed],
)
```

**License-gate tolerance convention** (mirror `add_reorder_policy`'s `Raises` docstring block,
timescale.py:905-912) — both new methods are TSL/Community-gated on Apache builds (confirmed live
by RESEARCH.md, SQLSTATE `0A000` → `FeatureNotSupported`), document identically:
```
Raises
------
ExtensionNotAvailableError
    If TimescaleDB extension is not installed.
psycopg.errors.FeatureNotSupported
    If the local TimescaleDB runs under the Apache license (Community
    feature not available).  Callers should catch this and tolerate it
    on non-Community builds (see D-12).
```

---

### F04 — `newer_than`-datetime SQL-shape test (optional micro-gap, verify+document only)

**Analog:** `test_show_chunks_sql_shape_datetime_older_than` (tests/test_timescale.py:159-175) —
mirror exactly, swap `older_than=` for `newer_than=` and adjust the assertion substring:
```python
def test_show_chunks_sql_shape_datetime_older_than(self, config):
    """show_chunks with datetime older_than emits bare %s fragment."""
    from pycopg.schema import SchemaAccessor

    db = Database(config)
    mock_schema = MagicMock(spec=SchemaAccessor)
    mock_schema.has_extension = MagicMock(return_value=True)
    db._schema = mock_schema
    db.execute = MagicMock(return_value=[])

    cutoff = datetime(2024, 1, 15)
    db.timescale.show_chunks("events", older_than=cutoff)

    sql, params = db.execute.call_args[0]
    assert ", older_than => %s" in sql
    assert "::interval" not in sql
    assert params == [cutoff]
```
No production code changes needed for F04 — `_build_chunk_bound_fragments` (timescale.py:33-70)
already symmetrically dispatches `newer_than` the same way as `older_than` (verified: the full
function body handles both bounds identically, str→`%s::interval`, datetime→bare `%s`).

---

## Shared Patterns

### Extension guard (`ExtensionNotAvailableError`)
**Source:** every existing `TimescaleAccessor` method, canonical form at
`pycopg/timescale.py:426-430` (`enable_compression`) or `timescale.py:914-918`
(`add_reorder_policy`).
**Apply to:** ALL 4 new methods (`drop_continuous_aggregate`, `remove_continuous_aggregate_policy`,
`compress_chunk`, `decompress_chunk`) — the guard must fire BEFORE the DB round-trip that would
trigger `FeatureNotSupported`, verified by a dedicated mock test asserting
`db.execute.assert_not_called()` when `has_extension` returns `False` (mirror
`test_show_chunks_no_extension_raises`, tests/test_timescale.py:196-211).
```python
if not self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailableError(
        "TimescaleDB extension not installed. "
        "Run db.schema.create_extension('timescaledb')"
    )
```

### Identifier validation (`validate_identifiers`)
**Source:** `pycopg/utils.py` (`validate_identifier`, `validate_identifiers`, `validate_interval`),
imported at `pycopg/timescale.py:24`, called as line-1-of-builder convention throughout (e.g.
`_build_time_bucket_sql` timescale.py:252, `add_reorder_policy` timescale.py:920).
**Apply to:** `drop_continuous_aggregate`/`remove_continuous_aggregate_policy` (validate
`view_name, schema`); the extended `_build_time_bucket_sql` (validate `table, schema,
time_column` — UNCHANGED call, origin/offset are bound values not identifiers). **Do NOT apply
to:** `compress_chunk`/`decompress_chunk` (no identifier args — `chunk` is a bound `%s::regclass`
value per RESEARCH.md's explicit carve-out).

### Plain-execute vs. autocommit-seam choice
**Source:** doc-comment convention established at `pycopg/timescale.py:1107-1110`
(`add_continuous_aggregate_policy`, "D-01 — transaction-safe... NOT the autocommit seam") vs.
`timescale.py:938-942`/`1018-1022` (`create_continuous_aggregate`/`refresh_continuous_aggregate`,
"Runs on a dedicated `connect(autocommit=True)` connection (D-02)").
**Apply to:** ALL 4 new Phase 48 methods use plain `self._db.execute(...)` — RESEARCH.md D-05
confirms `DROP MATERIALIZED VIEW` and `remove_continuous_aggregate_policy` do NOT need the
autocommit seam (single-transaction DDL/scalar-function, unlike CREATE/REFRESH's multi-batch
materialization). Do not introduce `with self._db.connect(autocommit=True)` anywhere in this
phase — that pattern stays reserved for the two pre-existing methods.

### Boolean-flag-as-SQL-literal idiom (never bound as `%s` for cagg-family calls)
**Source:** `pycopg/timescale.py:922` (`add_reorder_policy`'s `ne = ", if_not_exists => true" if
if_not_exists else ""`), `timescale.py:996-997` (`create_continuous_aggregate`'s `mo`/`data`
literal rendering).
**Apply to:** `if_exists`/`cascade` on `drop_continuous_aggregate`, `if_exists` on
`remove_continuous_aggregate_policy` — render as a Python-type-checked (`bool`) fixed literal
`"true"`/`"false"` string, never as a bound `%s` parameter (avoids the `IndeterminateDatatype`
risk class documented at timescale.py:1074-1082 for untyped-NULL-adjacent params; a `bool`-typed
Python value has no such ambiguity but the codebase's established idiom for TimescaleDB flag
arguments is literal rendering, not binding — stay consistent). **Exception:** F03's
`if_not_compressed`/`if_compressed` ARE bound as `%s` (RESEARCH.md D-10 exact SQL) — this is
correct because `compress_chunk`/`decompress_chunk` are plain PostgreSQL function calls (not
TimescaleDB policy-registration calls with `=>` named-arg literal-boolean idiom); follow
RESEARCH.md's exact SQL template per surface, not a single blanket rule.

### Test structure: mock SQL-shape class-per-method
**Source:** `TestShowChunksMock` (tests/test_timescale.py:115-265), `TestDropChunksMock`
(tests/test_timescale.py:273+).
**Apply to:** 4 new test classes — `TestDropContinuousAggregateMock`,
`TestRemoveContinuousAggregatePolicyMock`, `TestTimeBucketOriginOffsetMock` (or extend existing
`TestTimeBucketMock` at tests/test_timescale.py:2098), `TestCompressChunkMock`/
`TestDecompressChunkMock`. Standard shape per test:
```python
def test_<method>_sql_shape_<case>(self, config):
    from pycopg.schema import SchemaAccessor
    db = Database(config)
    mock_schema = MagicMock(spec=SchemaAccessor)
    mock_schema.has_extension = MagicMock(return_value=True)
    db._schema = mock_schema
    db.execute = MagicMock(return_value=[...])

    db.timescale.<method>(...)

    sql, params = db.execute.call_args[0]
    assert "<expected fragment>" in sql
    assert params == [...]
```
Async mirror: swap `Database`→`AsyncDatabase`, `MagicMock`→`AsyncMock` for `has_extension`/
`execute`, add `async def` + `await`, import `AsyncSchemaAccessor` instead of `SchemaAccessor`
(mirror `test_show_chunks_async_sql_shape`, tests/test_timescale.py:213-231).

**Guard-fires-before-execute test convention** (mirror
`test_drop_chunks_both_none_raises_before_execute`, tests/test_timescale.py:292-306, and
`test_show_chunks_no_extension_raises`, tests/test_timescale.py:196-211):
```python
with pytest.raises(ValueError, match="mutually exclusive"):
    db.timescale.time_bucket("t", "ts", "1 hour", "avg(v)", origin=..., offset=...)
db.execute.assert_not_called()
```

### Identifier-injection test convention
**Source:** `test_spatial.py:142-143` / `:204-226` (`with pytest.raises(InvalidIdentifierError):`
pattern) — `test_timescale.py` currently has NO dedicated "injection"-named tests but reuses the
same `InvalidIdentifierError`-raise convention implicitly via `validate_identifiers`; import
`InvalidIdentifierError` from `pycopg.exceptions` (already used across the codebase, e.g.
`test_spatial.py:7`).
**Apply to:** `drop_continuous_aggregate`/`remove_continuous_aggregate_policy` (validate
`view_name`/`schema`) and the extended `_build_time_bucket_sql` (existing `table`/`schema`/
`time_column` validation — no new identifier args from F02, so no new injection test needed there
beyond what's already covered). No injection test needed for `compress_chunk`/`decompress_chunk`
(no identifier args — binding IS the injection defense per RESEARCH.md's Security Domain table).
```python
def test_drop_continuous_aggregate_invalid_view_name_raises(self, config):
    from pycopg.exceptions import InvalidIdentifierError
    db = Database(config)
    with pytest.raises(InvalidIdentifierError):
        db.timescale.drop_continuous_aggregate("bad; DROP TABLE users; --")
```

### Parity registry extension
**Source:** `test_timescale_v080_surface` (tests/test_parity.py:64-99), most recent sibling
pattern `test_v44_surface` (tests/test_parity.py:221-236, note the naming drifted from
`test_timescaleXX_surface` to bare `v44_surface` var name — follow the OLDER `test_timescale_v080_surface`
naming for THIS phase since it's the same accessor family, not spatial).
**Apply to:** add a new `test_timescale_v110_surface()` function (do not touch
`ACCESSOR_PAIRS`, which only checks bidirectional existence, not full-name-set):
```python
def test_timescale_v110_surface():
    """Assert both timescale accessors expose the Phase 48 (v1.1.0) surface additions."""
    v110_surface = frozenset(
        {
            "drop_continuous_aggregate",
            "remove_continuous_aggregate_policy",
            "compress_chunk",
            "decompress_chunk",
        }
    )
    for cls in (TimescaleAccessor, AsyncTimescaleAccessor):
        public = {
            name for name, _ in inspect.getmembers(cls) if not name.startswith("_")
        }
        missing = v110_surface - public
        assert (
            not missing
        ), f"{cls.__name__} is missing Phase 48 method(s): {sorted(missing)}"
```
Note: F02's `origin`/`offset` are param additions to the EXISTING `time_bucket` name, not new
method names — they do NOT belong in this frozenset (per RESEARCH.md Wave 0 Gaps), but ARE
covered automatically by `test_accessor_parameter_kind_parity` (tests/test_parity.py:432) once
the signature changes on both classes — no separate action needed there beyond editing both
classes' signatures.

## No Analog Found

None. Every Phase 48 surface has an exact, cited, same-file analog — this phase is
additive-by-analogy with zero missing infrastructure (confirmed by RESEARCH.md's "Don't
Hand-Roll" table and "Key insight" closing note).

## Metadata

**Analog search scope:** `pycopg/timescale.py` (both accessor classes, full file read across
non-overlapping targeted ranges: 1-70, 214-333, 400-499, 646-745, 879-1178, 1207-1337),
`tests/test_timescale.py` (115-315), `tests/test_parity.py` (1-236)
**Files scanned:** 3 (all pre-identified in `<required_reading>` / phase prompt canonical_refs —
no additional Glob/Grep discovery needed beyond confirming exact line numbers and extracting
excerpts)
**Pattern extraction date:** 2026-07-02

## PATTERN MAPPING COMPLETE
