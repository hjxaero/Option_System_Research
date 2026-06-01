from option_platform.data.contracts import OptionContract
from option_platform.data.futures.im_contracts import ImFutureContract
from option_platform.data.futures.resolve import (
    contract_months_from_mo_four_term,
    resolve_im_contracts_for_trade_date,
)


def _mo(symbol: str, expiry: str) -> OptionContract:
    month = symbol.split(".")[1][2:6]
    return OptionContract(
        symbol=symbol,
        name=symbol,
        underlying_symbol=f"CFFEX.IM{month}",
        underlying_product="MO",
        exchange="CFFEX",
        strike_price=6000.0,
        option_type="call",
        expiry_date=expiry,
        volume_multiple=100,
        price_tick=0.2,
        expired=False,
    )


def _im(month: str, expiry: str) -> ImFutureContract:
    return ImFutureContract(
        symbol=f"CFFEX.IM{month}",
        contract_month=month,
        expiry_date=expiry,
        exchange="CFFEX",
        expired=False,
    )


def test_resolve_pairs_mo_yymm_to_im():
    mo = [
        _mo("CFFEX.MO2506-C-6000", "2025-06-20"),
        _mo("CFFEX.MO2506-P-6100", "2025-06-20"),
        _mo("CFFEX.MO2507-C-6000", "2025-07-18"),
        _mo("CFFEX.MO2509-C-6000", "2025-09-19"),
        _mo("CFFEX.MO2512-C-6000", "2025-12-19"),
    ]
    im = [
        _im("2506", "2025-06-20"),
        _im("2507", "2025-07-18"),
        _im("2509", "2025-09-19"),
        _im("2512", "2025-12-19"),
    ]
    resolved = resolve_im_contracts_for_trade_date(mo, im, "2025-05-27")
    months = [item.contract_month for item in resolved]
    assert "2506" in months
    assert "2507" in months
    assert all(item.symbol == f"CFFEX.IM{item.contract_month}" for item in resolved)


def test_contract_months_from_four_term_unique():
    mo = [
        _mo("CFFEX.MO2506-C-6000", "2025-06-20"),
        _mo("CFFEX.MO2507-C-6000", "2025-07-18"),
        _mo("CFFEX.MO2509-C-6000", "2025-09-19"),
        _mo("CFFEX.MO2512-C-6000", "2025-12-19"),
    ]
    months = contract_months_from_mo_four_term(mo, "2025-05-27")
    assert months == sorted(set(months))
    assert len(months) >= 2
