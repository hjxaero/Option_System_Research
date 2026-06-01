from __future__ import annotations

from datetime import date, datetime, timedelta


def iter_download_windows(
    start: str,
    end: str,
    window_days: int = 10,
) -> list[tuple[str, str]]:
    """Split an inclusive calendar range into chunks of at most ``window_days`` days.

    Each window is ``(window_start, window_end)`` as ``YYYY-MM-DD`` strings.
    The underlying minute-quote downloader still filters to trading weekdays.
    """
    if window_days < 1:
        raise ValueError(f"window_days must be >= 1, got {window_days}")

    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if start_dt > end_dt:
        return []

    windows: list[tuple[str, str]] = []
    current = start_dt
    step = timedelta(days=window_days - 1)
    while current <= end_dt:
        window_end = min(current + step, end_dt)
        windows.append(
            (
                current.strftime("%Y-%m-%d"),
                window_end.strftime("%Y-%m-%d"),
            )
        )
        current = window_end + timedelta(days=1)
    return windows


def _parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()
