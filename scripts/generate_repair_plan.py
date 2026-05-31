from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.quality.repair import (
    RepairThresholds,
    active_trading_dates,
    build_repair_plan,
    infer_expected_symbols,
    load_quote_files,
    summarize_by_date,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate active-date quality summary and repair list.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--product", default="MO")
    parser.add_argument("--output-dir")
    parser.add_argument("--prefix", help="Output file prefix, default PRODUCT_YYYYMMDD_YYYYMMDD")
    parser.add_argument("--min-symbol-usable-ratio", type=float, default=0.50)
    parser.add_argument("--max-symbol-missing-ratio", type=float, default=0.40)
    parser.add_argument("--max-symbol-stale-ratio", type=float, default=0.20)
    return parser.parse_args()


def weekday_dates(start: str, end: str) -> list[str]:
    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    dates = []
    current = start_dt
    while current <= end_dt:
        if current.weekday() < 5:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    dates = weekday_dates(args.start, args.end)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else paths.data_root / "quality" / args.product.upper() / "repair"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or f"{args.product.upper()}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"

    quote_files = load_quote_files(paths.data_root, args.product, dates)
    date_summary = summarize_by_date(quote_files)
    active_dates = active_trading_dates(date_summary)
    expected_symbols = infer_expected_symbols(quote_files, active_dates)
    repair_plan = build_repair_plan(
        quote_files,
        active_dates,
        expected_symbols,
        RepairThresholds(
            min_symbol_usable_ratio=args.min_symbol_usable_ratio,
            max_symbol_missing_ratio=args.max_symbol_missing_ratio,
            max_symbol_stale_ratio=args.max_symbol_stale_ratio,
        ),
    )

    date_path = output_dir / f"{prefix}_date_summary.csv"
    repair_path = output_dir / f"{prefix}_repair_plan.csv"
    date_summary.to_csv(date_path, index=False, encoding="utf-8-sig")
    repair_plan.to_csv(repair_path, index=False, encoding="utf-8-sig")
    print(
        f"dates={len(dates)} active_dates={len(active_dates)} "
        f"expected_symbols={len(expected_symbols)} repairs={len(repair_plan)}"
    )
    print(f"date_summary={date_path}")
    print(f"repair_plan={repair_path}")


if __name__ == "__main__":
    main()
