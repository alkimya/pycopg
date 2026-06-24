---
phase: 35-schema-introspection
plan: 02
type: execute
wave: 2
depends_on: [35-01]
files_modified:
  - pycopg/schema.py
  - tests/test_database.py
  - tests/test_database_integration.py
  - tests/test_parity.py
autonomous: true
requirements: [INTRO-05, INTRO-06]
must_haves:
  truths:
    - "db.schema.describe('users') returns one flat dict with exactly the keys columns, primary_key, foreign_keys, indexes"
    - "describe's 'columns' value is exactly table_info(table, schema)'s list[dict]; 'primary_key' is exactly primary_key(table, schema)'s dict|None; 'foreign_keys' is exactly foreign_keys(table, schema)'s list[dict]; 'indexes' is exactly list_indexes(table, schema)'s list[dict] (no shape drift)"
    - "describe composes the standalone helpers (does NOT run its own consolidated SQL) so the sub-shapes can never drift from the standalone helpers (D-04)"
    - "describe on a missing table returns a dict with empty/None sections (columns [], primary_key None, foreign_keys [], indexes []) — no error class, no extra existence pre-check (D-06)"
    - "describe exists identically on AsyncSchemaAccessor using await; test_accessor_parity passes"
  artifacts:
    - path: "pycopg/schema.py"
      provides: "sync describe on SchemaAccessor + async describe on AsyncSchemaAccessor (composition of the 4 helpers)"
      contains: "def describe("
    - path: "tests/test_database_integration.py"
      provides: "live-DB test asserting describe's 4 keys and that each sub-value equals the standalone helper's output"
      contains: "def test_describe"
    - path: "tests/test_parity.py"
      provides: "optional named-surface frozenset test for the 5 new v0.9.0 introspection methods"
      contains: "v090"
  key_links:
    - from: "pycopg/schema.py:describe"
      to: "pycopg/schema.py:table_info / primary_key / foreign_keys / list_indexes"
      via: "composes the four standalone helpers into one flat dict"
      pattern: "self\\.(table_info|primary_key|foreign_keys|list_indexes)"
---

<objective>
Add the `describe(table, schema="public") -> dict` consolidation helper (INTRO-05, D-04) to BOTH
`SchemaAccessor` and `AsyncSchemaAccessor` (`pycopg/schema.py`), with full sync/async parity
(INTRO-06, D-08). `describe` is the all-in-one introspection snapshot: it returns ONE flat dict that
COMPOSES the existing + new standalone helpers — it does NOT run its own consolidated SQL. Each
sub-value is EXACTLY the shape its standalone helper returns:
`{'columns': table_info(...), 'primary_key': primary_key(...), 'foreign_keys': foreign_keys(...),
'indexes': list_indexes(...)}`. Composing (rather than re-querying) guarantees the sub-shapes can never
drift from the standalone helpers and keeps new SQL at zero. This plan also adds the OPTIONAL
named-surface test asserting the 5 v0.9.0 introspection methods exist on both classes
(belt-and-suspenders over the auto-enforced `test_accessor_parity`).

Purpose: Give users a one-call table snapshot (columns+types, PK, FKs, indexes) with guaranteed-
consistent sub-shapes and zero new SQL.
Output: 1 new method on each class (sync + async `describe`); live-DB + composition-equality tests;
an optional `v090` named-surface frozenset test. Parity is auto-covered once `describe` exists on both classes.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/35-schema-introspection/35-CONTEXT.md
@.planning/codebase/CONVENTIONS.md
@.planning/phases/35-schema-introspection/35-01-SUMMARY.md
</context>

<artifacts_this_phase_produces>
This plan (35-02) produces these NEW symbols (source-grounding / drift passes MUST treat these as
created here, not pre-existing):
- `pycopg/schema.py` on `SchemaAccessor`: `describe` (sync).
- `pycopg/schema.py` on `AsyncSchemaAccessor`: `describe` (async).
- `tests/test_database_integration.py`: a `test_describe`-style live-DB test (keys + sub-shape equality).
- `tests/test_database.py`: an optional mock-based `describe` composition test (exact name the executor's call).
- `tests/test_parity.py`: an OPTIONAL named-surface frozenset test (e.g. `test_schema_v090_surface`) over the
  5 new introspection methods (`primary_key`, `foreign_keys`, `sequences`, `views`, `describe`).

`primary_key`/`foreign_keys`/`sequences`/`views` are produced in plan 35-01. `table_info`/`list_indexes`
are PRE-EXISTING helpers (analogs being composed), NOT new symbols.
</artifacts_this_phase_produces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add describe composition helper to both classes</name>
  <files>pycopg/schema.py</files>
  <read_first>
    - pycopg/schema.py:402-418 — sync `table_info` (the `'columns'` sub-value; `list[dict]`).
    - pycopg/schema.py:642-657 — sync `list_indexes` (the `'indexes'` sub-value; `list[dict]`).
    - pycopg/schema.py — the new sync `primary_key`/`foreign_keys` from 35-01 (the `'primary_key'` dict|None and
      `'foreign_keys'` list[dict] sub-values; read their bodies to confirm exact return shapes).
    - pycopg/schema.py:1009-1025 + 1292-1307 — async `table_info` / async `list_indexes` (the await-composition
      idiom for the async `describe`).
    - .planning/phases/35-schema-introspection/35-CONTEXT.md §D-04 — the exact flat-dict key set and "compose, do
      not re-query" rule.
  </read_first>
  <behavior>
    - `describe('users')` -> `{'columns': [...], 'primary_key': {...}|None, 'foreign_keys': [...], 'indexes': [...]}`
      with EXACTLY those four keys.
    - `describe('users')['columns'] == table_info('users')`; `['primary_key'] == primary_key('users')`;
      `['foreign_keys'] == foreign_keys('users')`; `['indexes'] == list_indexes('users')` (each sub-value is
      the standalone helper's exact output — no reshaping, no extra/missing keys).
    - `describe` on a missing table -> `{'columns': [], 'primary_key': None, 'foreign_keys': [], 'indexes': []}`
      (each composed helper already returns its own empty/None for a missing table — D-06; describe does NOT add
      a table-existence pre-check or a new error class).
    - Async `describe` returns the identical flat dict.
  </behavior>
  <action>
    Append to `SchemaAccessor` (after the new `views` from 35-01) and to `AsyncSchemaAccessor` (after its
    `views`):
    `def describe(self, table: str, schema: str = "public") -> dict:` — return ONE flat dict composing the four
    helpers (do NOT write new SQL, do NOT add a constant to queries.py):
    `return {'columns': self.table_info(table, schema), 'primary_key': self.primary_key(table, schema),
    'foreign_keys': self.foreign_keys(table, schema), 'indexes': self.list_indexes(table, schema)}`.
    NOTE: `table_info`'s first positional param is named `name` (not `table`) — pass positionally
    (`self.table_info(table, schema)`) so the call is correct regardless of param name. Identifier validation
    is already performed by each composed helper, so `describe` itself does not need a separate
    `validate_identifiers` call (the composed helpers guard their own inputs); calling them in order is
    sufficient and keeps the "compose, don't re-query" contract (D-04). The async `describe` is the same but
    `await`s each composed helper:
    `return {'columns': await self.table_info(table, schema), 'primary_key': await self.primary_key(table,
    schema), 'foreign_keys': await self.foreign_keys(table, schema), 'indexes': await self.list_indexes(table,
    schema)}`. Numpydoc shallow docstring documenting the four keys (no Examples section — match the existing
    schema.py docstring style). Do NOT add an `into=`/DataFrame/dataclass rendering option (INTRO-F01, deferred).
  </action>
  <acceptance_criteria>
    - `pycopg/schema.py` contains `def describe(` (sync) AND `async def describe(` with identical signature
      `(self, table: str, schema: str = "public")`.
    - The sync `describe` body references `self.table_info`, `self.primary_key`, `self.foreign_keys`, and
      `self.list_indexes` (grep: all four `self.<helper>` calls appear in the `describe` body); the async body
      awaits all four. No new SQL constant is added to `queries.py` (grep `queries.py` shows no `DESCRIBE`).
    - The returned dict has exactly the keys `columns`, `primary_key`, `foreign_keys`, `indexes` (asserted in Task 2).
    - `uv run pytest tests/test_parity.py -o addopts="" -q` passes (parity green once both classes have `describe`).
    - `uv run ruff check pycopg/schema.py` exits 0.
  </acceptance_criteria>
  <verify>
    <automated>uv run ruff check pycopg/schema.py && uv run pytest tests/test_parity.py -o addopts="" -q</automated>
  </verify>
  <done>`describe` exists on BOTH SchemaAccessor and AsyncSchemaAccessor, composing `table_info`/`primary_key`/`foreign_keys`/`list_indexes` into one flat 4-key dict with no new SQL; sub-shapes equal the standalone helpers; parity green; ruff clean.</done>
</task>

<task type="auto">
  <name>Task 2: Tests for describe (composition equality + missing-table) and optional v090 named-surface test</name>
  <files>tests/test_database.py, tests/test_database_integration.py, tests/test_parity.py</files>
  <read_first>
    - tests/test_database_integration.py:1-48 — the `db`, `temp_table_name`, `cleanup_table` fixtures.
    - tests/test_database_integration.py:197-208 — `test_table_info` live-DB shape assertion (the model for the
      describe live test: create a table with a PK+FK+index, then assert describe's sub-values).
    - tests/test_database.py:642-657 — `test_table_info` mock-based unit test (optional mock describe test model).
    - tests/test_parity.py:64-98 — `test_timescale_v080_surface` (the named-surface frozenset pattern to copy
      for the optional `test_schema_v090_surface`; iterate `for cls in (SchemaAccessor, AsyncSchemaAccessor)`).
    - pycopg/schema.py — the new `describe` body from Task 1 (assert against its EXACT 4-key composition).
    - MEMORY "pycopg-flaky-db-tests" / "pycopg-test-db-broken-timescaledb" — run targeted DB tests with
      `-o addopts=""`; use `PGDATABASE=pycopg_test2` if the default DB is broken.
  </read_first>
  <behavior>
    - Live-DB: create a table with a SERIAL PK, an FK to another table, and an index; `describe` returns the
      4-key dict, and `describe(t)['columns'] == db.schema.table_info(t)`, `['primary_key'] ==
      db.schema.primary_key(t)`, `['foreign_keys'] == db.schema.foreign_keys(t)`, `['indexes'] ==
      db.schema.list_indexes(t)` (composition equality — proves no drift).
    - Live-DB missing table: `describe('no_such_table_xyz')` -> `{'columns': [], 'primary_key': None,
      'foreign_keys': [], 'indexes': []}`.
    - Named-surface (optional): both `SchemaAccessor` and `AsyncSchemaAccessor` expose the frozenset
      `{primary_key, foreign_keys, sequences, views, describe}` as public members.
  </behavior>
  <action>
    Add a live-DB test to `tests/test_database_integration.py` (using `db`/`temp_table_name`/`cleanup_table`):
    create a parent table with a PK, a child table with a SERIAL PK + an FK to the parent + a secondary index;
    call `db.schema.describe(child)`; assert `set(result) == {'columns', 'primary_key', 'foreign_keys',
    'indexes'}` AND assert each sub-value equals the corresponding standalone helper's output
    (`result['columns'] == db.schema.table_info(child)`, etc.) — this composition-equality assertion is the
    anti-drift guarantee of D-04. Add a missing-table assertion: `db.schema.describe('no_such_table_<uuid>')`
    returns `{'columns': [], 'primary_key': None, 'foreign_keys': [], 'indexes': []}`.
    Optionally add a mock-based `describe` composition test to `tests/test_database.py` if it adds value over the
    live test (executor's call).
    Add the OPTIONAL named-surface test to `tests/test_parity.py` mirroring `test_timescale_v080_surface`
    (lines 64-98): define `v090_surface = frozenset({'primary_key', 'foreign_keys', 'sequences', 'views',
    'describe'})` and assert it is a subset of the public members of BOTH `SchemaAccessor` and
    `AsyncSchemaAccessor` (import already present at tests/test_parity.py:15). Name it `test_schema_v090_surface`.
    Do NOT modify `ACCESSOR_PAIRS` (parity is already auto-enforced; the pair is registered at line 31).
  </action>
  <acceptance_criteria>
    - `tests/test_database_integration.py` contains a `describe` test asserting `set(result) == {'columns',
      'primary_key', 'foreign_keys', 'indexes'}` AND four composition-equality assertions (each sub-value ==
      the standalone helper's output).
    - `tests/test_database_integration.py` asserts `describe` on a nonexistent table returns the all-empty/None dict.
    - `tests/test_parity.py` contains `test_schema_v090_surface` asserting the 5-method frozenset is a subset of
      both classes' public members (grep: `v090` present in tests/test_parity.py).
    - `uv run pytest tests/test_database_integration.py -o addopts="" -q -k describe` passes (live DB; use
      `PGDATABASE=pycopg_test2` if the default DB is broken per memory).
    - `uv run pytest tests/test_parity.py -o addopts="" -q` passes (both `test_accessor_parity` and the new surface test).
    - `uv run ruff check pycopg tests` exits 0.
  </acceptance_criteria>
  <verify>
    <automated>uv run ruff check pycopg tests && uv run pytest tests/test_database_integration.py tests/test_parity.py -o addopts="" -q -k "describe or accessor_parity or v090"</automated>
  </verify>
  <done>Live-DB describe test (4-key set + composition-equality + missing-table empty/None) and the optional `test_schema_v090_surface` named-surface test pass; `test_accessor_parity` green; ruff clean.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| caller -> db.schema.describe | The `table`/`schema` args reach SQL, but only via the composed standalone helpers. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-35-03 | Tampering | `describe` identifier args (`table`, `schema`) | mitigate | `describe` writes NO SQL of its own — it composes `table_info`/`primary_key`/`foreign_keys`/`list_indexes`, each of which already calls `validate_identifiers(...)` first and binds user values as `%s`. The identifier guard is therefore enforced by the composed helpers; `describe` introduces no new interpolation surface. |
| T-35-04 | Information Disclosure | read-only consolidated introspection | accept | Read-only composition of existing catalog queries scoped to the schema arg; no DDL, no new SQL, no new dependencies, no new network/file I/O, no auth surface. |

No high-severity threats: `describe` is a pure read-only composition of already-mitigated helpers; it adds no
SQL, no new constant, no error class, and no new dependency.
</threat_model>

<verification>
- `uv run pytest tests/test_parity.py -o addopts="" -q` — `test_accessor_parity` + `test_schema_v090_surface` green (INTRO-05/INTRO-06).
- `uv run pytest tests/test_database_integration.py -o addopts="" -q -k describe` — describe composition + missing-table tests pass.
- `uv run ruff check pycopg tests` exits 0.
- Coverage ratchet held ≥94% (verified at release gate).
</verification>

<success_criteria>
- `db.schema.describe(table, schema)` returns one flat dict with exactly `columns`/`primary_key`/`foreign_keys`/`indexes`, each sub-value equal to its standalone helper's output, composing (not re-querying) per D-04 (INTRO-05).
- `describe` on a missing table returns the all-empty/None dict (D-06) — no error class, no extra pre-check.
- `describe` exists identically on `AsyncSchemaAccessor`; `test_accessor_parity` (and the optional `test_schema_v090_surface`) pass (INTRO-06).
</success_criteria>

<output>
Create `.planning/phases/35-schema-introspection/35-02-SUMMARY.md` when done.
</output>
