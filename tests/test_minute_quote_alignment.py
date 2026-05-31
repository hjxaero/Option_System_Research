import pandas as pd

from option_platform.data.sources.tq_minute_quotes import align_ticks_to_minutes
from option_platform.data.trading_minutes import generate_session_minutes


def test_generate_mo_session_minutes():
    minutes = generate_session_minutes("2026-05-27")

    assert minutes.iloc[0]["target_time"] == pd.Timestamp("2026-05-27 09:30:00")
    assert minutes.iloc[-1]["target_time"] == pd.Timestamp("2026-05-27 15:00:00")
    assert len(minutes) == 242


def test_align_ticks_to_minutes_uses_last_quote_before_target():
    ticks = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                [
                    "2026-05-27 09:29:59",
                    "2026-05-27 09:30:30",
                    "2026-05-27 09:31:00",
                ]
            ),
            "last_price": [9.8, 10.0, 10.1],
            "bid_price1": [9.7, 9.9, 10.0],
            "ask_price1": [9.9, 10.1, 10.2],
            "bid_volume1": [1, 2, 3],
            "ask_volume1": [1, 2, 3],
        }
    )
    targets = pd.DataFrame(
        {
            "target_time": pd.to_datetime(
                [
                    "2026-05-27 09:30:00",
                    "2026-05-27 09:31:00",
                ]
            )
        }
    )

    aligned = align_ticks_to_minutes(ticks, targets, max_quote_age_ms=60_000)

    assert aligned.iloc[0]["quote_time"] == pd.Timestamp("2026-05-27 09:29:59")
    assert aligned.iloc[0]["quote_age_ms"] == 1000
    assert aligned.iloc[1]["quote_time"] == pd.Timestamp("2026-05-27 09:31:00")
    assert aligned.iloc[1]["quote_age_ms"] == 0
    assert aligned.iloc[1]["quote_quality"] == "ok"


def test_align_ticks_to_minutes_marks_stale_quotes():
    ticks = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-05-27 09:30:00"]),
            "last_price": [10.0],
            "bid_price1": [9.9],
            "ask_price1": [10.1],
            "bid_volume1": [1],
            "ask_volume1": [1],
        }
    )
    targets = pd.DataFrame({"target_time": pd.to_datetime(["2026-05-27 09:32:00"])})

    aligned = align_ticks_to_minutes(ticks, targets, max_quote_age_ms=30_000)

    assert aligned.iloc[0]["quote_quality"] == "stale"

