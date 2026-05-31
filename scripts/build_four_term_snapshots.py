from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.snapshots.four_term import (
    build_four_term_snapshot,
    expected_four_term_symbols,
    expected_snapshot_minutes,
    four_term_snapshot_path,
    missing_minute_quote_files,
    save_four_term_snapshot,
    should_skip_four_term_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build resumable four-term option-chain snapshots.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--product", default="MO")
    parser.add_argument("--contract-cache", help="Contract cache JSON. Defaults to data_store/contracts/PRODUCT/tq_contracts_cache.json")
    parser.add_argument("--max-contracts", type=int, default=0, help="Debug limit. 0 means all selected contracts.")
    parser.add_argument("--min-quote-rows", type=int, default=200)
    parser.add_argument("--max-quote-age-ms", type=int, default=60_000)
    parser.add_argument("--max-normal-spread-bps", type=float, default=500.0)
    parser.add_argument("--skip-complete", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
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


def load_contract_cache(path: Path) -> list[SimpleNamespace]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SimpleNamespace(**item) for item in payload]


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    product = args.product.upper()
    contract_cache = (
        Path(args.contract_cache)
        if args.contract_cache
        else paths.data_root / "contracts" / product / "tq_contracts_cache.json"
    )
    if not contract_cache.exists():
        raise FileNotFoundError(f"contract cache not found: {contract_cache}")

    contracts = load_contract_cache(contract_cache)
    dates = weekday_dates(args.start, args.end)
    built = 0
    skipped = 0
    incomplete = 0

    for trade_date in dates:
        symbols = expected_four_term_symbols(contracts, trade_date)
        if args.max_contracts > 0:
            symbols = symbols[: args.max_contracts]
            contracts_for_date = [contract for contract in contracts if contract.symbol in set(symbols)]
        else:
            contracts_for_date = contracts

        output = four_term_snapshot_path(paths.data_root, product, trade_date)
        missing = missing_minute_quote_files(
            paths.data_root,
            product,
            symbols,
            trade_date,
            min_rows=args.min_quote_rows,
        )
        if missing:
            incomplete += 1
            print(
                f"[{trade_date}] incomplete minute quotes "
                f"missing_or_short={len(missing)}/{len(symbols)} first={missing[:5]}",
                flush=True,
            )
            continue

        if (
            args.skip_complete
            and not args.force
            and should_skip_four_term_snapshot(
                output,
                symbols,
                trade_date,
                min_minutes=args.min_quote_rows,
            )
        ):
            skipped += 1
            print(f"[{trade_date}] skip complete snapshot {output}", flush=True)
            continue

        if args.dry_run:
            print(
                f"[dry-run] {trade_date} symbols={len(symbols)} "
                f"expected_minutes={expected_snapshot_minutes(trade_date)} output={output}",
                flush=True,
            )
            continue

        snapshot = build_four_term_snapshot(
            paths.data_root,
            product,
            contracts_for_date,
            trade_date,
            max_quote_age_ms=args.max_quote_age_ms,
            max_normal_spread_bps=args.max_normal_spread_bps,
        )
        save_four_term_snapshot(snapshot, output)
        built += 1
        print(f"[{trade_date}] built rows={len(snapshot)} symbols={snapshot['symbol'].nunique()} output={output}", flush=True)

    print(f"done dates={len(dates)} built={built} skipped={skipped} incomplete={incomplete}", flush=True)


if __name__ == "__main__":
    main()
