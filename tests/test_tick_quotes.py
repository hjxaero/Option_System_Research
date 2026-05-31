import pandas as pd

from option_platform.data.sources.tq_ticks import ticks_to_minute_quotes


def test_ticks_to_minute_quotes_keeps_last_quote_per_minute():
    ticks = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                [
                    "2026-05-27 09:30:01",
                    "2026-05-27 09:30:30",
                    "2026-05-27 09:31:01",
                ]
            ),
            "last_price": [9.9, 10.0, 10.2],
            "bid_price1": [9.8, 9.9, 10.1],
            "ask_price1": [10.2, 10.1, 10.3],
            "bid_volume1": [1, 2, 3],
            "ask_volume1": [2, 2, 3],
            "volume": [100, 110, 120],
            "amount": [1000, 1100, 1200],
            "open_interest": [1000, 1001, 1002],
        }
    )

    quotes = ticks_to_minute_quotes(ticks)

    assert len(quotes) == 2
    assert quotes.iloc[0]["timestamp"] == pd.Timestamp("2026-05-27 09:30:00")
    assert quotes.iloc[0]["quote_time"] == pd.Timestamp("2026-05-27 09:30:30")
    assert quotes.iloc[0]["mid_price"] == 10.0
    assert quotes.iloc[0]["quote_valid"]

