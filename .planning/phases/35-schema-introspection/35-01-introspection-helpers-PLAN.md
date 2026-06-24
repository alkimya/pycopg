---
phase: 35-schema-introspection
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pycopg/queries.py
  - pycopg/schema.py
  - tests/test_database.py
  - tests/test_database_integration.py
autonomous: true
requirements: [INTRO-01, INTRO-02, INTRO-03, INTRO-04, INTRO-06]
must_haves:
  truths:
    - "db.schema.primary_key('users') returns {'constraint_name': 'users_pkey', 'columns': ['id']} (columns in key order) and None for a table with no primary key"
    - "db.schema.primary_key on a composite PK returns columns in key (conkey) order, e.g. ['org_id', 'user_id']"
    - "db.schema.foreign_keys('orders') returns a list[dict], each entry with exactly the keys constraint_name, columns, referenced_table, referenced_columns; [] when the table has no FKs"
    - "db.schema.foreign_keys composite-FK entry lists local columns and referenced_columns in key (conkey/confkey) order; NO on_delete/on_update/referenced_schema keys (deferred)"
    - "db.schema.sequences('public') returns a list[str] of sequence names scoped to the schema arg (includes SERIAL/identity-backed sequences)"
    - "db.schema.views('public') returns a list[str] of REGULAR view names scoped to the schema arg, EXCLUDING materialized views"
    - "A nonexistent table yields the same empty/None result (no table-existence pre-check, no new error class) — primary_key -> None, foreign_keys -> []"
    - "Every new method exists identically on AsyncSchemaAccessor using await; test_accessor_parity passes"
  artifacts:
    - path: "pycopg/queries.py"
      provides: "PRIMARY_KEY, FOREIGN_KEYS, SEQUENCES, VIEWS SQL constants (UPPER_SNAKE, %s-bound)"
      contains: "PRIMARY_KEY ="
    - path: "pycopg/schema.py"
      provides: "sync primary_key, foreign_keys, sequences, views on SchemaAccessor + async twins on AsyncSchemaAccessor"
      contains: "def primary_key("
    - path: "tests/test_database.py"
      provides: "mock-based unit tests for the 4 helpers (shape + None/[] edge cases)"
      contains: "def test_primary_key"
    - path: "tests/test_database_integration.py"
      provides: "live-DB tests for the 4 helpers (composite PK/FK order, schema scoping, matview exclusion)"
      contains: "def test_foreign_keys"
  key_links:
    - from: "pycopg/schema.py:primary_key"
      to: "pycopg/queries.py:PRIMARY_KEY"
      via: "self._db.execute(queries.PRIMARY_KEY, [schema, table])"
      pattern: "queries\\.PRIMARY_KEY"
    - from: "pycopg/schema.py:foreign_keys"
      to: "pycopg/queries.py:FOREIGN_KEYS"
      via: "self._db.execute(queries.FOREIGN_KEYS, [schema, table])"
      pattern: "queries\\.FOREIGN_KEYS"
    - from: "pycopg/schema.py:primary_key"
      to: "pycopg/utils.py:validate_identifiers"
      via: "validate_identifiers(table, schema) before binding"
      pattern: "validate_identifiers"
---

<objective>
Add FOUR standalone read-only introspection helpers to BOTH `SchemaAccessor` and
`AsyncSchemaAccessor` (`pycopg/schema.py`), sitting next to the existing introspection methods
(`table_info`, `list_indexes`, `list_constraints`): `primary_key` (INTRO-01, D-01),
`foreign_keys` (INTRO-02, D-02), `sequences` (INTRO-03, D-03), `views` (INTRO-04, D-03/D-07),
with full sync/async parity (INTRO-06, D-08 — auto-enforced by `tests/test_parity.py`). Each helper
follows the established `validate_identifiers(...)` first → `self._db.execute(queries.CONSTANT,
[schema, table])` → reshape pattern, with the SQL held as a new UPPER_SNAKE constant in
`pycopg/queries.py`. `primary_key`/`foreign_keys` source `pg_catalog` (`pg_constraint` with
`conkey`/`confkey` arrays) for reliable composite-column ordering (D-05); `sequences` sources
`information_schema.sequences`; `views` sources a view that naturally excludes materialized views.

Purpose: Give users reliable, composite-safe PK/FK introspection and schema-scoped sequence/view
listings — the building blocks the `describe()` consolidation (plan 02) composes.
Output: 4 new SQL constants in `queries.py`; 8 new methods (4 sync + 4 async) in `schema.py`;
mock-based + live-DB tests. Parity is auto-covered once each method exists on both classes.
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
@.planning/phases/34-crud-ergonomics/34-CONTEXT.md
@.planning/codebase/CONVENTIONS.md
</context>

<artifacts_this_phase_produces>
This plan (35-01) produces these NEW symbols (source-grounding / drift passes MUST treat these as
created here, not pre-existing):
- `pycopg/queries.py`: `PRIMARY_KEY`, `FOREIGN_KEYS`, `SEQUENCES`, `VIEWS` (4 new SQL constants).
- `pycopg/schema.py` on `SchemaAccessor`: `primary_key`, `foreign_keys`, `sequences`, `views` (4 sync methods).
- `pycopg/schema.py` on `AsyncSchemaAccessor`: `primary_key`, `foreign_keys`, `sequences`, `views` (4 async methods).
- `tests/test_database.py`: `test_primary_key`, `test_primary_key_none`, `test_foreign_keys`,
  `test_foreign_keys_empty`, `test_sequences`, `test_views` (mock-based unit tests; exact names the
  executor's call as long as the shape/edge assertions hold).
- `tests/test_database_integration.py`: live-DB tests for the 4 helpers (composite PK/FK ordering,
  schema scoping, matview exclusion). Exact names the executor's call.

`describe` is produced in plan 02. The existing `table_info`/`list_indexes`/`list_constraints`/
`list_columns`/`validate_identifiers` are NOT new — they are the analogs being mirrored.
</artifacts_this_phase_produces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add PRIMARY_KEY + FOREIGN_KEYS pg_catalog SQL constants and primary_key/foreign_keys methods on both classes</name>
  <files>pycopg/queries.py, pycopg/schema.py</files>
  <read_first>
    - pycopg/queries.py:129-139 — `LIST_CONSTRAINTS` (the `pg_constraint` JOIN `pg_class` JOIN `pg_namespace`
      WHERE `n.nspname = %s AND t.relname = %s` scaffold; copy this join/namespace-filter structure for the
      two new pg_catalog constants).
    - pycopg/queries.py:41-61 — `TABLE_INFO` / `GET_COLUMNS` (the `%s`-on-[schema, table] binding style).
    - pycopg/schema.py:642-674 — sync `list_indexes` + `list_constraints` (the
      `return self._db.execute(queries.CONSTANT, [schema, table])` list[dict] pattern; the dict style PK/FK mirror).
    - pycopg/schema.py:321-337 — sync `list_columns` (the reshape-rows-into-a-list pattern PK/FK use to build
      the `columns` lists from per-column rows).
    - pycopg/schema.py:1292-1324 — async `list_indexes` + `list_constraints` (the `await self._db.execute(...)`
      mirror to copy for the async twins).
    - pycopg/utils.py:107-122 — `validate_identifiers(*names)` (the guard called FIRST).
  </read_first>
  <behavior>
    - `primary_key('users')` -> `{'constraint_name': 'users_pkey', 'columns': ['id']}`.
    - `primary_key` on a composite-PK table -> `{'constraint_name': '...', 'columns': ['org_id', 'user_id']}`
      with columns in `conkey` (key) order, NOT alphabetical/ordinal-position order.
    - `primary_key` on a PK-less table (and on a nonexistent table) -> `None` (no extra round-trip, no error class).
    - `foreign_keys('orders')` -> `[{'constraint_name': 'orders_user_id_fkey', 'columns': ['user_id'],
      'referenced_table': 'users', 'referenced_columns': ['id']}]`.
    - `foreign_keys` on a table with a composite FK -> local `columns` and `referenced_columns` aligned in
      `conkey`/`confkey` order; multiple FKs -> multiple list entries.
    - `foreign_keys` on a table with no FKs (and on a nonexistent table) -> `[]`.
    - Each FK entry has EXACTLY the keys constraint_name, columns, referenced_table, referenced_columns —
      NO on_delete, on_update, or referenced_schema (deferred per D-02).
    - Async `primary_key`/`foreign_keys` return the identical shapes.
  </behavior>
  <action>
    In `pycopg/queries.py`, in the CONSTRAINT QUERIES section near `LIST_CONSTRAINTS` (line 129), add two new
    UPPER_SNAKE constants, both parameterized `%s` on `[schema, table]` (schema first, table second — matching
    `LIST_CONSTRAINTS`):
    `PRIMARY_KEY` — select the PK constraint for the table from `pg_constraint c` with `c.contype = 'p'`,
    joined to `pg_class t` / `pg_namespace n` filtered by `n.nspname = %s AND t.relname = %s`; unnest
    `c.conkey WITH ORDINALITY` and JOIN `pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = conkey_element`
    so column names come out in key order; return `c.conname AS constraint_name` and `a.attname AS column_name`,
    `ORDER BY` the conkey ordinality. (Exact SQL text is your discretion per D-05/Discretion, as long as
    identifiers are validated upstream, values bind as `%s`, columns are emitted in conkey order, and the
    method can reshape rows into the D-01 dict.)
    `FOREIGN_KEYS` — select every FK constraint for the table from `pg_constraint c` with `c.contype = 'f'`,
    same `n.nspname = %s AND t.relname = %s` filter; for each constraint emit `c.conname AS constraint_name`,
    the local column name (via `conkey` unnest-with-ordinality JOIN `pg_attribute` on `c.conrelid`), the
    referenced table name (`pg_class` on `c.confrelid` -> `referenced_table`), and the referenced column name
    (via `confkey` unnest-with-ordinality JOIN `pg_attribute` on `c.confrelid` -> aligned by the SAME
    ordinality so local/referenced columns pair up), `ORDER BY c.conname, conkey ordinality` for stable
    per-constraint column order. (Exact SQL your discretion; the method reshapes the flat rows into the D-02
    list[dict].)
    In `pycopg/schema.py`, append to `SchemaAccessor` (after `list_constraints`, before the
    `AsyncSchemaAccessor` class at line 677) and to `AsyncSchemaAccessor` (after async `list_constraints` at
    the end of file):
    `def primary_key(self, table: str, schema: str = "public") -> dict | None:` — `validate_identifiers(table,
    schema)` FIRST; `rows = self._db.execute(queries.PRIMARY_KEY, [schema, table])`; if no rows `return None`;
    else `return {'constraint_name': rows[0]['constraint_name'], 'columns': [r['column_name'] for r in rows]}`.
    `def foreign_keys(self, table: str, schema: str = "public") -> list[dict]:` — `validate_identifiers(table,
    schema)` FIRST; `rows = self._db.execute(queries.FOREIGN_KEYS, [schema, table])`; group the flat rows by
    `constraint_name` (preserving row order so columns stay in conkey order) into the D-02 entry shape
    (`constraint_name`, `columns` list, `referenced_table`, `referenced_columns` list); `return []` when there
    are no rows. The async twins are byte-for-byte the same with `rows = await self._db.execute(...)`.
    Numpydoc shallow docstrings (no Examples section — match `list_indexes`/`list_constraints` docstring style).
    All values bind as `%s`; never f-string/format a user value or unvalidated identifier into SQL.
  </action>
  <acceptance_criteria>
    - `pycopg/queries.py` contains `PRIMARY_KEY =` and `FOREIGN_KEYS =`; both use `pg_constraint` and bind
      `%s` (grep: `grep -n "PRIMARY_KEY =\|FOREIGN_KEYS =" pycopg/queries.py` returns both; neither constant
      contains a Python `%`-format or f-string of a user value).
    - `pycopg/schema.py` contains `def primary_key(` AND `async def primary_key(`, and `def foreign_keys(` AND
      `async def foreign_keys(` (grep shows the sync method once and the async twin once for each).
    - `primary_key` returns `{'constraint_name': ..., 'columns': [...]}` for a PK table and `None` for a PK-less
      table; composite PK columns come out in conkey order (asserted in Task 3 live-DB test).
    - Each `foreign_keys` entry has exactly the keys `constraint_name`, `columns`, `referenced_table`,
      `referenced_columns` (no `on_delete`/`on_update`/`referenced_schema`); `[]` for an FK-less table.
    - Both methods call `validate_identifiers(table, schema)` before any execute (grep: `validate_identifiers`
      appears in both `primary_key` and `foreign_keys` bodies).
    - `uv run pytest tests/test_parity.py -o addopts="" -q` passes (parity green once both classes have the methods).
    - `uv run ruff check pycopg/queries.py pycopg/schema.py` exits 0.
  </acceptance_criteria>
  <verify>
    <automated>uv run ruff check pycopg/queries.py pycopg/schema.py && uv run pytest tests/test_parity.py -o addopts="" -q</automated>
  </verify>
  <done>`PRIMARY_KEY`/`FOREIGN_KEYS` pg_catalog constants exist in queries.py; `primary_key` (dict|None, columns in conkey order) and `foreign_keys` (list[dict], core fields only, []-on-none) exist on BOTH SchemaAccessor and AsyncSchemaAccessor with identical signatures; identifiers validated, values `%s`-bound; parity green; ruff clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add SEQUENCES + VIEWS SQL constants and sequences/views methods on both classes</name>
  <files>pycopg/queries.py, pycopg/schema.py</files>
  <read_first>
    - pycopg/queries.py:25-34 — `LIST_TABLES` (the `information_schema.tables` WHERE `table_schema = %s`
      schema-only filter + ORDER BY; the model for the schema-scoped, single-`%s` SEQUENCES/VIEWS constants).
    - pycopg/schema.py:296-301 — sync `list_tables` (the `execute(queries.CONSTANT, [schema])` -> extract one
      column into a `list[str]` pattern: `return [r["table_name"] for r in result]`).
    - pycopg/schema.py:321-337 — sync `list_columns` (the same `list[str]` reshape, the D-03 precedent).
    - pycopg/schema.py (async `list_tables`, mirror of the sync one) — the `await self._db.execute(...)` form.
    - pycopg/utils.py:107-122 — `validate_identifiers(*names)` (the guard; here only `schema` is validated —
      these helpers take NO table arg).
  </read_first>
  <behavior>
    - `sequences('public')` -> `list[str]` of sequence names in the `public` schema (e.g. `['users_id_seq', ...]`),
      INCLUDING SERIAL/identity-backed sequences (they are real sequences). System schemas excluded naturally
      by the schema filter.
    - `sequences('some_other_schema')` -> only that schema's sequences (strict schema scoping per D-07).
    - `views('public')` -> `list[str]` of REGULAR view names in the schema, EXCLUDING materialized views.
    - A schema with no sequences/views -> `[]`.
    - Async `sequences`/`views` return identical lists.
  </behavior>
  <action>
    In `pycopg/queries.py` (a new SEQUENCE / VIEW QUERIES section, style-matching the existing section
    banners) add two UPPER_SNAKE constants, each parameterized `%s` on `[schema]` only (single param —
    these are schema-level, no table arg):
    `SEQUENCES` — `SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = %s
    ORDER BY sequence_name` (information_schema.sequences naturally includes SERIAL/identity-backed sequences
    and is scoped to the schema arg).
    `VIEWS` — a query returning REGULAR view names for the schema, EXCLUDING materialized views. Use
    `information_schema.views` (which naturally omits matviews) `WHERE table_schema = %s ORDER BY table_name`,
    OR `pg_catalog` with `relkind = 'v'` (matviews are `relkind = 'm'`, so they are excluded) — your call per
    D-05/D-07, as long as matviews are excluded and the result is schema-scoped.
    In `pycopg/schema.py`, append to `SchemaAccessor` (after the new `foreign_keys` from Task 1) and to
    `AsyncSchemaAccessor` (after its `foreign_keys`):
    `def sequences(self, schema: str = "public") -> list[str]:` — `validate_identifiers(schema)` FIRST;
    `result = self._db.execute(queries.SEQUENCES, [schema])`; `return [r["sequence_name"] for r in result]`
    (use the actual column alias your SQL emits).
    `def views(self, schema: str = "public") -> list[str]:` — `validate_identifiers(schema)` FIRST;
    `result = self._db.execute(queries.VIEWS, [schema])`; `return [r["..."] for r in result]` (the view-name
    column your SQL emits). Async twins identical with `await self._db.execute(...)`.
    NOTE: these helpers take NO `table` argument — only `schema` is validated, and the SQL binds a single
    `%s` on `[schema]`. Numpydoc shallow docstrings (no Examples). Values bind as `%s`; never interpolate.
  </action>
  <acceptance_criteria>
    - `pycopg/queries.py` contains `SEQUENCES =` and `VIEWS =`; `SEQUENCES` queries `information_schema.sequences`;
      `VIEWS` excludes materialized views (uses `information_schema.views` or `relkind = 'v'`); both bind a single
      `%s` on schema (grep: `grep -n "SEQUENCES =\|VIEWS =" pycopg/queries.py` returns both).
    - `pycopg/schema.py` contains `def sequences(` AND `async def sequences(`, and `def views(` AND
      `async def views(`; each signature is `(self, schema: str = "public")` (NO `table` arg).
    - `sequences`/`views` each call `validate_identifiers(schema)` before execute and return `list[str]`.
    - `views` result excludes materialized views (asserted in Task 3 live-DB test that creates a matview and a
      regular view and confirms only the regular view name is returned).
    - `uv run pytest tests/test_parity.py -o addopts="" -q` passes.
    - `uv run ruff check pycopg/queries.py pycopg/schema.py` exits 0.
  </acceptance_criteria>
  <verify>
    <automated>uv run ruff check pycopg/queries.py pycopg/schema.py && uv run pytest tests/test_parity.py -o addopts="" -q</automated>
  </verify>
  <done>`SEQUENCES`/`VIEWS` constants exist in queries.py (schema-scoped, single `%s`, matviews excluded from VIEWS); `sequences` and `views` (both `-> list[str]`, schema-only signature) exist on BOTH classes; identifiers validated, values `%s`-bound; parity green; ruff clean.</done>
</task>

<task type="auto">
  <name>Task 3: Tests for primary_key/foreign_keys/sequences/views (mock unit + live-DB integration)</name>
  <files>tests/test_database.py, tests/test_database_integration.py</files>
  <read_first>
    - tests/test_database.py:1044-1087 — `test_list_indexes` / `test_list_constraints` (the `@patch
      ("pycopg.database.psycopg")` mock_cursor.fetchall pattern; mirror it for mock-based PK/FK/seq/view tests
      with the EXACT new return shapes).
    - tests/test_database_integration.py:1-48 — the `db`, `temp_table_name`, `cleanup_table` fixtures (use these).
    - tests/test_database_integration.py:360-398 — `test_create_index`/`test_drop_index` (the CREATE TABLE
      autocommit=True → assert-against-real-DB pattern; copy for composite-PK/FK/matview live tests).
    - pycopg/schema.py — the new `primary_key`/`foreign_keys`/`sequences`/`views` bodies from Tasks 1-2
      (assert against their EXACT documented return shapes, D-01..D-03).
    - MEMORY note "pycopg-flaky-db-tests" — run targeted DB tests with `-o addopts=""`; the default
      `pycopg_test` DB may need `PGDATABASE=pycopg_test2` (see "pycopg-test-db-broken-timescaledb" memory).
  </read_first>
  <behavior>
    - Mock unit tests (no DB): `primary_key` reshapes constraint+column rows into `{'constraint_name', 'columns'}`;
      an empty fetchall -> `None`. `foreign_keys` groups rows into the D-02 entry shape; empty fetchall -> `[]`.
      `sequences`/`views` map rows to `list[str]`.
    - Live-DB tests: a single-column PK table -> `{'constraint_name': '<t>_pkey', 'columns': ['id']}`; a
      composite-PK table (`PRIMARY KEY (org_id, user_id)`) -> columns `['org_id', 'user_id']` in key order; a
      PK-less table -> `None`. An FK table -> one entry naming the local column, referenced table, referenced
      column; a no-FK table -> `[]`. `sequences` on a schema with a SERIAL table includes the `_id_seq`. `views`
      returns a created regular view's name but NOT a created materialized view's name. A nonexistent table ->
      `primary_key` None / `foreign_keys` [].
  </behavior>
  <action>
    Add mock-based unit tests to `tests/test_database.py` (near `TestDatabaseConstraints`, using the
    `@patch("pycopg.database.psycopg")` + `mock_cursor.fetchall.return_value = [...]` pattern from
    `test_list_constraints`): feed `primary_key` two constraint+column rows and assert the
    `{'constraint_name', 'columns': [...]}` shape; feed an EMPTY fetchall and assert `None`. Feed `foreign_keys`
    grouped rows and assert the D-02 entry keys exactly (`set(entry) == {'constraint_name', 'columns',
    'referenced_table', 'referenced_columns'}`); feed empty and assert `[]`. Feed `sequences`/`views` name rows
    and assert `list[str]`.
    Add live-DB tests to `tests/test_database_integration.py` using the `db`, `temp_table_name`,
    `cleanup_table` fixtures and the CREATE TABLE `autocommit=True` idiom (register every created table/view via
    `cleanup_table`): (1) single-PK table -> assert columns `['id']` and a non-None `constraint_name`;
    (2) composite-PK table (`PRIMARY KEY (org_id, user_id)`) -> assert `columns == ['org_id', 'user_id']` (key
    order); (3) PK-less table -> assert `primary_key(...) is None`; (4) FK table referencing the PK table ->
    assert one entry with the right `referenced_table`/`referenced_columns`; (5) no-FK table -> assert
    `foreign_keys(...) == []`; (6) `sequences('public')` includes the SERIAL table's `<t>_id_seq`; (7) create a
    regular view AND a materialized view, assert `views('public')` contains the regular view name and does NOT
    contain the matview name; (8) `primary_key`/`foreign_keys` on a nonexistent table name -> `None`/`[]`. Use
    unique `temp_table_name`-derived names to avoid collisions and clean them up.
    Do NOT add async tests here if `test_accessor_parity` already covers async surface — but if the project's
    live async tests live in `tests/test_async_database.py`, add async equivalents there mirroring the sync ones.
  </action>
  <acceptance_criteria>
    - `tests/test_database.py` contains a mock-based test asserting `primary_key` returns the
      `{'constraint_name', 'columns'}` dict AND a separate assertion that an empty result -> `None`.
    - `tests/test_database.py` contains a mock-based test asserting a `foreign_keys` entry's key set is exactly
      `{'constraint_name', 'columns', 'referenced_table', 'referenced_columns'}` AND empty -> `[]`.
    - `tests/test_database_integration.py` contains a composite-PK test asserting column key-order
      (`['org_id', 'user_id']`) and a matview-exclusion test asserting the regular view is listed and the matview is not.
    - `uv run pytest tests/test_database.py -o addopts="" -q -k "primary_key or foreign_keys or sequences or views"` passes.
    - `uv run pytest tests/test_database_integration.py -o addopts="" -q -k "primary_key or foreign_keys or sequences or views"` passes (against the live DB; use `PGDATABASE=pycopg_test2` if the default DB is broken per memory).
    - `uv run pytest tests/test_parity.py -o addopts="" -q` passes.
    - `uv run ruff check pycopg tests` exits 0.
  </acceptance_criteria>
  <verify>
    <automated>uv run ruff check pycopg tests && uv run pytest tests/test_database.py tests/test_parity.py -o addopts="" -q -k "primary_key or foreign_keys or sequences or views or accessor_parity"</automated>
  </verify>
  <done>Mock unit tests (shape + None/[] edges) and live-DB tests (composite PK/FK key-order, schema scoping, matview exclusion, nonexistent-table None/[]) for all four helpers pass; parity green; ruff clean.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| caller -> db.schema.* | The `table` and `schema` arguments are caller-supplied identifiers that reach SQL. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-35-01 | Tampering | `primary_key`/`foreign_keys`/`sequences`/`views` identifier args (`table`, `schema`) | mitigate | `validate_identifiers(...)` called FIRST in every method (before any execute); all user values bound as `%s` parameters on `[schema, table]` / `[schema]` — SQL text is a static UPPER_SNAKE constant in `queries.py`, never f-string/format-interpolated with a user value. |
| T-35-02 | Information Disclosure | read-only catalog introspection | accept | Read-only `pg_catalog`/`information_schema` queries scoped to the caller's schema arg; no DDL, no data rows exposed, no new network/file I/O, no auth surface. Caller already holds a connection. |

No high-severity threats: this phase is read-only introspection — no DDL, no destructive predicates, no new
exception class, no new dependencies, no new network/file I/O.
</threat_model>

<verification>
- `uv run pytest tests/test_parity.py -o addopts="" -q` — `test_accessor_parity` green (INTRO-06/D-08).
- `uv run pytest tests/test_database.py tests/test_database_integration.py -o addopts="" -q -k "primary_key or foreign_keys or sequences or views"` — all new-helper tests pass.
- `uv run ruff check pycopg tests` exits 0.
- Coverage ratchet held ≥94% (verified at end-of-phase / release gate).
</verification>

<success_criteria>
- `db.schema.primary_key(table, schema)` returns `{'constraint_name', 'columns': [...]}` (key order) or `None` (INTRO-01).
- `db.schema.foreign_keys(table, schema)` returns `list[dict]` with the exact 4 core keys, `[]` when none (INTRO-02).
- `db.schema.sequences(schema)` and `db.schema.views(schema)` return schema-scoped `list[str]`; views excludes matviews (INTRO-03, INTRO-04).
- All four methods exist identically on `AsyncSchemaAccessor`; `test_accessor_parity` passes (INTRO-06).
</success_criteria>

<output>
Create `.planning/phases/35-schema-introspection/35-01-SUMMARY.md` when done.
</output>
