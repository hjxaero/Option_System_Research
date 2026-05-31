from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from option_platform.data.contracts import IvQuality, PriceSource


@dataclass(frozen=True)
class MarkPrice:
    price: float | None
    source: PriceSource
    quality: IvQuality


def _valid_number(value: object) -> bool:
    try:
        return value is not None and isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def choose_mark_price(
    *,
    bid_price1: float | None,
    ask_price1: float | None,
    bid_volume1: float | None = None,
    ask_volume1: float | None = None,
    last_price: float | None = None,
    max_spread_bps: float = 500.0,
) -> MarkPrice:
    """Choose the IV/Greeks pricing input from market data.

    Preferred source is best bid/ask mid. Last price is only accepted when it
    sits inside a valid spread, or as a deliberately low-quality fallback.
    """
    if _valid_number(bid_price1) and _valid_number(ask_price1):
        bid = float(bid_price1)
        ask = float(ask_price1)
        if ask >= bid:
            mid = (bid + ask) / 2
            spread_bps = (ask - bid) / mid * 10000 if mid > 0 else float("inf")
            if spread_bps <= max_spread_bps:
                if _valid_number(bid_volume1) and _valid_number(ask_volume1):
                    bv = float(bid_volume1)
                    av = float(ask_volume1)
                    if bv > 0 and av > 0:
                        micro = (ask * bv + bid * av) / (bv + av)
                        return MarkPrice(micro, "micro", "ok")
                return MarkPrice(mid, "mid", "ok")

            if _valid_number(last_price) and bid <= float(last_price) <= ask:
                return MarkPrice(float(last_price), "last_inside_spread", "wide_spread")

            return MarkPrice(mid, "mid", "wide_spread")

    if _valid_number(last_price):
        return MarkPrice(float(last_price), "last", "last_fallback")

    return MarkPrice(None, "none", "no_price")
