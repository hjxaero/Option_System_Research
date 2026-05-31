from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


VALID_QUOTE_QUALITIES = {"ok", "wide_spread", "stale", "stale_quote", "invalid_bid_ask"}


def load_first_valid_date_cache(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}
    cache_path = Path(path)
    if not cache_path.exists():
        return {}
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    return {str(symbol): str(date) for symbol, date in payload.items()}


def save_first_valid_date_cache(cache: dict[str, str], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def filter_dates_by_first_valid(symbol: str, dates: list[str], cache: dict[str, str]) -> list[str]:
    first_valid = cache.get(symbol)
    if not first_valid:
        return dates
    return [date for date in dates if date >= first_valid]


def infer_first_valid_dates_from_quote_root(
    data_root: str | Path,
    product: str,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, str]:
    root = Path(data_root) / "quotes" / "minute" / product.upper()
    if not root.exists():
        return {}

    result: dict[str, str] = {}
    for parquet_path in sorted(root.glob("*/*.parquet")):
        trade_date = parquet_path.stem
        if start and trade_date < start:
            continue
        if end and trade_date > end:
            continue
        try:
            frame = pd.read_parquet(parquet_path, columns=["symbol", "quote_quality"])
        except Exception:
            continue
        if frame.empty or "quote_quality" not in frame.columns:
            continue
        valid = frame["quote_quality"].isin(VALID_QUOTE_QUALITIES)
        if not bool(valid.any()):
            continue
        symbol = str(frame["symbol"].dropna().iloc[0]) if "symbol" in frame.columns and frame["symbol"].notna().any() else parquet_path.parent.name.replace("_", ".")
        previous = result.get(symbol)
        if previous is None or trade_date < previous:
            result[symbol] = trade_date
    return result
