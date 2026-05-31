from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


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
    legacy_root: str | Path = r"E:\Option_Sell_Research",
    batch_size: int = 50,
    verbose: bool = True,
) -> list[object]:
    """Query option contract metadata in batches.

    We reuse the old project's OptionContractInfo dataclass so legacy period
    classification remains compatible, but avoid its slow per-symbol metadata
    loop.
    """
    legacy_root = Path(legacy_root).resolve()
    import sys

    if str(legacy_root) not in sys.path:
        sys.path.insert(0, str(legacy_root))

    from data.data_loader import OptionContractInfo

    option_symbols = api.query_quotes(ins_class="OPTION")
    filtered_symbols = filter_option_symbols(option_symbols, product)
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
            option_type = "call" if option_class == "CALL" else "put"
            contracts.append(
                OptionContractInfo(
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
