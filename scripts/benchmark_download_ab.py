from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.data.live_update import update_daily_minute_quotes, update_symbol_range_minute_quotes
from option_platform.data.sources.tq import tq_api

DEFAULT_SYMBOLS = [
    "CFFEX.MO2601-C-6500",
    "CFFEX.MO2601-C-6600",
    "CFFEX.MO2601-C-6700",
    "CFFEX.MO2601-C-6800",
    "CFFEX.MO2601-C-6900",
    "CFFEX.MO2601-C-7000",
    "CFFEX.MO2601-C-7100",
    "CFFEX.MO2601-C-7200",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark download granularity and worker counts.")
    parser.add_argument("--start", default="2026-01-12")
    parser.add_argument("--end", default="2026-01-16")
    parser.add_argument("--symbols", type=int, default=8, help="Number of symbols from DEFAULT_SYMBOLS.")
    parser.add_argument("--workers", default="1,2,4,6,8", help="Worker counts for test 2.")
    parser.add_argument("--output-root", default="data_store/benchmark_ab")
    parser.add_argument("--skip-granularity", action="store_true")
    parser.add_argument("--skip-workers", action="store_true")
    return parser.parse_args()


def trading_days(start: str, end: str) -> list[str]:
    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    dates: list[str] = []
    current = start_dt
    while current <= end_dt:
        if current.weekday() < 5:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def _run_daily(symbol: str, trade_dates: list[str], data_root: Path) -> dict:
    errors: list[str] = []
    saved = 0
    t0 = time.perf_counter()
    try:
        with tq_api() as api:
            for trade_date in trade_dates:
                try:
                    update_daily_minute_quotes(
                        api=api,
                        data_root=data_root,
                        product="MO",
                        symbol=symbol,
                        trade_date=trade_date,
                        max_quote_age_ms=60_000,
                    )
                    saved += 1
                except Exception as exc:
                    errors.append(f"{trade_date}: {exc}")
    except Exception as exc:
        errors.append(f"api: {exc}")
    elapsed = time.perf_counter() - t0
    return {
        "symbol": symbol,
        "mode": "daily_per_trade_date",
        "tq_calls_est": len(trade_dates),
        "saved_days": saved,
        "errors": errors,
        "elapsed_s": round(elapsed, 2),
    }


def _run_range(symbol: str, trade_dates: list[str], data_root: Path) -> dict:
    errors: list[str] = []
    saved = 0
    skipped = 0
    t0 = time.perf_counter()
    try:
        with tq_api() as api:
            saved, skipped, failures = update_symbol_range_minute_quotes(
                api=api,
                data_root=data_root,
                product="MO",
                symbol=symbol,
                trade_dates=trade_dates,
                max_quote_age_ms=60_000,
                skip_if_complete=False,
            )
        errors.extend(failures)
    except Exception as exc:
        errors.append(f"api: {exc}")
    elapsed = time.perf_counter() - t0
    return {
        "symbol": symbol,
        "mode": "symbol_range_once",
        "tq_calls_est": 1,
        "saved_days": saved,
        "skipped_days": skipped,
        "errors": errors,
        "elapsed_s": round(elapsed, 2),
    }


def benchmark_granularity(symbols: list[str], trade_dates: list[str], output_root: Path) -> dict:
    daily_root = output_root / "granularity_daily"
    range_root = output_root / "granularity_range"
    for path in (daily_root, range_root):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    daily_results = []
    range_results = []
    print(f"[test1] daily mode symbols={len(symbols)} days={len(trade_dates)}", flush=True)
    for idx, symbol in enumerate(symbols, 1):
        print(f"  daily [{idx}/{len(symbols)}] {symbol}", flush=True)
        daily_results.append(_run_daily(symbol, trade_dates, daily_root))

    print(f"[test1] range mode symbols={len(symbols)} days={len(trade_dates)}", flush=True)
    for idx, symbol in enumerate(symbols, 1):
        print(f"  range [{idx}/{len(symbols)}] {symbol}", flush=True)
        range_results.append(_run_range(symbol, trade_dates, range_root))

    daily_wall = round(sum(r["elapsed_s"] for r in daily_results), 2)
    range_wall = round(sum(r["elapsed_s"] for r in range_results), 2)
    daily_errors = sum(len(r["errors"]) for r in daily_results)
    range_errors = sum(len(r["errors"]) for r in range_results)
    speedup = round(daily_wall / range_wall, 2) if range_wall > 0 else None

    return {
        "symbols": len(symbols),
        "trade_dates": trade_dates,
        "daily": {
            "wall_seconds": daily_wall,
            "tq_calls_est_total": len(symbols) * len(trade_dates),
            "errors": daily_errors,
            "per_symbol": daily_results,
        },
        "range": {
            "wall_seconds": range_wall,
            "tq_calls_est_total": len(symbols),
            "errors": range_errors,
            "per_symbol": range_results,
        },
        "range_vs_daily_speedup": speedup,
        "winner": "range" if speedup and speedup > 1.05 else ("daily" if speedup and speedup < 0.95 else "tie"),
    }


def _worker_job(payload: dict) -> dict:
    return _run_daily(payload["symbol"], payload["trade_dates"], Path(payload["data_root"]))


def benchmark_workers(
    symbols: list[str],
    trade_dates: list[str],
    worker_list: list[int],
    output_root: Path,
) -> list[dict]:
    rows: list[dict] = []
    baseline: float | None = None
    expected_calls = len(symbols) * len(trade_dates)

    for workers in worker_list:
        case_root = output_root / f"workers_{workers}"
        if case_root.exists():
            shutil.rmtree(case_root)
        case_root.mkdir(parents=True, exist_ok=True)
        jobs = [
            {"symbol": symbol, "trade_dates": trade_dates, "data_root": str(case_root)}
            for symbol in symbols
        ]
        errors: list[str] = []
        calls = 0
        t0 = time.perf_counter()
        print(f"[test2] workers={workers}", flush=True)
        if workers <= 1:
            for job in jobs:
                result = _worker_job(job)
                calls += result["saved_days"]
                errors.extend(result["errors"])
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_worker_job, job) for job in jobs]
                for future in as_completed(futures):
                    result = future.result()
                    calls += result["saved_days"]
                    errors.extend(result["errors"])
        wall = round(time.perf_counter() - t0, 2)
        row = {
            "workers": workers,
            "wall_seconds": wall,
            "completed_calls": calls,
            "expected_calls": expected_calls,
            "calls_per_second": round(calls / wall, 3) if wall > 0 else 0.0,
            "errors": len(errors),
            "error_samples": errors[:3],
            "speedup_vs_1": None,
        }
        if baseline is None:
            baseline = wall
            row["speedup_vs_1"] = 1.0
        elif baseline > 0:
            row["speedup_vs_1"] = round(baseline / wall, 2)
        rows.append(row)
        print(
            f"  wall={row['wall_seconds']}s cps={row['calls_per_second']} "
            f"speedup={row['speedup_vs_1']} errors={row['errors']}",
            flush=True,
        )
    return rows


def main() -> None:
    args = parse_args()
    symbols = DEFAULT_SYMBOLS[: max(args.symbols, 1)]
    trade_dates = trading_days(args.start, args.end)
    output_root = PROJECT_ROOT / args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start": args.start,
        "end": args.end,
        "symbols": symbols,
        "trade_dates": trade_dates,
    }

    if not args.skip_granularity:
        report["granularity"] = benchmark_granularity(symbols, trade_dates, output_root)

    if not args.skip_workers:
        worker_list = [int(x.strip()) for x in args.workers.split(",") if x.strip()]
        report["workers"] = benchmark_workers(symbols, trade_dates, worker_list, output_root)

    report_path = output_root / "ab_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report={report_path}", flush=True)


if __name__ == "__main__":
    main()
