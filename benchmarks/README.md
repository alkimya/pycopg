# pycopg Insertion Benchmarks

Reproducible, stdlib-only benchmark suite for the four shipped insertion
paths in pycopg.  Documents the COPY gains delivered in Phase 38 and
provides a human-read regression guard-rail — with **no automated timing
assertion** (D-03), so the suite stays stable in CI.

---

## Prerequisites

1. Install the dev environment:

   ```bash
   uv sync --all-extras --dev
   ```

2. A running PostgreSQL instance (TimescaleDB not required).

3. Set the standard `PG*` environment variables before running:

   ```bash
   export PGHOST=localhost
   export PGPORT=5432
   export PGUSER=postgres
   export PGPASSWORD=postgres
   export PGDATABASE=pycopg_test2   # use a throwaway test database
   ```

   All four env vars are optional if your local Postgres accepts peer/trust
   auth with the defaults.  The benchmark calls `Database.from_env()`, which
   reads the same `PG*` env vars that the test suite uses.

---

## How to Run

### Option A — directly

```bash
PGDATABASE=pycopg_test2 python -m benchmarks
```

### Option B — via make

```bash
PGDATABASE=pycopg_test2 make bench
```

> The `make bench` target calls `python -m benchmarks` directly (not via
> `uv run`) so the caller controls the environment.  Set `PG*` before
> invoking make.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--rows N` | 100 000 | Rows inserted per method per run |
| `--runs N` | 5 | Number of timed runs (one warmup run is always discarded) |

```bash
PGDATABASE=pycopg_test2 python -m benchmarks --rows 50000 --runs 3
```

---

## How to Read the Table

Sample output (100 000 rows, 5 runs, warmup=1):

```
pycopg insertion benchmark — 100 000 rows, 5 runs (warmup=1)
=======================================================================
Method                 |       rows/s |    median_ms | speedup vs insert_batch
-----------------------+--------------+--------------+------------------------
insert_batch           |       45 000 |      2 222.3 | 1.00x (baseline)
copy_insert            |      890 000 |        112.4 | 19.8x
from_dataframe         |      750 000 |        133.3 | 16.7x
etl.run (replace)      |      620 000 |        161.3 | 13.8x
```

**Columns:**

- `rows/s` — throughput: `n_rows / median_elapsed_s`.  Higher is better.
- `median_ms` — median wall-clock time across the `--runs` timed calls.
  The warmup call is discarded to avoid planner and connection cold-start
  distortion.
- `speedup vs insert_batch` — ratio `insert_batch_median / method_median`.
  `1.00x` is the executemany baseline.  Values > 1 are faster; < 1 slower.

**Expected range (100 000 rows, idle local machine):**

- `insert_batch` — ~30–60 k rows/s (executemany, round-trips per batch).
- `copy_insert` — ~500 k–1.5 M rows/s (COPY binary, ~10x–30x faster).
- `from_dataframe` — similar to `copy_insert` (Hybrid DDL + COPY seam).
- `etl.run (replace)` — slightly below `copy_insert` due to the run-log
  overhead of the ETL accessor (TRUNCATE + COPY + pipeline_runs row).

Numbers are hardware- and Postgres-config-dependent.  Use them as
relative ratios, not absolute benchmarks.

---

## Regression Protocol

This suite is a **human-read signal, not a CI gate** (D-03).  No timing
assertion is ever added here.

**What to watch:**

If the speedup of `copy_insert` or `from_dataframe` vs `insert_batch`
drops below approximately **5x on 100 000 rows**, investigate before
releasing:

1. Run the benchmark twice consecutively.  Occasional outliers are normal.
2. If consistently low, check whether the COPY seam was accidentally
   bypassed (look for `if_exists="fail"` in `from_dataframe` or
   `load_mode="upsert"` in the ETL path).
3. Profile with `EXPLAIN (ANALYZE, BUFFERS)` on the target table.
4. Check Postgres autovacuum and bloat on the throwaway tables.

**What is NOT a regression:**

- Low speedup at small `--rows` values (e.g., 1 000) — connection overhead
  dominates; COPY advantages only emerge at high row counts.
- Variance of ±20% between runs — acceptable on a loaded machine.

---

## Stable-Environment Tips

For reproducible numbers:

- Run on an idle machine with no competing workload.
- Use the same hardware and the same Postgres configuration for comparisons.
- Ensure Postgres `shared_buffers` and `work_mem` settings are constant.
- Warm the database (run once, discard, then record) — the benchmark does
  this automatically with `warmup=1`.

---

## Scope

`benchmarks/` is a **top-level dev-only package** outside `testpaths`.
It is never collected by `uv run pytest` and never enters the coverage gate.
It does not appear in the published PyPI wheel.
