import pandas as pd

from option_platform.data.quality.repair import (
    active_trading_dates,
    build_repair_plan,
    infer_expected_symbols,
    summarize_by_date,
)


def _frame(symbol: str, quality: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol] * len(quality),
            "target_time": pd.date_range("2026-01-05 09:30", periods=len(quality), freq="min"),
            "quote_quality": quality,
            "quote_age_ms": [0 if q != "missing" else None for q in quality],
            "spread_bps": [100 if q in {"ok", "wide_spread"} else None for q in quality],
        }
    )


def test_active_trading_dates_excludes_all_missing_dates():
    quote_files = {
        ("2026-01-02", "a"): _frame("a", ["missing", "missing"]),
        ("2026-01-05", "a"): _frame("a", ["ok", "wide_spread"]),
    }
    summary = summarize_by_date(quote_files)

    assert active_trading_dates(summary) == ["2026-01-05"]


def test_build_repair_plan_detects_missing_file_and_low_usable():
    quote_files = {
        ("2026-01-05", "a"): _frame("a", ["ok", "wide_spread"]),
        ("2026-01-05", "b"): _frame("b", ["missing", "missing"]),
        ("2026-01-06", "a"): _frame("a", ["ok", "ok"]),
    }
    active_dates = ["2026-01-05", "2026-01-06"]
    expected_symbols = infer_expected_symbols(quote_files, active_dates)
    plan = build_repair_plan(quote_files, active_dates, expected_symbols)

    assert set(expected_symbols) == {"a", "b"}
    reason_sets = {frozenset(reason.split("|")) for reason in plan["reason"]}
    assert reason_sets == {frozenset({"low_usable", "high_missing"}), frozenset({"missing_file"})}
