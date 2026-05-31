from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from option_platform.data.contracts import TermRole
from option_platform.data.term_selection import select_four_terms, term_role_map


@dataclass(frozen=True)
class ContractWithTerm:
    contract: object
    term_role: TermRole

    @property
    def symbol(self) -> str:
        return self.contract.symbol

    @property
    def expiry_date(self) -> str:
        return self.contract.expiry_date


def select_four_term_contracts(
    contracts: Sequence[object],
    as_of: str,
) -> list[ContractWithTerm]:
    expiries = [c.expiry_date for c in contracts if getattr(c, "expiry_date", None)]
    selections = select_four_terms(expiries, as_of=as_of)
    roles = term_role_map(selections)
    selected = [
        ContractWithTerm(contract=c, term_role=roles[c.expiry_date])
        for c in contracts
        if getattr(c, "expiry_date", None) in roles
    ]
    return sorted(
        selected,
        key=lambda item: (
            item.expiry_date,
            item.term_role,
            getattr(item.contract, "option_type", ""),
            getattr(item.contract, "strike_price", 0),
            item.symbol,
        ),
    )


def unique_symbols(contracts: Iterable[ContractWithTerm]) -> list[str]:
    seen = set()
    symbols = []
    for item in contracts:
        if item.symbol in seen:
            continue
        seen.add(item.symbol)
        symbols.append(item.symbol)
    return symbols

