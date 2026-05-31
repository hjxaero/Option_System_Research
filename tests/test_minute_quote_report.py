import pandas as pd

from option_platform.data.quality.minute_quote_report import (
    summarize_by_symbol,
    summarize_minute_quotes,
)


def test_summarize_minute_quotes():
    frame = pd.DataFrame(
        {
            "symbol": ["a", "a", "b", "b"],
            "target_time": pd.to_datetime(
                [
                    "2026-05-27 09:30",
                    "2026-05-27 09:31",
                    "2026-05-27 09:30",
                    "2026-05-27 09:31",
                ]
            ),
            "quote_quality": ["ok", "stale", "missing", "invalid_bid_ask"],
            "quote_age_ms": [0, 70_000, None, 1000],
            "spread_bps": [10, 20, None, 30],
        }
    )

    summary = summarize_minute_quotes(frame)

    assert summary.rows == 4
    assert summary.symbols == 2
    assert summary.target_minutes == 2
    assert summary.ok_ratio == 0.25
    assert summary.wide_spread_ratio == 0.0
    assert summary.usable_ratio == 0.25
    assert summary.stale_ratio == 0.25
    assert summary.missing_ratio == 0.25
    assert summary.invalid_ratio == 0.25


def test_summarize_by_symbol_orders_lower_quality_first():
    frame = pd.DataFrame(
        {
            "symbol": ["good", "bad"],
            "target_time": pd.to_datetime(["2026-05-27 09:30", "2026-05-27 09:30"]),
            "quote_quality": ["ok", "missing"],
            "quote_age_ms": [0, None],
            "spread_bps": [10, None],
        }
    )

    summary = summarize_by_symbol(frame)

    assert summary.iloc[0]["symbol"] == "bad"
