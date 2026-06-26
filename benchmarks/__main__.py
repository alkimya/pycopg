"""Benchmark suite for pycopg insertion paths.

Measures the four shipped insertion methods head-to-head on a configurable
volume and prints a comparative table with rows/s, median ms, and speedup
vs insert_batch (the executemany baseline).

Usage::

    PGDATABASE=pycopg_test2 python -m benchmarks [--rows N] [--runs N]

Options
-------
--rows N    Number of rows to insert per method (default 100 000).
--runs N    Number of timed runs per method (default 5); one warmup run
            is always discarded before timing begins.

No timing assertion is performed (D-03). A human interprets the table.
"""

from __future__ import annotations

import argparse
import statistics
import time
import uuid

import pandas as pd

from pycopg import Database
from pycopg.etl import Pipeline

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _make_rows(n: int) -> list[dict]:
    """Return *n* simple dicts with id, val, and label columns."""
    return [{"id": i, "val": float(i) * 0.1, "label": f"row_{i}"} for i in range(n)]


def _make_df(n: int) -> pd.DataFrame:
    """Return a DataFrame with id, val, and label columns."""
    return pd.DataFrame(_make_rows(n))


# ---------------------------------------------------------------------------
# Timing harness
# ---------------------------------------------------------------------------


def _time_it(fn, *, runs: int, warmup: int = 1):
    """Time *fn* over *runs* measured calls, discarding *warmup* runs first.

    Parameters
    ----------
    fn:
        Zero-argument callable to benchmark.
    runs:
        Number of timed calls (each call is a full insert + implicit teardown
        handled by the caller).
    warmup:
        Number of calls discarded before timing begins (warms connection
        cache / planner).

    Returns
    -------
    tuple[int, list[int]]
        ``(median_ns, times_ns)`` — median over timed calls in nanoseconds,
        and the full list of per-call timings.
    """
    for _ in range(warmup):
        fn()
    times: list[int] = []
    for _ in range(runs):
        t0 = time.perf_counter_ns()
        fn()
        times.append(time.perf_counter_ns() - t0)
    return statistics.median(times), times


# ---------------------------------------------------------------------------
# Table management helpers
# ---------------------------------------------------------------------------


def _fresh_name(base: str) -> str:
    """Return a UUID-suffixed table name to avoid cross-run collisions."""
    suffix = uuid.uuid4().hex[:8]
    return f"{base}_{suffix}"


def _create_bench_table(db: Database, table: str) -> None:
    """Create a simple table for benchmarking (id, val, label)."""
    db.execute(
        f"CREATE TABLE IF NOT EXISTS {table} "
        "(id INTEGER, val DOUBLE PRECISION, label TEXT)"
    )


def _drop_table(db: Database, table: str) -> None:
    """Drop a table unconditionally (IF EXISTS for safety)."""
    db.execute(f"DROP TABLE IF EXISTS {table}")


def _truncate_pipeline_runs(db: Database) -> None:
    """Remove accumulated pipeline_runs rows so repeat runs stay comparable."""
    db.execute("TRUNCATE TABLE pipeline_runs")


# ---------------------------------------------------------------------------
# Per-method benchmark functions
# ---------------------------------------------------------------------------


def _bench_insert_batch(db: Database, rows: list[dict], runs: int) -> int:
    """Benchmark insert_batch (executemany baseline).

    Returns median elapsed time in nanoseconds.
    """
    table = _fresh_name("bench_insert_batch")
    try:
        _create_bench_table(db, table)

        def fn() -> None:
            db.execute(f"TRUNCATE TABLE {table}")
            db.insert_batch(table, rows)

        # Warmup: one run to warm connection/planner; then timed runs
        median_ns, _ = _time_it(fn, runs=runs, warmup=1)
    finally:
        _drop_table(db, table)
    return int(median_ns)


def _bench_copy_insert(db: Database, rows: list[dict], runs: int) -> int:
    """Benchmark copy_insert (COPY protocol).

    Returns median elapsed time in nanoseconds.
    """
    table = _fresh_name("bench_copy_insert")
    try:
        _create_bench_table(db, table)

        def fn() -> None:
            db.execute(f"TRUNCATE TABLE {table}")
            db.copy_insert(table, rows)

        median_ns, _ = _time_it(fn, runs=runs, warmup=1)
    finally:
        _drop_table(db, table)
    return int(median_ns)


def _bench_from_dataframe(db: Database, df: pd.DataFrame, runs: int) -> int:
    """Benchmark from_dataframe (Hybrid DDL+COPY).

    Returns median elapsed time in nanoseconds.
    """
    table = _fresh_name("bench_from_dataframe")
    try:
        # First call (warmup) creates the table via DDL; subsequent calls
        # use if_exists="replace" which truncates and re-loads via COPY.
        def fn() -> None:
            db.from_dataframe(df, table, if_exists="replace")

        median_ns, _ = _time_it(fn, runs=runs, warmup=1)
    finally:
        _drop_table(db, table)
    return int(median_ns)


def _bench_etl_run(db: Database, rows: list[dict], runs: int) -> int:
    """Benchmark db.etl.run via the COPY seam (load_mode='replace').

    Returns median elapsed time in nanoseconds.
    """
    src = _fresh_name("bench_etl_src")
    dst = _fresh_name("bench_etl_dst")
    try:
        # Create and populate the source table once.
        _create_bench_table(db, src)
        db.insert_batch(src, rows)

        # Create the destination table (replace mode TRUNCATEs then COPYs).
        _create_bench_table(db, dst)

        pipeline = Pipeline(
            name="bench_etl",
            source=src,
            target=dst,
            load_mode="replace",  # routes via COPY seam (D-03 in plan)
            schema="public",
        )

        def fn() -> None:
            db.etl.run(pipeline)

        median_ns, _ = _time_it(fn, runs=runs, warmup=1)
    finally:
        _drop_table(db, src)
        _drop_table(db, dst)
        # Clean up pipeline_runs rows so repeat bench runs stay comparable.
        try:
            _truncate_pipeline_runs(db)
        except Exception:
            pass  # pipeline_runs may not exist if ETL never ran
    return int(median_ns)


# ---------------------------------------------------------------------------
# Table printer
# ---------------------------------------------------------------------------

_COL_METHOD = 22
_COL_ROWS_S = 12
_COL_MS = 12
_COL_SPEEDUP = 26


def _print_table(n_rows: int, runs: int, results: dict[str, int]) -> None:
    """Print a comparative table of the benchmark results.

    Parameters
    ----------
    n_rows:
        Number of rows inserted per run.
    runs:
        Number of timed runs per method.
    results:
        Mapping of method label to median elapsed time in nanoseconds.
    """
    sep_total = _COL_METHOD + _COL_ROWS_S + _COL_MS + _COL_SPEEDUP + 9
    header_title = (
        f"pycopg insertion benchmark — {n_rows:,} rows, {runs} runs (warmup=1)"
    )
    print()
    print(header_title)
    print("=" * max(len(header_title), sep_total))

    col_h = (
        f"{'Method':<{_COL_METHOD}} | "
        f"{'rows/s':>{_COL_ROWS_S}} | "
        f"{'median_ms':>{_COL_MS}} | "
        f"{'speedup vs insert_batch':<{_COL_SPEEDUP}}"
    )
    print(col_h)
    print(
        "-" * _COL_METHOD
        + "-+-"
        + "-" * _COL_ROWS_S
        + "-+-"
        + "-" * _COL_MS
        + "-+-"
        + "-" * _COL_SPEEDUP
    )

    baseline_ns = results.get("insert_batch", 1)

    for label, median_ns in results.items():
        rows_per_s = n_rows / (median_ns / 1_000_000_000)
        median_ms = median_ns / 1_000_000
        speedup = baseline_ns / median_ns
        if label == "insert_batch":
            speedup_str = "1.00x (baseline)"
        else:
            speedup_str = f"{speedup:.2f}x"
        print(
            f"{label:<{_COL_METHOD}} | "
            f"{rows_per_s:>{_COL_ROWS_S},.0f} | "
            f"{median_ms:>{_COL_MS},.1f} | "
            f"{speedup_str:<{_COL_SPEEDUP}}"
        )
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all four insertion benchmarks and print a comparative table."""
    parser = argparse.ArgumentParser(
        description="pycopg benchmark suite — measures all 4 insertion paths"
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=100_000,
        help="Number of rows per method (default: 100 000)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Timed runs per method, excluding warmup (default: 5)",
    )
    args = parser.parse_args()

    n_rows = args.rows
    runs = args.runs

    print(f"Connecting via Database.from_env() — {n_rows:,} rows, {runs} runs …")
    db = Database.from_env()

    rows = _make_rows(n_rows)
    df = _make_df(n_rows)

    results: dict[str, int] = {}

    print("  [1/4] insert_batch …", end=" ", flush=True)
    results["insert_batch"] = _bench_insert_batch(db, rows, runs)
    print("done")

    print("  [2/4] copy_insert …", end=" ", flush=True)
    results["copy_insert"] = _bench_copy_insert(db, rows, runs)
    print("done")

    print("  [3/4] from_dataframe …", end=" ", flush=True)
    results["from_dataframe"] = _bench_from_dataframe(db, df, runs)
    print("done")

    print("  [4/4] etl.run (replace) …", end=" ", flush=True)
    results["etl.run (replace)"] = _bench_etl_run(db, rows, runs)
    print("done")

    _print_table(n_rows, runs, results)


if __name__ == "__main__":
    main()
