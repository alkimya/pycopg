# Phase 50: CRUD + Introspection Follow-ups - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-03
**Phase:** 50-crud-introspection-follow-ups
**Areas discussed:** Raw-SQL escape hatch, Keyset pagination, Page envelope, Introspection output

---

## Raw-SQL escape hatch (CRUD-F01)

### Param shape / naming
| Option | Description | Selected |
|--------|-------------|----------|
| `where_sql` + `where_params` | Two keyword args; mirrors `execute(sql, params)` idiom | ✓ |
| `where_sql` tuple | One atomic `(fragment, params)` arg; can't desync but diverges from house idiom | |

**User's choice:** where_sql + where_params

### Composition with dict `where`
| Option | Description | Selected |
|--------|-------------|----------|
| Mutually exclusive | Pass one or the other; ValueError if both. Restrictive-first, widenable later | ✓ |
| Compose with AND | `WHERE (dict) AND (raw)`; more ergonomic but more precedence/guard surface to freeze | |

**User's choice:** Mutually exclusive
**Notes:** AND-composition and the tuple form both captured as future non-breaking widenings in Deferred Ideas.

---

## Keyset pagination (CRUD-F02)

### Surface
| Option | Description | Selected |
|--------|-------------|----------|
| New `paginate_keyset()` | Dedicated method parallel to `paginate()`; own tight signature | ✓ |
| New `seek()` | Same, textbook name; less discoverable next to `paginate()` | |
| `method=` mode on `paginate()` | One entry point but two models tangle in one signature | |

**User's choice:** New paginate_keyset()

### Cursor representation
| Option | Description | Selected |
|--------|-------------|----------|
| Explicit `after=` tuple | Transparent, no wire format to freeze; envelope's next_cursor is the last key tuple | ✓ |
| Opaque encoded token | Cleaner one-arg surface but adds encode/decode + a frozen format | |
| Both | after= tuples AND an opaque token; most surface | |

**User's choice:** Explicit after= tuple

### Ordering key / tiebreaker
| Option | Description | Selected |
|--------|-------------|----------|
| Require explicit `order_by` | Mandatory; user owns unique/total order; row-value compare `(c1,c2) > (%s,%s)`; no hidden round-trip | ✓ |
| Auto-append primary key | "Just works" but needs a PK-introspection round-trip + hidden behavior | |

**User's choice:** Require explicit order_by

### Direction
| Option | Description | Selected |
|--------|-------------|----------|
| Forward-only + descending | `after=` walks forward; `descending` flips comparison; `before=` deferred | ✓ |
| Bidirectional | Both after= and before=; doubles the logic to lock into 1.0 now | |

**User's choice:** Forward-only + descending

---

## Page envelope (CRUD-F03)

### Envelope type
| Option | Description | Selected |
|--------|-------------|----------|
| Frozen dataclass `Page` | Typed attribute access; mirrors the `RunResult` precedent | ✓ |
| Plain dict | Zero new type but untyped, inconsistent with RunResult | |
| TypedDict | Typed keys, dict access; middle ground | |

**User's choice:** Frozen dataclass Page

### Offset envelope surface
| Option | Description | Selected |
|--------|-------------|----------|
| New `paginate_page()` sibling | Leaves `paginate()` untouched; no return-type overload; symmetric with keyset | ✓ |
| `envelope=` flag on `paginate()` | One method but a bool that switches return type — call-site smell | |
| Keyset-only envelope | Offset stays list-only; minimal but no offset has_next convenience | |

**User's choice:** New paginate_page() sibling

### total cost
| Option | Description | Selected |
|--------|-------------|----------|
| Opt-in `with_total` | Default off; has_next always cheap (limit+1 trim); COUNT(*) only on request | ✓ |
| Always compute total | Simpler model but every page pays a COUNT(*) | |

**User's choice:** Opt-in with_total

---

## Introspection output (INTRO-F01 + INTRO-F02)

### describe() structured surface (INTRO-F01)
| Option | Description | Selected |
|--------|-------------|----------|
| `into=` param | `describe(into='dict'|'dataclass'|'dataframe')`, dict default; matches house convention | ✓ |
| Separate methods | `describe_dataclass()`/`describe_dataframe()`; proliferates methods | |

**User's choice:** into= param

### describe() forms / DataFrame semantics (INTRO-F01)
| Option | Description | Selected |
|--------|-------------|----------|
| Both (DF = columns) | dataclass = full `TableDescription`; dataframe = columns section (the tabular part) | ✓ |
| Dataclass only | Full typed snapshot; skip DataFrame | |
| DataFrame only | Columns-as-frame; skip the typed snapshot | |

**User's choice:** Both (DF = columns)

### Matview surface (INTRO-F02)
| Option | Description | Selected |
|--------|-------------|----------|
| Two parallel methods | `materialized_views()` (names) + `materialized_view_columns()` (pg_catalog); parallel to table introspection | ✓ |
| One rich method | `materialized_views()` returns name+columns objects; fewer calls, diverges from views() | |

**User's choice:** Two parallel methods
**Notes:** Verified during discussion that `information_schema.columns` excludes matviews → a dedicated `pg_catalog` query is required (can't reuse `table_info`).

### Matview metadata (INTRO-F02)
| Option | Description | Selected |
|--------|-------------|----------|
| Names + columns only | Mirror table introspection; defer ispopulated/definition/size | ✓ |
| Add ispopulated | Also surface the populated/needs-REFRESH flag; more surface to lock in | |

**User's choice:** Names + columns only

---

## Claude's Discretion

- Exact new `queries.*` constant names/placement (keyset row-value builder, matview list + matview-columns pg_catalog queries).
- The `@overload` stub set for `describe(into=...)` and the `Page`-returning methods.
- Whether the keyset row-value builder is a fresh helper or extends an existing WHERE builder.
- `has_next` limit+1 trim mechanics; where `Page`/`TableDescription` slot into `__init__.py` exports + api-reference.
- Test layering (mock SQL-shape + live-DB integration; injection test per new builder path); `PGDATABASE=pycopg_test3`.

## Deferred Ideas

- AND-composition of dict `where` + raw `where_sql` (future non-breaking widening).
- Opaque/encoded keyset cursor token over the explicit `after=` tuples.
- Bidirectional keyset (`before=` / backward paging).
- Matview-specific metadata (`ispopulated`, `definition`, size) and per-column dataclass nesting for describe.
- Auto-PK tiebreaker for keyset (rejected to avoid a hidden round-trip).
- Already tracked milestone deferrals: SPAT-F01 (gridSize), RASTER-F01 (raster), ETL-INC-F05 (CDC).
