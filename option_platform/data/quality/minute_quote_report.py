from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class QuoteQualitySummary:
    rows: int
    symbols: int
    target_minutes: int
    ok_ratio: float
    wide_spread_ratio: float
    usable_ratio: float
    stale_ratio: float
    missing_ratio: float
    invalid_ratio: float
    median_quote_age_ms: float | None
    p95_quote_age_ms: float | None
    median_spread_bps: float | None
    p95_spread_bps: float | None


def summarize_minute_quotes(frame: pd.DataFrame) -> QuoteQualitySummary:
    if frame.empty:
        return QuoteQualitySummary(
            rows=0,
            symbols=0,
            target_minutes=0,
            ok_ratio=0.0,
            wide_spread_ratio=0.0,
            usable_ratio=0.0,
            stale_ratio=0.0,
            missing_ratio=0.0,
            invalid_ratio=0.0,
            median_quote_age_ms=None,
            p95_quote_age_ms=None,
            median_spread_bps=None,
            p95_spread_bps=None,
        )

    quality = frame["quote_quality"].fillna("unknown") if "quote_quality" in frame else pd.Series([], dtype=str)
    rows = len(frame)

    def ratio(name: str) -> float:
        return float((quality == name).sum() / rows) if rows else 0.0

    quote_age = pd.to_numeric(
        frame["quote_age_ms"] if "quote_age_ms" in frame.columns else pd.Series(index=frame.index, dtype=float),
        errors="coerce",
    )
    spread = pd.to_numeric(
        frame["spread_bps"] if "spread_bps" in frame.columns else pd.Series(index=frame.index, dtype=float),
        errors="coerce",
    )

    return QuoteQualitySummary(
        rows=rows,
        symbols=int(frame["symbol"].nunique()) if "symbol" in frame else 0,
        target_minutes=int(frame["target_time"].nunique()) if "target_time" in frame else 0,
        ok_ratio=ratio("ok"),
        wide_spread_ratio=ratio("wide_spread"),
        usable_ratio=ratio("ok") + ratio("wide_spread"),
        stale_ratio=ratio("stale"),
        missing_ratio=ratio("missing"),
        invalid_ratio=ratio("invalid_bid_ask"),
        median_quote_age_ms=float(quote_age.median()) if quote_age.notna().any() else None,
        p95_quote_age_ms=float(quote_age.quantile(0.95)) if quote_age.notna().any() else None,
        median_spread_bps=float(spread.median()) if spread.notna().any() else None,
        p95_spread_bps=float(spread.quantile(0.95)) if spread.notna().any() else None,
    )


def summarize_by_symbol(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    rows = []
    for symbol, group in frame.groupby("symbol"):
        summary = summarize_minute_quotes(group)
        rows.append(
            {
                "symbol": symbol,
                "rows": summary.rows,
                "ok_ratio": summary.ok_ratio,
                "wide_spread_ratio": summary.wide_spread_ratio,
                "usable_ratio": summary.usable_ratio,
                "stale_ratio": summary.stale_ratio,
                "missing_ratio": summary.missing_ratio,
                "invalid_ratio": summary.invalid_ratio,
                "median_quote_age_ms": summary.median_quote_age_ms,
                "p95_quote_age_ms": summary.p95_quote_age_ms,
                "median_spread_bps": summary.median_spread_bps,
                "p95_spread_bps": summary.p95_spread_bps,
            }
        )
    return pd.DataFrame(rows).sort_values(["ok_ratio", "p95_spread_bps"], ascending=[True, False])


def write_quality_report(
    frame: pd.DataFrame,
    output_dir: str | Path,
    prefix: str,
) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = summarize_minute_quotes(frame)
    by_symbol = summarize_by_symbol(frame)

    summary_path = output / f"{prefix}_summary.json"
    by_symbol_path = output / f"{prefix}_by_symbol.csv"

    summary_path.write_text(
        pd.Series(summary.__dict__).to_json(force_ascii=False, indent=2),
        encoding="utf-8",
    )
    by_symbol.to_csv(by_symbol_path, index=False, encoding="utf-8-sig")
    return summary_path, by_symbol_path
