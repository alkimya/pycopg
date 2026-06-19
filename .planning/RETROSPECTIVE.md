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

## Milestone: v0.6.0 — Réorganisation en accessors

**Shipped:** 2026-06-19
**Phases:** 4 (21–24) | **Plans:** 13 | **Tasks:** 24

### What Was Built

- **Infrastructure + pattern proof (Phase 21):** `@deprecated_alias` decorator (`pycopg/aliases.py`, sync + async, `stacklevel=2`, `iscoroutinefunction` branch, no eval/exec) — the single shared warn+delegate mechanism — proven end-to-end with `TimescaleAccessor`/`AsyncTimescaleAccessor` (6 methods moved verbatim, `self.`→`self._db.`).
- **Three small accessors (Phase 22):** `AdminAccessor` (11), `MaintAccessor` (6), `BackupAccessor` (4) delivered in one phase by replicating the Phase 21 pattern; 21 flat aliases per class; `_psql_restore` kept private on the accessor.
- **Largest block + spatial relocation (Phase 23):** `SchemaAccessor` (27 DDL/introspection methods) + relocation of `create_spatial_index`/`list_geometry_columns` into `SpatialAccessor`; 8 internal `from_dataframe`/`from_geodataframe` call-sites rewritten to accessor paths; sibling-accessor and `self._db.schema.has_extension` rewrites across `timescale.py`/`etl.py`/`spatial.py`.
- **Exports, docs, release (Phase 24):** 10 accessor classes in `__all__`; README "Accessor Namespaces" overview + 5 Sphinx automodule blocks (green `-W`); CHANGELOG `[0.6.0]` + prepended 56-row MIGRATION v0.5→v0.6 guide (1:1 with `@deprecated_alias` stubs); version bump; v0.6.0 tag + PyPI publish via OIDC; clean-venv smoke.

### What Worked

- **The "validate once at Phase 21, replicate mechanically" bet held exactly as designed (D-SCOPE-3).** The decorator + lazy-accessor + alias-test + parity-pair recipe proved once on timescale, then Phases 22-24 were near-mechanical applications — admin/maint/backup landed together in a single phase, schema (the 27-method block) went smoothly because the geometry was already known.
- **DB-free MagicMock alias tests scaled the coverage requirement cheaply.** Every alias gets a fast, no-DB test asserting it both warns (correct message + `stacklevel`) and delegates; 56 aliases covered without touching the DB, and coverage *rose* to 95.64%.
- **The `-W error::DeprecationWarning` gate caught the real risk of this milestone** — internal self-calls to now-deprecated flat methods. Phase 23's call-site rewrites were verified by 1030 unit tests running clean under the gate, proving no production path emits a spurious warning to users.
- **`test_parity`'s data-driven `ACCESSOR_PAIRS` registry** turned "every moved method exists on both sync and async" into one parametrized invariant; adding a pair per accessor kept the Core Value automated.
- **A real milestone audit ran this time** (`/gsd-audit-milestone` — skipped in v0.5.0): 3-source requirements cross-reference + a `gsd-integration-checker` pass confirming 56/56 aliases resolve E2E and 0 broken flows. Cheap insurance that the refactor integrates end-to-end.

### What Was Inefficient

- **SUMMARY one-liner noise recurred (third milestone running).** `milestone.complete` again auto-extracted junk "accomplishments" (bare filenames `pycopg/admin.py`, a commit hash `374534c`, bug-rule fragments) from SUMMARY files whose `one_liner` frontmatter was malformed — hand-cleaned in MILESTONES.md. This is now a confirmed three-milestone pattern (v0.4.0, v0.5.0, v0.6.0).
- **Nyquist VALIDATION.md left in draft for 3 of 4 phases.** Phases 22-24's VALIDATION.md stayed `status: draft` / `nyquist_compliant: false` — they were verified PASSED via VERIFICATION.md regardless, but the formal Nyquist sign-off was never promoted. Bookkeeping gap, recorded as deferred.
- **REQUIREMENTS.md ADM-01 "12 methods" stale off-by-one** (real count 11) propagated as a note through every Phase 22+ artifact — a single source-doc typo that each downstream doc had to caveat rather than fix at the root.
- **Ran sequential-on-main, not via worktrees.** Given the prior two milestones' worktree wrong-base tax, this milestone executed phases inline on `main` (per project memory guidance). It worked and avoided the recovery dance, but means the parallelization the executor supports went unused.

### Patterns Established

- **`@deprecated_alias` decorator as the deprecation-cycle primitive:** real logic lives in the accessor, the old flat name is a thin warn+delegate wrapper (D-SCOPE-2). Removal next version = deleting one block of stubs, no logic touched — making v0.7.0's ALIAS-RM-01 trivial by construction.
- **DB-free MagicMock alias test per moved method** — the standard way to cover a delegating wrapper without DB cost while holding the coverage ratchet.
- **Verify refactors under `-W error::DeprecationWarning`** to prove no internal caller still routes through a deprecated path — the specific failure mode of an alias-migration milestone.
- **Group accessors by domain, not by operation type** (schema stays one block; spatial-index methods follow PostGIS coherence over DDL grouping) — consistent with the spatial/etl precedent.

### Key Lessons

1. **A purely mechanical, repetitive milestone is exactly where "prove the pattern once, then replicate" earns its keep.** The one-phase-of-real-design-then-N-phases-of-application shape (D-SCOPE-3) compressed 5 accessors + a release into 4 phases with no rework.
2. **The SUMMARY one-liner auto-extraction is now a confirmed three-milestone defect** — worth fixing the `summary-extract` field handling (or the SUMMARY template's frontmatter) rather than hand-cleaning MILESTONES.md a fourth time.
3. **For an alias-migration refactor, the `-W error` gate is the load-bearing check** — it's what distinguishes "moved the code" from "moved the code AND rerouted every internal caller." Make it a required gate for any deprecation milestone.
4. **Running the milestone audit is cheap and worth it even when the release already shipped** — the integration checker's E2E alias-resolution pass is precisely the cross-phase confidence per-phase verification can't give.

### Cost Observations

- Model mix: Opus for orchestration/planning, Sonnet for researchers/executors/verifier/integration-checker.
- Sessions: spread across 2026-06-17 (Phases 21-23) → 2026-06-19 (Phase 24 release + audit + close).
- Notable: sequential-on-main execution traded parallel speed for zero worktree-recovery overhead; the mature pattern made discuss-phase unnecessary for the mechanical middle phases.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v0.3.0 | 7 (1–7) | 14 | Initial consolidation: full async parity, real-PostgreSQL testing |
| v0.4.0 | 7 (9–15) | 36 | uv toolchain, coverage ratchet discipline, builder/accessor pattern, human-gated release |
| v0.5.0 | 5 (16–20) | 13 | ETL pipeline runner via the spatial mirror pattern; structural run-log isolation; fenced reversible-prep + human-gated publish |
| v0.6.0 | 4 (21–24) | 13 | Accessor reorg via `@deprecated_alias` + lazy accessors; prove-once-replicate-N; `-W error` as the load-bearing refactor gate; milestone audit restored |

### Cumulative Quality

| Milestone | Test files | Coverage | Notes |
|-----------|-----------|----------|-------|
| v0.3.0 | — | 72.76% | Coverage 23% → 72.76%; real-DB tests |
| v0.4.0 | 22 (~749 tests) | 94.09% | Ratchet 70→80→90→92→94; numpydoc + interrogate gate |
| v0.5.0 | 23 (~983 tests) | 94.26% | Ratchet held at 94 with new async ETL behavioral tests; interrogate 100% |
| v0.6.0 | 30+ (~1100 tests) | 95.64% | Ratchet held at 94; +56 DB-free alias tests + 7-pair parity; `-W error::DeprecationWarning` green at 1030 unit tests; interrogate 100% |

### Top Lessons (Verified Across Milestones)

1. **Real PostgreSQL beats mocks** for catching driver/DB interaction bugs (v0.3.0, v0.4.0, and v0.5.0 all surfaced latent bugs only real-DB tests caught).
2. **Sync is the established core-value API; align async toward it** — enriching async never breaking sync kept the parity promise with zero sync breakage across all three milestones.
3. **The builder/accessor mirror pattern compounds.** Established in v0.4.0 (spatial), reused wholesale in v0.5.0 (ETL), and in v0.6.0 it became the *target shape* the whole monolith was refactored toward — the most reusable architectural decision of the project, and it makes each new sync/async surface near-mechanical.
4. **Recurring tooling taxes, now tracked across milestones:** (a) the SUMMARY one-liner auto-extraction emits junk "accomplishments" — confirmed in v0.4.0, v0.5.0, *and* v0.6.0 (three running); (b) manual REQUIREMENTS.md checkbox updates at close (v0.4.0 + v0.5.0) — sidestepped in v0.6.0 by running on `main` where the milestone CLI marks them. The worktree wrong-base tax (v0.4.0 + v0.5.0) did **not** recur in v0.6.0 because phases ran sequential-on-main by design — trading parallelism for zero recovery overhead is a viable mitigation in this environment.
5. **Match execution mode to the work.** v0.6.0's mechanical, low-conflict refactor ran cleanly sequential-on-main; the worktree parallelization that caused two milestones of recovery pain was simply not needed. Reserve worktrees for genuinely parallel, file-disjoint work.
