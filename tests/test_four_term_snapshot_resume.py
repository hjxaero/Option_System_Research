from __future__ import annotations

import pandas as pd

from option_platform.data.contracts import OptionContract
from option_platform.data.live_update import minute_quote_path
from option_platform.data.snapshots.four_term import (
    build_four_term_snapshot,
    four_term_snapshot_path,
    missing_minute_quote_files,
    save_four_term_snapshot,
    should_skip_four_term_snapshot,
)
from option_platform.data.trading_minutes import generate_session_minutes


def _contract(symbol: str, expiry: str, strike: float = 7000.0) -> OptionContract:
    return OptionContract(
        symbol=symbol,
        name=symbol,
        underlying_symbol="CFFEX.IM2601",
        underlying_product="MO",
        exchange="CFFEX",
        strike_price=strike,
        option_type="call" if "-C-" in symbol else "put",
        expiry_date=expiry,
        volume_multiple=100,
        price_tick=0.2,
        expired=False,
    )


def _minute_frame(symbol: str, trade_date: str) -> pd.DataFrame:
    minutes = generate_session_minutes(trade_date).head(3)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trade_date": trade_date,
            "target_time": minutes["target_time"],
            "quote_time": minutes["target_time"],
            "quote_age_ms": [0, 0, 0],
            "last_price": [10.0, 10.2, 10.4],
            "bid_price1": [9.8, 10.0, 10.2],
            "ask_price1": [10.2, 10.4, 10.6],
            "bid_volume1": [1, 1, 1],
            "ask_volume1": [1, 1, 1],
            "volume": [1, 2, 3],
            "open_interest": [100, 100, 100],
            "mid_price": [10.0, 10.2, 10.4],
            "micro_price": [10.0, 10.2, 10.4],
            "spread_bps": [400, 392.1568, 384.6154],
            "quote_quality": ["ok", "ok", "ok"],
        }
    )


def test_missing_minute_quote_files_checks_presence_and_rows(tmp_path):
    symbol = "CFFEX.MO2601-C-7000"
    path = minute_quote_path(tmp_path, "MO", symbol, "2026-01-05")
    path.parent.mkdir(parents=True)
    _minute_frame(symbol, "2026-01-05").to_parquet(path, index=False)

    assert missing_minute_quote_files(tmp_path, "MO", [symbol], "2026-01-05", min_rows=3) == []
    assert missing_minute_quote_files(tmp_path, "MO", [symbol], "2026-01-05", min_rows=4) == [symbol]
    assert missing_minute_quote_files(tmp_path, "MO", ["CFFEX.MO2601-P-7000"], "2026-01-05") == [
        "CFFEX.MO2601-P-7000"
    ]


def test_build_snapshot_and_skip_complete(tmp_path):
    trade_date = "2026-01-05"
    symbols = [
        "CFFEX.MO2601-C-7000",
        "CFFEX.MO2602-C-7000",
        "CFFEX.MO2603-C-7000",
        "CFFEX.MO2606-C-7000",
    ]
    contracts = [
        _contract(symbols[0], "2026-01-16"),
        _contract(symbols[1], "2026-02-20"),
        _contract(symbols[2], "2026-03-20"),
        _contract(symbols[3], "2026-06-19"),
    ]
    for symbol in symbols:
        path = minute_quote_path(tmp_path, "MO", symbol, trade_date)
        path.parent.mkdir(parents=True)
        _minute_frame(symbol, trade_date).to_parquet(path, index=False)

    snapshot = build_four_term_snapshot(tmp_path, "MO", contracts, trade_date)
    assert len(snapshot) == 12
    assert set(snapshot["term_role"]) == {"current_month", "next_month", "current_quarter", "next_quarter"}
    assert snapshot[["symbol", "timestamp"]].duplicated().sum() == 0

    output = four_term_snapshot_path(tmp_path, "MO", trade_date)
    save_four_term_snapshot(snapshot, output)
    assert should_skip_four_term_snapshot(output, symbols, trade_date, min_minutes=3)

    duplicated = pd.concat([snapshot, snapshot.head(1)], ignore_index=True)
    save_four_term_snapshot(duplicated, output)
    assert not should_skip_four_term_snapshot(output, symbols, trade_date, min_minutes=3)
