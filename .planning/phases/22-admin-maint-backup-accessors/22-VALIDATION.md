---
phase: 22
slug: admin-maint-backup-accessors
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-17
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (≥7.0.0) + pytest-cov + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (`--cov-fail-under=94`) |
| **Quick run command** | `uv run pytest tests/test_admin_aliases.py tests/test_maint_aliases.py tests/test_backup_aliases.py tests/test_parity.py -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30 seconds (quick) / ~90 seconds (full, with coverage) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (DB-free alias + parity tests are fast).
- **After every plan wave:** Run the full suite command (`uv run pytest`) — enforces the ≥94% coverage gate.
- **Before `/gsd-verify-work`:** Full suite must be green AND the `-W error::DeprecationWarning` gate must pass (no internal alias warnings leaking from moved bodies — see D-02/D-03).
- **Max feedback latency:** 90 seconds.

---

## Per-Task Verification Map

> Decomposition mirrors Phase 21: 3 plans / 3 waves (D-04). Wave 1 = new accessor modules; Wave 2 = wiring (properties, stubs, exports); Wave 3 = alias tests + parity registry + call-site migration + gates.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 22-01-* | 01 | 1 | ADM-01, MNT-01, BKP-01 | — / — | Identifier validators (`validate_identifier`/etc.) travel verbatim with moved bodies — no SQL-injection regression | unit | `uv run pytest tests/test_sql_injection.py -x -q` | ✅ exists | ⬜ pending |
| 22-02-* | 02 | 2 | ADM-01, MNT-01, BKP-01 | — / — | Flat aliases warn at `stacklevel=2`; internal sibling calls (`create_role`) use `self._db.admin.*` NOT flat alias (no internal DeprecationWarning) | unit | `uv run pytest tests/test_parity.py -x -q` | ✅ exists | ⬜ pending |
| 22-03-* | 03 | 3 | ADM-01 | — / — | `db.admin.*` (11) work; 11 flat names warn + delegate | unit (DB-free mock) | `uv run pytest tests/test_admin_aliases.py -x -q` | ❌ W3 | ⬜ pending |
| 22-03-* | 03 | 3 | MNT-01 | — / — | `db.maint.*` (6) work; 6 flat names warn + delegate | unit (DB-free mock) | `uv run pytest tests/test_maint_aliases.py -x -q` | ❌ W3 | ⬜ pending |
| 22-03-* | 03 | 3 | BKP-01 | — / — | `db.backup.*` (4) work; 4 flat names warn + delegate | unit (DB-free mock) | `uv run pytest tests/test_backup_aliases.py -x -q` | ❌ W3 | ⬜ pending |
| 22-03-* | 03 | 3 | ADM-01, MNT-01, BKP-01 | — / — | sync/async parity for all 3 pairs via `ACCESSOR_PAIRS` | unit (inspect) | `uv run pytest tests/test_parity.py::test_accessor_parity -x -q` | ✅ exists | ⬜ pending |
| 22-03-* | 03 | 3 | ADM-01, MNT-01, BKP-01 | — / — | Coverage ≥ 94% holds with alias tests in place; `-W error::DeprecationWarning` gate green | gate | `uv run pytest` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: plan task IDs (`22-PP-TT`) are assigned by the planner; the rows above bind each Wave/Requirement to its automated proof so no requirement lands without an executable check.*

---

## Wave 0 Requirements

The 3 alias test modules below do not exist yet — they are authored in **Wave 3** (not a separate Wave 0), mirroring Phase 21 where the alias tests ship in the final wave alongside the `@deprecated_alias` stubs they exercise:

- [ ] `tests/test_admin_aliases.py` — 11 sync + 11 async alias tests (warn + `stacklevel=2` + delegate) — Wave 3
- [ ] `tests/test_maint_aliases.py` — 6 sync + 6 async alias tests — Wave 3
- [ ] `tests/test_backup_aliases.py` — 4 sync + 4 async alias tests — Wave 3
- [ ] `tests/test_parity.py` — append 3 `ACCESSOR_PAIRS` tuples (registry + parametrized test already exist) — Wave 3

*No framework install needed — pytest, pytest-cov, pytest-asyncio all already present (Phase 21 infra).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live `pg_dump`/`pg_restore` subprocess round-trip against a real PostgreSQL | BKP-01 | Backup methods shell out via `subprocess`/`asyncio.create_subprocess_exec` and need a live server + `pg_dump`/`psql` binaries; existing integration tests cover this and are unchanged by the verbatim move | Run `uv run pytest tests/test_database_integration.py -k backup` against a live DB (already covered — the move must not change observable behavior) |

*The DB-free MagicMock alias tests prove warn+delegate without a live DB; behavioral equivalence of the moved bodies is covered by the pre-existing integration suite (bodies move verbatim, D-06).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 / Wave 3 test dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 3 covers all 3 new alias test modules + parity registry entries
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter (set by checker once plans bind every requirement to an automated command)

**Approval:** pending
