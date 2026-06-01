from __future__ import annotations

from pathlib import Path

import pandas as pd

from option_platform.data.futures.calendar import upsert_calendar_day
from option_platform.data.futures.layout import im_minute_day_path
from option_platform.data.futures.resolve import ImDayContract
from option_platform.data.pricing import choose_mark_price
from option_platform.data.sources.tq_minute_quotes import build_daily_minute_quotes
from option_platform.data.storage.upsert import upsert_parquet


def annotate_im_minute_frame(
    frame: pd.DataFrame,
    *,
    contract_month: str,
    expiry_date: str,
) -> pd.DataFrame:
    result = frame.copy()
    result["contract_month"] = contract_month
    result["expiry_date"] = expiry_date
    sources: list[str] = []
    for row in result.itertuples(index=False):
        mark = choose_mark_price(
            bid_price1=getattr(row, "bid_price1", None),
            ask_price1=getattr(row, "ask_price1", None),
            bid_volume1=getattr(row, "bid_volume1", None),
            ask_volume1=getattr(row, "ask_volume1", None),
            last_price=getattr(row, "last_price", None),
        )
        sources.append(mark.source if mark.price is not None else "missing")
    result["price_source"] = sources
    return result


def should_skip_im_day(
    path: str | Path,
    *,
    expected_symbols: int,
    min_rows_per_symbol: int = 200,
    min_ok_ratio: float = 0.70,
) -> bool:
    parquet_path = Path(path)
    if not parquet_path.exists():
        return False
    try:
        frame = pd.read_parquet(parquet_path)
    except Exception:
        return False
    if frame.empty or "quote_quality" not in frame.columns:
        return False
    min_rows = min_rows_per_symbol * max(expected_symbols, 1)
    if len(frame) < min_rows:
        return False
    ok_ratio = float((frame["quote_quality"] == "ok").mean())
    if ok_ratio < min_ok_ratio:
        return False
    if "symbol" in frame.columns and frame["symbol"].nunique() < expected_symbols:
        return False
    return True


def build_im_minutes_for_day(
    api: object,
    trade_date: str,
    contracts: list[ImDayContract],
    *,
    max_quote_age_ms: int = 60_000,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for item in contracts:
        quotes = build_daily_minute_quotes(
            api,
            symbol=item.symbol,
            trade_date=trade_date,
            max_quote_age_ms=max_quote_age_ms,
        )
        frames.append(
            annotate_im_minute_frame(
                quotes,
                contract_month=item.contract_month,
                expiry_date=item.expiry_date,
            )
        )
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["contract_month", "target_time"])


def save_im_minute_day(
    data_root: str | Path,
    trade_date: str,
    frame: pd.DataFrame,
    contracts: list[ImDayContract],
) -> Path:
    output = im_minute_day_path(data_root, trade_date)
    upsert_parquet(output, frame)
    upsert_calendar_day(data_root, trade_date, contracts)
    return output


def update_im_trade_date(
    api: object,
    data_root: str | Path,
    trade_date: str,
    contracts: list[ImDayContract],
    *,
    max_quote_age_ms: int = 60_000,
    skip_if_complete: bool = False,
    min_ok_ratio: float = 0.70,
) -> tuple[bool, str | None]:
    """Return (saved, error_message). skipped when skip_if_complete and file looks good."""
    output = im_minute_day_path(data_root, trade_date)
    if skip_if_complete and should_skip_im_day(
        output,
        expected_symbols=len(contracts),
        min_ok_ratio=min_ok_ratio,
    ):
        return False, None
    if not contracts:
        return False, "no_im_contracts_resolved"
    try:
        frame = build_im_minutes_for_day(
            api,
            trade_date,
            contracts,
            max_quote_age_ms=max_quote_age_ms,
        )
        save_im_minute_day(data_root, trade_date, frame, contracts)
        return True, None
    except Exception as exc:
        return False, str(exc)
