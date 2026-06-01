from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Iterable

from option_platform.core.models import (
    OptionChainRow,
    OptionContractRef,
    OptionGreeks,
    OptionQuote,
    UnderlyingQuote,
)
from option_platform.option_chain.chain import OptionChain


def build_option_chain(
    *,
    underlying: UnderlyingQuote,
    contracts: Iterable[OptionContractRef],
    quotes: Iterable[OptionQuote] = (),
    greeks: Iterable[OptionGreeks] = (),
    as_of: date | datetime | str | None = None,
) -> OptionChain:
    """Build a queryable option chain from normalized contracts and quotes."""
    quote_by_id = {quote.contract_id: quote for quote in quotes}
    greeks_by_id = {item.contract_id: item for item in greeks}
    grouped: dict[tuple[date, float], dict[str, object]] = defaultdict(dict)

    for contract in contracts:
        key = (contract.expiration, contract.strike)
        slot = grouped[key]
        if contract.right == "call":
            slot["call_contract"] = contract
            slot["call_quote"] = quote_by_id.get(contract.contract_id)
            slot["call_greeks"] = greeks_by_id.get(contract.contract_id)
        else:
            slot["put_contract"] = contract
            slot["put_quote"] = quote_by_id.get(contract.contract_id)
            slot["put_greeks"] = greeks_by_id.get(contract.contract_id)

    rows = [
        OptionChainRow(
            expiration=expiration,
            strike=strike,
            call_contract=slot.get("call_contract"),  # type: ignore[arg-type]
            put_contract=slot.get("put_contract"),  # type: ignore[arg-type]
            call_quote=slot.get("call_quote"),  # type: ignore[arg-type]
            put_quote=slot.get("put_quote"),  # type: ignore[arg-type]
            call_greeks=slot.get("call_greeks"),  # type: ignore[arg-type]
            put_greeks=slot.get("put_greeks"),  # type: ignore[arg-type]
        )
        for (expiration, strike), slot in grouped.items()
    ]

    return OptionChain(underlying=underlying, rows=rows, as_of=as_of)
