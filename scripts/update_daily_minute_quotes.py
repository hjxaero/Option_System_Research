from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.live_update import update_daily_minute_quotes
from option_platform.data.sources.tq import tq_api


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Incrementally update daily minute quote parquet.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--product", default="MO")
    parser.add_argument("--max-quote-age-ms", type=int, default=60_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    with tq_api() as api:
        result = update_daily_minute_quotes(
            api,
            data_root=paths.data_root,
            product=args.product,
            symbol=args.symbol,
            trade_date=args.date,
            max_quote_age_ms=args.max_quote_age_ms,
        )

    print(
        " ".join(
            [
                f"rows={result.rows_written}",
                f"output={result.output_path}",
                f"state={result.state_path}",
                f"max_target_time={result.max_target_time}",
                f"max_quote_time={result.max_quote_time}",
                f"quality={result.quality_counts}",
            ]
        )
    )


if __name__ == "__main__":
    main()

