# Phase 32: Query Helpers & Parity Verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-23
**Phase:** 32-Query Helpers & Parity Verification
**Areas discussed:** into= routing + bucket column, Builder/file structure, gapfill validation/guards, TS-ADV-10 parity proof

---

## into= routing + bucket column

### Bucket column source
| Option | Description | Selected |
|--------|-------------|----------|
| Builder injects AS bucket | Builder always renders `time_bucket(...) AS bucket`; deterministic, matches ROADMAP wording | ✓ |
| User controls alias | User writes the time_bucket expression/alias themselves; more flexible but puts the `bucket`-column contract on the user | |

**User's choice:** Builder injects AS bucket → **D-01**

### into="df" execution path
| Option | Description | Selected |
|--------|-------------|----------|
| Reuse _to_named_binds→to_dataframe | Convert %s→:p0 binds, call to_dataframe(sql, params=dict); mirrors spatial._run; resolves milestone open Q | ✓ |
| Build DataFrame from rows | execute() + pd.DataFrame(rows); bypasses to_dataframe, diverges from spatial precedent | |

**User's choice:** Reuse _to_named_binds→to_dataframe → **D-02**

### into= guard / valid set
| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated check, df default | timescale-local valid set (df,rows), default df; ValueError before SQL catches gdf | ✓ |
| Reuse spatial _check_into as-is | spatial's set is (rows,gdf) — would reject df, accept gdf; wrong | |

**User's choice:** Dedicated check, df default → **D-03**

### where clause
| Option | Description | Selected |
|--------|-------------|----------|
| Optional %s-param WHERE | Optional structural-SQL fragment; gapfill always has start/finish range, extra where ANDs on | ✓ |
| Defer where to a follow-up | Rejected — REQ TS-ADV-06/07 both list where=None in scope | |

**User's choice:** Optional %s-param WHERE → **D-04**

---

## Builder/file structure

### Builder location
| Option | Description | Selected |
|--------|-------------|----------|
| Module-level pure builders in timescale.py | `_build_time_bucket_sql` + `_build_time_bucket_gapfill_sql`; testable, thin method bodies | ✓ |
| Inline SQL in the methods | Duplicates SQL across sync+async (4 copies), harder to test | |

**User's choice:** Module-level pure builders → **D-05**

### Shared routing helpers
| Option | Description | Selected |
|--------|-------------|----------|
| Local copies in timescale.py | Local _to_named_binds + _check_into (df/rows) + _run; self-contained, no cross-accessor import | ✓ |
| Import from spatial.py | Creates timescale→spatial private-helper dependency; _check_into not reusable anyway | |
| Promote to utils.py | Cleanest DRY but touches spatial.py (out of file scope), a refactor beyond this phase | |

**User's choice:** Local copies in timescale.py → **D-06**

### Async df routing
| Option | Description | Selected |
|--------|-------------|----------|
| Mirror spatial async _run | await to_dataframe / await execute; audit await on ext guard (Phase-23 gotcha) | ✓ |
| Decide at plan time | Risk of recurring missing-await gotcha; better locked now | |

**User's choice:** Mirror spatial async _run → **D-07**

---

## gapfill validation/guards

### License / live-test strategy
| Option | Description | Selected |
|--------|-------------|----------|
| Real live assertions, no license try/except | time_bucket/gapfill/locf/interpolate are Apache-free → assert real output; spatial-style two-layer, NOT Phase-31 pattern | ✓ |
| License-tolerant like Phase 31 | Wrap in try/except FeatureNotSupported; weaker coverage if gapfill is free (expected) | |

**User's choice:** Real live assertions, no license try/except → **D-08**

### Pre-flight guards
| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: identifiers + required args | Validate identifiers + required start/finish; no start<finish, no locf heuristic; DB raises on bad usage | ✓ |
| Add semantic guards | start<finish + locf-presence heuristic; risks false-rejecting valid plain-aggregate gapfill | |

**User's choice:** Minimal: identifiers + required args → **D-09**

### start/finish binding
| Option | Description | Selected |
|--------|-------------|----------|
| Bind in both places as %s | start/finish bound in gapfill() args AND WHERE range (passed twice); structurally-correct gapfill | ✓ |
| Decide exact SQL at plan time | Lock the contract now, leave exact template (named vs positional, WHERE inclusivity) to planner | (partial — exact template to live-verify) |

**User's choice:** Bind in both places as %s → **D-10** (exact template details to live-verify per planner)

---

## TS-ADV-10 parity proof

### Parity proof thoroughness
| Option | Description | Selected |
|--------|-------------|----------|
| Rely on existing parity test + count assertion | Trust test_accessor_parity (set-diff both directions) + add explicit 9-method-name set assertion | ✓ |
| Just the existing test | Adds nothing; 9-method contract not explicitly pinned | |
| Full per-method signature parity | Strongest but a new pattern beyond Phase 32 scope | |

**User's choice:** Rely on existing parity test + count assertion → **D-11**

### Coverage interpretation
| Option | Description | Selected |
|--------|-------------|----------|
| Cover Phase 32 lines; verify 94% ratchet holds | Phase 32 adds no autocommit code; the autocommit-branch clause is inherited Phase-31 wording | ✓ |
| Re-audit all 9 methods' autocommit coverage | Largely re-checks already-verified Phase-31 work | |

**User's choice:** Cover Phase 32 lines; verify 94% ratchet holds → **D-12**

---

## Claude's Discretion

- Exact module-level builder names and `_run` signature shape.
- Exact ValueError / docstring wording for the into= guard and gapfill required-args.
- Whether a `queries.py` SQL constant is warranted (likely inlined).
- Precise gapfill SQL template (named vs positional gapfill args, WHERE bound inclusivity) — live-verify.
- Aggregate-output column naming beyond the fixed `bucket` alias.

## Deferred Ideas

- `into="query"` (return built SQL/params) — mirrors spatial's deferral.
- Semantic gapfill guards (start<finish, locf-presence) — intentionally omitted (D-09).
- Per-method signature-level parity — beyond scope (D-11).
- Promoting `_to_named_binds` to `utils.py` — would touch spatial.py, out of file scope (D-06).
- Docs / CHANGELOG / version bump / release gates — Phase 33 (REL-08).
