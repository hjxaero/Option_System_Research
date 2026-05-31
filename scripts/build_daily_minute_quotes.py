from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.sources.tq import tq_api
from option_platform.data.sources.tq_minute_quotes import (
    build_daily_minute_quotes,
    save_daily_minute_quotes,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one trading day's minute bid/ask quote database from TQ ticks."
    )
    parser.add_argument("--symbol", required=True, help="TQ symbol, e.g. CFFEX.MO2606-C-6000")
    parser.add_argument("--date", required=True, help="Trading date, YYYY-MM-DD")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--max-quote-age-ms", type=int, default=60_000)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    safe_symbol = args.symbol.replace(".", "_")
    output = (
        Path(args.output)
        if args.output
        else paths.data_root
        / "quotes"
        / "minute"
        / args.product.upper()
        / safe_symbol
        / f"{args.date}.parquet"
    )

    with tq_api() as api:
        quotes = build_daily_minute_quotes(
            api,
            symbol=args.symbol,
            trade_date=args.date,
            max_quote_age_ms=args.max_quote_age_ms,
        )

    saved = save_daily_minute_quotes(quotes, output)
    quality_counts = quotes["quote_quality"].value_counts(dropna=False).to_dict()
    print(f"rows={len(quotes)} output={saved} quality={quality_counts}")


if __name__ == "__main__":
    main()

