from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable
import warnings

import pandas as pd

from option_platform.data.cleaning import add_clean_quote_columns
from option_platform.data.contracts import SnapshotSchema
from option_platform.data.live_update import minute_quote_path
from option_platform.data.trading_minutes import generate_session_minutes
from option_platform.data.universe import select_four_term_contracts, unique_symbols


def four_term_snapshot_path(data_root: str | Path, product: str, trade_date: str) -> Path:
    return Path(data_root) / "snapshots" / "four_term" / product.upper() / f"{trade_date}.parquet"


def _contract_rows(contracts: Iterable[object], as_of: str) -> pd.DataFrame:
    selected = select_four_term_contracts(
        [contract for contract in contracts if getattr(contract, "expiry_date", "") >= as_of],
        as_of=as_of,
    )
    rows = []
    for item in selected:
        contract = getattr(item, "contract", item)
        if hasattr(contract, "__dataclass_fields__"):
            row = asdict(contract)
        else:
            row = {
                "symbol": getattr(contract, "symbol", ""),
                "name": getattr(contract, "name", ""),
                "underlying_symbol": getattr(contract, "underlying_symbol", ""),
                "underlying_product": getattr(contract, "underlying_product", ""),
                "exchange": getattr(contract, "exchange", ""),
                "strike_price": getattr(contract, "strike_price", 0.0),
                "option_type": getattr(contract, "option_type", ""),
                "expiry_date": getattr(contract, "expiry_date", ""),
                "volume_multiple": getattr(contract, "volume_multiple", 1),
                "price_tick": getattr(contract, "price_tick", 0.0),
                "expired": getattr(contract, "expired", False),
                "term_role": getattr(contract, "term_role", ""),
            }
        row["term_role"] = getattr(item, "term_role", getattr(contract, "term_role", row.get("term_role", "")))
        rows.append(row)
    return pd.DataFrame(rows)


def expected_four_term_symbols(contracts: Iterable[object], as_of: str) -> list[str]:
    selected = select_four_term_contracts(
        [contract for contract in contracts if getattr(contract, "expiry_date", "") >= as_of],
        as_of=as_of,
    )
    return unique_symbols(selected)


def missing_minute_quote_files(
    data_root: str | Path,
    product: str,
    symbols: list[str],
    trade_date: str,
    min_rows: int = 200,
) -> list[str]:
    missing = []
    for symbol in symbols:
        path = minute_quote_path(data_root, product, symbol, trade_date)
        if not path.exists():
            missing.append(symbol)
            continue
        try:
            frame = pd.read_parquet(path, columns=["target_time"])
        except Exception:
            missing.append(symbol)
            continue
        if len(frame) < min_rows:
            missing.append(symbol)
    return missing


def build_four_term_snapshot(
    data_root: str | Path,
    product: str,
    contracts: Iterable[object],
    trade_date: str,
    *,
    max_quote_age_ms: int = 60_000,
    max_normal_spread_bps: float = 500.0,
) -> pd.DataFrame:
    contract_frame = _contract_rows(contracts, trade_date)
    if contract_frame.empty:
        return pd.DataFrame(columns=SnapshotSchema().columns)

    frames = []
    for symbol in sorted(contract_frame["symbol"].unique()):
        path = minute_quote_path(data_root, product, symbol, trade_date)
        if path.exists():
            frames.append(pd.read_parquet(path))

    if not frames:
        return pd.DataFrame(columns=SnapshotSchema().columns)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, message=".*DataFrame concatenation.*")
        quotes = pd.concat(frames, ignore_index=True, sort=False)
    quotes["timestamp"] = pd.to_datetime(quotes["target_time"])
    snapshot = quotes.merge(
        contract_frame,
        on="symbol",
        how="left",
        suffixes=("", "_contract"),
    )

    snapshot["underlying_price"] = pd.NA
    snapshot["futures_symbol"] = snapshot.get("underlying_symbol", "")
    snapshot["futures_price"] = pd.NA
    snapshot["iv"] = pd.NA
    snapshot["delta"] = pd.NA
    snapshot["gamma"] = pd.NA
    snapshot["theta"] = pd.NA
    snapshot["vega"] = pd.NA
    snapshot["iv_method"] = "none"
    snapshot["margin"] = pd.NA

    snapshot = add_clean_quote_columns(
        snapshot,
        forward_col="last_price",
        strike_col="strike_price",
        option_type_col="option_type",
        max_quote_age_ms=max_quote_age_ms,
        max_normal_spread_bps=max_normal_spread_bps,
    )

    if "spread" not in snapshot.columns:
        snapshot["spread"] = snapshot["ask_price1"] - snapshot["bid_price1"]

    for column in SnapshotSchema().columns:
        if column not in snapshot.columns:
            snapshot[column] = pd.NA

    snapshot = snapshot[list(SnapshotSchema().columns)].copy()
    snapshot = snapshot.sort_values(["timestamp", "expiry_date", "strike_price", "option_type", "symbol"])
    return snapshot.reset_index(drop=True)


def save_four_term_snapshot(frame: pd.DataFrame, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output.with_suffix(output.suffix + ".tmp")
    frame.to_parquet(tmp_path, index=False)
    tmp_path.replace(output)
    return output


def should_skip_four_term_snapshot(
    path: str | Path,
    expected_symbols: list[str],
    trade_date: str,
    min_minutes: int = 200,
) -> bool:
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        return False
    try:
        frame = pd.read_parquet(snapshot_path, columns=["timestamp", "symbol"])
    except Exception:
        return False
    if frame.empty:
        return False

    expected_symbol_set = set(expected_symbols)
    if set(frame["symbol"].dropna().unique()) != expected_symbol_set:
        return False

    expected_min_rows = len(expected_symbol_set) * min_minutes
    if len(frame) < expected_min_rows:
        return False

    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    if frame["timestamp"].dt.strftime("%Y-%m-%d").nunique() != 1:
        return False
    if frame["timestamp"].dt.strftime("%Y-%m-%d").iloc[0] != trade_date:
        return False

    return not frame.duplicated(["symbol", "timestamp"]).any()


def expected_snapshot_minutes(trade_date: str) -> int:
    return len(generate_session_minutes(trade_date))
