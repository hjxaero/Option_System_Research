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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize minute quote quality from on-disk parquet files.")
    parser.add_argument("--start", required=True, help="Range start, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Range end, YYYY-MM-DD")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--prefix", help="Report file prefix")
    parser.add_argument("--output-dir")
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


def load_range_quotes(data_root: Path, product: str, dates: list[str]) -> pd.DataFrame:
    root = data_root / "quotes" / "minute" / product.upper()
    if not root.exists():
        return pd.DataFrame()

    date_set = set(dates)
    frames: list[pd.DataFrame] = []
    for parquet_path in sorted(root.glob("*/*.parquet")):
        if parquet_path.stem not in date_set:
            continue
        frame = pd.read_parquet(parquet_path)
        if "symbol" not in frame.columns:
            frame = frame.copy()
            parent_name = parquet_path.parent.name
            if "_" in parent_name:
                exchange, rest = parent_name.split("_", 1)
                frame["symbol"] = f"{exchange}.{rest}"
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    dates = trading_days(args.start, args.end)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else paths.data_root / "quality" / args.product.upper() / "month_probe"
    )
    prefix = args.prefix or f"{args.product.upper()}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
    frame = load_range_quotes(paths.data_root, args.product, dates)
    summary_path, by_symbol_path = write_quality_report(frame, output_dir, prefix)
    print(f"rows={len(frame)} summary={summary_path} by_symbol={by_symbol_path}")


if __name__ == "__main__":
    main()
