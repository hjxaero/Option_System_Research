from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.quality.minute_quote_report import write_quality_report
from option_platform.data.sources.tq import tq_api
from option_platform.data.sources.tq_contracts import query_option_contracts_fast
from option_platform.data.sources.tq_minute_quotes import build_daily_minute_quotes
from option_platform.data.storage.upsert import upsert_parquet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download one MO expiry cycle sample and report minute quote quality.")
    parser.add_argument("--legacy-root", default=r"E:\Option_Sell_Research")
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--expiry", help="Use the cycle with this expiry date.")
    parser.add_argument("--start", help="Override cycle start date.")
    parser.add_argument("--end", help="Override cycle end date.")
    parser.add_argument("--max-contracts", type=int, default=20, help="0 means all contracts in the cycle.")
    parser.add_argument("--max-days", type=int, default=0, help="0 means all trading days in the selected date range.")
    parser.add_argument("--max-quote-age-ms", type=int, default=60_000)
    parser.add_argument("--output-dir")
    return parser.parse_args()


def _load_period(args: argparse.Namespace, api: object):
    legacy_root = Path(args.legacy_root).resolve()
    if str(legacy_root) not in sys.path:
        sys.path.insert(0, str(legacy_root))

    from data.data_loader import TQDataLoader

    contracts = query_option_contracts_fast(api, "MO", legacy_root=legacy_root)
    contracts = [c for c in contracts if c.expiry_date >= args.as_of]
    loader = TQDataLoader(api)
    periods = loader.classify_trading_periods_by_expiry(contracts, start_date=args.as_of)
    if not periods:
        raise RuntimeError("No MO trading periods found.")

    if args.expiry:
        for period in periods:
            if period.expiry_date == args.expiry:
                return period
        raise RuntimeError(f"Expiry not found: {args.expiry}")
    return periods[0]


def _date_range(start: str, end: str, max_days: int) -> list[str]:
    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    dates = []
    current = start_dt
    while current <= end_dt:
        if current.weekday() < 5:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates[:max_days] if max_days > 0 else dates


def _select_contracts(period, max_contracts: int):
    contracts = list(period.tradable_contracts)
    contracts.sort(key=lambda c: (c.expiry_date, c.option_type, c.strike_price, c.symbol))
    if max_contracts <= 0 or len(contracts) <= max_contracts:
        return contracts

    strikes = sorted({c.strike_price for c in contracts})
    center = strikes[len(strikes) // 2] if strikes else 0
    contracts.sort(key=lambda c: (abs(c.strike_price - center), c.option_type, c.symbol))
    return sorted(contracts[:max_contracts], key=lambda c: (c.option_type, c.strike_price, c.symbol))


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    output_dir = Path(args.output_dir) if args.output_dir else paths.data_root / "quality" / "MO" / "cycle_probe"
    frames = []

    with tq_api() as api:
        period = _load_period(args, api)
        start = args.start or period.start_date
        end = args.end or period.expiry_date
        dates = _date_range(start, end, args.max_days)
        contracts = _select_contracts(period, args.max_contracts)

        print(
            f"cycle={period.start_date}~{period.expiry_date} "
            f"download_range={start}~{end} dates={len(dates)} contracts={len(contracts)}"
        )

        for trade_date in dates:
            for idx, contract in enumerate(contracts, 1):
                print(f"[{trade_date}] {idx}/{len(contracts)} {contract.symbol}")
                frame = build_daily_minute_quotes(
                    api,
                    symbol=contract.symbol,
                    trade_date=trade_date,
                    max_quote_age_ms=args.max_quote_age_ms,
                )
                safe_symbol = contract.symbol.replace(".", "_")
                parquet_path = (
                    paths.data_root
                    / "quotes"
                    / "minute"
                    / "MO"
                    / safe_symbol
                    / f"{trade_date}.parquet"
                )
                upsert_parquet(parquet_path, frame)
                frames.append(frame)

    all_quotes = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    prefix = f"MO_{period.start_date.replace('-', '')}_{period.expiry_date.replace('-', '')}"
    summary_path, by_symbol_path = write_quality_report(all_quotes, output_dir, prefix)
    print(f"rows={len(all_quotes)} summary={summary_path} by_symbol={by_symbol_path}")


if __name__ == "__main__":
    main()
