from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from option_platform.data.quality.quote_quality import add_quote_quality_columns


TICK_COLUMNS = [
    "datetime",
    "last_price",
    "bid_price1",
    "ask_price1",
    "bid_volume1",
    "ask_volume1",
    "volume",
    "amount",
    "open_interest",
]


def normalize_tq_datetime(frame: pd.DataFrame, column: str = "datetime") -> pd.DataFrame:
    result = frame.copy()
    values = result[column]
    if pd.api.types.is_integer_dtype(values):
        parsed = pd.to_datetime(values, unit="ns", utc=True)
    else:
        parsed = pd.to_datetime(values, utc=True)
    result[column] = (
        parsed.dt.tz_convert("Asia/Shanghai").dt.tz_localize(None).astype("datetime64[ns]")
    )
    return result


def download_tick_frame(api: object, symbol: str, start_dt: date | datetime, end_dt: date | datetime) -> pd.DataFrame:
    frame = api.get_tick_data_series(symbol=symbol, start_dt=start_dt, end_dt=end_dt)
    if frame is None or len(frame) == 0:
        return pd.DataFrame(columns=TICK_COLUMNS)
    frame = normalize_tq_datetime(frame)
    keep = [col for col in TICK_COLUMNS if col in frame.columns]
    return frame[keep].copy()


def ticks_to_minute_quotes(ticks: pd.DataFrame) -> pd.DataFrame:
    if ticks.empty:
        return pd.DataFrame()

    frame = ticks.copy().sort_values("datetime")
    frame["timestamp"] = frame["datetime"].dt.floor("min")
    last_per_minute = frame.groupby("timestamp", as_index=False).tail(1)

    rename = {
        "datetime": "quote_time",
        "last_price": "last_price",
        "bid_price1": "bid_price1",
        "ask_price1": "ask_price1",
        "bid_volume1": "bid_volume1",
        "ask_volume1": "ask_volume1",
        "volume": "cum_volume",
        "amount": "cum_amount",
        "open_interest": "open_interest",
    }
    result = last_per_minute[["timestamp", *[c for c in rename if c in last_per_minute.columns]]].rename(columns=rename)
    return add_quote_quality_columns(result.reset_index(drop=True))


def save_minute_quotes(frame: pd.DataFrame, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path
