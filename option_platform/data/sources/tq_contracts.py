from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

import pandas as pd

from option_platform.data.contracts import OptionContract, OptionType


def extract_product_code(symbol: str) -> str:
    if not symbol:
        return ""
    symbol_part = symbol.split(".")[-1]
    match = re.match(r"^([A-Za-z]+)", symbol_part)
    return match.group(1).upper() if match else ""


def filter_option_symbols(symbols: Iterable[str], product: str) -> list[str]:
    product = product.upper()
    pattern = re.compile(r"[.\-]" + re.escape(product) + r"\d", re.IGNORECASE)
    return sorted([symbol for symbol in symbols if pattern.search(symbol)])


def query_option_contracts_fast(
    api: object,
    product: str,
    legacy_root: str | None = None,
    batch_size: int = 50,
    verbose: bool = True,
) -> list[OptionContract]:
    """Query option contract metadata in batches.

    ``legacy_root`` is deprecated and ignored; kept for CLI compatibility.
    """
    del legacy_root

    symbol_set: set[str] = set()
    for expired in (False, True):
        try:
            option_symbols = api.query_quotes(ins_class="OPTION", expired=expired)
        except TypeError:
            option_symbols = api.query_quotes(ins_class="OPTION")
            symbol_set.update(filter_option_symbols(option_symbols, product))
            break
        symbol_set.update(filter_option_symbols(option_symbols, product))
    filtered_symbols = sorted(symbol_set)
    if verbose:
        print(f"found {len(filtered_symbols)} {product.upper()} option symbols", flush=True)
    contracts: list[object] = []

    for start in range(0, len(filtered_symbols), batch_size):
        batch = filtered_symbols[start : start + batch_size]
        if verbose:
            end = min(start + len(batch), len(filtered_symbols))
            print(f"query_symbol_info {start + 1}-{end}/{len(filtered_symbols)}", flush=True)
        info = api.query_symbol_info(batch)
        for _, row in info.iterrows():
            underlying_symbol = row.get("underlying_symbol", "")
            underlying_product = extract_product_code(underlying_symbol)
            if not underlying_product:
                underlying_product = extract_product_code(row.get("instrument_id", ""))
            if underlying_product != product.upper():
                continue

            expire_dt = row.get("expire_datetime")
            expiry_date = ""
            if pd.notna(expire_dt):
                expiry_date = datetime.fromtimestamp(expire_dt).strftime("%Y-%m-%d")

            option_class = row.get("option_class", "")
            option_type: OptionType = "call" if option_class == "CALL" else "put"
            contracts.append(
                OptionContract(
                    symbol=row.get("instrument_id", ""),
                    name=row.get("instrument_name", ""),
                    underlying_symbol=underlying_symbol,
                    underlying_product=underlying_product,
                    exchange=row.get("exchange_id", ""),
                    strike_price=float(row.get("strike_price", 0.0))
                    if pd.notna(row.get("strike_price"))
                    else 0.0,
                    option_type=option_type,
                    expiry_date=expiry_date,
                    volume_multiple=int(row.get("volume_multiple", 1)),
                    price_tick=float(row.get("price_tick", 0.01)),
                    expired=bool(row.get("expired", False)),
                )
            )

    return contracts
