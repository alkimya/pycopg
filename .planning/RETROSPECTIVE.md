# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v0.4.0 — Quality & Spatial Helpers

**Shipped:** 2026-06-14
**Phases:** 7 (9–15) | **Plans:** 36 | **Tasks:** 62

### What Was Built

- **uv toolchain (Phase 9):** PEP 735 dev groups, committed `uv.lock`/`.python-version`, CI test matrix (3.11/3.12/3.13) and publish both under uv; hatchling backend + OIDC trusted publishing preserved.
- **Residual security & robustness (Phase 10):** B1/B2/B3/B5 closed with dedicated red→green regression tests; coverage ratchet → 80.
- **Full sync/async parity (Phase 11):** 13 mirrored methods, C1/C2/C3 fixes, `test_parity` extended to real-DB behavior; ratchet → 90. Two latent source bugs fixed in passing (NOTIFY binding, copy_to_csv memoryview).
- **Wired abstractions (Phase 12):** `Database`/`AsyncDatabase` inherit `DatabaseBase`+`QueryMixin`; ~25 inline SQL → `queries.py`; pure DB-free builders extracted; ratchet 90→92.
- **Documentation quality (Phase 13):** numpydoc migration of all public docstrings, interrogate (≥95) + mypy CI, real exception types, `__version__` via importlib.metadata.
- **Spatial helpers (Phase 14):** `spatial.py` with geometry resolver + 11 pure PostGIS builders + `SpatialAccessor`/`AsyncSpatialAccessor` at parity; ratchet → 94.
- **Release (Phase 15):** Sphinx spatial docs, RTD green, CHANGELOG/MIGRATION, Node 24 CI bumps, tag `v0.4.0`, PyPI publish via OIDC.

### What Worked

- **Coverage ratchet discipline (70→80→90→92→94).** Measuring real green-suite coverage *before* flipping the gate (D-08 "never freeze an unmet threshold") kept the gate honest and caught the unreachable 95 stretch early instead of at release.
- **Sequencing uv first (Phase 9).** Every later phase ran under the new tooling from the start — no mid-milestone toolchain churn.
- **Pure DB-free builders + accessors.** Extracting stateless SQL builders made spatial helpers (Phase 14) testable to 100% without a live DB, and gave Phase 12's refactor a clean target.
- **Parity-by-construction.** Phase 11's extended `test_parity` (real-DB behavior, minimal allow-list) turned "sync/async parity" from an aspiration into an enforced invariant; Phase 14 spatial added zero allow-list entries.
- **Human-gated release (Phase 15).** Irreversible supply-chain steps (RTD, tag, PyPI publish) required maintainer confirmation — clean-venv install verified before declaring done.

### What Was Inefficient

- **Worktree/background-agent infra repeatedly fell back to inline execution.** Phases 11+ hit stale `origin/main` worktree-base mismatches and missing background-Bash permissions; recovery meant pushing unpushed commits then running inline. This recurred across phases — a known environment constraint, not a one-off.
- **SUMMARY frontmatter inconsistency.** Requirements were recorded under `requirements:`, `requirements_completed:`, `dependency_graph.provides`, or omitted entirely — so the 3-source audit cross-check leaned on VERIFICATION.md alone for several phases. A schema check would have caught this.
- **REQUIREMENTS.md status drift.** Traceability rows lagged the actual code state for several phases (executors didn't update the table); verifiers had to note "tracking artifact, code is correct" repeatedly.
- **Coverage-95 stretch carried as a label longer than it was reachable.** The unreachable last ~1pt (DB/IO paths) was only formally deferred at Phase 12; the ROADMAP kept the "→95" framing.

### Patterns Established

- **Measure-then-ratchet** for coverage gates (D-07/D-08) — gate value must equal a measured-and-passing floor.
- **Builder/accessor split** — pure stateless SQL builders + thin lazy accessors (`db.spatial`) — reused from refactor (Phase 12) into spatial (Phase 14).
- **Async catches up to the richer sync signature, never the reverse** (D-07 parity rule): 0 sync breaking changes.
- **`listen` is the sole documented async-only method**; everything else is parity-enforced.
- **Per-phase VERIFICATION.md as the authoritative coverage source**, with SUMMARY frontmatter + REQUIREMENTS traceability as cross-checks.

### Key Lessons

1. **Pick the toolchain phase first.** Migrating uv before any feature work meant zero rework under a changing toolchain.
2. **Make the gate equal reality.** A coverage gate frozen above measured-and-passing coverage is a lie that blocks later phases; ratchet to the floor and defer the stretch explicitly.
3. **Testability is a design choice.** Pure DB-free builders bought 100% module coverage and DB-free unit tests for the most SQL-heavy code.
4. **Normalize SUMMARY frontmatter.** Inconsistent `requirements` field naming weakened the audit's 3-source cross-reference; standardize the field (and have executors update REQUIREMENTS.md) next milestone.
5. **Fix the worktree/background-agent infra or commit to inline.** The repeated stale-base fallback cost time every phase; either push-before-spawn becomes routine or phases run inline by default in this environment.

### Cost Observations

- Model mix: predominantly Opus (orchestration + verification) with Sonnet for the integration checker and several executors.
- Sessions: multiple across 2026-06-06 → 2026-06-14.
- Notable: ~96 phase commits in the window; inline execution (vs worktree) avoided repeated base-mismatch recovery once adopted.

---

## Milestone: v0.5.0 — ETL Pipeline Runner

**Shipped:** 2026-06-15
**Phases:** 5 (16–20) | **Plans:** 13 | **Tasks:** 18

### What Was Built

- **Pure ETL layer (Phase 16):** `Pipeline` frozen dataclass with construction-time validation + DB-free pure SQL builders gated by `validate_identifiers`; ETL exception hierarchy + 5 SQL constants; 31 DB-free tests.
- **Run-tracking foundation (Phase 17):** `ETLAccessor` wired as lazy `db.etl`; structural run-log isolation via a dedicated `connect(autocommit=True)` per write — run rows commit independently of the load transaction, even under an active `db.session()`.
- **Load modes & extract (Phase 18):** append/replace/upsert with atomic loads, SQL/table sources, single/list/None transform chains; failed transforms raise `ETLTransformError` naming the failing step.
- **Query surface (Phase 19):** 8-field `RunResult` (via re-SELECT), `history()`, `last_run()`, `dry_run=True` (no run row written).
- **Async parity & release (Phase 20):** `AsyncETLAccessor` async mirror with `asyncio.to_thread` transforms, lazy `async_db.etl`, `TestEtlParity` (inspect.getmembers), `docs/etl.md`, v0.5.0 tag + PyPI publish via OIDC.

### What Worked

- **The `spatial.py` mirror pattern paid off again.** Phases 16–20 reused the builder/accessor split from v0.4.0 wholesale — pure builders unit-tested without a DB, lazy accessors under `db.etl`/`async_db.etl`. Phase 20's async accessor was a near-mechanical mirror, which made the parity claim cheap to honor and verify.
- **Phase 17's structural run-log isolation closed v0.4.0's session-isolation gap at the design level**, not with a patch — run rows survive a rolled-back load on every code path, proven by regression test.
- **Async parity enforced by `TestEtlParity`** turned the headline requirement into an automated invariant; wiring `async_db.etl` even turned two pre-existing red `TestAsyncParity` tests green.
- **The publish boundary held.** The Phase 20 release executor was explicitly fenced to do only reversible prep (version bump, CHANGELOG, gates) and stop before tag/push/publish; the irreversible PyPI publish happened only after explicit human sign-off, with all three gates independently re-verified on merged `main` first.
- **Coverage ratchet held at 94** with new async ETL behavioral tests added specifically so the async code path was exercised (not dead-code coverage).

### What Was Inefficient

- **Worktree wrong-base recurred (again).** The Phase 20 Wave 1 executor forked off stale `origin/HEAD` instead of the dispatch base — the same class of failure flagged in v0.4.0. The executor self-recovered (`git reset --hard <base>` at 0 commits ahead) and the orchestrator verified merge-base + clean diff-stat before every merge, but this is now a *repeat* known issue that still hasn't been fixed at the infra level.
- **REQUIREMENTS.md status drift, again.** ETL-12/ETL-13 stayed unchecked after Phase 20 because worktree executors don't touch REQUIREMENTS.md and the phase-complete step didn't tick them — fixed by hand at milestone close. Same lesson as v0.4.0; still unautomated.
- **SUMMARY one-liner noise.** `milestone.complete` auto-extracted two junk "accomplishments" (a bare `tests/test_parity.py` and a bug-rule fragment) from SUMMARY files whose one-liner field was malformed — hand-cleaned in MILESTONES.md.
- **No milestone audit was run** (`/gsd-audit-milestone` skipped) — defensible because the release was already shipped and Phase 20 verification was 5/5, but it means the close leaned on per-phase verification rather than a cross-phase E2E pass.

### Patterns Established

- **Fence irreversible release steps in the executor prompt, verify gates on the merged mainline, then human-gate the publish.** This split (reversible prep autonomous; tag/publish human-approved) worked cleanly and should be the default for any release phase.
- **Re-verify every release gate independently on `main` after merge** — don't trust the worktree executor's self-reported gate output for irreversible actions.
- **Reserve-the-column forward-compat** — `pipeline_runs.watermark JSONB` (always NULL in v0.5.0) lets v0.6.0 incremental support land additively with no breaking migration.

### Key Lessons

1. **The worktree wrong-base failure is now a confirmed recurring tax, not a fluke.** Two milestones running. Either make push-before-spawn / base-pinning routine, or default release-critical phases to inline execution in this environment.
2. **Automate REQUIREMENTS.md checkbox updates at phase close.** Hand-fixing traceability at milestone close has now happened twice; have the phase-complete step (or verifier) tick requirement boxes.
3. **For irreversible outward-facing steps, the orchestrator re-verifies — the executor only prepares.** Independently re-running coverage/interrogate/Sphinx on merged `main` before publishing caught nothing this time but is the right cost for a permanent PyPI upload.
4. **A small, mechanical final phase still benefits from real research.** Phase 20 looked like pure mirror work, yet the RESEARCH pass (exact file:line analogs, the `asyncio.to_thread` idiom, the publish trigger) made the plans exact and the execution near-deviation-free.

### Cost Observations

- Model mix: Opus for orchestration/planning/discussion, Sonnet for researcher/executors/verifier/checker.
- Sessions: single focused session 2026-06-15 (discuss → plan → execute → ship → close in one sitting).
- Notable: fastest milestone yet (~1.2 days, 13 plans) — the mature `spatial.py` pattern + locked design (no discuss-phase needed for the final phase) compressed the cycle.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v0.3.0 | 7 (1–7) | 14 | Initial consolidation: full async parity, real-PostgreSQL testing |
| v0.4.0 | 7 (9–15) | 36 | uv toolchain, coverage ratchet discipline, builder/accessor pattern, human-gated release |
| v0.5.0 | 5 (16–20) | 13 | ETL pipeline runner via the spatial mirror pattern; structural run-log isolation; fenced reversible-prep + human-gated publish |

### Cumulative Quality

| Milestone | Test files | Coverage | Notes |
|-----------|-----------|----------|-------|
| v0.3.0 | — | 72.76% | Coverage 23% → 72.76%; real-DB tests |
| v0.4.0 | 22 (~749 tests) | 94.09% | Ratchet 70→80→90→92→94; numpydoc + interrogate gate |
| v0.5.0 | 23 (~983 tests) | 94.26% | Ratchet held at 94 with new async ETL behavioral tests; interrogate 100% |

### Top Lessons (Verified Across Milestones)

1. **Real PostgreSQL beats mocks** for catching driver/DB interaction bugs (v0.3.0, v0.4.0, and v0.5.0 all surfaced latent bugs only real-DB tests caught).
2. **Sync is the established core-value API; align async toward it** — enriching async never breaking sync kept the parity promise with zero sync breakage across all three milestones.
3. **The builder/accessor mirror pattern compounds.** Established in v0.4.0 (spatial), reused wholesale in v0.5.0 (ETL) — the most reusable architectural decision of the project, and it makes each new sync/async surface near-mechanical.
4. **Two recurring infra taxes remain unfixed across milestones:** worktree wrong-base recovery (v0.4.0 + v0.5.0) and manual REQUIREMENTS.md checkbox updates (v0.4.0 + v0.5.0). Both are now confirmed patterns, not one-offs — worth fixing before the next milestone.
