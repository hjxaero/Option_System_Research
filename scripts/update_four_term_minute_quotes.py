from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.live_update import recent_window, update_batch_minute_quotes
from option_platform.data.sources.tq import tq_api
from option_platform.data.sources.tq_contracts import query_option_contracts_fast
from option_platform.data.universe import select_four_term_contracts, unique_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update minute quotes for all contracts in current/next month and quarter terms."
    )
    parser.add_argument("--legacy-root", default=r"E:\Option_Sell_Research")
    parser.add_argument("--date", required=True, help="Trading date, YYYY-MM-DD")
    parser.add_argument("--as-of", help="Contract selection date, defaults to --date")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--window-minutes", type=int, default=30)
    parser.add_argument("--full-refresh", action="store_true")
    parser.add_argument("--end-time", help="Window end time, HH:MM or YYYY-MM-DD HH:MM")
    parser.add_argument("--max-quote-age-ms", type=int, default=60_000)
    parser.add_argument("--quote-lookback-minutes", type=int, default=30)
    parser.add_argument("--max-contracts", type=int, default=0, help="Debug limit. 0 means all selected contracts.")
    return parser.parse_args()


def _parse_end_time(value: str | None, trade_date: str) -> datetime | None:
    if not value:
        return None
    if len(value) <= 5:
        return datetime.strptime(f"{trade_date} {value}", "%Y-%m-%d %H:%M")
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def _load_mo_contracts(api: object, legacy_root: Path, as_of: str):
    contracts = query_option_contracts_fast(api, "MO", legacy_root=legacy_root)
    return [c for c in contracts if c.expiry_date >= as_of]


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    as_of = args.as_of or args.date
    end_time = _parse_end_time(args.end_time, args.date)
    window_minutes = None if args.full_refresh else args.window_minutes
    target_start, target_end = recent_window(args.date, end_time, window_minutes)

    with tq_api() as api:
        contracts = _load_mo_contracts(api, Path(args.legacy_root).resolve(), as_of)
        selected = select_four_term_contracts(contracts, as_of=as_of)
        symbols = unique_symbols(selected)
        if args.max_contracts > 0:
            symbols = symbols[: args.max_contracts]

        print(
            f"terms={sorted(set(item.expiry_date + ':' + item.term_role for item in selected))} "
            f"symbols={len(symbols)} window={target_start}~{target_end}"
        )
        result = update_batch_minute_quotes(
            api=api,
            data_root=paths.data_root,
            product=args.product,
            symbols=symbols,
            trade_date=args.date,
            max_quote_age_ms=args.max_quote_age_ms,
            target_start_time=target_start,
            target_end_time=target_end,
            quote_lookback_minutes=args.quote_lookback_minutes,
        )

    print(
        f"total={result.total_symbols} succeeded={result.succeeded} failed={result.failed} "
        f"errors={result.errors}"
    )


if __name__ == "__main__":
    main()
