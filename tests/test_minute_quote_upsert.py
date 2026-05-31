import json

import pandas as pd

from option_platform.data.storage.state import UpdateState, save_state
from option_platform.data.storage.upsert import merge_minute_quotes, upsert_parquet


def test_merge_minute_quotes_keeps_newer_quote_for_same_quality():
    existing = pd.DataFrame(
        {
            "symbol": ["CFFEX.MO2606-C-6000"],
            "target_time": pd.to_datetime(["2026-05-27 09:30:00"]),
            "quote_time": pd.to_datetime(["2026-05-27 09:29:58"]),
            "quote_quality": ["ok"],
            "bid_price1": [10.0],
        }
    )
    incoming = pd.DataFrame(
        {
            "symbol": ["CFFEX.MO2606-C-6000"],
            "target_time": pd.to_datetime(["2026-05-27 09:30:00"]),
            "quote_time": pd.to_datetime(["2026-05-27 09:30:00"]),
            "quote_quality": ["ok"],
            "bid_price1": [10.1],
        }
    )

    merged = merge_minute_quotes(existing, incoming)

    assert len(merged) == 1
    assert merged.iloc[0]["bid_price1"] == 10.1


def test_merge_minute_quotes_keeps_better_quality_over_newer_stale():
    existing = pd.DataFrame(
        {
            "symbol": ["CFFEX.MO2606-C-6000"],
            "target_time": pd.to_datetime(["2026-05-27 09:30:00"]),
            "quote_time": pd.to_datetime(["2026-05-27 09:29:58"]),
            "quote_quality": ["ok"],
            "bid_price1": [10.0],
        }
    )
    incoming = pd.DataFrame(
        {
            "symbol": ["CFFEX.MO2606-C-6000"],
            "target_time": pd.to_datetime(["2026-05-27 09:30:00"]),
            "quote_time": pd.to_datetime(["2026-05-27 09:30:00"]),
            "quote_quality": ["stale"],
            "bid_price1": [9.0],
        }
    )

    merged = merge_minute_quotes(existing, incoming)

    assert len(merged) == 1
    assert merged.iloc[0]["bid_price1"] == 10.0
    assert merged.iloc[0]["quote_quality"] == "ok"


def test_upsert_parquet_and_state_file(tmp_path):
    path = tmp_path / "quotes.parquet"
    frame = pd.DataFrame(
        {
            "symbol": ["CFFEX.MO2606-C-6000"],
            "target_time": pd.to_datetime(["2026-05-27 09:30:00"]),
            "quote_time": pd.to_datetime(["2026-05-27 09:30:00"]),
            "quote_quality": ["ok"],
        }
    )

    merged = upsert_parquet(path, frame)
    assert path.exists()
    assert len(merged) == 1

    state_file = tmp_path / "state.json"
    save_state(
        state_file,
        UpdateState(
            product="MO",
            symbol="CFFEX.MO2606-C-6000",
            trade_date="2026-05-27",
            rows=1,
        ),
    )

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["product"] == "MO"
    assert payload["rows"] == 1
    assert payload["updated_at"]

