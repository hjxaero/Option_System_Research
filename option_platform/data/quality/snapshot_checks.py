from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CompletenessResult:
    status: str
    detail: str = ""

    @property
    def is_complete(self) -> bool:
        return self.status == "complete"


def check_snapshot_completeness(
    filepath: str | Path,
    expiry_date: str,
    as_of_date: str | None = None,
) -> CompletenessResult:
    path = Path(filepath)
    if not path.exists():
        return CompletenessResult("missing")

    try:
        frame = pd.read_parquet(path, columns=["timestamp"])
    except Exception as exc:
        return CompletenessResult("incomplete", f"read error: {exc}")

    if frame.empty:
        return CompletenessResult("incomplete", "empty file")

    last_ts = pd.Timestamp(frame["timestamp"].max()).to_pydatetime()
    expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d")
    today_dt = (
        datetime.strptime(as_of_date, "%Y-%m-%d")
        if as_of_date
        else datetime.now()
    )

    if expiry_dt <= today_dt:
        target = expiry_dt.replace(hour=14, minute=30)
        if last_ts >= target:
            return CompletenessResult("complete", f"last={last_ts:%Y-%m-%d %H:%M}")
        return CompletenessResult(
            "incomplete",
            f"last={last_ts:%Y-%m-%d %H:%M}, expect>={expiry_date} 14:30",
        )

    target = (today_dt - timedelta(days=1)).replace(hour=14, minute=0)
    if last_ts >= target:
        return CompletenessResult("complete", f"last={last_ts:%Y-%m-%d %H:%M} ongoing")
    return CompletenessResult(
        "incomplete",
        f"last={last_ts:%Y-%m-%d %H:%M}, expect>={target:%Y-%m-%d %H:%M}",
    )

