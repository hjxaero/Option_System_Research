from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from option_platform.data.quality.minute_quote_report import summarize_minute_quotes


@dataclass(frozen=True)
class RepairThresholds:
    min_symbol_usable_ratio: float = 0.50
    max_symbol_missing_ratio: float = 0.40
    max_symbol_stale_ratio: float = 0.20


def load_quote_files(data_root: str | Path, product: str, dates: list[str]) -> dict[tuple[str, str], pd.DataFrame]:
    root = Path(data_root) / "quotes" / "minute" / product.upper()
    date_set = set(dates)
    result: dict[tuple[str, str], pd.DataFrame] = {}
    if not root.exists():
        return result

    for parquet_path in sorted(root.glob("*/*.parquet")):
        trade_date = parquet_path.stem
        if trade_date not in date_set:
            continue
        frame = pd.read_parquet(parquet_path)
        symbol = frame["symbol"].iloc[0] if "symbol" in frame.columns and len(frame) else parquet_path.parent.name
        result[(trade_date, symbol)] = frame
    return result


def summarize_by_date(quote_files: dict[tuple[str, str], pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for trade_date in sorted({key[0] for key in quote_files}):
        frames = [frame for (date, _), frame in quote_files.items() if date == trade_date]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        summary = summarize_minute_quotes(combined)
        rows.append(
            {
                "date": trade_date,
                "files": len(frames),
                "rows": summary.rows,
                "symbols": summary.symbols,
                "ok_ratio": summary.ok_ratio,
                "wide_spread_ratio": summary.wide_spread_ratio,
                "usable_ratio": summary.usable_ratio,
                "stale_ratio": summary.stale_ratio,
                "missing_ratio": summary.missing_ratio,
                "invalid_ratio": summary.invalid_ratio,
                "p95_quote_age_ms": summary.p95_quote_age_ms,
                "p95_spread_bps": summary.p95_spread_bps,
            }
        )
    return pd.DataFrame(rows)


def active_trading_dates(date_summary: pd.DataFrame) -> list[str]:
    if date_summary.empty:
        return []
    active = date_summary[
        (date_summary["rows"] > 0)
        & (
            (date_summary["usable_ratio"] > 0)
            | (date_summary["stale_ratio"] > 0)
            | (date_summary["invalid_ratio"] > 0)
        )
    ]
    return active["date"].tolist()


def infer_expected_symbols(
    quote_files: dict[tuple[str, str], pd.DataFrame],
    active_dates: list[str],
) -> list[str]:
    if not active_dates:
        return []

    counts = {
        date: len({symbol for (d, symbol) in quote_files if d == date})
        for date in active_dates
    }
    if not counts:
        return []
    reference_date = max(counts, key=lambda date: counts[date])
    return sorted({symbol for (date, symbol) in quote_files if date == reference_date})


def build_repair_plan(
    quote_files: dict[tuple[str, str], pd.DataFrame],
    active_dates: list[str],
    expected_symbols: list[str],
    thresholds: RepairThresholds = RepairThresholds(),
) -> pd.DataFrame:
    repairs = []
    for trade_date in active_dates:
        for symbol in expected_symbols:
            frame = quote_files.get((trade_date, symbol))
            if frame is None:
                repairs.append(
                    {
                        "date": trade_date,
                        "symbol": symbol,
                        "reason": "missing_file",
                        "rows": 0,
                        "usable_ratio": 0.0,
                        "missing_ratio": 1.0,
                        "stale_ratio": 0.0,
                    }
                )
                continue

            summary = summarize_minute_quotes(frame)
            reasons = []
            if summary.usable_ratio < thresholds.min_symbol_usable_ratio:
                reasons.append("low_usable")
            if summary.missing_ratio > thresholds.max_symbol_missing_ratio:
                reasons.append("high_missing")
            if summary.stale_ratio > thresholds.max_symbol_stale_ratio:
                reasons.append("high_stale")
            if reasons:
                repairs.append(
                    {
                        "date": trade_date,
                        "symbol": symbol,
                        "reason": "|".join(reasons),
                        "rows": summary.rows,
                        "usable_ratio": summary.usable_ratio,
                        "missing_ratio": summary.missing_ratio,
                        "stale_ratio": summary.stale_ratio,
                    }
                )

    return pd.DataFrame(repairs).sort_values(["date", "reason", "symbol"]).reset_index(drop=True)

