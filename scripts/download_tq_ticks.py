from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.sources.tq import tq_api
from option_platform.data.sources.tq_ticks import (
    download_tick_frame,
    save_minute_quotes,
    ticks_to_minute_quotes,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download TQ tick data and save minute quote bars.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    safe_symbol = args.symbol.replace(".", "_")
    output = (
        Path(args.output)
        if args.output
        else paths.data_root / "quotes" / "minute" / f"{safe_symbol}_{args.start}_{args.end}.parquet"
    )

    with tq_api() as api:
        ticks = download_tick_frame(api, args.symbol, start_dt, end_dt)
    quotes = ticks_to_minute_quotes(ticks)
    saved = save_minute_quotes(quotes, output)
    print(f"ticks={len(ticks)} minute_quotes={len(quotes)} output={saved}")


if __name__ == "__main__":
    main()

