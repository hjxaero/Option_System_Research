from __future__ import annotations

from pathlib import Path

IM_PRODUCT = "IM"


def futures_im_root(data_root: str | Path) -> Path:
    return Path(data_root) / "futures" / IM_PRODUCT


def im_minute_day_path(data_root: str | Path, trade_date: str) -> Path:
    return futures_im_root(data_root) / "minute" / f"{trade_date}.parquet"


def im_calendar_path(data_root: str | Path) -> Path:
    return futures_im_root(data_root) / "meta" / "contract_calendar.parquet"


def im_contracts_cache_path(data_root: str | Path) -> Path:
    return Path(data_root) / "contracts" / IM_PRODUCT / "tq_futures_cache.json"
