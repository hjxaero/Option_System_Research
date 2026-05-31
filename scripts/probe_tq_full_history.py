from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.data.sources.tq import tq_api
from option_platform.data.sources.tq_contracts import filter_option_symbols, query_option_contracts_fast
from option_platform.data.sources.tq_ticks import download_tick_frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe whether TqSdk can discover and download full-history option data.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--legacy-root", default=r"E:\Option_Sell_Research")
    parser.add_argument("--sample-ticks", action="store_true")
    return parser.parse_args()


def _summarize_contracts(label: str, contracts: list[object]) -> None:
    if not contracts:
        print(f"{label}: count=0", flush=True)
        return
    expiries = sorted({getattr(contract, "expiry_date", "") for contract in contracts if getattr(contract, "expiry_date", "")})
    symbols = sorted({getattr(contract, "symbol", "") for contract in contracts})
    print(
        f"{label}: count={len(contracts)} symbols={len(symbols)} "
        f"expiry_min={expiries[0] if expiries else ''} expiry_max={expiries[-1] if expiries else ''}",
        flush=True,
    )
    print(f"{label}: first_symbols={symbols[:5]}", flush=True)


def _try_query_quotes(api: object, product: str, expired: bool | None) -> list[str]:
    kwargs = {"ins_class": "OPTION"}
    if expired is not None:
        kwargs["expired"] = expired
    symbols = api.query_quotes(**kwargs)
    return filter_option_symbols(symbols, product)


def _sample_tick_download(api: object, contracts: list[object]) -> None:
    if not contracts:
        print("sample_ticks: skipped no contracts", flush=True)
        return

    ordered = sorted(
        [contract for contract in contracts if getattr(contract, "expiry_date", "")],
        key=lambda item: (getattr(item, "expiry_date", ""), getattr(item, "symbol", "")),
    )
    contract = ordered[0]
    expiry = datetime.strptime(contract.expiry_date, "%Y-%m-%d").date()
    trade_date = expiry - timedelta(days=3)
    while trade_date.weekday() >= 5:
        trade_date -= timedelta(days=1)
    start_dt = datetime.strptime(f"{trade_date} 09:30:00", "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(f"{trade_date} 15:00:00", "%Y-%m-%d %H:%M:%S")
    print(f"sample_ticks: symbol={contract.symbol} start={start_dt} end={end_dt}", flush=True)
    ticks = download_tick_frame(api, contract.symbol, start_dt, end_dt)
    print(
        f"sample_ticks: rows={len(ticks)} columns={list(ticks.columns)} "
        f"first_time={ticks['datetime'].min() if len(ticks) and 'datetime' in ticks else None} "
        f"last_time={ticks['datetime'].max() if len(ticks) and 'datetime' in ticks else None}",
        flush=True,
    )


def main() -> None:
    args = parse_args()
    product = args.product.upper()
    with tq_api() as api:
        for expired in (False, True, None):
            try:
                symbols = _try_query_quotes(api, product, expired)
                print(f"query_quotes expired={expired}: filtered_symbols={len(symbols)} first={symbols[:5]}", flush=True)
            except Exception as exc:
                print(f"query_quotes expired={expired}: ERROR {exc}", flush=True)

        contracts = query_option_contracts_fast(
            api,
            product,
            legacy_root=Path(args.legacy_root),
            verbose=False,
        )
        _summarize_contracts("query_option_contracts_fast_default", contracts)

        if args.sample_ticks:
            _sample_tick_download(api, contracts)


if __name__ == "__main__":
    main()
