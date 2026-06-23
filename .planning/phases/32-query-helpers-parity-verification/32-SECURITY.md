---
phase: 32
slug: query-helpers-parity-verification
status: secured
threats_open: 0
threats_total: 8
threats_closed: 8
asvs_level: 1
register_authored_at_plan_time: true
created: 2026-06-23
---

# SECURITY.md — Phase 32: Query Helpers & Parity Verification

**Audit date:** 2026-06-23
**Auditor:** gsd-security-auditor
**Threat register:** authored at plan time (`register_authored_at_plan_time: true`) — verification mode (no new-threat scan)
**ASVS level:** default (unset)
**block_on:** default (block on OPEN high/critical only)

**Result: SECURED — 8/8 threats closed.**

Three `mitigate` threats actively verified in code (grep-located, all entry points
checked); five `accept` / `n/a` threats confirmed and logged below.

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-32-01 | Tampering (SQL injection via identifiers) | mitigate | CLOSED | `validate_identifiers(table, schema, time_column)` is the FIRST statement in BOTH builders — `pycopg/timescale.py:251` (`_build_time_bucket_sql`) and `pycopg/timescale.py:314` (`_build_time_bucket_gapfill_sql`), precedes all f-string interpolation. Backed by strict whitelist `_IDENTIFIER_PATTERN = ^[a-zA-Z_][a-zA-Z0-9_]*$` (`pycopg/utils.py:13`, `validate_identifiers` at `pycopg/utils.py:107`). All 4 accessor entry points (sync+async × both helpers) route through these builders. |
| T-32-02 | Tampering (value injection) | mitigate | CLOSED | `bucket_width`/`start`/`finish` reach SQL only as `%s` placeholders (`pycopg/timescale.py:254`, `316-319`); params lists `[bucket_width]` / `[bucket_width, start, finish, start, finish]` (`:261`, `:325`). rows path: positional `self._db.execute(sql, params)` (`:1170`, async `:2137`). df path: `_to_named_binds` rewrites `%s`→`:pN` (`:204-210`) then `to_dataframe(sql=named_sql, params=binds)` (`:1169`, async `:2136`), bound via SQLAlchemy `text()` in `pd.read_sql(text(sql), engine, params=params)` (`pycopg/database.py:935`). Grep confirms NO `{bucket_width}`/`{start}`/`{finish}` f-string interpolation anywhere. |
| T-32-03 | Tampering (structural-SQL fragment: `aggregates`/`where`) | accept | CLOSED (accepted) | See Accepted Risks log below. Documented as caller-supplied STRUCTURAL SQL (not untrusted input), 17 in-code references; same posture as shipped spatial accessor. |
| T-32-04 | Denial of Service (unbounded time_bucket scan) | accept | CLOSED (accepted) | See Accepted Risks log below. Read-only SELECT under the caller's own connection/statement-timeout. |
| T-32-SC | Supply chain (runtime deps) | n/a | CLOSED | Phase-32 code/test commits (`7743627`, `63ac0d2`, `3ec345b`, `b2acb16`, `72ef0fe`, `5a04e1d`) touch ONLY `pycopg/timescale.py`, `tests/test_timescale.py`, `tests/test_parity.py`. No `pyproject.toml` / `uv.lock` / `requirements*` / `setup.*` changes (D-12). |
| T-32T-01 | Tampering (test residue: live tests create hypertables) | mitigate | CLOSED | All 4 new live tests drop their table in a `finally` block, table-create inside `try`: `tests/test_timescale.py:2471-2472`, `:2486-2487`, `:2502-2503`, `:2520-2521` (TimeBucket) and `:2578-2579`, `:2619-2620` (Gapfill). uuid4-suffixed throwaway names; async twins drop via a sync `Database(async_ts_db.config)`. |
| T-32T-02 | Information disclosure (DB creds in tests) | accept | CLOSED (accepted) | See Accepted Risks log below. Creds from env/conftest defaults; no new secret surface. |
| T-32T-SC | Supply chain (test deps) | n/a | CLOSED | Zero new test dependencies; no manifest changes in phase-32 commits (same evidence as T-32-SC). |

---

## Accepted Risks Log

| Threat ID | Category | Rationale | Owner / Posture |
|-----------|----------|-----------|-----------------|
| T-32-03 | Tampering (structural-SQL fragment) | `aggregates` and `where` are caller-supplied SQL FRAGMENTS, documented as structural SQL — not untrusted end-user input. Identical trust posture to the shipped v0.6.0 spatial accessor `where=`/expression args. No new attack surface for the library's documented contract. The Phase-32 code review (32-REVIEW.md WR-01) flagged the `%`/`%s`-in-structural-SQL footgun as a caller-error usability issue, NOT injection. | Accepted; documented in builder + method docstrings (`pycopg/timescale.py`, 17 references). |
| T-32-04 | Denial of Service (unbounded scan) | `time_bucket` issues a read-only SELECT under the caller's own connection and statement_timeout; same posture as any user SELECT. Out of scope for a thin query helper. | Accepted; caller owns connection/timeout. |
| T-32T-02 | Information disclosure (test creds) | Tests read DB creds from env / conftest defaults (`postgres`/`postgres` on local `pycopg_test`). No new secret surface; identical to all pre-existing DB tests. | Accepted; test-only, no new secret material. |

---

## Unregistered Flags

None. Neither `32-01-SUMMARY.md` nor `32-02-SUMMARY.md` contains a `## Threat Flags`
section — the executor flagged no new attack surface during implementation. No
new public symbols beyond the 11 planned query-helper artifacts (all read-only
SELECT helpers covered by T-32-01/02/03/04).

---

## Notes

- Implementation files were NOT modified (read-only audit).
- Orchestrator context corroborated: 32-REVIEW.md (0 Critical, 1 Warning — WR-01
  caller-error footgun, not injection) and full-suite verification (1288 passed,
  cov 95.11%).
- The three `mitigate` threats (T-32-01, T-32-02, T-32T-01) were the verification
  targets; each mitigation was grep-located at the cited file:line and confirmed
  to apply to ALL entry points (the two pure builders are the single choke-point
  through which all four sync/async accessor methods route).

---

## Security Audit 2026-06-23

| Metric | Count |
|--------|-------|
| Threats found | 8 |
| Closed | 8 |
| Open | 0 |
