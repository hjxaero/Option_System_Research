from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


OptionType = Literal["call", "put"]
TermRole = Literal["current_month", "next_month", "current_quarter", "next_quarter"]
PriceSource = Literal["mid", "micro", "last_inside_spread", "last", "none"]
QuoteQuality = Literal[
    "ok",
    "wide_spread",
    "invalid_bid_ask",
    "crossed_market",
    "stale_quote",
    "missing",
]
IvQuality = Literal[
    "ok",
    "wide_spread",
    "last_inside_spread",
    "last_fallback",
    "stale_quote",
    "no_price",
    "invalid_bid_ask",
    "crossed_market",
    "below_intrinsic",
    "solve_failed",
    "outlier",
    "interpolated",
    "low_liquidity",
]


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    name: str
    underlying_symbol: str
    underlying_product: str
    exchange: str
    strike_price: float
    option_type: OptionType
    expiry_date: str
    volume_multiple: int
    price_tick: float
    expired: bool


@dataclass(frozen=True)
class SnapshotSchema:
    """Canonical minute option-chain snapshot columns."""

    columns: tuple[str, ...] = (
        "timestamp",
        "term_role",
        "underlying_symbol",
        "underlying_price",
        "futures_symbol",
        "futures_price",
        "expiry_date",
        "symbol",
        "option_type",
        "strike_price",
        "mark_price",
        "price_source",
        "last_price",
        "bid_price1",
        "ask_price1",
        "bid_volume1",
        "ask_volume1",
        "mid_price",
        "micro_price",
        "spread",
        "spread_bps",
        "quote_time",
        "quote_age_ms",
        "quote_quality",
        "open_interest",
        "volume",
        "volume_multiple",
        "iv",
        "delta",
        "gamma",
        "theta",
        "vega",
        "iv_method",
        "iv_quality",
        "margin",
    )


@dataclass(frozen=True)
class IvSurfaceSchema:
    columns: tuple[str, ...] = (
        "timestamp",
        "expiry_date",
        "term_role",
        "strike_price",
        "option_type",
        "moneyness",
        "log_moneyness",
        "delta",
        "t_years",
        "raw_iv",
        "smooth_iv",
        "iv_quality",
        "surface_quality",
    )
