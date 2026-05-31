from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from option_platform.data.live_update import recent_window
from option_platform.data.trading_minutes import generate_session_minutes
from option_platform.data.universe import select_four_term_contracts, unique_symbols


@dataclass(frozen=True)
class FakeContract:
    symbol: str
    expiry_date: str
    option_type: str
    strike_price: float


def test_recent_window_uses_trade_date_when_end_time_missing_for_other_day():
    start, end = recent_window("2026-05-27", datetime(2026, 5, 28, 10, 0), 5)

    assert start == datetime(2026, 5, 27, 14, 56)
    assert end == datetime(2026, 5, 27, 15, 0)


def test_generate_session_minutes_can_filter_window():
    minutes = generate_session_minutes(
        "2026-05-27",
        start_time=datetime(2026, 5, 27, 9, 58),
        end_time=datetime(2026, 5, 27, 10, 0),
    )

    assert minutes["target_time"].tolist() == [
        pd.Timestamp("2026-05-27 09:58"),
        pd.Timestamp("2026-05-27 09:59"),
        pd.Timestamp("2026-05-27 10:00"),
    ]


def test_select_four_term_contracts_and_unique_symbols():
    contracts = [
        FakeContract("m1c", "2026-03-20", "call", 100),
        FakeContract("m1p", "2026-03-20", "put", 100),
        FakeContract("m2c", "2026-04-17", "call", 100),
        FakeContract("q1c", "2026-06-19", "call", 100),
        FakeContract("q2c", "2026-09-18", "call", 100),
        FakeContract("later", "2026-12-18", "call", 100),
    ]

    selected = select_four_term_contracts(contracts, "2026-03-01")

    assert {item.term_role for item in selected} == {
        "current_month",
        "next_month",
        "current_quarter",
        "next_quarter",
    }
    assert unique_symbols(selected) == ["m1c", "m1p", "m2c", "q1c", "q2c"]

