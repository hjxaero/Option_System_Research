import pandas as pd
import pytest

pytest.importorskip("pyarrow")

from option_platform.data.futures.im_minute_store import (
    annotate_im_minute_frame,
    should_skip_im_day,
)
from option_platform.data.futures.layout import im_minute_day_path
from option_platform.data.futures.resolve import ImDayContract
from option_platform.data.futures.im_minute_store import save_im_minute_day
from option_platform.data.trading_minutes import generate_session_minutes


def _synthetic_frame(trade_date: str, symbol: str, contract_month: str) -> pd.DataFrame:
    minutes = generate_session_minutes(trade_date).head(3)
    frame = minutes.copy()
    frame.insert(0, "trade_date", trade_date)
    frame.insert(1, "symbol", symbol)
    frame["quote_time"] = frame["target_time"]
    frame["quote_age_ms"] = 0.0
    frame["bid_price1"] = 5000.0
    frame["ask_price1"] = 5000.2
    frame["bid_volume1"] = 10
    frame["ask_volume1"] = 12
    frame["last_price"] = 5000.1
    frame["mid_price"] = 5000.1
    frame["micro_price"] = 5000.09
    frame["spread"] = 0.2
    frame["spread_bps"] = 0.4
    frame["quote_valid"] = True
    frame["quote_quality"] = "ok"
    return annotate_im_minute_frame(
        frame,
        contract_month=contract_month,
        expiry_date="2025-06-20",
    )


def test_save_im_minute_day_merges_symbols(tmp_path):
    trade_date = "2025-05-27"
    contracts = [
        ImDayContract("2506", "CFFEX.IM2506", "2025-06-20"),
        ImDayContract("2507", "CFFEX.IM2507", "2025-07-18"),
    ]
    f1 = _synthetic_frame(trade_date, "CFFEX.IM2506", "2506")
    f2 = _synthetic_frame(trade_date, "CFFEX.IM2507", "2507")
    frame = pd.concat([f1, f2], ignore_index=True)

    path = save_im_minute_day(tmp_path, trade_date, frame, contracts)
    assert path == im_minute_day_path(tmp_path, trade_date)
    loaded = pd.read_parquet(path)
    assert loaded["symbol"].nunique() == 2
    assert "contract_month" in loaded.columns
    assert "price_source" in loaded.columns


def test_should_skip_im_day_requires_enough_rows(tmp_path):
    trade_date = "2025-05-27"
    path = im_minute_day_path(tmp_path, trade_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    tiny = _synthetic_frame(trade_date, "CFFEX.IM2506", "2506")
    tiny.to_parquet(path, index=False)
    assert not should_skip_im_day(path, expected_symbols=1, min_rows_per_symbol=200)
