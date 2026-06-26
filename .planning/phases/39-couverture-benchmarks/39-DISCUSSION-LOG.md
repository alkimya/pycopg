# Phase 39: Couverture & Benchmarks - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-26
**Phase:** 39-couverture-benchmarks
**Areas discussed:** Benchmark tooling, Comparative baseline, Regression guard-rail, Coverage 94→95 approach

---

## Benchmark tooling

| Option | Description | Selected |
|--------|-------------|----------|
| Stdlib script | Standalone `benchmarks/` runner using `time.perf_counter` + `statistics`; run via `python -m benchmarks` / `make bench`. Zero new deps even in dev, decoupled from pytest/coverage gate. | ✓ |
| pytest-benchmark | New dev-dep with statistical rigor + JSON compare + `--benchmark-compare`; couples to pytest, needs marker + deselection to stay out of the gate. | |
| asv | Airspeed-velocity — overkill (mentioned, not offered). | |

**User's choice:** Stdlib script (Recommended)
**Notes:** Settles location/isolation as a consequence — `benchmarks/` is top-level, NOT in `[tool.pytest.ini_options] testpaths` (stays `["tests"]`), so the coverage gate never touches it; entry `python -m benchmarks` + `make bench`; row-count is a CLI arg defaulting to ~100k. User accepted these consequences without objection.

---

## Comparative baseline

| Option | Description | Selected |
|--------|-------------|----------|
| Methods head-to-head | Benchmark real shipping paths against each other on the same volume: `insert_batch` (executemany baseline) vs `copy_insert` vs `from_dataframe` vs ETL load. COPY gain = speedup over `insert_batch`. No dead code. | ✓ |
| Resurrect to_sql baseline | Add a throwaway `df.to_sql()` inside the benchmark to show literal pre/post Phase 38; reintroduces dead SQLAlchemy-engine path + engine fixture. | |
| Both | Head-to-head AND a `to_sql` reference row for `from_dataframe`. | |

**User's choice:** Methods head-to-head (Recommended)
**Notes:** Every number maps to a method that ships; `insert_batch` is the row-by-row baseline COPY beats.

---

## Regression guard-rail

| Option | Description | Selected |
|--------|-------------|----------|
| Documented manual tool | Suite prints a readable comparative table; human runs on-demand and interprets regressions per a documented protocol. NOT wired to CI. Keeps timing out of the de-flaked gate (38-D-06). | ✓ |
| Committed baseline + threshold | Store baseline + assert tolerance; timing on shared/CI runners is noisy → risks re-flaking what Phase 37 fixed; needs a non-pytest harness. | |
| Relative-ratio check | Assert hardware-independent invariants (e.g. copy_insert ≥ Nx insert_batch); still an automated timing assertion to maintain. | |

**User's choice:** Documented manual tool (Recommended)
**Notes:** Protocol lives in `benchmarks/README.md` (how to run, how to read, what a regression looks like). Consistent with ROADMAP success criterion #3 ("comment interpréter une régression" ⇒ human reading).

---

## Coverage 94→95 approach

| Option | Description | Selected |
|--------|-------------|----------|
| Real tests, pragma as last resort | Prefer genuine behavioral tests for real untested branches; allow `pragma: no cover` ONLY for unreachable/defensive lines, each justified inline. Introduces the convention deliberately + sparingly. | ✓ |
| Real tests only, no pragma | Hit 95% purely with new tests; never add pragma; risks brittle tests on uninstrumentable defensive lines. | |
| Pragma-forward | Lean on pragma/excludes to reach 95% with minimal new tests; weakens the hardening intent. | |

**User's choice:** Real tests, pragma as last resort (Recommended)
**Notes:** Big miss pools to target: `async_database.py` (68), `database.py` (41), `etl.py` (27), `timescale.py` (24), `schema.py` (18) — researcher reconfirms exact lines under `PGDATABASE=pycopg_test2`. Bump `--cov-fail-under` 94→95 is the last act, after measured ≥95%.

---

## Claude's Discretion

- Exact output-table shape (columns, rows/s vs ms, warmup/discard of first run) — lean: warmup + N runs, median, speedup-vs-`insert_batch` column.
- Benchmark DB-env handling — reuse `PG*` vars / `pycopg_test`(CI) / `pycopg_test2`(local) like the tests.
- Which precise lines to test for 95% (and the rare few worth `pragma`) — after a clean `--cov-report=term-missing` run.
- Whether to also add `benchmarks/` to `[tool.coverage.run] omit` (belt-and-suspenders; already out of `testpaths`).

## Deferred Ideas

- REL-10 (version bump, CHANGELOG, 4 gates, tag + PyPI publish + smoke) → Phase 40.
- COPY binaire (PERF-F01) + numpy vectorization (PERF-F02) → v2.
- Committed-baseline automated regression gate → deferred for this milestone (D-03), reconsider post-1.0 with a stable perf runner.
- Benchmark-protocol pointer in project README / Sphinx docs → optional, planner's call.
- WR-03 (`copy_insert` session bypass) hardening → stays deferred to v1.0.0 (from Phase 37).
