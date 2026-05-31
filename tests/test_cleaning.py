import pandas as pd

from option_platform.data.cleaning import (
    add_clean_quote_columns,
    clean_option_quote,
    intrinsic_value,
)


def test_intrinsic_value():
    assert intrinsic_value(105, 100, "call") == 5
    assert intrinsic_value(95, 100, "call") == 0
    assert intrinsic_value(95, 100, "put") == 5


def test_clean_option_quote_prefers_micro_price():
    clean = clean_option_quote(
        bid_price1=10,
        ask_price1=10.2,
        bid_volume1=3,
        ask_volume1=1,
        last_price=10.1,
        quote_age_ms=0,
        spread_bps=198,
        forward_price=100,
        strike_price=100,
        option_type="call",
    )

    assert clean.price_source == "micro"
    assert clean.quote_quality == "ok"
    assert clean.iv_quality == "ok"


def test_clean_option_quote_marks_below_intrinsic():
    clean = clean_option_quote(
        bid_price1=1.0,
        ask_price1=1.2,
        bid_volume1=1,
        ask_volume1=1,
        last_price=1.1,
        quote_age_ms=0,
        spread_bps=100,
        forward_price=120,
        strike_price=100,
        option_type="call",
        price_tick=0.2,
    )

    assert clean.iv_quality == "below_intrinsic"


def test_add_clean_quote_columns():
    frame = pd.DataFrame(
        {
            "bid_price1": [10.0],
            "ask_price1": [10.2],
            "bid_volume1": [1],
            "ask_volume1": [1],
            "last_price": [10.1],
            "quote_age_ms": [0],
            "spread_bps": [198],
            "futures_price": [100],
            "strike_price": [100],
            "option_type": ["call"],
        }
    )

    result = add_clean_quote_columns(frame)

    assert result.iloc[0]["mark_price"] == 10.1
    assert result.iloc[0]["iv_quality"] == "ok"

