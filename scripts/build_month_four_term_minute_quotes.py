from __future__ import annotations

import argparse
import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.contracts import OptionContract
from option_platform.data.contract_dates import filter_dates_by_first_valid, load_first_valid_date_cache
from option_platform.data.live_update import (
    minute_quote_path,
    should_skip_minute_quote_update,
    update_symbol_range_minute_quotes,
)
from option_platform.data.quality.minute_quote_report import write_quality_report
from option_platform.data.sources.tq import tq_api
from option_platform.data.sources.tq_contracts import query_option_contracts_fast
from option_platform.data.universe import select_four_term_contracts, unique_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download four-term MO minute quotes with parallel per-symbol workers."
    )
    parser.add_argument("--start", required=True, help="Range start, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Range end, YYYY-MM-DD")
    parser.add_argument("--legacy-root", default=r"E:\Option_Sell_Research")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--symbols", help="Comma-separated symbols to download after four-term scheduling.")
    parser.add_argument("--symbols-file", help="Text/CSV file containing symbols to download.")
    parser.add_argument("--max-contracts", type=int, default=0, help="0 means all symbols in range.")
    parser.add_argument("--max-quote-age-ms", type=int, default=60_000)
    parser.add_argument("--workers", type=int, default=4, help="Parallel TqApi workers (default: 4).")
    parser.add_argument("--retry-attempts", type=int, default=2, help="Attempts per symbol-day before marking failure.")
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument("--first-valid-date-cache", help="JSON map symbol -> first valid quote date.")
    parser.add_argument("--report-prefix", help="Quality report prefix, default MO_YYYYMMDD_YYYYMMDD")
    parser.add_argument("--output-dir", help="Quality report directory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--refresh-contracts",
        action="store_true",
        help="Ignore cached contract list and re-query TQ.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing minute quote parquets for this product before downloading.",
    )
    parser.add_argument(
        "--skip-complete",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip days that already pass ok_ratio threshold (default: true).",
    )
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


def contract_cache_path(data_root: Path, product: str) -> Path:
    return data_root / "contracts" / product.upper() / "tq_contracts_cache.json"


def load_symbol_filter(symbols: str | None, symbols_file: str | None) -> set[str]:
    result: set[str] = set()
    if symbols:
        result.update(symbol.strip() for symbol in symbols.split(",") if symbol.strip())
    if symbols_file:
        path = Path(symbols_file)
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            value = line.split(",", 1)[0].strip()
            if value and value.lower() != "symbol":
                result.add(value)
    return result


def load_or_query_contracts(
    api: object,
    product: str,
    data_root: Path,
    refresh: bool,
) -> list[OptionContract]:
    cache_file = contract_cache_path(data_root, product)
    if cache_file.exists() and not refresh:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        return [
            OptionContract(
                symbol=item["symbol"],
                name=item.get("name", ""),
                underlying_symbol=item.get("underlying_symbol", ""),
                underlying_product=item.get("underlying_product", product),
                exchange=item.get("exchange", "CFFEX"),
                strike_price=float(item["strike_price"]),
                option_type=item["option_type"],
                expiry_date=item["expiry_date"],
                volume_multiple=int(item.get("volume_multiple", 1)),
                price_tick=float(item.get("price_tick", 0.2)),
                expired=bool(item.get("expired", False)),
            )
            for item in payload
        ]

    contracts = query_option_contracts_fast(api, product)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for contract in contracts:
        serializable.append(
            {
                "symbol": contract.symbol,
                "name": getattr(contract, "name", ""),
                "underlying_symbol": getattr(contract, "underlying_symbol", ""),
                "underlying_product": getattr(contract, "underlying_product", product),
                "exchange": getattr(contract, "exchange", "CFFEX"),
                "strike_price": contract.strike_price,
                "option_type": contract.option_type,
                "expiry_date": contract.expiry_date,
                "volume_multiple": getattr(contract, "volume_multiple", 1),
                "price_tick": getattr(contract, "price_tick", 0.2),
                "expired": getattr(contract, "expired", False),
            }
        )
    cache_file.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
    return contracts


def build_symbol_schedule(
    contracts: list[object],
    dates: list[str],
    max_contracts: int,
    first_valid_dates: dict[str, str] | None = None,
    symbol_filter: set[str] | None = None,
) -> dict[str, list[str]]:
    symbol_dates: dict[str, list[str]] = {}
    first_valid_dates = first_valid_dates or {}
    for trade_date in dates:
        selected = select_four_term_contracts(
            [c for c in contracts if c.expiry_date >= trade_date],
            as_of=trade_date,
        )
        for symbol in unique_symbols(selected):
            symbol_dates.setdefault(symbol, []).append(trade_date)

    symbols = sorted(symbol_dates)
    if symbol_filter:
        symbols = [symbol for symbol in symbols if symbol in symbol_filter]
    if max_contracts > 0:
        symbols = symbols[:max_contracts]
    result = {}
    for symbol in symbols:
        filtered_dates = filter_dates_by_first_valid(symbol, sorted(symbol_dates[symbol]), first_valid_dates)
        if filtered_dates:
            result[symbol] = filtered_dates
    return result


def _load_range_quotes(data_root: Path, product: str, dates: list[str]) -> pd.DataFrame:
    root = data_root / "quotes" / "minute" / product.upper()
    if not root.exists():
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    date_set = set(dates)
    for parquet_path in sorted(root.glob("*/*.parquet")):
        if parquet_path.stem not in date_set:
            continue
        frames.append(pd.read_parquet(parquet_path))
    if not frames:
        return pd.DataFrame()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, message=".*DataFrame concatenation.*")
        return pd.concat(frames, ignore_index=True)


def _symbol_daily_job(payload: dict) -> dict:
    symbol = payload["symbol"]
    trade_dates = payload["trade_dates"]
    pending_dates: list[str] = []
    saved = 0
    skipped = 0
    failures: list[str] = []
    for trade_date in trade_dates:
        output = minute_quote_path(
            payload["data_root"],
            payload["product"],
            symbol,
            trade_date,
        )
        if payload["skip_complete"] and should_skip_minute_quote_update(output):
            skipped += 1
            continue
        pending_dates.append(trade_date)

    if not pending_dates:
        return {
            "symbol": symbol,
            "saved": saved,
            "skipped": skipped,
            "failures": failures,
            "error": None,
        }

    try:
        with tq_api() as api:
            remaining_dates = pending_dates
            for attempt in range(1, payload["retry_attempts"] + 1):
                if not remaining_dates:
                    break
                attempt_saved, _attempt_skipped, attempt_failures = update_symbol_range_minute_quotes(
                    api=api,
                    data_root=payload["data_root"],
                    product=payload["product"],
                    symbol=symbol,
                    trade_dates=remaining_dates,
                    max_quote_age_ms=payload["max_quote_age_ms"],
                    skip_if_complete=False,
                )
                saved += attempt_saved
                if not attempt_failures:
                    remaining_dates = []
                    break
                if attempt < payload["retry_attempts"]:
                    failed_dates = []
                    for failure in attempt_failures:
                        trade_date, _, _message = failure.partition(": ")
                        if trade_date:
                            failed_dates.append(trade_date)
                    remaining_dates = failed_dates
                    sleep(payload["retry_sleep_seconds"])
                else:
                    failures.extend(attempt_failures)

        return {
            "symbol": symbol,
            "saved": saved,
            "skipped": skipped,
            "failures": failures,
            "error": None,
        }
    except Exception as exc:
        return {
            "symbol": symbol,
            "saved": 0,
            "skipped": skipped,
            "failures": failures,
            "error": str(exc),
        }


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    dates = trading_days(args.start, args.end)
    report_dir = (
        Path(args.output_dir)
        if args.output_dir
        else paths.data_root / "quality" / args.product.upper() / "month_probe"
    )
    prefix = args.report_prefix or (
        f"{args.product.upper()}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
    )

    with tq_api() as api:
        contracts = load_or_query_contracts(
            api,
            args.product,
            paths.data_root,
            args.refresh_contracts,
        )
    first_valid_cache = load_first_valid_date_cache(args.first_valid_date_cache)
    symbol_filter = load_symbol_filter(args.symbols, args.symbols_file)
    schedule = build_symbol_schedule(contracts, dates, args.max_contracts, first_valid_cache, symbol_filter)
    symbol_days = sum(len(v) for v in schedule.values())

    print(
        f"trading_days={len(dates)} symbols={len(schedule)} symbol_days={symbol_days} "
        f"workers={args.workers} skip_complete={args.skip_complete}",
        flush=True,
    )

    minute_root = paths.data_root / "quotes" / "minute" / args.product.upper()
    if args.clean and minute_root.exists() and not args.dry_run:
        removed = sum(1 for _ in minute_root.glob("*/*.parquet"))
        for parquet_path in minute_root.glob("*/*.parquet"):
            parquet_path.unlink()
        print(f"cleaned_parquets={removed}", flush=True)

    if args.dry_run:
        for symbol, trade_dates in list(schedule.items())[:5]:
            print(f"[dry-run] {symbol} days={len(trade_dates)}")
        return

    jobs = [
        {
            "symbol": symbol,
            "trade_dates": trade_dates,
            "data_root": str(paths.data_root),
            "product": args.product.upper(),
            "max_quote_age_ms": args.max_quote_age_ms,
            "skip_complete": args.skip_complete,
            "retry_attempts": max(args.retry_attempts, 1),
            "retry_sleep_seconds": max(args.retry_sleep_seconds, 0.0),
        }
        for symbol, trade_dates in schedule.items()
    ]

    saved_total = 0
    skipped_total = 0
    failed_symbols = 0
    results = []
    total = len(jobs)

    if args.workers <= 1:
        for idx, job in enumerate(jobs, 1):
            print(f"[{idx}/{total}] {job['symbol']} days={len(job['trade_dates'])}", flush=True)
            result = _symbol_daily_job(job)
            results.append(result)
            saved_total += result["saved"]
            skipped_total += result["skipped"]
            if result["error"] or result["failures"]:
                failed_symbols += 1
                print(f"  fail {result['error'] or result['failures'][:2]}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_symbol_daily_job, job): job["symbol"] for job in jobs}
            done = 0
            for future in as_completed(futures):
                done += 1
                result = future.result()
                results.append(result)
                saved_total += result["saved"]
                skipped_total += result["skipped"]
                if result["error"] or result["failures"]:
                    failed_symbols += 1
                    print(
                        f"[{done}/{total}] fail {result['symbol']}: "
                        f"{result['error'] or result['failures'][:2]}",
                        flush=True,
                    )
                else:
                    print(
                        f"[{done}/{total}] {result['symbol']} "
                        f"saved={result['saved']} skipped={result['skipped']}",
                        flush=True,
                    )

    print(
        f"done saved_days={saved_total} skipped_days={skipped_total} failed_symbols={failed_symbols}",
        flush=True,
    )

    failure_rows = []
    for result in results:
        if result.get("error"):
            failure_rows.append(
                {
                    "symbol": result["symbol"],
                    "trade_date": "",
                    "error": result["error"],
                    "failure": "",
                }
            )
        for failure in result.get("failures", []):
            trade_date, _, message = failure.partition(": ")
            failure_rows.append(
                {
                    "symbol": result["symbol"],
                    "trade_date": trade_date,
                    "error": "",
                    "failure": message,
                }
            )
    if failure_rows:
        report_dir.mkdir(parents=True, exist_ok=True)
        failure_path = report_dir / f"{prefix}_failures.csv"
        pd.DataFrame(failure_rows).to_csv(failure_path, index=False, encoding="utf-8-sig")
        print(f"failures={len(failure_rows)} failure_plan={failure_path}", flush=True)

    all_quotes = _load_range_quotes(paths.data_root, args.product, dates)
    summary_path, by_symbol_path = write_quality_report(all_quotes, report_dir, prefix)
    print(f"rows={len(all_quotes)} summary={summary_path} by_symbol={by_symbol_path}", flush=True)


if __name__ == "__main__":
    main()
