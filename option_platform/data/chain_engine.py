from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from option_platform.data.contract_dates import (
    filter_dates_by_first_valid,
    load_first_valid_date_cache,
)
from option_platform.data.contracts import OptionContract
from option_platform.data.live_update import (
    minute_quote_path,
    should_skip_minute_quote_update,
    update_symbol_range_minute_quotes,
)
from option_platform.data.snapshots.four_term import (
    build_four_term_snapshot,
    expected_four_term_symbols,
    four_term_snapshot_path,
    missing_minute_quote_files,
    save_four_term_snapshot,
    should_skip_four_term_snapshot,
)
from option_platform.data.sources.tq import tq_api
from option_platform.data.sources.tq_contracts import query_option_contracts_fast
from option_platform.data.universe import select_four_term_contracts, unique_symbols


def iter_weekday_dates(start: str, end: str) -> list[str]:
    """Iterate weekday calendar dates [start, end] in YYYY-MM-DD (Mon-Fri only)."""
    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    dates: list[str] = []
    current = start_dt
    while current <= end_dt:
        if current.weekday() < 5:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def contract_cache_path(data_root: str | Path, product: str) -> Path:
    return Path(data_root) / "contracts" / product.upper() / "tq_contracts_cache.json"


def load_contract_cache(path: str | Path) -> list[OptionContract]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        OptionContract(
            symbol=item["symbol"],
            name=item.get("name", ""),
            underlying_symbol=item.get("underlying_symbol", ""),
            underlying_product=item.get("underlying_product", ""),
            exchange=item.get("exchange", ""),
            strike_price=float(item.get("strike_price", 0.0)),
            option_type=item.get("option_type", "call"),
            expiry_date=item.get("expiry_date", ""),
            volume_multiple=int(item.get("volume_multiple", 1)),
            price_tick=float(item.get("price_tick", 0.0)),
            expired=bool(item.get("expired", False)),
        )
        for item in payload
    ]


def save_contract_cache(path: str | Path, contracts: Iterable[OptionContract]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for contract in contracts:
        serializable.append(
            {
                "symbol": contract.symbol,
                "name": getattr(contract, "name", ""),
                "underlying_symbol": getattr(contract, "underlying_symbol", ""),
                "underlying_product": getattr(contract, "underlying_product", ""),
                "exchange": getattr(contract, "exchange", ""),
                "strike_price": float(getattr(contract, "strike_price", 0.0)),
                "option_type": getattr(contract, "option_type", ""),
                "expiry_date": getattr(contract, "expiry_date", ""),
                "volume_multiple": int(getattr(contract, "volume_multiple", 1)),
                "price_tick": float(getattr(contract, "price_tick", 0.0)),
                "expired": bool(getattr(contract, "expired", False)),
            }
        )
    output.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
    return output


def load_or_query_contracts(
    *,
    data_root: str | Path,
    product: str,
    refresh: bool = False,
    contract_cache: str | Path | None = None,
) -> list[OptionContract]:
    """Load cached TQ contract list, or query and overwrite cache."""
    cache_file = Path(contract_cache) if contract_cache else contract_cache_path(data_root, product)
    if cache_file.exists() and not refresh:
        return load_contract_cache(cache_file)

    with tq_api() as api:
        contracts = query_option_contracts_fast(api, product)
    save_contract_cache(cache_file, contracts)
    return contracts


def build_four_term_symbol_schedule(
    *,
    contracts: list[object],
    start: str,
    end: str,
    max_contracts: int = 0,
    first_valid_date_cache: str | Path | None = None,
    symbol_filter: set[str] | None = None,
) -> dict[str, list[str]]:
    """Build {symbol -> [trade_dates]} schedule based on four-term selection per date."""
    dates = iter_weekday_dates(start, end)
    first_valid_dates = load_first_valid_date_cache(first_valid_date_cache)
    symbol_dates: dict[str, list[str]] = {}

    for trade_date in dates:
        selected = select_four_term_contracts(
            [c for c in contracts if getattr(c, "expiry_date", "") >= trade_date],
            as_of=trade_date,
        )
        for symbol in unique_symbols(selected):
            symbol_dates.setdefault(symbol, []).append(trade_date)

    symbols = sorted(symbol_dates)
    if symbol_filter:
        symbols = [symbol for symbol in symbols if symbol in symbol_filter]
    if max_contracts > 0:
        symbols = symbols[:max_contracts]

    result: dict[str, list[str]] = {}
    for symbol in symbols:
        filtered_dates = filter_dates_by_first_valid(symbol, sorted(symbol_dates[symbol]), first_valid_dates)
        if filtered_dates:
            result[symbol] = filtered_dates
    return result


@dataclass(frozen=True)
class FourTermMinuteQuoteResult:
    saved_days: int
    skipped_days: int
    failures: list[str]


def download_four_term_minute_quotes(
    *,
    data_root: str | Path,
    product: str,
    schedule: dict[str, list[str]],
    max_quote_age_ms: int = 60_000,
    skip_complete: bool = True,
) -> FourTermMinuteQuoteResult:
    """Download minute quotes for a pre-built (symbol -> dates) schedule.

    Notes
    - This is a **library** entry point, so it runs sequentially and keeps behavior simple.
    - For high throughput / parallel workers, keep using the `scripts/` entry points.
    """
    saved = 0
    skipped = 0
    failures: list[str] = []

    with tq_api() as api:
        for symbol, trade_dates in schedule.items():
            pending = []
            for trade_date in trade_dates:
                output = minute_quote_path(data_root, product, symbol, trade_date)
                if skip_complete and should_skip_minute_quote_update(output):
                    skipped += 1
                    continue
                pending.append(trade_date)
            if not pending:
                continue
            attempt_saved, _attempt_skipped, attempt_failures = update_symbol_range_minute_quotes(
                api=api,
                data_root=data_root,
                product=product,
                symbol=symbol,
                trade_dates=pending,
                max_quote_age_ms=max_quote_age_ms,
                skip_if_complete=False,
            )
            saved += attempt_saved
            failures.extend([f"{symbol} {item}" for item in attempt_failures])

    return FourTermMinuteQuoteResult(saved_days=saved, skipped_days=skipped, failures=failures)


@dataclass(frozen=True)
class FourTermSnapshotBuildResult:
    built: int
    skipped: int
    incomplete: int


def build_four_term_snapshots_for_range(
    *,
    data_root: str | Path,
    product: str,
    contracts: Iterable[object],
    start: str,
    end: str,
    min_quote_rows: int = 200,
    max_quote_age_ms: int = 60_000,
    max_normal_spread_bps: float = 500.0,
    skip_complete: bool = True,
    force: bool = False,
) -> FourTermSnapshotBuildResult:
    dates = iter_weekday_dates(start, end)
    built = 0
    skipped = 0
    incomplete = 0
    product = product.upper()

    for trade_date in dates:
        symbols = expected_four_term_symbols(contracts, trade_date)
        output = four_term_snapshot_path(data_root, product, trade_date)
        missing = missing_minute_quote_files(
            data_root,
            product,
            symbols,
            trade_date,
            min_rows=min_quote_rows,
        )
        if missing:
            incomplete += 1
            continue

        if (
            skip_complete
            and not force
            and should_skip_four_term_snapshot(
                output,
                symbols,
                trade_date,
                min_minutes=min_quote_rows,
            )
        ):
            skipped += 1
            continue

        snapshot = build_four_term_snapshot(
            data_root,
            product,
            contracts,
            trade_date,
            max_quote_age_ms=max_quote_age_ms,
            max_normal_spread_bps=max_normal_spread_bps,
        )
        save_four_term_snapshot(snapshot, output)
        built += 1

    return FourTermSnapshotBuildResult(built=built, skipped=skipped, incomplete=incomplete)

