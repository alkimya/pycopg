---
phase: 49
slug: incremental-etl-follow-ups
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-03
---

# Phase 49 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|----------------|
| consuming app → `Pipeline(initial_watermark=, incremental_inclusive=, incremental_lookback=, incremental_column=, concurrency=)` | Developer-set pipeline config that flows into the extract SQL WHERE clause and the advisory-lock key | Watermark scalars/tuples (bound values), column identifiers (structural), boundary operator (literal from bool), lock key source (pipeline name) |
| `run()` watermark read/seed/lookback arithmetic → `_build_incremental_extract_sql`/`_do_extract` → PostgreSQL | The resolved read floor (seeded, lookback-adjusted, single or composite) becomes the `WHERE col {>|>=} %s` / `WHERE (c1,c2) {>|>=} (%s,%s)` bound value(s) | Bound watermark value(s) |
| raw extract batch (pandas) → `_capture_watermark` → `_encode_watermark`/`_encode_composite_watermark` → `pipeline_runs.watermark` JSONB | The recorded high-water mark (scalar or composite tuple) is type-checked per element and persisted as a typed envelope | Encoded watermark envelope (JSONB) |
| `run()` → dedicated advisory-lock connection → PostgreSQL `pg_advisory_lock`/`pg_try_advisory_lock`/`pg_advisory_unlock` | Session-scoped mutual-exclusion primitive keyed on the pipeline name, derived server-side | Bound pipeline name; server-derived `bigint` lock key |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-49-01-01 | Tampering | `initial_watermark` value reaching the extract SQL | mitigate | The seed value flows through the existing watermark-bind discipline: `_build_incremental_extract_sql` emits a positional `%s` (`pycopg/etl.py:817-839`), reconciled to a named `:wm` bind by `_reconcile_watermark_binds` (`:1131-1171`) before `_do_extract` calls `to_dataframe` (sync `:1587`, async `:2366`) — never f-string interpolated. Proven by `tests/test_etl.py::TestBuildIncrementalExtractSql`/`TestAdvisoryLock` reconciliation cases and live-DB `TestInitialWatermark` seed-sequence tests in `tests/test_etl_accessor.py` | closed |
| T-49-01-02 | Denial of Service | Oversized seeded re-scan | accept | Construction-time operator config, bounded by `extract_limit`, not untrusted end-user input. See Accepted Risks Log | closed |
| T-49-02-01 | Tampering | Lookback-adjusted floor reaching the extract SQL | mitigate | `_apply_lookback` (`pycopg/etl.py:843-894`) performs the subtraction in Python and returns a plain `datetime`/`int`; the result is bound identically to any other floor via the `%s`/`:wm` path (T-49-01-01 mechanism). The comparison operator is `op = ">=" if inclusive else ">"` (`:818`) — a literal chosen from a `bool`, never user text. Verified: `grep` shows no f-string with `pipeline.incremental_lookback`/`wm`/`read_floor` interpolated into SQL | closed |
| T-49-02-02 | Tampering | Column identifier in the `>=` clause | mitigate | `validate_identifiers(column)` (scalar) / `validate_identifiers(*cols)` (composite) is executed as the first statements of `_build_incremental_extract_sql` (`pycopg/etl.py:804-811`), before the `inclusive`-parametrized `op` is substituted. Proven by `tests/test_etl.py::TestBuildIncrementalExtractSql` injection cases | closed |
| T-49-02-03 | Denial of Service | Oversized lookback overlap re-scan | accept | Construction-time operator config bounded by `extract_limit`; the overlap replay is an intended idempotent no-op (D-08). See Accepted Risks Log | closed |
| T-49-03-01 | Tampering | Composite column name injected into `(c1, c2) > (...)` | mitigate | `validate_identifiers(*cols)` runs over every composite element as the first statement of `_build_incremental_extract_sql` (`pycopg/etl.py:808-810`), before any interpolation. Proven by `tests/test_etl.py::TestAdvisoryLock::test_composite_builder_validates_every_element` and `TestCompositeWatermark::test_bad_composite_element_raises` (both assert `InvalidIdentifierError`) | closed |
| T-49-03-02 | Tampering | Composite watermark values in the WHERE clause | mitigate | Each element is bound as its own `%s` — `params: list[Any] = list(wm_seq)` (`pycopg/etl.py:822-825`) — never interpolated. Proven by `tests/test_etl.py::TestAdvisoryLock::test_composite_builder_table_source`/`test_composite_builder_sql_source` (assert `params == [5, 40]`) | closed |
| T-49-03-03 | Tampering | Bool/float smuggled into a composite watermark envelope | mitigate | `_encode_composite_watermark` (`pycopg/etl.py:950-983`) reuses the frozen per-scalar `_encode_watermark` element-wise (`[_encode_watermark(v) for v in values]`) — bool-before-int / float-reject holds per element, never a bulk `isinstance`. Proven by `tests/test_etl.py::TestCompositeWatermark::test_composite_seed_bool_element_raises` (construction) and the composite-with-bool encode raise assertions in `TestAdvisoryLock`/`TestEncodeDecodeWatermark` | closed |
| T-49-03-04 | Information Disclosure | Corrupted/unknown envelope tag | mitigate | `_decode_scalar_watermark` raises `ETLError` on any tag other than `'datetime'`/`'int'`/`'str'` (`pycopg/etl.py:1020-1034`); `_decode_watermark` routes `'composite'` through this same guard per element (`:1014-1017`). Proven by `tests/test_etl.py::TestEncodeDecodeWatermark::test_unknown_tag_still_raises` | closed |
| T-49-04-01 | Tampering | Composite watermark elements in the extract WHERE | mitigate | `_reconcile_watermark_binds` maps each positional `%s` to its own named bind (`:wm0`, `:wm1`, …), searching from the right so a literal `%s` embedded in a user SQL source is left untouched (WR-01 fixed in `c0ea441`) — `pycopg/etl.py:1131-1171`. Proven by `tests/test_etl.py::TestAdvisoryLock::test_reconcile_composite_maps_distinct_named_binds` and `test_reconcile_composite_leaves_literal_percent_s_in_source` | closed |
| T-49-04-02 | Tampering / Correctness | Fabricated composite max tuple silently skipping rows | mitigate | `_capture_watermark` (`pycopg/etl.py:1082-1128`) sorts the raw batch by the key columns and takes `.iloc[-1]` per column — the true greatest ROW, never per-column maxes. Proven by unit test `tests/test_etl.py::TestAdvisoryLock::test_capture_composite_is_sorted_last_row_not_per_column_max` (asserts `(2, 1)` not `(2, 99)`) AND the live-DB `tests/test_etl_accessor.py::TestCompositeWatermarkLive::test_records_true_max_row_not_per_column_max` (`result.watermark_recorded == (2, 1)`) | closed |
| T-49-04-03 | Correctness | NaN element in composite max ROW voiding rows on next extract | mitigate | `_capture_watermark`'s composite branch applies `_coerce_watermark_scalar`'s `pd.isna` guard per element and returns `None` for the WHOLE tuple if any element is NaN (`pycopg/etl.py:1125-1127`) — the prior watermark is preserved (never advanced on a corrupted capture). Proven by `tests/test_etl.py::TestAdvisoryLock::test_capture_composite_nan_element_voids_watermark` | closed |
| T-49-04-04 | Tampering | Bool/float composite element reaching the persisted envelope | mitigate | The recorded tuple is encoded via `_encode_watermark_value` → `_encode_composite_watermark`, reusing the per-element `_encode_watermark` allowlist (`pycopg/etl.py:1042-1055`, `:950-983`) BEFORE `_end_run` persists it (sync `:2019-2026`, async `:2775-2782`) | closed |
| T-49-05-01 | Tampering | Pipeline name used as the advisory-lock key | mitigate | `ETL_ADVISORY_LOCK`/`_TRY_LOCK`/`_UNLOCK` (`pycopg/queries.py:410-412`) each embed exactly one `%s` inside `hashtextextended(%s, 0)`; `run()` always calls `cur.execute(queries.ETL_ADVISORY_*, [pipeline.name])` (sync `:1655,1671,1679`; async `:2424,2440,2447`) — never string-formats the name into the SQL. Proven by `tests/test_etl.py::TestAdvisoryLock::test_advisory_constants_never_contain_name_text` and `test_each_advisory_constant_has_exactly_one_placeholder` | closed |
| T-49-05-02 | Spoofing / Correctness | Non-deterministic lock key defeating cross-process serialization | mitigate | The key is derived server-side via SQL `hashtextextended(name, 0)` — `grep` over `pycopg/etl.py` confirms no Python `hash()` call is used for the lock key anywhere in the module (the only key-derivation path is the three `ETL_ADVISORY_*` constants) | closed |
| T-49-05-03 | Denial of Service | Orphaned advisory lock from a crashed run | mitigate | The lock is acquired on a DEDICATED autocommit connection (sync `:1652`, async `:2421`), released in an explicit `finally` (sync `:1674-1681`, async `:2441-2450`), and the `with`/`async with` block additionally closes the connection on any exit path — PostgreSQL auto-releases session-level advisory locks on disconnect. Proven live by `tests/test_etl_accessor.py::TestAdvisoryLockLive::test_crash_mid_run_releases_lock` (a mid-run `ETLTransformError` is raised, then a second session's `pg_try_advisory_lock` succeeds) | closed |
| T-49-05-04 | Denial of Service | Transaction-scoped lock leaving the watermark-read/extract race open | mitigate | `ETL_ADVISORY_LOCK`/`_TRY_LOCK`/`_UNLOCK` use `pg_advisory_lock`/`pg_try_advisory_lock`/`pg_advisory_unlock` (session-scoped) — `grep -n "xact_lock" pycopg/etl.py pycopg/queries.py` returns no matches, confirming `pg_advisory_xact_lock` is never used. The lock wrap in `run()` spans from before `_read_watermark`/`_start_run` through `_end_run` (sync `:1647-1681`, async `:2419-2450`), covering the full read→extract→load→record span, not just the load transaction | closed |
| T-49-05-05 | Tampering | `'skipped'` transient status corrupting run-log state | mitigate | The `"skip"`-when-held branch returns a `RunResult(status="skipped", run_id=None, ...)` and returns BEFORE `self.init()`/`self._start_run()` are ever called (sync `:1653-1668`, async `:2422-2437`) — no `pipeline_runs` row is written; `queries.ETL_INIT_PIPELINE_RUNS`'s `status` CHECK constraint is unchanged (`'running','success','failed'` only). Proven by `tests/test_etl.py::TestAdvisoryLock::test_status_check_constraint_unchanged` and live-DB `tests/test_etl_accessor.py::TestAdvisoryLockLive::test_skip_when_held_returns_skipped_and_writes_no_row` (asserts `COUNT(*) == 0` for the pipeline, then `== 1` after the lock is released and a normal run completes) | closed |
| T-49-SC | Tampering | Supply-chain / package installs | accept | Zero new runtime/dev dependencies across all 5 plans — confirmed via `git diff 2ad153c..HEAD --stat -- pyproject.toml uv.lock` (no output, no changes). Every function used (`pg_advisory_lock`, `pg_try_advisory_lock`, `pg_advisory_unlock`, `hashtextextended`) is a core PostgreSQL `pg_catalog` built-in. See Accepted Risks Log | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

### Corroboration notes

- Sync/async parity verified directly (not just trusted from docs): `ETLAccessor.run`/`_run_impl`/`_do_extract` (`pycopg/etl.py:1614-2032`) and `AsyncETLAccessor.run`/`_run_impl`/`_do_extract` (`:2393-2788`) were read side-by-side — identical watermark-bind, composite-capture, and advisory-lock placement in both. All four `run()`-adjacent mitigations (T-49-01-01, T-49-02-01, T-49-04-01/02/03/04, T-49-05-01..05) were checked against BOTH accessors, not just the sync one.
- No `## Threat Flags` section found in any of `49-01-SUMMARY.md` through `49-05-SUMMARY.md` — no unregistered new attack surface reported by any executor for this phase.
- Independent code review (`49-REVIEW.md`, 2026-07-03, 0 critical / 3 warning / 1 info) corroborates: "the SQL-injection surface is clean: every new/changed builder... validates identifiers via `validate_identifiers` and binds all values as `%s`/named params... the advisory-lock key is correctly derived server-side... never Python `hash()`, never interpolated." Its **WR-01** finding (positional `%s`→named-bind reconciliation could mis-target a literal `%s` embedded in a user SQL source) was a real latent bug reaching back to Phase 27 and amplified by the composite N-placeholder loop — it was FIXED in commit `c0ea441` (right-to-left placeholder search) before this audit; `tests/test_etl.py::test_reconcile_leaves_literal_percent_s_in_user_source`/`test_reconcile_composite_leaves_literal_percent_s_in_source` now guard the fix. This audit closes T-49-04-01 against the POST-FIX code, not the pre-fix version the review examined. WR-02/WR-03 (stale docstring/docs claims) were documentation-only, non-security, also fixed in `c0ea441`.
- `grep -n "\bhash(" pycopg/etl.py` and `grep -n "xact_lock" pycopg/etl.py pycopg/queries.py` both return no matches — directly confirms T-49-05-02 and T-49-05-04 rather than inferring them from docstrings.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|--------------|------|
| AR-49-01 | T-49-01-02 | `initial_watermark` is construction-time operator/developer config (part of the `Pipeline` descriptor authored by the integrating application), not untrusted end-user input reaching the system at runtime. An oversized seeded first-scan is bounded by the existing `extract_limit` field and is, at worst, a self-inflicted performance cost to the operator's own pipeline, not an externally exploitable DoS | gsd-security-auditor (plan-time disposition, phase 49 register) | 2026-07-03 |
| AR-49-02 | T-49-02-03 | `incremental_lookback` is the same class of construction-time operator config as `initial_watermark`, also bounded by `extract_limit`. The overlap re-scan it causes is an intentional, documented, idempotent `ON CONFLICT` no-op (incremental requires `load_mode="upsert"`, D-08/C-01) rather than an attacker-controlled amplification vector | gsd-security-auditor (plan-time disposition, phase 49 register) | 2026-07-03 |
| AR-49-03 | T-49-SC | Zero new runtime or dev dependencies were introduced across all 5 plans of this phase (verified via `git diff` on `pyproject.toml`/`uv.lock`); every SQL function newly used (`pg_advisory_lock`/`pg_try_advisory_lock`/`pg_advisory_unlock`/`hashtextextended`) is a built-in `pg_catalog` primitive shipped with PostgreSQL core, not a third-party extension or package, so there is no new supply-chain surface to mitigate | gsd-security-auditor (plan-time disposition, phase 49 register) | 2026-07-03 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|----------------|--------|------|--------|
| 2026-07-03 | 19 | 19 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-03
