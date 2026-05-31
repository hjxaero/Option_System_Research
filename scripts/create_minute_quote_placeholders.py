from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.live_update import minute_quote_path, save_minute_quote_frame
from option_platform.data.sources.tq_minute_quotes import build_unavailable_minute_quotes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create canonical no-price minute quote files for unavailable historical quote days."
    )
    parser.add_argument("--start", required=True, help="Range start, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Range end, YYYY-MM-DD")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing parquet files.")
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


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
    dates = trading_days(args.start, args.end)

    written = 0
    skipped = 0
    for symbol in symbols:
        for trade_date in dates:
            output = minute_quote_path(paths.data_root, args.product, symbol, trade_date)
            if output.exists() and not args.force:
                skipped += 1
                continue
            frame = build_unavailable_minute_quotes(symbol, trade_date)
            save_minute_quote_frame(frame, paths.data_root, args.product, symbol, trade_date)
            written += 1
    print(f"placeholders_written={written} skipped_existing={skipped}", flush=True)


if __name__ == "__main__":
    main()
