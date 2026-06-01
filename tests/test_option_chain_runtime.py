import pandas as pd
import pytest

from option_platform.option_chain.runtime import build_pricing_frame, choose_best_timestamp


def test_choose_best_timestamp_prefers_ok_quotes_then_marks():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2022-07-22 09:30:00",
                    "2022-07-22 09:30:00",
                    "2022-07-22 09:31:00",
                    "2022-07-22 09:31:00",
                ]
            ),
            "symbol": ["a", "b", "a", "b"],
            "mark_price": [1.0, None, 1.0, 2.0],
            "quote_quality": ["ok", "missing", "ok", "ok"],
        }
    )

    assert choose_best_timestamp(frame) == pd.Timestamp("2022-07-22 09:31:00")


def test_build_pricing_frame_infers_forward_and_raw_iv():
    snapshot = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2022-07-22 10:00:00"] * 4),
            "underlying_symbol": ["MO"] * 4,
            "symbol": ["C100", "P100", "C105", "P105"],
            "expiry_date": ["2022-08-19"] * 4,
            "option_type": ["call", "put", "call", "put"],
            "strike_price": [100.0, 100.0, 105.0, 105.0],
            "mark_price": [5.0, 3.0, 3.0, 6.0],
            "quote_quality": ["ok"] * 4,
            "price_source": ["mid"] * 4,
            "spread_bps": [100.0] * 4,
            "open_interest": [100] * 4,
            "volume": [10] * 4,
        }
    )

    result = build_pricing_frame(snapshot, risk_free_rate=0.0)

    assert len(result) == 4
    assert result["forward_pairs"].iloc[0] == 2
    assert result["forward"].iloc[0] == pytest.approx(102.0)
    assert (result["raw_iv_quality"] == "ok").sum() >= 2
