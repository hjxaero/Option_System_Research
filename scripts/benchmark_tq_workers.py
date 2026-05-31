from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.data.live_update import update_daily_minute_quotes
from option_platform.data.sources.tq import tq_api


BENCHMARK_SYMBOLS = [
    "CFFEX.MO2601-C-6500",
    "CFFEX.MO2601-C-6600",
    "CFFEX.MO2601-C-6700",
    "CFFEX.MO2601-C-6800",
    "CFFEX.MO2601-C-6900",
    "CFFEX.MO2601-C-7000",
    "CFFEX.MO2601-C-7100",
    "CFFEX.MO2601-C-7200",
    "CFFEX.MO2601-C-7300",
    "CFFEX.MO2601-C-7400",
]
BENCHMARK_DATES = ["2026-01-15", "2026-01-16"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark TqSdk tick download throughput by worker count.")
    parser.add_argument("--workers", default="1,2,3,4,6,8", help="Comma-separated worker counts to test.")
    parser.add_argument("--output-root", help="Temp data root; default data_store/benchmark_workers")
    return parser.parse_args()


def _symbol_job(payload: dict) -> dict:
    symbol = payload["symbol"]
    errors: list[str] = []
    calls = 0
    t0 = time.perf_counter()
    try:
        with tq_api() as api:
            for trade_date in payload["trade_dates"]:
                try:
                    update_daily_minute_quotes(
                        api=api,
                        data_root=payload["data_root"],
                        product="MO",
                        symbol=symbol,
                        trade_date=trade_date,
                        max_quote_age_ms=60_000,
                    )
                    calls += 1
                except Exception as exc:
                    errors.append(f"{trade_date}: {exc}")
    except Exception as exc:
        errors.append(f"api: {exc}")
    elapsed = time.perf_counter() - t0
    return {"symbol": symbol, "calls": calls, "errors": errors, "elapsed": elapsed}


def run_case(workers: int, data_root: Path) -> dict:
    jobs = [
        {
            "symbol": symbol,
            "trade_dates": BENCHMARK_DATES,
            "data_root": str(data_root),
        }
        for symbol in BENCHMARK_SYMBOLS
    ]
    expected_calls = len(jobs) * len(BENCHMARK_DATES)
    errors: list[str] = []
    calls = 0
    t0 = time.perf_counter()

    if workers <= 1:
        for job in jobs:
            result = _symbol_job(job)
            calls += result["calls"]
            errors.extend(result["errors"])
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_symbol_job, job) for job in jobs]
            for future in as_completed(futures):
                result = future.result()
                calls += result["calls"]
                errors.extend(result["errors"])

    wall = time.perf_counter() - t0
    return {
        "workers": workers,
        "symbols": len(BENCHMARK_SYMBOLS),
        "days": len(BENCHMARK_DATES),
        "expected_calls": expected_calls,
        "completed_calls": calls,
        "wall_seconds": round(wall, 2),
        "calls_per_second": round(calls / wall, 3) if wall > 0 else 0.0,
        "speedup_vs_1": None,
        "errors": len(errors),
        "error_samples": errors[:3],
    }


def main() -> None:
    args = parse_args()
    worker_list = [int(x.strip()) for x in args.workers.split(",") if x.strip()]
    output_root = Path(args.output_root) if args.output_root else PROJECT_ROOT / "data_store" / "benchmark_workers"
    output_root.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    baseline: float | None = None
    for workers in worker_list:
        case_dir = output_root / f"w{workers}_{datetime.now().strftime('%H%M%S')}"
        case_dir.mkdir(parents=True, exist_ok=True)
        print(f"benchmark workers={workers} ...", flush=True)
        row = run_case(workers, case_dir)
        if baseline is None:
            baseline = row["wall_seconds"]
            row["speedup_vs_1"] = 1.0
        elif baseline and baseline > 0:
            row["speedup_vs_1"] = round(baseline / row["wall_seconds"], 2)
        results.append(row)
        print(
            f"  wall={row['wall_seconds']}s calls={row['completed_calls']}/{row['expected_calls']} "
            f"cps={row['calls_per_second']} speedup={row['speedup_vs_1']} errors={row['errors']}",
            flush=True,
        )

    report_path = output_root / "benchmark_results.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report={report_path}", flush=True)


if __name__ == "__main__":
    main()
