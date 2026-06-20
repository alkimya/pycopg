# Phase 26: Incremental ETL — Pure Layer - Pattern Map

**Mapped:** 2026-06-20
**Files analyzed:** 2 (`pycopg/etl.py`, `tests/test_etl.py`)
**Analogs found:** 6 / 6 (5 new symbols + test layer — all internal to the same two files)

This phase adds a pure, DB-free layer. Every new symbol has a near-exact in-module
analog; the new builder/serializers copy existing conventions byte-for-byte. No file
outside `pycopg/etl.py` and `tests/test_etl.py` is modified (the `watermark JSONB`
column at `queries.py:260` already exists and is the read-only round-trip target).

## File Classification

| New Symbol (file) | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `Pipeline.incremental_column: str \| None` (`etl.py`) | model (frozen dataclass field) | transform/validate | `extract_limit: int \| None` field (`etl.py:154`) + its `__post_init__` guard | exact |
| `_validate_incremental(column, load_mode)` (`etl.py`) | utility (module-level validator) | transform/validate | `_validate_load_mode` (`etl.py:52`) | exact |
| `_build_incremental_extract_sql(source, column, schema, watermark)` (`etl.py`) | utility (pure SQL builder) | transform → `(sql, params)` | `build_truncate_sql` (`etl.py:268`) + `_build_insert_sql` (`etl.py:330`); dispatch via `_is_sql_source` (`etl.py:241`) | exact (convention) / new (subquery-wrap shape) |
| `_encode_watermark(value) -> dict` (`etl.py`) | utility (pure serializer) | transform | pure-builder convention + `bool`-guard (`etl.py:191`); raises `ETLError` (`exceptions.py:54`) | role-match (no exact envelope analog) |
| `_decode_watermark(envelope: dict)` (`etl.py`) | utility (pure deserializer) | transform | `_row_to_result` (`etl.py:482`) dict→typed mapping | role-match |
| DB-free unit tests (`tests/test_etl.py`) | test | n/a | `TestValidateLoadMode` (`:249`), `TestBuilders` (`:167`), `TestEtlBuilders` (`:263`), `TestPipeline` (`:24`), `TestRowToResult` (`:424`) | exact |

## Pattern Assignments

### `Pipeline.incremental_column: str | None` (model field, D-17/D-04 precedent)

**Analog:** `extract_limit: int | None = None` field (`etl.py:154`) and its `__post_init__` block.

**Field declaration** — add to the field block (`etl.py:147-154`), after `extract_limit`:
```python
    name: str
    source: str
    target: str
    load_mode: str = "append"
    conflict_columns: tuple[str, ...] = ()
    schema: str = "public"
    transform: Callable | list[Callable] | None = None
    extract_limit: int | None = None
    # new:
    incremental_column: str | None = None
```
Plain optional `str | None`, default `None`. No `object.__setattr__` normalization needed
(unlike `conflict_columns` at `etl.py:178-179`) — only validation.

**`__post_init__` call-site (D-17 exact ordering)** — insert the new validator call
**after** `_validate_load_mode(self.load_mode)` (`etl.py:181`) and **before** the
upsert-requires-conflict_columns check (`etl.py:183`):
```python
        # Validate load_mode first (D-06).
        _validate_load_mode(self.load_mode)
        # Validate incremental_column / load_mode combo + identifier (D-14/D-15/D-16/D-17).
        _validate_incremental(self.incremental_column, self.load_mode)
        # Require conflict_columns when upsert is selected (D-07).
        if self.load_mode == "upsert" and not self.conflict_columns:
            ...
```
Final sequence (D-17): bare-string check → normalize conflict_columns → `_validate_load_mode`
→ **`_validate_incremental`** → upsert-requires-conflict_columns → extract_limit.

**Docstring (numpydoc shallow, Claude's Discretion)** — add a `Parameters` entry mirroring
the `extract_limit` entry (`etl.py:114-118`); note the aware/monotonic/non-decreasing
column expectation (D-03, documented-not-enforced here). Add a `Raises` line for the new
`ValueError`. `interrogate ≥ 95` gate applies.

---

### `_validate_incremental(incremental_column, load_mode)` (module-level validator, D-14)

**Analog:** `_validate_load_mode` (`etl.py:52-69`) — DIRECT template. Pure, module-level,
raises `ValueError`, called from `__post_init__`.

**Full analog to copy structure from** (`etl.py:52-69`):
```python
def _validate_load_mode(load_mode: str) -> None:
    """Validate a ``load_mode=`` value.

    Parameters
    ----------
    load_mode : str
        Load strategy — must be ``"append"``, ``"replace"``, or
        ``"upsert"`` (D-06).

    Raises
    ------
    ValueError
        If ``load_mode`` is not one of the accepted values.
    """
    if load_mode not in _VALID_LOAD_MODES:
        raise ValueError(
            f"load_mode must be one of {_VALID_LOAD_MODES}, got {load_mode!r}"
        )
```

**Shape for the new helper (D-15 order: combo check first, then identifier):**
```python
def _validate_incremental(incremental_column: str | None, load_mode: str) -> None:
    """..."""
    if incremental_column is None:          # D-15 short-circuit (non-incremental)
        return
    if load_mode in ("append", "replace"):  # D-16 forbidden combo → intent error first
        raise ValueError(
            f"incremental_column requires load_mode='upsert' (got {load_mode!r}); "
            "'append' and 'replace' are forbidden with incremental loads because "
            "upsert guarantees idempotency (ETL-INC-01)"
        )
    validate_identifiers(incremental_column)  # D-15 syntax error second (utils.py:107)
```
- `validate_identifiers` already imported at `etl.py:39`; raises `InvalidIdentifier` (utils.py:100).
- Decision-tag-in-message convention (D-16 cites `ETL-INC-01`) matches existing messages
  like the upsert `(D-07)` message at `etl.py:185`.

---

### `_build_incremental_extract_sql(source, column, schema, watermark)` (pure builder, D-06..D-13)

**Analogs:** `build_truncate_sql` (`etl.py:268-297`) for the `(sql, list)` + bare-validated-
identifier convention; `_build_insert_sql` (`etl.py:330-392`) for the `%s`-only-values +
pure-builder docstring; `_is_sql_source` (`etl.py:241-265`) for the source dispatch (D-11).

**`(sql, params)` 2-tuple + bare-validated-identifier convention** (`etl.py:296-297`):
```python
    validate_identifiers(table, schema)
    return f"TRUNCATE TABLE {schema}.{table}", []
```
Identifiers are interpolated **bare** (validated), values are **never** interpolated. The new
builder emits `column` bare (D-10) and the watermark as a single `%s` param.

**`%s`-placeholder-only values convention** (`_build_insert_sql`, `etl.py:386-392`):
```python
        row_placeholders = ", ".join(["%s"] * len(columns))
        ...
    sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES {values_str}{conflict_clause}"
    return sql, params
```

**Dispatch helper to reuse (D-11)** — `_is_sql_source` (`etl.py:261-265`):
```python
    stripped = source.strip()
    if stripped.upper().startswith(("SELECT", "WITH")):
        return True
    return " " in stripped
```

**Shape for the new builder (D-06/D-07/D-09/D-12):**
```python
def _build_incremental_extract_sql(
    source: str,
    column: str,
    schema: str = "public",
    watermark=None,
) -> tuple[str, list]:
    """..."""
    validate_identifiers(column)
    if watermark is None:                       # D-12 first run / no filter
        if _is_sql_source(source):
            return source, []                   # (or wrapped SELECT *; planner's call)
        validate_identifiers(source, schema)
        return f"SELECT * FROM {schema}.{source}", []
    if _is_sql_source(source):                  # D-06/D-07/D-08 subquery wrap
        clean = source.rstrip().rstrip(";").rstrip()
        return f"SELECT * FROM ({clean}) _pycopg_inc WHERE {column} > %s", [watermark]
    validate_identifiers(source, schema)        # D-09 table source → WHERE append
    return f"SELECT * FROM {schema}.{source} WHERE {column} > %s", [watermark]
```
- Reserved alias `_pycopg_inc` is fixed (D-07).
- `>` is exclusive (REQUIREMENTS Out-of-Scope table).
- One-line-vs-multiline wrap and the newline-before-`WHERE` hardening are Claude's Discretion (D-08).
- The pure-builder docstring sentence to mirror is `_build_insert_sql`'s: *"Pure builder —
  no `self`, no I/O, no DB connection."* (`etl.py:339`).

---

### `_encode_watermark(value) -> dict` / `_decode_watermark(envelope: dict)` (pure serializers, D-01..D-05)

**No exact envelope analog.** Closest patterns:
- Pure-builder convention (no `self`/IO/DB, returns a plain value) — same as all `etl.py` builders.
- The `bool`-is-`int` guard precedent (`etl.py:190-197`) for D-04's `bool` exclusion:
```python
        if self.extract_limit is not None:
            if isinstance(self.extract_limit, bool) or not isinstance(
                self.extract_limit, int
            ):
                raise ValueError(...)
```
  Apply the identical `isinstance(value, bool)`-first guard so a `bool` watermark is rejected
  before the `int` branch.
- `ETLError` base (`exceptions.py:54`) for the unsupported-type raise (D-04). Planner decides
  whether a new `ETLError` subclass is warranted or the base suffices; `ETLError` is NOT yet
  imported in `etl.py` (only `ETLTargetNotFoundError`, `ETLTransformError` at `etl.py:38`) —
  add the import.
- `_decode_watermark` is a dict→typed reconstruction; the structural analog is `_row_to_result`
  (`etl.py:498-507`), which maps dict keys to a typed result.

**Envelope shape (D-01/D-02):** `{"type": "datetime"|"int"|"str", "value": <scalar>}`.
- `datetime` → `value = dt.isoformat()`; decode → `datetime.fromisoformat(value)` (D-02, no UTC coercion).
- `int` / `str` → stored as-is.
- Supported allowlist is exactly `{datetime, int, str}` (D-04); `bool`/`float`/`Decimal` → `ETLError`
  naming the unsupported type and listing the supported set.
- `_encode_watermark` returns a **bare dict** (D-05) — the `psycopg.types.json.Jsonb(...)` wrap is
  Phase 27, not here. `_decode_watermark` accepts the plain dict psycopg returns from a JSONB read.
- `datetime` already imported at `etl.py:31`.

**Round-trip target (read-only this phase):** `watermark JSONB` at `queries.py:260` inside
`ETL_INIT_PIPELINE_RUNS` — do NOT modify `queries.py`.

---

### DB-free unit tests (`tests/test_etl.py`)

**Analogs (extend this file; Claude's Discretion confirms extend-not-new):**

- **Validator tests** → copy `TestValidateLoadMode` (`tests/test_etl.py:249-260`): one class,
  happy-path "must not raise" loop + `pytest.raises(ValueError, match=...)`. Add a
  `TestValidateIncremental` for None-short-circuit, forbidden append/replace combos, and
  bad-identifier (`InvalidIdentifier`).

- **Pipeline construction tests** → copy `TestPipeline` (`tests/test_etl.py:24-164`): the
  `extract_limit` cases (`:107-125`, including the `extract_limit=True` bool-guard test at `:122`)
  are the precise template for `incremental_column` field-storage + combo-rejection + bad-identifier
  tests.

- **SQL builder tests** → copy `TestBuilders` (`:167`) / `TestEtlBuilders` (`:263`): exact-string
  `assert sql == "..."` + `assert params == [...]`, the `(str, list)` 2-tuple shape assertion
  (`:321-327`), invalid-identifier `pytest.raises(InvalidIdentifier)` (`:306-319`), and reuse the
  `_is_sql_source` dispatch coverage style from `TestIsSqlSource` (`:219`). Add `watermark=None`
  (full SELECT, `[]` params) and both source-kind filtered cases; assert the `_pycopg_inc` alias
  and the single `%s` param.

- **Encode/decode round-trip tests** → structural template `TestRowToResult` (`:424-483`): a
  `_sample` helper + per-type assertions. Cover `datetime` (tz-aware, microseconds + offset
  preserved per D-02), `int`, `str` round-trips, and `pytest.raises(ETLError)` for `bool`/`float`
  with the unsupported type named.

**Import block to extend** (`tests/test_etl.py:9-21`): add the new symbols to the
`from pycopg.etl import (...)` tuple and `ETLError` (or its chosen subclass) to the
`from pycopg.exceptions import ...` line.

## Shared Patterns

### Identifier validation gate
**Source:** `validate_identifiers` (`pycopg/utils.py:107-122`); already imported `etl.py:39`.
**Apply to:** `_validate_incremental` (column), `_build_incremental_extract_sql` (column, source, schema).
```python
def validate_identifiers(*names: str) -> None:
    for name in names:
        if name is not None:
            validate_identifier(name)
```
Always called **before** any f-string interpolation (`etl.py` module docstring invariant, lines 16-22).

### `(sql, list)` 2-tuple return + `%s`-only values
**Source:** every builder in `etl.py` (`build_truncate_sql:297`, `_build_insert_sql:392`).
**Apply to:** `_build_incremental_extract_sql`. Watermark value is the only param; identifiers bare-validated.

### Module-level validator called from `__post_init__`
**Source:** `_validate_load_mode` (`etl.py:52`) + its call at `__post_init__` (`etl.py:181`).
**Apply to:** `_validate_incremental`. Pure, independently unit-testable, raises `ValueError`.

### `bool`-as-`int` exclusion guard
**Source:** `etl.py:190-197` (the `extract_limit` validation).
**Apply to:** `_encode_watermark` D-04 type allowlist — `isinstance(value, bool)` checked first.

### numpydoc shallow docstrings + interrogate ≥ 95
**Source:** every docstring in `etl.py` (Parameters / Returns / Raises sections, no extra Examples
beyond the dataclass). **Apply to:** all 3 new helpers and the new field's Parameter entry.
ruff + black gates apply (`uv run ruff check pycopg tests`, `uv run black pycopg tests`).

## No Analog Found

| Symbol | Role | Reason | Fallback |
|--------|------|--------|----------|
| `_encode_watermark` / `_decode_watermark` envelope shape `{"type", "value"}` | serializer | No typed-JSONB-envelope precedent exists in the codebase | Follow pure-builder convention + `bool`-guard + `ETLError` raise; envelope shape is specified directly in CONTEXT.md D-01..D-05 (stdlib `isoformat`/`fromisoformat`, zero new deps) |

## Metadata

**Analog search scope:** `pycopg/etl.py`, `pycopg/utils.py`, `pycopg/exceptions.py`, `pycopg/queries.py`, `tests/test_etl.py`
**Files scanned:** 5 (all read in full or targeted ranges; no re-reads)
**Pattern extraction date:** 2026-06-20
