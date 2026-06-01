from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from option_platform.core.models import (
    OptionContractRef,
    OptionGreeks,
    OptionQuote,
    UnderlyingQuote,
    normalize_option_right,
)
from option_platform.option_chain.builder import build_option_chain
from option_platform.option_chain.chain import OptionChain


REQUIRED_SNAPSHOT_COLUMNS = {
    "timestamp",
    "underlying_symbol",
    "symbol",
    "option_type",
    "strike_price",
    "expiry_date",
}


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_datetime(value: object) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).to_pydatetime()


def _positive_int(value: object, default: int = 1) -> int:
    if value is None or pd.isna(value):
        return default
    parsed = int(value)
    return parsed if parsed > 0 else default


def _snapshot_timestamp(frame: pd.DataFrame, timestamp: datetime | str | None) -> pd.Timestamp:
    if timestamp is not None:
        return pd.Timestamp(timestamp)
    values = pd.to_datetime(frame["timestamp"].dropna().unique())
    if len(values) != 1:
        raise ValueError("snapshot frame must contain exactly one timestamp, or pass timestamp explicitly")
    return pd.Timestamp(values[0])


def _underlying_price(row: pd.Series) -> float:
    for column in ("forward", "underlying_price", "futures_price"):
        value = row.get(column)
        if value is not None and not pd.isna(value) and float(value) > 0:
            return float(value)
    raise ValueError("snapshot row does not contain a positive underlying or futures price")


def chain_from_snapshot_frame(
    frame: pd.DataFrame,
    *,
    underlying_symbol: str | None = None,
    timestamp: datetime | str | None = None,
    as_of: date | datetime | str | None = None,
) -> OptionChain:
    """Build an OptionChain from a data-platform snapshot dataframe.

    The adapter expects one timestamp slice. Callers that pass a multi-minute
    frame should filter it first, or pass an explicit timestamp that selects
    the desired slice.
    """
    missing = REQUIRED_SNAPSHOT_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"snapshot frame missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("snapshot frame is empty")

    target_ts = _snapshot_timestamp(frame, timestamp)
    snapshot = frame[pd.to_datetime(frame["timestamp"]) == target_ts].copy()
    if snapshot.empty:
        raise ValueError(f"snapshot frame has no rows for timestamp {target_ts}")

    if underlying_symbol is not None:
        snapshot = snapshot[snapshot["underlying_symbol"] == underlying_symbol].copy()
        if snapshot.empty:
            raise ValueError(f"snapshot frame has no rows for underlying {underlying_symbol}")

    underlying_symbols = sorted(snapshot["underlying_symbol"].dropna().unique())
    if len(underlying_symbols) != 1:
        raise ValueError("snapshot frame must contain exactly one underlying symbol")

    first = snapshot.iloc[0]
    underlying = UnderlyingQuote(
        symbol=str(underlying_symbols[0]),
        price=_underlying_price(first),
        timestamp=target_ts.to_pydatetime(),
    )

    contracts: list[OptionContractRef] = []
    quotes: list[OptionQuote] = []
    greeks: list[OptionGreeks] = []

    for _, row in snapshot.iterrows():
        right = normalize_option_right(row["option_type"])
        contract_id = str(row["symbol"])
        contracts.append(
            OptionContractRef(
                contract_id=contract_id,
                underlying_symbol=underlying.symbol,
                expiration=pd.Timestamp(row["expiry_date"]).date(),
                strike=float(row["strike_price"]),
                right=right,
                multiplier=_positive_int(row.get("volume_multiple", 1)),
                exchange=str(row.get("exchange", "")),
            )
        )
        quotes.append(
            OptionQuote(
                contract_id=contract_id,
                timestamp=target_ts.to_pydatetime(),
                bid=_optional_float(row.get("bid_price1")),
                ask=_optional_float(row.get("ask_price1")),
                last=_optional_float(row.get("last_price")),
                mark=_optional_float(row.get("mark_price")),
                volume=_optional_float(row.get("volume")),
                open_interest=_optional_float(row.get("open_interest")),
                implied_volatility=_optional_float(row.get("iv")),
                quote_quality=str(row.get("quote_quality", "")),
            )
        )
        greeks.append(
            OptionGreeks(
                contract_id=contract_id,
                delta=_optional_float(row.get("delta")),
                gamma=_optional_float(row.get("gamma")),
                theta=_optional_float(row.get("theta")),
                vega=_optional_float(row.get("vega")),
                theoretical_price=_optional_float(row.get("mark_price")),
                model_iv=_optional_float(row.get("iv")),
            )
        )

    return build_option_chain(
        underlying=underlying,
        contracts=contracts,
        quotes=quotes,
        greeks=greeks,
        as_of=as_of or target_ts.date(),
    )
