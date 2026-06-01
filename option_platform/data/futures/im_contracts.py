from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from option_platform.data.futures.contract_month import im_contract_month, im_symbol_for_month
from option_platform.data.futures.layout import im_contracts_cache_path


_IM_SYMBOL_RE = re.compile(r"\.IM(\d{4})$", re.IGNORECASE)


@dataclass(frozen=True)
class ImFutureContract:
    symbol: str
    contract_month: str
    expiry_date: str
    exchange: str
    expired: bool


def filter_im_future_symbols(symbols: list[str]) -> list[str]:
    return sorted(s for s in symbols if _IM_SYMBOL_RE.search(s))


def query_im_futures_fast(
    api: object,
    batch_size: int = 50,
    verbose: bool = True,
) -> list[ImFutureContract]:
    symbol_set: set[str] = set()
    for expired in (False, True):
        try:
            future_symbols = api.query_quotes(ins_class="FUTURE", expired=expired)
        except TypeError:
            future_symbols = api.query_quotes(ins_class="FUTURE")
            symbol_set.update(filter_im_future_symbols(list(future_symbols)))
            break
        symbol_set.update(filter_im_future_symbols(list(future_symbols)))

    filtered = sorted(symbol_set)
    if verbose:
        print(f"found {len(filtered)} IM future symbols", flush=True)

    contracts: list[ImFutureContract] = []
    for start in range(0, len(filtered), batch_size):
        batch = filtered[start : start + batch_size]
        if verbose:
            end = min(start + len(batch), len(filtered))
            print(f"query_symbol_info {start + 1}-{end}/{len(filtered)}", flush=True)
        info = api.query_symbol_info(batch)
        for _, row in info.iterrows():
            symbol = str(row.get("instrument_id", ""))
            month = im_contract_month(symbol)
            if not month:
                continue
            expire_dt = row.get("expire_datetime")
            expiry_date = ""
            if pd.notna(expire_dt):
                expiry_date = datetime.fromtimestamp(expire_dt).strftime("%Y-%m-%d")
            contracts.append(
                ImFutureContract(
                    symbol=symbol,
                    contract_month=month,
                    expiry_date=expiry_date,
                    exchange=str(row.get("exchange_id", "CFFEX")),
                    expired=bool(row.get("expired", False)),
                )
            )
    return contracts


def load_or_query_im_contracts(
    api: object,
    data_root: str | Path,
    refresh: bool = False,
) -> list[ImFutureContract]:
    cache_file = im_contracts_cache_path(data_root)
    if cache_file.exists() and not refresh:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        return [ImFutureContract(**item) for item in payload]

    contracts = query_im_futures_fast(api)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps([asdict(c) for c in contracts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return contracts


def im_contracts_by_month(contracts: list[ImFutureContract]) -> dict[str, ImFutureContract]:
    """Map contract_month -> contract; prefer non-expired when duplicates exist."""
    index: dict[str, ImFutureContract] = {}
    for contract in contracts:
        existing = index.get(contract.contract_month)
        if existing is None or (existing.expired and not contract.expired):
            index[contract.contract_month] = contract
    return index


def lookup_im_contract(
    contracts_by_month: dict[str, ImFutureContract],
    contract_month: str,
) -> ImFutureContract:
    found = contracts_by_month.get(contract_month)
    if found is not None:
        return found
    return ImFutureContract(
        symbol=im_symbol_for_month(contract_month),
        contract_month=contract_month,
        expiry_date="",
        exchange="CFFEX",
        expired=False,
    )
