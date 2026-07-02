---
phase: 45
slug: api-completeness-gaps-structured-logging
status: secured
threats_total: 11
threats_closed: 11
threats_open: 0
register_authored_at_plan_time: true
asvs_level: 1
created: 2026-07-02
---

# Phase 45 — API Completeness Gaps + Structured Logging — Security Audit

**Phase:** 45 — api-completeness-gaps-structured-logging
**Threats Closed:** 11/11 (9 mitigate verified in code + 2 accept logged below)
**ASVS Level:** 1
**Register origin:** authored at plan time (four `<threat_model>` blocks across 45-01..45-04-PLAN.md)
**Verification mode:** static — code grep/read + phase VERIFICATION/SUMMARY evidence. Suite not
re-run by the auditor (fragile DB env; passes per 45-VERIFICATION.md: 1735/1736 @ 96.40% under
`PGDATABASE=pycopg_test2`).

This audit **verifies declared mitigations exist** in shipped code; it does not scan for new threats
(register was authored at plan time). No implementation files were modified.

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence (file:line) |
|-----------|----------|-------------|--------|----------------------|
| T-45-01 | Info disclosure — data in log `extra` | mitigate | CLOSED | `pycopg/logging.py:89-95` — `extra` holds ONLY `operation` (str), `duration_ms` (float), and `rows` (int, added only when `rows is not None`); log message `"pycopg: %s completed"` interpolates only `operation`. No SQL/params/DSN/conn passed. Guard: `tests/test_logging_module.py:42-54` (`test_log_operation_extra`) asserts record has exactly `operation`/`duration_ms`/`rows`; `:56-68` asserts `rows` absent when omitted. |
| T-45-02 | Tampering — hijack app logging config | mitigate | CLOSED | `pycopg/logging.py:23` attaches ONLY `logging.NullHandler()`; `basicConfig` appears only in docstring/comment (`:9`, `:59`), never called — tree-wide grep confirms zero `basicConfig(` call sites and only the one NullHandler `addHandler`. AST guard: `tests/test_logging_module.py:85-98` (`test_log_operation_no_basicconfig_call`). |
| T-45-03 | Tampering — SQLi via savepoint name | mitigate | CLOSED | `pycopg/database.py:708` `savepoint()` → `self._session_conn.transaction(savepoint_name=name)`; `:573`/`:579` `transaction(savepoint_name=)` → native `conn.transaction(savepoint_name=...)`. Async mirror `pycopg/async_database.py:648` / `:766`/`:773`. Name reaches psycopg's parameterized savepoint API — never string-interpolated. No new SQL builder → no `validate_identifiers` site required. |
| T-45-04 | Tampering — silent isolation downgrade | mitigate | CLOSED | `pycopg/database.py:566-572` — inside an active session, `isolation_level is not None` → `raise RuntimeError` (fail-closed, D-03); outside a session it is set on the fresh per-call conn (`:577-578`). Async mirror `pycopg/async_database.py:761-765`. |
| T-45-05 | DoS — leaked session connection | **accept** | CLOSED | Logged as **AR-45-01**. Verified accept holds: the `isolation_level` set happens BEFORE `try:` (`database.py:621-623`, async `async_database.py:576-578`); the pre-existing `finally` cleanup (`database.py:625-652`, async `:580-605`) is untouched and always runs `self._session_conn = None`. No new leak path. |
| T-45-06 | Tampering — SQLi via widened named params | mitigate | CLOSED | Annotation-only widening (`params: Params`) on execute/fetch_one/fetch_val/fetch_all/to_dataframe (both classes). Values are driver-bound: `cur.execute(sql, params)` (`database.py:801,863,972,1064,1173,1336,1395,1475`; async `801,892,968,1027,1187,1523,1634,1726,1760`) and `pd.read_sql(text(sql), ..., params=params)` (`database.py:1612`, async `:1245`). Tree-wide grep confirms **NO `_rewrite_named_params`/translator** exists and no `% params` / `.format`/f-string builds SQL from param values. |
| T-45-07 | Info disclosure — health `error` key | mitigate | CLOSED | `error = str(exc)` of the raw psycopg exception — `database.py:776`, async `async_database.py:718`, pooled `pool.py:285` & `:574`. Success dict returns only `connected`/`latency_ms`/`server_version` (`+pool_stats` for pooled); no DSN/password/`connect_params()` appended. Guard: `tests/test_health.py:84-97` (`test_health_never_raises`) asserts `error` contains the injected driver message and nothing propagates. |
| T-45-08 | DoS — health probe hang | **accept** | CLOSED | Logged as **AR-45-02**. Verified accept holds: `health()` uses standard connection acquisition (`psycopg.connect(**config.connect_params())` `database.py:758`, async `AsyncConnection.connect` `:698`, pooled `self.connection()` `pool.py:269`/`:558`); no unbounded wait added — connect-timeout governed by existing Config/DSN. On failure `except Exception` returns `connected: False` (never-raises, D-05). |
| T-45-09 | Info disclosure — instrumentation call sites (×13) | mitigate | CLOSED | All 13 `with log_operation(...)` sites pass a constant op-name + optional int `rows` only: `etl.py:1206,1902`; `backup.py:89,163,441,517` (pg_dump/pg_restore pass NO rows); `migrations.py:195`; `database.py:752,1534(rows=len(df)),1662(rows=len(gdf))`; `async_database.py:692,1298,1442`; `pool.py:266,555`. No DataFrame/SQL/paths/DSN passed. AST audit guard: `tests/test_logging_module.py:216-243`. |
| T-45-10 | Tampering — instrumentation alters behavior | mitigate | CLOSED | Wraps are pure enclosing `with` brackets around unchanged bodies (e.g. `backup.py:89-117` — cmd build/subprocess/`raise RuntimeError` on failure all inside, unchanged; return/exception path propagates through the CM). `log_operation` only emits a DEBUG record in `finally` (`logging.py:87-95`), never swallows/alters exceptions. Behavior-preservation confirmed by 45-VERIFICATION.md (suite 1735 pass @ 96.40%, `test_parity` 37/37, `TestInstrumentationSites` green). |
| T-45-11 | DoS — per-query timing overhead | mitigate (by exclusion) | CLOSED | D-09 hot-path exclusion verified: `execute`/`execute_many`/`fetch_one`/`fetch_val`/`fetch_all` (`database.py:779,806,1318,1339,1361`; async `async_database.py:776,806,950,971,993`) carry NO `log_operation` wrap. Only coarse heavyweight ops are instrumented. No per-query `time.perf_counter()` cost. |

**Verified mitigations:** 9/9 `mitigate` threats CLOSED in code. **Accepted risks:** 2/2 logged (below). **Open:** 0.

---

## Accepted Risks Log

| AR ID | Threat | Category | Rationale | Verification |
|-------|--------|----------|-----------|--------------|
| **AR-45-01** | T-45-05 | DoS — leaked session connection | The pre-existing `session()` commit/close/cleanup `finally` block is left untouched; the new `isolation_level` assignment happens before the `try:`, so it cannot bypass cleanup. No new leak path is introduced by Phase 45. Residual risk (session-conn leak on driver-level corruption) is the same as pre-phase and is accepted. | Set-before-`try:` at `database.py:621-623` / `async_database.py:576-578`; `self._session_conn = None` in the always-runs innermost `finally` (`database.py:652` / `async_database.py:605`). |
| **AR-45-02** | T-45-08 | DoS — health probe hang | `health()` reuses the standard connection acquisition path and adds no unbounded wait; connect-timeout remains governed by existing `Config`/DSN settings (unchanged this phase). A never-raises probe returning `connected: False` on failure is strictly safer for monitoring loops than one that throws (D-05). Residual risk (a hang bounded only by the caller's own connect-timeout config) is accepted. | `psycopg.connect(**config.connect_params())` at `database.py:758` (async `AsyncConnection.connect` `:698`, pooled `self.connection()` `pool.py:269`/`:558`); `except Exception → connected:False` at `database.py:771-777` and mirrors. |

---

## Unregistered Flags

None. All four SUMMARY files declare no new attack surface:
- `45-04-SUMMARY.md` `## Threat Flags` = "None — all new call sites emit only constant operation-name strings and integer row counts (T-45-09 mitigated). No new network endpoints, auth paths, or schema changes introduced."
- `45-01/02/03-SUMMARY.md` `## Threat Surface Scan` each declare no new threat surface beyond the registered T-45-01..08 threats.

No new attack surface appeared during implementation that lacks a threat mapping.

---

## Audit Notes

- Register authored at plan time → this audit **verifies declared mitigations exist**; it did not scan
  for new vulnerabilities.
- **Scoping of T-45-06:** the tree contains f-string SQL in *other* accessors (migrations/maint/admin/
  schema/timescale/spatial), but those compose **identifiers** guarded by `validate_identifiers` in prior
  phases (v0.10.0 AUDIT-01) and bind their *values* as `execute(...)` params — Phase 45 introduced no new
  interpolation surface. The widened `params` on execute/fetch_*/to_dataframe are all driver-bound.
- Implementation files were treated as READ-ONLY; git tree is clean (no auditor edits).
- Static-only per constraints: suite not re-run (fragile DB env). Guard tests confirmed to EXIST and
  assert the claimed shapes; suite-green evidence taken from 45-VERIFICATION.md / 45-04-SUMMARY.md.

_Audited: 2026-07-02 — gsd-security-auditor_
