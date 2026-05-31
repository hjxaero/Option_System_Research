from __future__ import annotations

from datetime import date, datetime, time
from typing import Iterable

import pandas as pd

from option_platform.data.trading_minutes import MO_DAY_SESSIONS


TRADING_DAYS_PER_YEAR = 252
TRADING_MINUTES_PER_DAY = 240


def _as_date(value: str | date | datetime | pd.Timestamp) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _as_datetime(value: str | datetime | pd.Timestamp) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime: {value}")


def trading_minutes_elapsed_in_day(
    current_time: str | datetime | pd.Timestamp,
    sessions: tuple[tuple[time, time], ...] = MO_DAY_SESSIONS,
) -> int:
    current = _as_datetime(current_time)
    elapsed = 0
    for session_start, session_end in sessions:
        start = datetime.combine(current.date(), session_start)
        end = datetime.combine(current.date(), session_end)
        if current <= start:
            continue
        segment_end = min(current, end)
        if segment_end > start:
            elapsed += int((segment_end - start).total_seconds() // 60)
    return max(0, min(elapsed, TRADING_MINUTES_PER_DAY))


def calculate_t_years_by_trading_minutes(
    current_time: str | datetime | pd.Timestamp,
    expiry_date: str | date | datetime | pd.Timestamp,
    trading_days: Iterable[str | date | datetime | pd.Timestamp],
    expiry_close: time = time(15, 0),
) -> float:
    """Calculate time to expiry by trading-minute decay.

    One trading day is treated as 240 minutes. This avoids an artificial IV jump
    at the open caused by subtracting a whole calendar day overnight.
    """
    current = _as_datetime(current_time)
    expiry = _as_date(expiry_date)
    days = sorted({_as_date(day) for day in trading_days})
    current_day = current.date()

    if current_day > expiry:
        return 1 / (TRADING_DAYS_PER_YEAR * TRADING_MINUTES_PER_DAY)

    remaining_minutes = 0
    for day in days:
        if day < current_day or day > expiry:
            continue
        if day == current_day:
            elapsed = trading_minutes_elapsed_in_day(current)
            remaining_minutes += max(TRADING_MINUTES_PER_DAY - elapsed, 0)
        elif day == expiry:
            # Current day is handled above. Future expiry day contributes a full
            # trading day under the 240-minute convention.
            remaining_minutes += TRADING_MINUTES_PER_DAY
        else:
            remaining_minutes += TRADING_MINUTES_PER_DAY

    if current_day == expiry and current.time() >= expiry_close:
        remaining_minutes = 0

    return max(remaining_minutes, 1) / (TRADING_DAYS_PER_YEAR * TRADING_MINUTES_PER_DAY)

