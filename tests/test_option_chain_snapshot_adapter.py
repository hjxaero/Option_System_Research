import pandas as pd
import pytest

from option_platform.option_chain.adapters import chain_from_snapshot_frame


def test_chain_from_snapshot_frame_maps_snapshot_fields_to_chain():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-06-01 09:31:00",
                    "2026-06-01 09:31:00",
                    "2026-06-01 09:31:00",
                ]
            ),
            "underlying_symbol": ["MO", "MO", "MO"],
            "futures_price": [105.0, 105.0, 105.0],
            "symbol": ["MO-C-100", "MO-P-100", "MO-C-105"],
            "option_type": ["call", "put", "call"],
            "strike_price": [100.0, 100.0, 105.0],
            "expiry_date": ["2026-06-19", "2026-06-19", "2026-06-19"],
            "volume_multiple": [100, 100, 100],
            "bid_price1": [5.0, 0.8, 3.0],
            "ask_price1": [5.2, 1.0, 3.2],
            "last_price": [5.1, 0.9, 3.1],
            "mark_price": [5.1, 0.9, 3.1],
            "volume": [10, 8, 20],
            "open_interest": [100, 80, 200],
            "quote_quality": ["ok", "ok", "ok"],
            "iv": [0.22, 0.24, 0.2],
            "delta": [0.75, -0.25, 0.5],
            "gamma": [0.01, 0.02, 0.03],
            "theta": [-0.1, -0.2, -0.3],
            "vega": [1.0, 1.1, 1.2],
        }
    )

    chain = chain_from_snapshot_frame(frame, as_of="2026-06-01")
    row = chain.get_row("2026-06-19", 100)

    assert chain.underlying.symbol == "MO"
    assert chain.underlying.price == 105
    assert row.call_quote.effective_price == pytest.approx(5.1)
    assert row.put_quote.implied_volatility == pytest.approx(0.24)
    assert row.call_greeks.delta == pytest.approx(0.75)
    assert chain.get_atm("2026-06-19").strike == 105


def test_chain_from_snapshot_frame_requires_single_timestamp_slice():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-06-01 09:31:00", "2026-06-01 09:32:00"]),
            "underlying_symbol": ["MO", "MO"],
            "futures_price": [105.0, 105.0],
            "symbol": ["MO-C-100", "MO-C-100"],
            "option_type": ["call", "call"],
            "strike_price": [100.0, 100.0],
            "expiry_date": ["2026-06-19", "2026-06-19"],
        }
    )

    with pytest.raises(ValueError, match="exactly one timestamp"):
        chain_from_snapshot_frame(frame)

    chain = chain_from_snapshot_frame(frame, timestamp="2026-06-01 09:32:00")

    assert len(chain.rows) == 1
