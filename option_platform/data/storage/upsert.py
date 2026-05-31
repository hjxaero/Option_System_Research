from __future__ import annotations

from pathlib import Path

import pandas as pd


def _quality_rank(value: object) -> int:
    ranks = {
        "ok": 5,
        "wide_spread": 4,
        "invalid_bid_ask": 3,
        "stale": 2,
        "missing": 1,
    }
    return ranks.get(str(value), 0)


def merge_minute_quotes(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Merge minute quote rows and keep the best row for each symbol/target_time."""
    if existing.empty:
        merged = incoming.copy()
    elif incoming.empty:
        merged = existing.copy()
    else:
        merged = pd.concat([existing, incoming], ignore_index=True, sort=False)

    if merged.empty:
        return merged

    if "quote_quality" in merged.columns:
        merged["_quality_rank"] = merged["quote_quality"].map(_quality_rank).fillna(0)
    else:
        merged["_quality_rank"] = 0

    for col in ("target_time", "quote_time"):
        if col in merged.columns:
            merged[col] = pd.to_datetime(merged[col])

    sort_cols = ["symbol", "target_time", "_quality_rank"]
    ascending = [True, True, True]
    if "quote_time" in merged.columns:
        sort_cols.append("quote_time")
        ascending.append(True)

    merged = merged.sort_values(sort_cols, ascending=ascending)
    merged = merged.drop_duplicates(["symbol", "target_time"], keep="last")
    merged = merged.drop(columns=["_quality_rank"])
    return merged.sort_values(["symbol", "target_time"]).reset_index(drop=True)


def upsert_parquet(path: str | Path, incoming: pd.DataFrame) -> pd.DataFrame:
    output = Path(path)
    existing = pd.read_parquet(output) if output.exists() else pd.DataFrame()
    merged = merge_minute_quotes(existing, incoming)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output.with_suffix(output.suffix + ".tmp")
    merged.to_parquet(tmp_path, index=False)
    tmp_path.replace(output)
    return merged

