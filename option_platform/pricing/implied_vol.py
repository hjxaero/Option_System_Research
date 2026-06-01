from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite

from option_platform.core.models import OptionRight, normalize_option_right
from option_platform.pricing.black76 import black76_price


@dataclass(frozen=True)
class ImpliedVolResult:
    implied_volatility: float | None
    quality: str
    method: str = "black76_bisection"
    iterations: int = 0
    pricing_error: float | None = None


def _intrinsic_value(right: OptionRight, forward: float, strike: float, risk_free_rate: float, time_to_expiry: float) -> float:
    discount = exp(-risk_free_rate * time_to_expiry)
    if normalize_option_right(right) == "call":
        return discount * max(forward - strike, 0.0)
    return discount * max(strike - forward, 0.0)


def implied_volatility_black76(
    *,
    right: OptionRight,
    forward: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    market_price: float | None,
    lower: float = 1e-6,
    upper: float = 5.0,
    tolerance: float = 1e-8,
    max_iterations: int = 100,
) -> ImpliedVolResult:
    if market_price is None or not isfinite(float(market_price)) or float(market_price) <= 0:
        return ImpliedVolResult(None, "no_price")
    if not isfinite(float(forward)) or float(forward) <= 0:
        return ImpliedVolResult(None, "invalid_forward")
    if not isfinite(float(strike)) or float(strike) <= 0:
        return ImpliedVolResult(None, "invalid_strike")
    if not isfinite(float(time_to_expiry)) or float(time_to_expiry) <= 0:
        return ImpliedVolResult(None, "zero_time")

    right = normalize_option_right(right)
    market = float(market_price)
    intrinsic = _intrinsic_value(right, float(forward), float(strike), float(risk_free_rate), float(time_to_expiry))
    if market + tolerance < intrinsic:
        return ImpliedVolResult(None, "below_intrinsic")

    low_price = black76_price(
        right=right,
        forward=forward,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=lower,
    )
    high_price = black76_price(
        right=right,
        forward=forward,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=upper,
    )
    if low_price is None or high_price is None:
        return ImpliedVolResult(None, "solve_failed")
    if market < low_price - tolerance:
        return ImpliedVolResult(None, "below_intrinsic")
    if market > high_price + tolerance:
        return ImpliedVolResult(None, "outlier")

    low = lower
    high = upper
    mid = (low + high) / 2.0
    price = None
    for iteration in range(1, max_iterations + 1):
        mid = (low + high) / 2.0
        price = black76_price(
            right=right,
            forward=forward,
            strike=strike,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=mid,
        )
        if price is None:
            return ImpliedVolResult(None, "solve_failed", iterations=iteration)
        error = price - market
        if abs(error) <= tolerance:
            return ImpliedVolResult(mid, "ok", iterations=iteration, pricing_error=error)
        if error > 0:
            high = mid
        else:
            low = mid

    final_error = None if price is None else price - market
    if final_error is not None and abs(final_error) <= tolerance * 10:
        return ImpliedVolResult(mid, "ok", iterations=max_iterations, pricing_error=final_error)
    return ImpliedVolResult(None, "solve_failed", iterations=max_iterations, pricing_error=final_error)
