# Phase 26: Incremental ETL — Pure Layer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-20
**Phase:** 26-incremental-etl-pure-layer
**Areas discussed:** Watermark JSONB envelope, Subquery wrap & alias, Builder API shape, Validation guard & errors

---

## Watermark JSONB envelope

### Envelope shape
| Option | Description | Selected |
|--------|-------------|----------|
| Typed envelope object | `{"type":..,"value":..}` self-describing, unambiguous datetime vs text | ✓ |
| Raw JSON scalar | Store value directly; datetime/text ambiguous on read | |

**User's choice:** Typed envelope object.

### Datetime serialization
| Option | Description | Selected |
|--------|-------------|----------|
| ISO 8601 via isoformat() | Lossless round-trip, stdlib-only, preserves offset | ✓ |
| Normalize to UTC first | Canonical but mutates offset + forces naive policy now | |

**User's choice:** ISO 8601 via isoformat() (after follow-up).
**Notes:** User stated a preference for not mixing naive/aware datetime formats — tends to use only aware datetimes. Resolved with a follow-up: lock isoformat (preserve offset, no UTC mutation) and document the aware-only contract, enforcing any naive-rejection policy later in the live-extract phase (27/28) rather than baking value-policy into the pure serializer. User confirmed: "Yes — isoformat + doc the aware-only contract."

### Type guards
| Option | Description | Selected |
|--------|-------------|----------|
| Strict allowlist + clear raise | `{datetime, int (no bool), str}`; other types -> ETLError | ✓ |
| Allowlist + permit float | Adds float now; precision caveats, not in ETL-INC-10 | |

**User's choice:** Strict allowlist + clear raise.
**Notes:** `bool` excluded (subclass-of-int trap, already guarded for `extract_limit`).

### JSONB adapter placement
| Option | Description | Selected |
|--------|-------------|----------|
| _encode returns bare dict; Jsonb wrap at write-site (P27) | Pure, DB-free, unit-testable; adapter in Phase 27 | ✓ |
| _encode returns Jsonb-wrapped object | Couples pure fn to psycopg; asymmetric encode/decode | |

**User's choice:** _encode returns bare dict; Jsonb wrap at write-site (Phase 27).

---

## Subquery wrap & alias

### Alias name
| Option | Description | Selected |
|--------|-------------|----------|
| Fixed reserved alias `_pycopg_inc` | Deterministic, greppable, collision-safe by convention | ✓ |
| Generic short alias `sub` | Matches PROJECT.md sketch but less obviously library-internal | |

**User's choice:** Fixed reserved alias `_pycopg_inc`.

### SQL hygiene (trailing ; / comments)
| Option | Description | Selected |
|--------|-------------|----------|
| Strip trailing ; and whitespace; defer comments | Safe common case, no SQL parser; comments = caller responsibility | ✓ |
| Newline-wrap to neutralize comments too | Belt-and-suspenders, still no parser | |

**User's choice:** Strip trailing ; and whitespace; defer comments.
**Notes:** Newline-before-WHERE is recorded as a free hardening the planner may apply, but the contract does not promise to neutralize trailing line-comments — no SQL parser is introduced.

### Table-source form
| Option | Description | Selected |
|--------|-------------|----------|
| SELECT * FROM schema.table WHERE col > %s | Full qualified SELECT, validated identifiers | ✓ |
| Wrap table same as SQL source | Unnecessary subquery nesting for a plain table | |

**User's choice:** SELECT * FROM schema.table WHERE col > %s.

### Column emit
| Option | Description | Selected |
|--------|-------------|----------|
| Bare, validated (match existing builders) | Consistent with build_truncate_sql etc. | ✓ |
| Double-quote the column | Supports mixed-case/reserved words but inconsistent with module | |

**User's choice:** Bare, validated (match existing builders).

---

## Builder API shape

### Builder structure
| Option | Description | Selected |
|--------|-------------|----------|
| One builder dispatching on _is_sql_source | Single entry point; classification internal | ✓ |
| Two builders + caller chooses | More granular but pushes branch to caller | |

**User's choice:** One builder dispatching on _is_sql_source.

### First-run (None watermark)
| Option | Description | Selected |
|--------|-------------|----------|
| watermark=None -> full SELECT, no WHERE | One code path for first + subsequent runs | ✓ |
| Builder always filters; caller skips on first run | Splits first-run logic into DB-side caller | |

**User's choice:** watermark=None -> full SELECT, no WHERE.

### Naming & return contract
| Option | Description | Selected |
|--------|-------------|----------|
| Private _build_incremental_extract_sql, (sql, params) | Internal helper tier, uniform 2-tuple | ✓ |
| Public build_incremental_extract_sql | Over-exposes an internal operation | |

**User's choice:** Private _build_incremental_extract_sql, (sql, params); encode/decode also private.

### max(col) scope
| Option | Description | Selected |
|--------|-------------|----------|
| Out of Phase 26 — stays in 28 | Respects traceability; runtime concern | ✓ |
| Add a pure _max_watermark helper now | Front-loads ETL-INC-04 scope | |

**User's choice:** Out of Phase 26 — stays in 28.

---

## Validation guard & errors

### Guard shape
| Option | Description | Selected |
|--------|-------------|----------|
| Module-level _validate_incremental helper | Mirrors _validate_load_mode; unit-testable | ✓ |
| Inline in __post_init__ | Breaks the extract-a-helper precedent | |

**User's choice:** Module-level _validate_incremental helper.

### Guard scope
| Option | Description | Selected |
|--------|-------------|----------|
| Both, combo-check then identifier-check | Cohesive; intent error before syntax error | ✓ |
| Combo only; identifier-check inline | Splits validation across two spots | |

**User's choice:** Both, combo-check then identifier-check (None short-circuits).

### Error text
| Option | Description | Selected |
|--------|-------------|----------|
| Explain + prescribe upsert, cite ETL-INC-01 | Actionable + traceable | ✓ |
| Terse statement of the rule | Drops rationale + tag | |

**User's choice:** Explain + prescribe upsert, cite ETL-INC-01.

### Call order in __post_init__
| Option | Description | Selected |
|--------|-------------|----------|
| After load_mode validation, before upsert/extract_limit | Deliberate dependency order | ✓ |
| Last, after all existing checks | Ordering incidental | |

**User's choice:** After load_mode validation, before upsert/extract_limit.

---

## Claude's Discretion

- Exact docstring wording for the `incremental_column` Parameter entry + watermark-column requirements note (numpydoc shallow style; full usage docs are Phase 28).
- One-line vs multi-line emit of the subquery wrap (formatting).
- Unit-test placement (extend `tests/test_etl.py` vs new module) — follow existing DB-free builder-test pattern.
- Whether the unsupported-type raise uses base `ETLError` or a new subclass (planner's call).

## Deferred Ideas

- `max(incremental_column)` extraction + missing-column ETLError → Phase 28 (ETL-INC-04).
- `float` watermark support → not in v0.7.0 (additive later).
- Mixed-case / reserved-word column quoting → module-wide change, revisit globally if needed.
- `initial_watermark` first-run bound → v0.8.0 (ETL-INC-F01).
- Naive-datetime rejection policy → live-extract phase (27/28), not the pure layer.
