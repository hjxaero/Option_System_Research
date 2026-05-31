from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd


MO_DAY_SESSIONS: tuple[tuple[time, time], ...] = (
    (time(9, 30), time(11, 30)),
    (time(13, 0), time(15, 0)),
)


def _parse_trade_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def generate_session_minutes(
    trade_date: str | date | datetime,
    sessions: tuple[tuple[time, time], ...] = MO_DAY_SESSIONS,
    include_session_close: bool = True,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> pd.DataFrame:
    """Generate the canonical target minute timestamps for a trading day."""
    day = _parse_trade_date(trade_date)
    ranges = []
    for session_start, session_end in sessions:
        start = datetime.combine(day, session_start)
        end = datetime.combine(day, session_end)
        inclusive = "both" if include_session_close else "left"
        ranges.append(pd.date_range(start=start, end=end, freq="min", inclusive=inclusive))

    if not ranges:
        return pd.DataFrame({"target_time": pd.Series(dtype="datetime64[ns]")})

    frame = pd.DataFrame({"target_time": ranges[0].append(ranges[1:])})
    if start_time is not None:
        frame = frame[frame["target_time"] >= pd.Timestamp(start_time)]
    if end_time is not None:
        frame = frame[frame["target_time"] <= pd.Timestamp(end_time)]
    return frame.reset_index(drop=True)


def trade_day_bounds(trade_date: str | date | datetime) -> tuple[datetime, datetime]:
    day = _parse_trade_date(trade_date)
    return datetime.combine(day, time(9, 0)), datetime.combine(day, time(15, 15))
