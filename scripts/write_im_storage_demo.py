#!/usr/bin/env python3
"""Write synthetic IM futures minute storage demo under data_store/_demo/."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from option_platform.data.quality.quote_quality import add_quote_quality_columns
from option_platform.data.trading_minutes import generate_session_minutes


def _write_table(frame: pd.DataFrame, path_without_suffix: Path) -> tuple[Path, Path]:
    try:
        out = path_without_suffix.with_suffix(".parquet")
        frame.to_parquet(out, index=False)
        return out, out
    except ImportError:
        out = path_without_suffix.with_suffix(".csv")
        frame.to_csv(out, index=False)
        return out, out


def _synthetic_im_day(trade_date: str, symbol: str, expiry_date: str, base_price: float) -> pd.DataFrame:
    minutes = generate_session_minutes(trade_date)
    n = len(minutes)
    frame = minutes.copy()
    frame.insert(0, "trade_date", trade_date)
    frame.insert(1, "symbol", symbol)
    frame.insert(2, "expiry_date", expiry_date)

    # Simple walk: bid/ask around base + minute index
    offset = pd.Series(range(n), dtype=float) * 0.2
    frame["bid_price1"] = base_price + offset
    frame["ask_price1"] = base_price + offset + 0.4
    frame["bid_volume1"] = 12
    frame["ask_volume1"] = 15
    frame["last_price"] = base_price + offset + 0.2
    frame["quote_time"] = frame["target_time"]
    frame["quote_age_ms"] = 0.0
    frame["volume"] = 1000 + offset * 10
    frame["open_interest"] = 50000.0

    frame = add_quote_quality_columns(frame)
    frame["price_source"] = "micro"
    frame.loc[~frame["quote_valid"].fillna(False), "price_source"] = "missing"
    frame["quote_quality"] = "ok"
    frame.loc[frame["price_source"] == "missing", "quote_quality"] = "missing"
    return frame


def write_demo(root: Path, trade_date: str = "2025-05-27") -> None:
    im_root = root / "futures" / "IM"
    meta_dir = im_root / "meta"
    minute_dir = im_root / "minute"
    meta_dir.mkdir(parents=True, exist_ok=True)
    minute_dir.mkdir(parents=True, exist_ok=True)

    calendar = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "symbol": "CFFEX.IM2506",
                "expiry_date": "2025-06-20",
                "pricing_rank": 1,
                "note": "demo primary pricing contract",
            }
        ]
    )
    minute_frame = _synthetic_im_day(
        trade_date=trade_date,
        symbol="CFFEX.IM2506",
        expiry_date="2025-06-20",
        base_price=5120.0,
    )
    calendar_path, _ = _write_table(calendar, meta_dir / "contract_calendar")
    minute_path, _ = _write_table(minute_frame, minute_dir / trade_date)

    print(f"wrote {calendar_path} ({len(calendar)} rows)")
    print(
        f"wrote {minute_path} ({len(minute_frame)} rows, "
        f"target_minutes={minute_frame['target_time'].nunique()})"
    )
    print(minute_frame.head(3).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Write IM futures minute storage demo parquet files.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data_store/_demo"),
        help="Root directory (default: data_store/_demo)",
    )
    parser.add_argument("--trade-date", default="2025-05-27")
    args = parser.parse_args()
    write_demo(args.data_root.resolve(), trade_date=args.trade_date)


if __name__ == "__main__":
    main()
