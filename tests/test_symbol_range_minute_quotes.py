import pandas as pd

from option_platform.data.sources.tq_minute_quotes import filter_ticks_for_trade_date


def test_filter_ticks_for_trade_date():
    ticks = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                ["2026-01-05 09:30:01", "2026-01-06 09:30:01"],
            ),
            "last_price": [10.0, 11.0],
            "bid_price1": [9.9, 10.9],
            "ask_price1": [10.1, 11.1],
            "bid_volume1": [1, 1],
            "ask_volume1": [1, 1],
        }
    )
    day = filter_ticks_for_trade_date(ticks, "2026-01-05")
    assert len(day) == 1
    assert day.iloc[0]["last_price"] == 10.0

