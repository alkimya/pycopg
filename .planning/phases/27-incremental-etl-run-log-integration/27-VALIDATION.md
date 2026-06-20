---
phase: 27
slug: incremental-etl-run-log-integration
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-20
---

# Phase 27 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ `pytest-cov`, ratchet ≥ 94) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]` — `addopts` carry `--cov-fail-under`) |
| **Quick run command** | `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -o addopts="" -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30 seconds (etl modules) / full suite longer |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -o addopts="" -x -q`
- **After every plan wave:** Run `uv run pytest -o addopts=""` for the etl test modules + coverage spot-check on `etl.py`/`queries.py`
- **Before `/gsd-verify-work`:** Full suite green (modulo the named pre-existing flaky DB tests); `interrogate ≥ 95`; coverage ratchet ≥ 94 held; `ruff check` + `black` clean
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (SC-1) | 27-01 | 1 | ETL-INC-02 | — | N/A | integration | `... -k first_run_records_watermark ...` | ❌ W0 | ⬜ pending |
| (SC-2) | 27-01 | 1 | ETL-INC-06 | — | Failed load leaves `watermark IS NULL`; no advance | integration | `... -k failed_run_does_not_advance_watermark ...` | ❌ W0 | ⬜ pending |
| (SC-3) | 27-01 | 1 | ETL-INC-05 | — | Empty batch preserves prior; never writes NULL | integration | `... -k empty_batch_preserves_watermark ...` | ❌ W0 | ⬜ pending |
| (SC-4) | 27-01 | 1 | ETL-INC-10 | — | N/A | integration | `... -k watermark_jsonb_roundtrip ...` | ❌ W0 | ⬜ pending |
| (D-04) | 27-01 | 1 | ETL-INC-02 | — | `_read_watermark` → `None` on first run | integration | `... -k read_watermark_none_first_run ...` | ❌ W0 | ⬜ pending |
| (D-06) | 27-01 | 1 | ETL-INC-02 | — | Missing column → `ETLError`, not `KeyError` | integration | `... -k incremental_column_missing_raises_etlerror ...` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Concrete Runnable Assertions per Success Criterion

- **SC-1 / ETL-INC-02 (first run persists max):** build `etl_src` with a known max in `incremental_column` (e.g. `id INTEGER`); `Pipeline(incremental_column="id", load_mode="upsert", conflict_columns=["id"], ...)`; `result = db.etl.run(p)`; then assert the `pipeline_runs.watermark` row equals `{"type": "int", "value": <known_max>}` (plain dict from JSONB) AND `db.etl._read_watermark(name) == <known_max>`.
- **SC-2 / ETL-INC-06 (no-advance-on-failure):** (a) seed a prior success watermark `W0`; (b) induce a deterministic failure (reuse the `_start_run` + `db.transaction()` + forced-`RuntimeError` harness from `test_failed_run_commits_despite_load_rollback`, `tests/test_etl_accessor.py:259`); assert the failed row has `status='failed'` AND `watermark IS NULL`, and `_read_watermark(name) == W0` (prior preserved).
- **SC-3 / ETL-INC-05 (empty batch preserves):** seed prior `W0`; run a pipeline whose source returns 0 rows (`source="SELECT 1 AS id WHERE false"`) with `incremental_column="id"`; assert the row has `status='success'`, `rows_loaded=0`, `watermark IS NULL` for that run, and `_read_watermark(name) == W0`.
- **SC-4 / ETL-INC-10 (round-trip no-drift):** parametrize over `(timestamp tz-aware, integer, text)`; for each, run an incremental pipeline and assert the decoded read-back equals the **coerced** `max()` (compare datetime to `m.to_pydatetime()`, NOT a hand literal — Pitfall 4 timestamptz UTC-normalization); assert the persisted `type` tag matches and (datetime) the ISO string retains its offset + microseconds.

---

## Wave 0 Requirements

- [ ] `tests/test_etl_accessor.py` — add the 6 incremental integration tests above (extend `TestRunPipelineIntegration`, reuse `db` / `cleanup_pipeline_runs` / `etl_table` / `etl_src` fixtures, `:422-444`)
- [ ] (optional) `tests/test_etl.py::TestEncodeDecodeWatermark` (`:629`) — only if a pure coercion helper is extracted; otherwise coercion is covered by the integration tests
- [ ] Framework install: **none** — pytest + live DB already in place

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
