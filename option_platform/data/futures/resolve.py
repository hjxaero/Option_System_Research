from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from option_platform.data.contracts import OptionContract
from option_platform.data.futures.contract_month import mo_contract_month
from option_platform.data.futures.im_contracts import ImFutureContract, im_contracts_by_month, lookup_im_contract
from option_platform.data.universe import select_four_term_contracts


@dataclass(frozen=True)
class ImDayContract:
    contract_month: str
    symbol: str
    expiry_date: str


def contract_months_from_mo_four_term(
    mo_contracts: Sequence[OptionContract],
    trade_date: str,
) -> list[str]:
    """Unique YYMM codes implied by MO four-term selection on ``trade_date``."""
    four_term = select_four_term_contracts(mo_contracts, trade_date)
    months: list[str] = []
    seen: set[str] = set()
    for item in four_term:
        month = mo_contract_month(item.symbol)
        if month and month not in seen:
            seen.add(month)
            months.append(month)
    return sorted(months)


def resolve_im_contracts_for_trade_date(
    mo_contracts: Sequence[OptionContract],
    im_contracts: Sequence[ImFutureContract],
    trade_date: str,
) -> list[ImDayContract]:
    """Map MO four-term months to paired IM futures for one trading day."""
    by_month = im_contracts_by_month(list(im_contracts))
    result: list[ImDayContract] = []
    for month in contract_months_from_mo_four_term(mo_contracts, trade_date):
        im = lookup_im_contract(by_month, month)
        result.append(
            ImDayContract(
                contract_month=month,
                symbol=im.symbol,
                expiry_date=im.expiry_date,
            )
        )
    return result
