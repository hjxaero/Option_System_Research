from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pandas as pd

from option_platform.data.pricing import MarkPrice, choose_mark_price


@dataclass(frozen=True)
class CleanOptionQuote:
    mark_price: float | None
    price_source: str
    quote_quality: str
    iv_quality: str
    intrinsic_value: float | None


def intrinsic_value(forward_price: float, strike_price: float, option_type: str) -> float:
    if option_type == "call":
        return max(forward_price - strike_price, 0.0)
    if option_type == "put":
        return max(strike_price - forward_price, 0.0)
    raise ValueError(f"Unsupported option_type: {option_type}")


def _positive(value: object) -> bool:
    try:
        return value is not None and isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def classify_quote_quality(
    *,
    bid_price1: float | None,
    ask_price1: float | None,
    quote_age_ms: float | None = None,
    max_quote_age_ms: int = 60_000,
    spread_bps: float | None = None,
    max_normal_spread_bps: float = 500.0,
) -> str:
    if quote_age_ms is None or pd.isna(quote_age_ms):
        return "missing"
    if quote_age_ms > max_quote_age_ms:
        return "stale_quote"
    if not _positive(bid_price1) or not _positive(ask_price1):
        return "invalid_bid_ask"
    if float(ask_price1) < float(bid_price1):
        return "crossed_market"
    if spread_bps is not None and not pd.isna(spread_bps) and float(spread_bps) > max_normal_spread_bps:
        return "wide_spread"
    return "ok"


def iv_quality_from_mark(mark: MarkPrice, quote_quality: str) -> str:
    if mark.price is None or mark.source == "none":
        return "no_price"
    if quote_quality in {"stale_quote", "invalid_bid_ask", "crossed_market", "missing"}:
        return quote_quality
    if mark.source == "last_inside_spread":
        return "last_inside_spread"
    if mark.source == "last":
        return "last_fallback"
    if quote_quality == "wide_spread":
        return "wide_spread"
    return "ok"


def clean_option_quote(
    *,
    bid_price1: float | None,
    ask_price1: float | None,
    bid_volume1: float | None,
    ask_volume1: float | None,
    last_price: float | None,
    quote_age_ms: float | None,
    spread_bps: float | None,
    forward_price: float,
    strike_price: float,
    option_type: str,
    max_quote_age_ms: int = 60_000,
    max_normal_spread_bps: float = 500.0,
    price_tick: float = 0.2,
) -> CleanOptionQuote:
    quote_quality = classify_quote_quality(
        bid_price1=bid_price1,
        ask_price1=ask_price1,
        quote_age_ms=quote_age_ms,
        max_quote_age_ms=max_quote_age_ms,
        spread_bps=spread_bps,
        max_normal_spread_bps=max_normal_spread_bps,
    )
    mark = choose_mark_price(
        bid_price1=bid_price1,
        ask_price1=ask_price1,
        bid_volume1=bid_volume1,
        ask_volume1=ask_volume1,
        last_price=last_price,
        max_spread_bps=max_normal_spread_bps,
    )
    iv_quality = iv_quality_from_mark(mark, quote_quality)

    intrinsic = None
    if _positive(forward_price) and strike_price > 0:
        intrinsic = intrinsic_value(float(forward_price), float(strike_price), option_type)
        if mark.price is not None and mark.price + max(price_tick, 0.0) < intrinsic:
            iv_quality = "below_intrinsic"

    return CleanOptionQuote(
        mark_price=mark.price,
        price_source=mark.source,
        quote_quality=quote_quality,
        iv_quality=iv_quality,
        intrinsic_value=intrinsic,
    )


def add_clean_quote_columns(
    frame: pd.DataFrame,
    *,
    forward_col: str = "futures_price",
    strike_col: str = "strike_price",
    option_type_col: str = "option_type",
    max_quote_age_ms: int = 60_000,
    max_normal_spread_bps: float = 500.0,
) -> pd.DataFrame:
    result = frame.copy()
    clean_rows = []
    for _, row in result.iterrows():
        clean = clean_option_quote(
            bid_price1=row.get("bid_price1"),
            ask_price1=row.get("ask_price1"),
            bid_volume1=row.get("bid_volume1"),
            ask_volume1=row.get("ask_volume1"),
            last_price=row.get("last_price"),
            quote_age_ms=row.get("quote_age_ms"),
            spread_bps=row.get("spread_bps"),
            forward_price=row.get(forward_col),
            strike_price=row.get(strike_col),
            option_type=row.get(option_type_col),
            max_quote_age_ms=max_quote_age_ms,
            max_normal_spread_bps=max_normal_spread_bps,
            price_tick=row.get("price_tick", 0.2),
        )
        clean_rows.append(clean)

    clean_frame = pd.DataFrame([row.__dict__ for row in clean_rows], index=result.index)
    for col in clean_frame.columns:
        result[col] = clean_frame[col]
    return result

