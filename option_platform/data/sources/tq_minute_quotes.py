from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from option_platform.data.quality.quote_quality import add_quote_quality_columns
from option_platform.data.sources.tq_ticks import download_tick_frame
from option_platform.data.trading_minutes import generate_session_minutes, trade_day_bounds


def align_ticks_to_minutes(
    ticks: pd.DataFrame,
    target_minutes: pd.DataFrame,
    max_quote_age_ms: int = 60_000,
) -> pd.DataFrame:
    """Align historical ticks to target minute timestamps by last quote <= target_time."""
    if "target_time" not in target_minutes.columns:
        raise ValueError("target_minutes must contain target_time")

    targets = target_minutes[["target_time"]].copy().sort_values("target_time")
    if targets.empty:
        return targets

    required = ["datetime", "last_price", "bid_price1", "ask_price1", "bid_volume1", "ask_volume1"]
    if ticks.empty:
        for col in ["quote_time", *required[1:], "quote_age_ms"]:
            targets[col] = pd.NA
        targets["quote_quality"] = "missing"
        return targets

    missing = [col for col in required if col not in ticks.columns]
    if missing:
        raise ValueError(f"ticks missing columns: {missing}")

    quotes = ticks[required + [c for c in ["volume", "amount", "open_interest"] if c in ticks.columns]].copy()
    quotes = quotes.sort_values("datetime").rename(columns={"datetime": "quote_time"})

    aligned = pd.merge_asof(
        targets,
        quotes,
        left_on="target_time",
        right_on="quote_time",
        direction="backward",
        allow_exact_matches=True,
    )
    aligned["quote_age_ms"] = (
        aligned["target_time"] - aligned["quote_time"]
    ).dt.total_seconds() * 1000
    aligned.loc[aligned["quote_time"].isna(), "quote_age_ms"] = pd.NA

    aligned = add_quote_quality_columns(aligned)
    stale = aligned["quote_age_ms"].isna() | (aligned["quote_age_ms"] > max_quote_age_ms)
    invalid = ~aligned["quote_valid"].fillna(False)
    wide = aligned["spread_bps"].notna() & (aligned["spread_bps"] > 500)

    aligned["quote_quality"] = "ok"
    aligned.loc[wide, "quote_quality"] = "wide_spread"
    aligned.loc[invalid, "quote_quality"] = "invalid_bid_ask"
    aligned.loc[stale, "quote_quality"] = "stale"
    aligned.loc[aligned["quote_time"].isna(), "quote_quality"] = "missing"
    return aligned


def filter_ticks_for_trade_date(ticks: pd.DataFrame, trade_date: str | date | datetime) -> pd.DataFrame:
    if ticks.empty or "datetime" not in ticks.columns:
        return ticks
    day = pd.Timestamp(trade_date).date()
    times = pd.to_datetime(ticks["datetime"])
    return ticks.loc[times.dt.date == day].copy()


def build_symbol_range_minute_quotes(
    api: object,
    symbol: str,
    trade_dates: list[str],
    max_quote_age_ms: int = 60_000,
) -> dict[str, pd.DataFrame]:
    """Download ticks once for a date range, then align each trading day locally."""
    if not trade_dates:
        return {}

    ordered_dates = sorted(trade_dates)
    range_start, _ = trade_day_bounds(ordered_dates[0])
    _, range_end = trade_day_bounds(ordered_dates[-1])
    ticks = download_tick_frame(api, symbol, range_start, range_end)

    results: dict[str, pd.DataFrame] = {}
    for trade_date in ordered_dates:
        minutes = generate_session_minutes(trade_date)
        day_ticks = filter_ticks_for_trade_date(ticks, trade_date)
        quotes = align_ticks_to_minutes(day_ticks, minutes, max_quote_age_ms=max_quote_age_ms)
        quotes.insert(0, "symbol", symbol)
        quotes.insert(1, "trade_date", pd.Timestamp(trade_date).strftime("%Y-%m-%d"))
        results[trade_date] = quotes
    return results


def build_daily_minute_quotes(
    api: object,
    symbol: str,
    trade_date: str | date | datetime,
    max_quote_age_ms: int = 60_000,
    target_start_time: datetime | None = None,
    target_end_time: datetime | None = None,
    quote_lookback_minutes: int = 30,
) -> pd.DataFrame:
    day_start, day_end = trade_day_bounds(trade_date)
    start_dt = day_start
    end_dt = day_end
    if target_start_time is not None:
        lookback = timedelta(minutes=max(quote_lookback_minutes, 1))
        start_dt = max(day_start, target_start_time - lookback)
    if target_end_time is not None:
        end_dt = min(day_end, target_end_time + timedelta(minutes=1))

    ticks = download_tick_frame(api, symbol, start_dt, end_dt)
    minutes = generate_session_minutes(
        trade_date,
        start_time=target_start_time,
        end_time=target_end_time,
    )
    quotes = align_ticks_to_minutes(ticks, minutes, max_quote_age_ms=max_quote_age_ms)
    quotes.insert(0, "symbol", symbol)
    quotes.insert(1, "trade_date", pd.Timestamp(trade_date).strftime("%Y-%m-%d"))
    return quotes


def build_unavailable_minute_quotes(symbol: str, trade_date: str | date | datetime) -> pd.DataFrame:
    """Build a canonical no-price frame when a historical quote request is unavailable."""
    minutes = generate_session_minutes(trade_date)
    frame = minutes.copy()
    frame.insert(0, "symbol", symbol)
    frame.insert(1, "trade_date", pd.Timestamp(trade_date).strftime("%Y-%m-%d"))
    frame["quote_time"] = pd.NaT
    for column in [
        "last_price",
        "bid_price1",
        "ask_price1",
        "bid_volume1",
        "ask_volume1",
        "volume",
        "amount",
        "open_interest",
        "quote_age_ms",
        "mid_price",
        "spread",
        "spread_bps",
        "micro_price",
    ]:
        frame[column] = pd.NA
    frame["quote_valid"] = False
    frame["quote_quality"] = "source_unavailable"
    frame["data_issue"] = "historical_quote_unavailable"
    return frame


def save_daily_minute_quotes(frame: pd.DataFrame, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path
