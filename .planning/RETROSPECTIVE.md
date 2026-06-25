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

## Milestone: v0.7.0 — Alias Removal + Incremental ETL

**Shipped:** 2026-06-22
**Phases:** 5 (25–29) | **Plans:** 13 | **Tasks:** 20

### What Was Built

- **Alias removal (Phase 25):** hard-deleted all 56 `@deprecated_alias` stubs from each of `Database`/`AsyncDatabase` (112 total) by text-pattern (stubs were interleaved with real methods, so line-range deletion was unsafe); deleted `pycopg/aliases.py` + 6 warn+delegate test files; added a 114-test `test_alias_removal.py` proving every removed name raises plain `AttributeError` + WR-01 `inspect` assertions; closed 13 IN-02 guard/error-message sites.
- **Incremental ETL — pure layer (Phase 26):** validated `Pipeline.incremental_column` field, `_build_incremental_extract_sql` (subquery-wrap / WHERE-append, watermark always `%s`), typed-JSONB `_encode_watermark`/`_decode_watermark`; 5 symbols, 34 DB-free tests, zero new deps.
- **Run-log integration (Phase 27):** `_read_watermark` reads the last *successful* run; success-only `_end_run(watermark=)`; `max(col)` capture; JSONB round-trip proven for int/str/datetime on live DB; no-advance-on-failure + empty-batch-preserves invariants.
- **Extract, RunResult & async parity (Phase 28):** wired the filter into `run()` via a shared `_do_extract()` helper (prevents dry_run/real-path drift); `RunResult.watermark_used/recorded`; incremental `dry_run`; full async 1:1 mirror closing ETL-INC-11; `docs/etl.md` incremental section.
- **Release (Phase 29):** version bump (2 sources), CHANGELOG Breaking/Added, MIGRATION v0.6→v0.7 (56-name table + incremental notes), 4 gates green (cov 95.11%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`), tag `v0.7.0` + PyPI publish via OIDC, clean-venv smoke.

### What Worked

- **D-SCOPE-2 paid off exactly as designed.** Because v0.6.0 put the real logic in the accessors and made each flat name a thin warn+delegate wrapper, v0.7.0's removal was the promised "delete one block" — the breaking change carried zero logic risk, and the 114-test `test_alias_removal.py` turned "the surface is now accessor-only" into a hard, enumerated invariant.
- **The reserved `watermark JSONB` column made incremental ETL fully additive.** The v0.5.0 forward-compat bet (column reserved, always NULL) meant incremental loading shipped with **no breaking migration** — the typed envelope just started populating an existing column.
- **Layered phase decomposition (pure → run-log → extract/parity) kept each step DB-free-testable or live-DB-provable in isolation.** The pure builders (Phase 26) were unit-tested without a DB; the invariants (Phase 27) were proven on live DB before the extract loop (Phase 28) ever wired them together — bugs surfaced at the layer that owned them.
- **The shared `_do_extract()` helper structurally prevented dry_run/real-path drift** — the same watermark-aware extract path serves both, so a `dry_run` preview can never diverge from what a real run would filter.
- **Code review caught two REAL latent bugs in `run()` coercion** (Phase 27: float-truncation, NaN-not-`ETLError`) that tests had missed — the `pd.isna`-before-`is_float` ordering lesson came directly from that review and is now encoded.

### What Was Inefficient

- **Ran sequential-on-main again (4th milestone running for this pattern).** Per project memory, phases executed inline on `main` rather than via worktrees — avoided the wrong-base recovery tax but left executor parallelism unused. Local `main` ran far ahead of `origin` the whole milestone (79+ commits) without issue, but it's an accumulating divergence.
- **STATE.md drift required hand-fixing on essentially every phase (6+ times this milestone).** `phase.complete`/`milestone.complete` repeatedly left STATE.md frontmatter or a stale "Next action" line that didn't match reality; the `milestone.complete` CLI also couldn't update one STATE.md field at close (format mismatch warning).
- **Shared-mapper changes needed full `test_etl.py` + `test_etl_accessor.py` re-runs to catch stragglers.** Phase 28 left 3 issues executors missed (a stale `KeyError`-type regression test, a new ~2.7% flaky bound-param test, an ETL-INC-11 req-drift) that only a full ETL-suite run surfaced post-merge — now the standing rule after any shared-mapper edit.
- **Decode-hardening (WR-01/WR-02) was deferred phase-to-phase (26→27→28) and ultimately judged unreachable** with own-written envelopes — defensible, but it rode along as open carry-forward for three phases before being closed.

### Patterns Established

- **A deprecation removal is "delete the wrapper block + enumerate the AttributeErrors in one test file"** — the clean back-half of the v0.6.0 `@deprecated_alias` pattern; `test_alias_removal.py` is the template.
- **Reserve-the-column forward-compat delivers a breaking-free feature one milestone later** — proven end-to-end (v0.5.0 reserve → v0.7.0 use); worth doing whenever a future additive feature is foreseeable.
- **Single shared extract/transform helper for dry-run and real paths** — `_do_extract()` makes preview/execute divergence structurally impossible.
- **`pd.isna()` must precede any `is_float`/numeric coercion check** — NaN is a float; this ordering is now a fixed rule in `run()` coercion.
- **After any change to a shared mapper/builder, run the full module test files (not just the targeted tests)** before declaring a phase done.

### Key Lessons

1. **Forward-compat scaffolding is the highest-leverage thing a milestone can leave behind.** v0.5.0's one reserved column turned what could have been a breaking migration into a purely additive v0.7.0 feature. Look for these bets every milestone.
2. **A breaking removal is low-risk only if the prior cycle set it up that way.** The hard part of ALIAS-RM was done in v0.6.0 (logic-in-accessor, warn+delegate wrappers); v0.7.0 just collected the payoff. Sequencing the deprecation cycle correctly is what made the break safe.
3. **Code review earns its place even on well-tested code.** Two real coercion bugs survived the test suite and were caught only by review — for data-coercion paths (types crossing a DB boundary), an adversarial read is worth the cost.
4. **STATE.md bookkeeping drift is now a confirmed multi-milestone tax** (hand-fixed 6+ times this milestone alone) — the file format the CLIs write and the format the close step expects have diverged; worth reconciling at the tooling level rather than hand-patching a seventh time.
5. **The SUMMARY one-liner auto-extraction junk is now a four-milestone defect** (v0.4.0–v0.7.0) — though v0.7.0's extraction was mostly clean, the `Delivered`/`Stats`/`deferred` enrichment of the MILESTONES entry still had to be added by hand every time.

### Cost Observations

- Model mix: Opus for orchestration/planning/review, Sonnet for researchers/executors/verifier.
- Sessions: spread across 2026-06-19 (Phase 25 + cadrage) → 2026-06-22 (Phases 26–29 + release + close).
- Notable: ~3 days, 13 plans; the layered pure→integration→parity decomposition let each phase be small and independently provable, and the mature ETL/accessor patterns meant minimal design churn.

---

## Milestone: v0.8.0 — TimescaleDB avancé

**Shipped:** 2026-06-23
**Phases:** 4 (30–33) | **Plans:** 11 | **Tasks:** 29

### What Was Built

- **Chunk & dimension management (Phase 30):** `show_chunks` (list[str], oldest-first, `older_than`/`newer_than` filters), `drop_chunks` (both-None `ValueError` pre-flight + capture-before-drop `dry_run`, DESTRUCTIVE docstring), `add_dimension` (TSDB 2.x `by_hash`/`by_range` builder form, construction-time mutual-exclusivity `ValueError`, dup-dimension → `TimescaleError`), `add_reorder_policy` — sync + async. New milestone-wide `TimescaleError(PycopgError)`, `TSDB_SHOW_CHUNKS`/`TSDB_DROP_CHUNKS` constants, new `tests/test_timescale.py` with `ts_db`/`async_ts_db` skip-fixtures.
- **Continuous aggregate lifecycle (Phase 31):** `create_continuous_aggregate` + `refresh_continuous_aggregate` via the `connect(autocommit=True)` seam (`time_bucket(` heuristic guard; `datetime|None`-only refresh window; both-None = full refresh), `add_continuous_aggregate_policy` via plain `execute` (D-01) with a `_check_offset_ordering` best-effort guard — sync + async.
- **Query helpers & parity (Phase 32):** `time_bucket` + `time_bucket_gapfill` with `into="df"/"rows"` routing via a LOCAL `_to_named_binds`/`_check_into` (not imported from spatial); gapfill takes required positional `start`/`finish`, double-bound. TS-ADV-10 full 9-method parity confirmed via `test_accessor_parity` + an explicit 9-name surface assertion.
- **Release (Phase 33):** version bump (2 sources), CHANGELOG `[0.8.0]` Added-only (no MIGRATION — purely additive), `docs/timescaledb.md` rewritten to first-class `db.timescale.*` calls + Advanced Chunk & Dimension Management section + `api-reference.md` 15-row table + README "15 methods", 4 gates green (cov 95.11%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`), human-gated tag `v0.8.0` + OIDC publish (run 28044147070), clean-venv smoke.

### What Worked

- **The autocommit seam from v0.5.0 ETL transferred verbatim to caggs.** `create`/`refresh` reuse the exact `connect(autocommit=True)` pattern that isolated run-log writes — and a live test proved it bypasses an enclosing `db.session()`. A structural seam designed for one feature family paid off in a second, three milestones later.
- **Two-layer mock-authoritative + license-tolerant testing handled the Apache/TSL split cleanly.** Because the local/CI TimescaleDB is Apache-licensed (no caggs, gapfill, or reorder), the mock SQL-shape test is the authority and the live test uses `try/except FeatureNotSupported` — so the suite is green on Apache while the SQL contract is still pinned.
- **Live verification at plan time caught a material wrong assumption before any code was written.** D-08 ("gapfill is Apache-free") was *reversed* during Phase 32 planning by running the query against the local DB — gapfill is TSL-only, exactly like caggs. Catching it at plan time (not in a failing CI run) saved a wrong test strategy.
- **Code review again caught real latent bugs in new code** (Phase 30: over-broad `except Exception` swallowing non-DB errors, missing `number_partitions` validation, unvalidated chunk-bound types on the destructive path) — fixed with 13 regression tests before ship.
- **The `db.meta`-free single-block decisions and local-copy-not-import discipline kept the accessor coupling-free.** `time_bucket` helpers deliberately copied `_to_named_binds` rather than importing from spatial, avoiding a timescale→spatial dependency.

### What Was Inefficient

- **Ran sequential-on-main yet again (now the de-facto default, 12th+ phase).** No worktrees; local `main` ran ~79–99 commits ahead of `origin` for the whole milestone. Fine for this mechanical single-file-per-phase work, but the divergence keeps accumulating and the executor parallelism stays unused.
- **STATE.md drift recurred and needed hand-fixing across the milestone (7th+ tracked occurrence); `milestone.complete` again warned it could not update one STATE.md field at close** ("Last Activity Description" format mismatch) — the same CLI-format-vs-expected-format divergence flagged in v0.6.0/v0.7.0.
- **REQUIREMENTS.md checkbox-vs-traceability-table drift resurfaced at close** — 6 of 11 checkboxes were left unticked while the authoritative traceability table showed all 11 Complete; had to be reconciled by hand in the archive. The phase CLIs update the table but not the inline checkboxes.
- **Carry-forward cosmetic debt rode along untouched for the whole milestone** — the stale `pycopg.aliases` Sphinx cross-reference in accessor docstrings (IN-01/IN-02) has now survived removal of `aliases.py` itself and several phases; never blocking, never closed.

### Patterns Established

- **A connection seam built for one feature family is reusable infrastructure.** The `connect(autocommit=True)` seam (v0.5.0 run-log → v0.8.0 caggs) is now a proven cross-milestone primitive for "this DDL/operation cannot run inside a transaction."
- **For license-gated DB features: mock SQL-shape test is authoritative, live test is license-tolerant.** `try/except FeatureNotSupported` + a pinned SQL assertion keeps the suite green on a restricted-license DB while still verifying the generated SQL.
- **Verify license/feature assumptions against the live DB at plan time, not in CI.** A 30-second `psql` check reversed a wrong test-strategy decision (D-08) before it cost a phase.
- **Accessor-to-accessor coupling is avoided by copying small helpers locally** (`_to_named_binds`/`_check_into`) rather than cross-importing — keeps each accessor independently movable.

### Key Lessons

1. **Structural seams are the second-highest-leverage thing a milestone leaves behind** (after forward-compat scaffolding). The autocommit seam designed for ETL run-logs in v0.5.0 was the enabling primitive for the entire cagg lifecycle in v0.8.0 — at zero design cost.
2. **A 30-second live check beats a confident assumption.** The D-08 reversal (gapfill TSL-only, not Apache-free) shows that for environment-dependent facts (licenses, extension versions, planner behavior), querying the real DB at plan time is cheaper than discovering it in a failing test.
3. **Code review continues to earn its place on new feature code** — three real bugs in Phase 30's new methods (error-swallowing, missing validation, unvalidated destructive-path input) survived the tests and were caught only by review. The pattern from v0.7.0 (review data/error paths adversarially) held again.
4. **The recurring tooling taxes are now multi-milestone certainties, not anomalies:** STATE.md drift (7th+), the MILESTONES `Delivered`/`Stats`/`deferred` enrichment-by-hand (5th milestone), and now REQUIREMENTS.md checkbox-vs-table drift at close. These are tooling-level fixes overdue across the board.

### Cost Observations

- Model mix: Opus for orchestration/planning/review, Sonnet for researchers/executors/verifier.
- Sessions: 2026-06-22 (milestone launch + Phase 30 + Phase 31 context) → 2026-06-23 (Phases 31–33 + release + close), ~2 days.
- Notable: 4 phases, 11 plans; mature accessor + builder-pur patterns meant near-zero design churn — the only material design event was the live-verified D-08 license reversal at plan time.

---

## Milestone: v0.9.0 — CRUD ergonomique + introspection enrichie

**Shipped:** 2026-06-25
**Phases:** 3 (34–36) | **Plans:** 7 | **Tasks:** 7

### What Was Built

- **CRUD ergonomics (Phase 34):** a shared `_build_where_dict` pure staticmethod on `QueryMixin` (dict of equality conditions → AND-ed `col = %s`, `validate_identifiers` keys, values as `%s`) feeding seven flat helpers on `Database`/`AsyncDatabase` — `upsert` (single-row `RETURNING *`, empty-update-set guard), `delete_where`/`update_where` (rowcount, empty-where `ValueError` pre-flight), `exists` (`SELECT EXISTS`), `count` (`SELECT COUNT(*)`, `where=None` routes around the builder), `paginate` (validated `order_by`, non-str/empty rejection, int-cast LIMIT/OFFSET, optional dict-WHERE), `fetch_all` (dict-fetch twin to `fetch_one`). Built TDD red→green across 3 dependency-ordered waves (builder → write helpers → read helpers).
- **Schema introspection (Phase 35):** `primary_key`/`foreign_keys` (pg_catalog, composite-safe conkey-order arrays, grouped by constraint) + `sequences`/`views` (information_schema, views naturally excludes matviews) + `describe` (consolidated dict composing `table_info`/`primary_key`/`foreign_keys`/`list_indexes` — no new SQL) on `SchemaAccessor`/`AsyncSchemaAccessor`, growing `db.schema.*` 27→32. New `PRIMARY_KEY`/`FOREIGN_KEYS`/`SEQUENCES`/`VIEWS` constants in `queries.py`; `test_schema_v090_surface` frozenset surface assertion.
- **Release (Phase 36):** version bump (pyproject canonical + uv.lock + conf.py; `__version__` stays dynamic via `importlib.metadata`, D-36-01), CHANGELOG `[0.9.0]` Added-only with code-exact signatures for all 12 methods (D-36-03 signature-drift guard), docs surfaces (README 27→32 + flat-CRUD note, api-reference rows, database/async-database CRUD sections), cosmetic-debt cleanup (CLAUDE.md version line, `pycopg.aliases` xrefs removed from 5 accessor docstrings), 4 gates green (cov 94.11%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`), human-gated tag `v0.9.0` + OIDC publish (run 28171811187), clean-venv smoke.

### What Worked

- **The builder-pur + accessor pattern is now zero-friction muscle memory.** Three milestones of `validate_identifiers`-first / values-as-`%s` / pure `(sql, params)` discipline meant the entire CRUD + introspection surface dropped in with no design churn — the only new primitive (`_build_where_dict`) is a 25-line staticmethod, and every predicate consumer routes through it (integration check confirmed: no hand-rolled WHERE anywhere).
- **`describe` as pure composition (no new SQL) eliminated a whole class of drift.** By delegating to the four existing introspection helpers, `describe` has one source of truth per fact; the composition-equality test asserts it can never diverge from the standalone helpers. No `DESCRIBE` constant to maintain.
- **The 3-source audit cross-reference caught the SUMMARY frontmatter gap and resolved it cleanly.** Phase 34's SUMMARYs omit the `requirements_completed` field — the audit matrix flagged it as "verify manually," the manual check (source methods + parity 26/26 + REQUIREMENTS `[x]`) confirmed satisfied. The audit machinery did exactly what it's for: surfaced a tracking gap without raising a false coverage alarm.
- **Coverage was actively steered to clear the ratchet, not luck.** 36-01 added a `TestAsyncSchemaIntrospection` class (6 tests) to lift coverage 93.31→94.11% — the ratchet held because the gap was identified and closed, not because it happened to pass.
- **One-cadrage-two-families worked.** Both additive, low-risk families (CRUD + introspection) shipped in one milestone with no scope creep — the right call for purely-additive convenience work.

### What Was Inefficient

- **Ran sequential-on-main yet again (now the de-facto default since v0.6.0).** No worktrees, single-file-per-phase, local `main` ran well ahead of `origin` for the milestone. Fine for mechanical additive work; executor parallelism stays unused.
- **`milestone.complete` again could not update STATE.md's "Last Activity Description" field at close** — the same CLI-format-vs-expected-format divergence flagged every milestone since v0.6.0 (now 8th+ occurrence).
- **MILESTONES.md `Delivered`/`Stats` again needed hand-enrichment** — the CLI creates only the base entry (counts + accomplishments); the one-sentence Delivered summary and Stats block are added manually every milestone (6th occurrence).
- **REQUIREMENTS.md checkbox-vs-traceability drift recurred** — Phase 35's VERIFICATION noted INTRO-01..04 left "Pending"/unchecked while implementations were fully present; reconciled at Phase 36 release. The phase CLIs update the traceability table but not the inline `[x]` boxes.

### Patterns Established

- **A shared pure builder is the cleanest way to guarantee injection-safety across a method family.** `_build_where_dict` is the single WHERE-construction path for five CRUD methods × two classes — validated once, reused ten times. Future predicate methods should route through it, not re-implement.
- **Consolidation helpers compose existing helpers, never issue their own SQL.** `describe` sets the precedent: an "all-in-one" view is a composition over standalone primitives, asserted equal by test — never a parallel query that can drift.
- **Decide explicitly AGAINST deferred carves when the surface is clean.** The v0.6.0 `db.meta.*` question was closed by choosing to stay additive on `db.schema.*` — no new accessor, no deprecation cycle on a just-cleaned surface. "Resolve the old open question" is a legitimate milestone deliverable.

### Key Lessons

1. **Accumulated pattern discipline compounds into near-zero-cost milestones.** v0.9.0 added 12 methods across two families with essentially no design events — the builder-pur/accessor/parity conventions established v0.4.0–v0.8.0 did all the heavy lifting. The investment in conventions pays its largest dividend on the most routine work.
2. **A good audit surfaces tracking gaps without crying wolf.** The 3-source cross-reference flagged the missing SUMMARY frontmatter as "verify manually" rather than "unsatisfied" — exactly the right severity. Trust the matrix, then do the manual check it asks for.
3. **The recurring tooling taxes are now certainties to design around, not surprises.** STATE.md "Last Activity Description" drift (8th+), MILESTONES `Delivered`/`Stats` hand-enrichment (6th), REQUIREMENTS checkbox-vs-table drift at close (recurring) — these are overdue CLI fixes, not milestone anomalies. Budget the hand-fix time up front.

### Cost Observations

- Model mix: Opus for orchestration/planning/review/audit, Sonnet for executors/verifier/integration-checker.
- Sessions: 2026-06-24 (milestone launch + Phases 34–35) → 2026-06-25 (Phase 35 verify + Phase 36 release + close), ~2 days.
- Notable: 3 phases, 7 plans, smallest milestone since v0.5.0; mature patterns meant zero design churn — the work was almost entirely mechanical additive implementation + a clean human-gated release.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v0.3.0 | 7 (1–7) | 14 | Initial consolidation: full async parity, real-PostgreSQL testing |
| v0.4.0 | 7 (9–15) | 36 | uv toolchain, coverage ratchet discipline, builder/accessor pattern, human-gated release |
| v0.5.0 | 5 (16–20) | 13 | ETL pipeline runner via the spatial mirror pattern; structural run-log isolation; fenced reversible-prep + human-gated publish |
| v0.6.0 | 4 (21–24) | 13 | Accessor reorg via `@deprecated_alias` + lazy accessors; prove-once-replicate-N; `-W error` as the load-bearing refactor gate; milestone audit restored |
| v0.7.0 | 5 (25–29) | 13 | Alias hard-removal (delete-the-wrapper-block) + incremental ETL on the reserved `watermark JSONB`; layered pure→run-log→extract/parity decomposition; review caught real coercion bugs |
| v0.8.0 | 4 (30–33) | 11 | Advanced TimescaleDB surface (`db.timescale.*` 6→15) on the v0.5.0 autocommit seam; mock-authoritative + license-tolerant testing for Apache/TSL split; plan-time live verification reversed a wrong license assumption (D-08) |
| v0.9.0 | 3 (34–36) | 7 | Ergonomic CRUD + enriched introspection (12 methods, full parity) via one shared `_build_where_dict` builder + `describe` pure-composition; near-zero design churn from mature patterns; resolved the v0.6.0 `db.meta.*` carve question (decided against) |

### Cumulative Quality

| Milestone | Test files | Coverage | Notes |
|-----------|-----------|----------|-------|
| v0.3.0 | — | 72.76% | Coverage 23% → 72.76%; real-DB tests |
| v0.4.0 | 22 (~749 tests) | 94.09% | Ratchet 70→80→90→92→94; numpydoc + interrogate gate |
| v0.5.0 | 23 (~983 tests) | 94.26% | Ratchet held at 94 with new async ETL behavioral tests; interrogate 100% |
| v0.6.0 | 30+ (~1100 tests) | 95.64% | Ratchet held at 94; +56 DB-free alias tests + 7-pair parity; `-W error::DeprecationWarning` green at 1030 unit tests; interrogate 100% |
| v0.7.0 | 30+ (~1180 tests) | 95.11% | Ratchet held at 94; +114-test `test_alias_removal.py` (AttributeError + WR-01) + 34 DB-free incremental builder tests + live-DB watermark round-trips; `-W error::DeprecationWarning` green (no stubs left); interrogate 100% |
| v0.8.0 | 31+ (~1288 tests) | 95.11% | Ratchet held at 94; new `test_timescale.py` two-layer (mock SQL-shape + Apache-tolerant live) for 9 methods + 9-name surface parity assertion; `-W error::DeprecationWarning` green; interrogate 100% |
| v0.9.0 | 31+ (~1331 tests) | 94.11% | Ratchet held at 94; +CRUD unit/integration (`_build_where_dict` + 7 helpers × sync/async) + schema-introspection mock+live + `TestAsyncSchemaIntrospection` to clear the ratchet + `test_schema_v090_surface`; `-W error::DeprecationWarning` green; interrogate 100% |

### Top Lessons (Verified Across Milestones)

1. **Real PostgreSQL beats mocks** for catching driver/DB interaction bugs (v0.3.0, v0.4.0, and v0.5.0 all surfaced latent bugs only real-DB tests caught).
2. **Sync is the established core-value API; align async toward it** — enriching async never breaking sync kept the parity promise with zero sync breakage across all three milestones.
3. **The builder/accessor mirror pattern compounds.** Established in v0.4.0 (spatial), reused wholesale in v0.5.0 (ETL), the *target shape* the v0.6.0 monolith was refactored toward, in v0.7.0 it made the async incremental surface a near-mechanical 1:1 mirror of sync, and in v0.8.0 it absorbed 9 new TimescaleDB methods with near-zero design churn — the most reusable architectural decision of the project.
4. **Forward-compat scaffolding pays off a milestone later.** v0.5.0 reserved a nullable `watermark JSONB` column (always NULL); v0.7.0 turned it into incremental ETL with **zero breaking migration**. The reserve-the-column bet is now a proven, repeatable pattern — make the cheap forward-compat move whenever a future additive feature is foreseeable.
5. **A breaking removal is safe only if the prior deprecation cycle set it up.** v0.6.0's logic-in-accessor + warn+delegate wrappers (D-SCOPE-2) made v0.7.0's hard removal a one-block delete with zero logic risk; the enumerated `test_alias_removal.py` made "surface is accessor-only" a hard invariant. Sequence the deprecation cycle correctly and the break is mechanical.
6. **Recurring tooling taxes, now tracked across milestones:** (a) the SUMMARY one-liner auto-extraction / MILESTONES enrichment-by-hand — confirmed v0.4.0–v0.8.0 (five running); (b) STATE.md bookkeeping drift requiring hand-fixes at phase/milestone close — acute v0.6.0–v0.8.0 (7th+ occurrence), the CLI-written format and the close-step's expected format have diverged (`milestone.complete` warns it cannot update "Last Activity Description"); (c) **new in v0.8.0:** REQUIREMENTS.md checkbox-vs-traceability-table drift at close (the phase CLIs update the table but not the inline checkboxes). All three are tooling-level fixes overdue. Manual REQUIREMENTS.md checkbox updates stayed sidestepped v0.6.0/v0.7.0 by running on `main`, but resurfaced in v0.8.0's archive.
7. **Match execution mode to the work; review data/error paths adversarially.** v0.6.0–v0.8.0 all ran cleanly sequential-on-main (mechanical/low-conflict work) — reserve worktrees for genuinely parallel, file-disjoint work. Separately, code review keeps earning its cost on types/errors crossing a DB boundary: v0.7.0 caught two coercion bugs (`pd.isna` before `is_float`, float-vs-int), v0.8.0 caught three in new TimescaleDB code (error-swallowing `except`, missing validation, unvalidated destructive-path input).
8. **Structural connection seams are reusable cross-milestone infrastructure.** The `connect(autocommit=True)` seam built for v0.5.0 ETL run-log isolation became the enabling primitive for the entire v0.8.0 continuous-aggregate lifecycle — at zero design cost. Second only to forward-compat scaffolding in leverage. And for environment-dependent facts (licenses, extension versions, planner behavior), a 30-second live `psql` check at plan time beats a confident assumption — v0.8.0's D-08 reversal proved it.
