from option_platform.data.futures.contract_month import (
    im_contract_month,
    im_symbol_for_month,
    mo_contract_month,
)


def test_mo_contract_month_from_option_symbol():
    assert mo_contract_month("CFFEX.MO2601-C-6000") == "2601"
    assert mo_contract_month("CFFEX.MO2506-P-7000") == "2506"


def test_im_contract_month_from_future_symbol():
    assert im_contract_month("CFFEX.IM2601") == "2601"
    assert im_contract_month("CFFEX.IM2509") == "2509"


def test_im_symbol_for_month():
    assert im_symbol_for_month("2601") == "CFFEX.IM2601"
