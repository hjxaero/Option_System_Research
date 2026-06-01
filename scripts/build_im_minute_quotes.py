#!/usr/bin/env python3
"""Download IM index-futures minute order-book quotes paired to MO four-term months."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.contracts import OptionContract
from option_platform.data.futures.im_contracts import load_or_query_im_contracts
from option_platform.data.futures.im_minute_store import update_im_trade_date
from option_platform.data.futures.resolve import resolve_im_contracts_for_trade_date
from option_platform.data.quality.minute_quote_report import write_quality_report
from option_platform.data.sources.tq import tq_api
from option_platform.data.sources.tq_contracts import query_option_contracts_fast


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download IM minute quotes by trade date (paired to MO YYMM months)."
    )
    parser.add_argument("--start", required=True, help="Range start YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Range end YYYY-MM-DD")
    parser.add_argument("--mo-product", default="MO", help="Option product for four-term pairing")
    parser.add_argument("--max-quote-age-ms", type=int, default=60_000)
    parser.add_argument(
        "--skip-complete",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip trade dates that already pass quality thresholds (default: true).",
    )
    parser.add_argument("--refresh-contracts", action="store_true", help="Re-query MO and IM from TQ.")
    parser.add_argument("--retry-attempts", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-prefix", help="Quality report prefix, default IM_YYYYMMDD_YYYYMMDD")
    parser.add_argument("--output-dir", help="Quality report directory")
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


def mo_contract_cache_path(data_root: Path, product: str) -> Path:
    return data_root / "contracts" / product.upper() / "tq_contracts_cache.json"


def load_or_query_mo_contracts(
    api: object,
    data_root: Path,
    product: str,
    refresh: bool,
) -> list[OptionContract]:
    cache_file = mo_contract_cache_path(data_root, product)
    if cache_file.exists() and not refresh:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        return [
            OptionContract(
                symbol=item["symbol"],
                name=item.get("name", ""),
                underlying_symbol=item.get("underlying_symbol", ""),
                underlying_product=item.get("underlying_product", product),
                exchange=item.get("exchange", ""),
                strike_price=float(item.get("strike_price", 0.0)),
                option_type=item.get("option_type", "call"),
                expiry_date=item.get("expiry_date", ""),
                volume_multiple=int(item.get("volume_multiple", 1)),
                price_tick=float(item.get("price_tick", 0.01)),
                expired=bool(item.get("expired", False)),
            )
            for item in payload
        ]
    contracts = query_option_contracts_fast(api, product)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            [
                {
                    "symbol": c.symbol,
                    "name": c.name,
                    "underlying_symbol": c.underlying_symbol,
                    "underlying_product": c.underlying_product,
                    "exchange": c.exchange,
                    "strike_price": c.strike_price,
                    "option_type": c.option_type,
                    "expiry_date": c.expiry_date,
                    "volume_multiple": c.volume_multiple,
                    "price_tick": c.price_tick,
                    "expired": c.expired,
                }
                for c in contracts
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return contracts


def load_im_day_frames(data_root: Path, dates: list[str]) -> list:
    import pandas as pd

    from option_platform.data.futures.layout import im_minute_day_path

    frames = []
    for trade_date in dates:
        path = im_minute_day_path(data_root, trade_date)
        if path.exists():
            frames.append(pd.read_parquet(path))
    return frames


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    dates = trading_days(args.start, args.end)
    report_dir = (
        Path(args.output_dir)
        if args.output_dir
        else paths.data_root / "quality" / "IM"
    )
    prefix = args.report_prefix or f"IM_{args.start.replace('-', '')}_{args.end.replace('-', '')}"

    with tq_api() as api:
        mo_contracts = load_or_query_mo_contracts(
            api,
            paths.data_root,
            args.mo_product,
            args.refresh_contracts,
        )
        im_contracts = load_or_query_im_contracts(
            api,
            paths.data_root,
            args.refresh_contracts,
        )

    print(
        f"trading_days={len(dates)} mo_contracts={len(mo_contracts)} "
        f"im_contracts={len(im_contracts)} skip_complete={args.skip_complete}",
        flush=True,
    )

    if args.dry_run:
        sample = dates[0] if dates else args.start
        resolved = resolve_im_contracts_for_trade_date(mo_contracts, im_contracts, sample)
        print(f"dry_run sample_date={sample} im_symbols={[c.symbol for c in resolved]}")
        return

    saved_days = 0
    skipped_days = 0
    failures: list[str] = []

    with tq_api() as api:
        for trade_date in dates:
            day_contracts = resolve_im_contracts_for_trade_date(mo_contracts, im_contracts, trade_date)
            if not day_contracts:
                failures.append(f"{trade_date}: no_im_contracts_resolved")
                continue

            success = False
            last_error: str | None = None
            for attempt in range(1, args.retry_attempts + 1):
                saved, error = update_im_trade_date(
                    api,
                    paths.data_root,
                    trade_date,
                    day_contracts,
                    max_quote_age_ms=args.max_quote_age_ms,
                    skip_if_complete=args.skip_complete,
                )
                if error is None and not saved and args.skip_complete:
                    skipped_days += 1
                    success = True
                    break
                if error is None and saved:
                    saved_days += 1
                    success = True
                    print(
                        f"[OK] {trade_date} symbols={[c.symbol for c in day_contracts]}",
                        flush=True,
                    )
                    break
                last_error = error
                if attempt < args.retry_attempts:
                    sleep(args.retry_sleep_seconds)

            if not success and last_error:
                failures.append(f"{trade_date}: {last_error}")
                print(f"[FAIL] {trade_date}: {last_error}", flush=True)

    import pandas as pd

    frames = load_im_day_frames(paths.data_root, dates)
    if frames:
        summary_path, by_symbol_path = write_quality_report(
            pd.concat(frames, ignore_index=True),
            report_dir,
            prefix,
        )
        print(f"quality_summary={summary_path} by_symbol={by_symbol_path}", flush=True)

    manifest = {
        "start": args.start,
        "end": args.end,
        "saved_days": saved_days,
        "skipped_days": skipped_days,
        "failed_days": len(failures),
        "failures": failures,
    }
    manifest_path = report_dir / f"{prefix}_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest={manifest_path}", flush=True)


if __name__ == "__main__":
    main()
