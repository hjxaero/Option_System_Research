from datetime import datetime

import pytest

from option_platform.core.models import (
    OptionContractRef,
    OptionGreeks,
    OptionQuote,
    UnderlyingQuote,
)
from option_platform.option_chain import build_option_chain


def _contract(contract_id: str, strike: float, right: str) -> OptionContractRef:
    return OptionContractRef(
        contract_id=contract_id,
        underlying_symbol="MO",
        expiration="2026-06-19",
        strike=strike,
        right=right,
        multiplier=100,
    )


def test_core_contract_normalizes_right_and_calculates_intrinsic():
    contract = OptionContractRef(
        contract_id="MO-C-100",
        underlying_symbol="MO",
        expiration="2026-06-19",
        strike=100,
        right="C",
    )

    assert contract.right == "call"
    assert contract.dte("2026-06-01") == 18
    assert contract.intrinsic_value(105) == 5
    assert contract.moneyness(105) == pytest.approx(100 / 105)


def test_build_option_chain_pairs_call_and_put_by_expiration_and_strike():
    underlying = UnderlyingQuote("MO", 105, datetime(2026, 6, 1, 9, 30))
    contracts = [
        _contract("MO-C-100", 100, "call"),
        _contract("MO-P-100", 100, "put"),
        _contract("MO-C-110", 110, "call"),
    ]
    quotes = [
        OptionQuote("MO-C-100", bid=5.0, ask=5.2, volume=10, open_interest=100),
        OptionQuote("MO-P-100", bid=0.8, ask=1.0, volume=5, open_interest=80),
        OptionQuote("MO-C-110", bid=1.0, ask=1.4, volume=1, open_interest=20),
    ]

    chain = build_option_chain(underlying=underlying, contracts=contracts, quotes=quotes)
    row = chain.get_row("2026-06-19", 100)

    assert chain.expirations() == [contracts[0].expiration]
    assert chain.strikes("2026-06-19") == [100, 110]
    assert row is not None
    assert row.call_contract.contract_id == "MO-C-100"
    assert row.put_contract.contract_id == "MO-P-100"
    assert row.call_quote.mid == pytest.approx(5.1)


def test_option_chain_selects_atm_and_filters_by_query_fields():
    underlying = UnderlyingQuote("MO", 105, datetime(2026, 6, 1, 9, 30))
    contracts = [
        _contract("MO-C-100", 100, "call"),
        _contract("MO-C-105", 105, "call"),
        _contract("MO-C-110", 110, "call"),
    ]
    quotes = [
        OptionQuote("MO-C-100", bid=6.0, ask=6.4, volume=3, open_interest=40),
        OptionQuote("MO-C-105", bid=3.0, ask=3.2, volume=20, open_interest=200),
        OptionQuote("MO-C-110", bid=1.0, ask=1.6, volume=30, open_interest=200),
    ]
    greeks = [
        OptionGreeks("MO-C-100", delta=0.75),
        OptionGreeks("MO-C-105", delta=0.52),
        OptionGreeks("MO-C-110", delta=0.25),
    ]

    chain = build_option_chain(
        underlying=underlying,
        contracts=contracts,
        quotes=quotes,
        greeks=greeks,
        as_of="2026-06-01",
    )

    assert chain.get_atm("2026-06-19").strike == 105

    filtered = chain.filter(
        dte=(15, 30),
        right="call",
        delta=(0.4, 0.6),
        min_volume=10,
        min_open_interest=100,
        max_spread_bps=1000,
        moneyness=(0.95, 1.05),
    )

    assert [row.strike for row in filtered] == [105]
