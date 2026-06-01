from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, isfinite, log, pi, sqrt

from option_platform.core.models import OptionRight, normalize_option_right


SQRT_TWO = sqrt(2.0)
INV_SQRT_TWO_PI = 1.0 / sqrt(2.0 * pi)


@dataclass(frozen=True)
class Black76Result:
    price: float | None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    model: str = "black76"
    quality: str = "ok"


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / SQRT_TWO))


def _norm_pdf(value: float) -> float:
    return INV_SQRT_TWO_PI * exp(-0.5 * value * value)


def _valid_positive(value: float) -> bool:
    return isfinite(float(value)) and float(value) > 0


def _validate_inputs(
    *,
    forward: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
) -> str:
    if not _valid_positive(forward):
        return "invalid_forward"
    if not _valid_positive(strike):
        return "invalid_strike"
    if not isfinite(float(time_to_expiry)) or float(time_to_expiry) <= 0:
        return "zero_time"
    if not _valid_positive(volatility):
        return "invalid_volatility"
    return "ok"


def _d1_d2(forward: float, strike: float, time_to_expiry: float, volatility: float) -> tuple[float, float]:
    sigma_sqrt_t = volatility * sqrt(time_to_expiry)
    d1 = (log(forward / strike) + 0.5 * volatility * volatility * time_to_expiry) / sigma_sqrt_t
    return d1, d1 - sigma_sqrt_t


def black76_price(
    *,
    right: OptionRight,
    forward: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
) -> float | None:
    result = black76_price_and_greeks(
        right=right,
        forward=forward,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
    )
    return result.price


def black76_price_and_greeks(
    *,
    right: OptionRight,
    forward: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
) -> Black76Result:
    quality = _validate_inputs(
        forward=forward,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=volatility,
    )
    if quality != "ok":
        return Black76Result(price=None, quality=quality)

    right = normalize_option_right(right)
    forward = float(forward)
    strike = float(strike)
    time_to_expiry = float(time_to_expiry)
    risk_free_rate = float(risk_free_rate)
    volatility = float(volatility)

    discount = exp(-risk_free_rate * time_to_expiry)
    d1, d2 = _d1_d2(forward, strike, time_to_expiry, volatility)
    pdf_d1 = _norm_pdf(d1)

    if right == "call":
        price = discount * (forward * _norm_cdf(d1) - strike * _norm_cdf(d2))
        delta = discount * _norm_cdf(d1)
    else:
        price = discount * (strike * _norm_cdf(-d2) - forward * _norm_cdf(-d1))
        delta = -discount * _norm_cdf(-d1)

    gamma = discount * pdf_d1 / (forward * volatility * sqrt(time_to_expiry))
    vega = discount * forward * pdf_d1 * sqrt(time_to_expiry)
    theta = -(discount * forward * pdf_d1 * volatility) / (2.0 * sqrt(time_to_expiry)) + risk_free_rate * price
    rho = -time_to_expiry * price

    return Black76Result(
        price=price,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
    )
