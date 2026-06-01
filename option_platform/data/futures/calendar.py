from __future__ import annotations

from pathlib import Path

import pandas as pd

from option_platform.data.futures.layout import im_calendar_path
from option_platform.data.futures.resolve import ImDayContract
CALENDAR_COLUMNS = ("trade_date", "contract_month", "symbol", "expiry_date", "note")


def calendar_rows_for_day(trade_date: str, contracts: list[ImDayContract]) -> pd.DataFrame:
    if not contracts:
        return pd.DataFrame(columns=list(CALENDAR_COLUMNS))
    rows = [
        {
            "trade_date": trade_date,
            "contract_month": item.contract_month,
            "symbol": item.symbol,
            "expiry_date": item.expiry_date,
            "note": f"pairs with MO{item.contract_month}-*",
        }
        for item in contracts
    ]
    return pd.DataFrame(rows)


def upsert_calendar_day(
    data_root: str | Path,
    trade_date: str,
    contracts: list[ImDayContract],
) -> pd.DataFrame:
    incoming = calendar_rows_for_day(trade_date, contracts)
    path = im_calendar_path(data_root)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        incoming.to_parquet(path, index=False)
        return incoming

    existing = pd.read_parquet(path)
    if "trade_date" in existing.columns:
        existing = existing[existing["trade_date"].astype(str) != trade_date]
    merged = pd.concat([existing, incoming], ignore_index=True)
    merged = merged.sort_values(["trade_date", "contract_month"]).reset_index(drop=True)
    tmp = path.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    tmp.replace(path)
    return merged
