---
phase: 48
slug: timescaledb-follow-ups
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-03
---

# Phase 48 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|----------------|
| caller → `db.timescale.*` / `async_db.timescale.*` | Application code calls TimescaleDB helper methods; some arguments are interpolated as SQL identifiers (schema/table/view/column/index names), others are bound as parameterized values (intervals, timestamps, chunk names, booleans) | Identifiers (structural), bound values (data), boolean flags |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-48-01 | Tampering | `drop_continuous_aggregate(view_name, schema)` identifier injection | mitigate | `validate_identifiers(view_name, schema)` is line 1 of the method body — `pycopg/timescale.py:1338` (sync), `:2665` (async) — before any string interpolation at `:1346-1348`/`:2673-2675`. Proven by `tests/test_timescale.py:2182` `test_drop_continuous_aggregate_invalid_view_name_raises` — asserts `InvalidIdentifierError` + `db.execute.assert_not_called()` | closed |
| T-48-02 | Tampering | `remove_continuous_aggregate_policy(view_name, schema)` identifier injection | mitigate | `validate_identifiers(view_name, schema)` is line 1 — `pycopg/timescale.py:1383` (sync), `:2711` (async) — before interpolation at `:1391-1394`/`:2719-2722`. Proven by `tests/test_timescale.py:2280` `test_remove_continuous_aggregate_policy_invalid_view_name_raises` | closed |
| T-48-03 | Tampering | Bool-flag injection via `if_exists`/`cascade` | mitigate | Both flags are `bool`-typed by signature and rendered ONLY as fixed literals: `ie = "IF EXISTS " if if_exists else ""`, `cas = " CASCADE" if cascade else ""` (`pycopg/timescale.py:1346-1347`, async `:2673-2674`); `if_exists` → `"true"`/`"false"` in `remove_continuous_aggregate_policy` (`:1391`, async `:2719`). No caller string ever reaches these fragments. Proven by `test_drop_continuous_aggregate_if_exists_cascade` (`tests/test_timescale.py:2148`) and `test_remove_continuous_aggregate_policy_if_exists_false` (`:2248`) asserting the exact rendered SQL | closed |
| T-48-04 | Denial of Service | Accidental `DROP` of the wrong cagg | accept | `if_exists` defaults `False` (`pycopg/timescale.py:1298`, async `:2624`) so a missing target raises instead of silently no-op'ing; `.. note:: **DESTRUCTIVE / IRREVERSIBLE**` docstring callout present at `:1332-1336`/async equivalent. Caller supplies the identifier directly — no untrusted-input path in this trust boundary. See Accepted Risks Log | closed |
| T-48-05 | Tampering | `origin`/`offset` value injection into `time_bucket` | mitigate | `origin` bound as bare `%s` (`pycopg/timescale.py:281-282`); `offset` bound as `%s::interval` (`:284-285`) — neither is ever string-interpolated. Proven by `tests/test_timescale.py:2498` `test_time_bucket_origin_sql_shape` (asserts `", origin => %s"` in SQL, no `::interval`) and `:2518` `test_time_bucket_offset_sql_shape` (asserts `'"offset" => %s::interval'`, value only in `params`) | closed |
| T-48-06 | Tampering | `table`/`time_column`/`schema` identifier injection (pre-existing) | mitigate | `validate_identifiers(table, schema, time_column)` remains line 1 of `_build_time_bucket_sql` — `pycopg/timescale.py:269` — unchanged by this phase (confirmed by diff: origin/offset add no new identifier args) | closed |
| T-48-07 | Denial of Service | Both `origin`+`offset` set → confusing DB "no matching overload" error / wasted round-trip | mitigate | Client-side `ValueError` guard in `_build_time_bucket_sql` (`pycopg/timescale.py:271-276`) fires before the SQL string is built (`:278` onward). Proven by `tests/test_timescale.py:2552` `test_time_bucket_origin_offset_mutual_exclusion` — asserts `db.execute.assert_not_called()` and `db.to_dataframe.assert_not_called()`, i.e. the malformed `time_bucket()` SQL is never sent to the DB. See caveat below (WR-01) | closed |
| T-48-08 | Tampering | Chunk string injection into `compress_chunk`/`decompress_chunk` | mitigate | `chunk` bound as `%s::regclass`, never interpolated: `"SELECT compress_chunk(%s::regclass, if_not_compressed => %s)"` (`pycopg/timescale.py:561`, async `:1919`); decompress mirror (`:602`, async `:1960`). `chunk` is a value not a SQL identifier — `validate_identifiers` correctly N/A (RESEARCH D-10/D-11 carve-out documented in both docstrings). Proven by `tests/test_timescale.py:2662` `test_compress_chunk_binds_not_interpolates` and `:2758` `test_decompress_chunk_binds_not_interpolates` — malicious string `"x'; DROP TABLE t; --"` asserted `not in sql` and present only at `params[0]` | closed |
| T-48-09 | Tampering | Bool-flag injection via `if_not_compressed`/`if_compressed` | mitigate | Both flags are `bool`-typed and passed as a bound `%s` param (`[chunk, if_not_compressed]` / `[chunk, if_compressed]`) — never interpolated. Proven by `test_compress_chunk_if_not_compressed_false` (`tests/test_timescale.py:2628`) and `test_decompress_chunk_if_compressed_false` (`:2724`) asserting `params[1] is False` | closed |
| T-48-10 | Information Disclosure | Distinguishing extension-absent vs license-gated failure | accept | Both are legitimate sequential failure modes to a trusted caller (own DB). `ExtensionNotAvailableError` fires first from the `has_extension` guard (e.g. `pycopg/timescale.py:1340-1344`); no `try/except` wraps the subsequent DB call, so `psycopg.errors.FeatureNotSupported` (license-gated) propagates unswallowed (D-09) — verified by reading every T-48 method: no exception-swallowing code path exists. See Accepted Risks Log | closed |
| T-48-SC | Tampering | Supply-chain / package installs | mitigate | Zero new runtime packages this phase — confirmed via `git log` on `pyproject.toml` (last touch: `9770342` v1.0.0 bump, pre-dating phase 48) and `dependencies`/`timescale` extra unchanged (`timescale = []  # No additional deps, just PostgreSQL extension`). No install tasks in any of the three 48-0N plans | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

### Corroboration notes

- Sync/async parity verified directly (not just trusted from docs): both `TimescaleAccessor` and `AsyncTimescaleAccessor` implementations of `drop_continuous_aggregate`, `remove_continuous_aggregate_policy`, `compress_chunk`, `decompress_chunk` were read side-by-side — identical `validate_identifiers`/binding placement in both. `tests/test_parity.py:101` `test_timescale_v110_surface` locks the 4 new method names onto both classes; `test_accessor_parameter_kind_parity` (`:459`) guards KIND parity.
- No `## Threat Flags` section found in any of `48-01-SUMMARY.md`, `48-02-SUMMARY.md`, `48-03-SUMMARY.md` — no unregistered new attack surface reported by the executor for this phase.
- Independent code review (`48-REVIEW.md`, 2026-07-03, 0 critical / 1 warning / 2 info) corroborates: "Security posture is clean... every identifier reaching SQL passes through `validate_identifiers`... every value is a bind parameter, never string-interpolated." Its **WR-01** finding (origin/offset mutual-exclusion `ValueError` fires *after* the `has_extension()` round-trip, contradicting the "before any DB round-trip" docstring wording) is a **documentation/ordering correctness gap, not a security bypass**: the malformed `time_bucket(...)` SQL itself is still never built or sent (test-proven), so the T-48-07 DoS mitigation holds as declared. Recommended as a non-blocking follow-up fix (hoist the guard ahead of `has_extension`, per reviewer's suggested diff) — tracked here for visibility, not reopening T-48-07.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|--------------|------|
| AR-48-01 | T-48-04 | `drop_continuous_aggregate` defaults `if_exists=False`, forcing an explicit opt-in for silent no-op behavior; the DESTRUCTIVE/IRREVERSIBLE docstring warns callers. Caller controls the identifier directly in this trust boundary — there is no untrusted-input path from an external actor to this argument, so residual risk is caller error, not an external attacker | gsd-security-auditor (plan-time disposition, phase 48 register) | 2026-07-03 |
| AR-48-02 | T-48-10 | `ExtensionNotAvailableError` (pycopg-level guard) and `FeatureNotSupported` (DB-level, 0A000, license-gated) are both legitimate, expected failure modes surfaced to a trusted caller operating their own database; neither leaks information to an untrusted party. Consistent with the v0.8.0-established D-09 posture of propagating DB errors unswallowed rather than obscuring them | gsd-security-auditor (plan-time disposition, phase 48 register) | 2026-07-03 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|----------------|--------|------|--------|
| 2026-07-03 | 11 | 11 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-03
