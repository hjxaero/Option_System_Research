import math

import pytest

from option_platform.pricing import (
    black76_price,
    black76_price_and_greeks,
    implied_volatility_black76,
)


def test_black76_put_call_parity():
    forward = 105.0
    strike = 100.0
    time_to_expiry = 30 / 252
    risk_free_rate = 0.02
    volatility = 0.25

    call = black76_price(
        right="call",
        forward=forward,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
    )
    put = black76_price(
        right="put",
        forward=forward,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
    )

    discount = math.exp(-risk_free_rate * time_to_expiry)
    assert call - put == pytest.approx(discount * (forward - strike))


def test_black76_greeks_have_expected_signs():
    call = black76_price_and_greeks(
        right="call",
        forward=100,
        strike=100,
        time_to_expiry=0.25,
        risk_free_rate=0.02,
        volatility=0.2,
    )
    put = black76_price_and_greeks(
        right="put",
        forward=100,
        strike=100,
        time_to_expiry=0.25,
        risk_free_rate=0.02,
        volatility=0.2,
    )

    assert call.quality == "ok"
    assert call.price > 0
    assert call.delta > 0
    assert put.delta < 0
    assert call.gamma > 0
    assert call.vega > 0


def test_implied_volatility_black76_recovers_model_volatility():
    price = black76_price(
        right="call",
        forward=100,
        strike=105,
        time_to_expiry=0.2,
        risk_free_rate=0.02,
        volatility=0.32,
    )

    result = implied_volatility_black76(
        right="call",
        forward=100,
        strike=105,
        time_to_expiry=0.2,
        risk_free_rate=0.02,
        market_price=price,
    )

    assert result.quality == "ok"
    assert result.implied_volatility == pytest.approx(0.32, abs=1e-7)
    assert result.iterations > 0


def test_implied_volatility_rejects_below_intrinsic_price():
    result = implied_volatility_black76(
        right="call",
        forward=110,
        strike=100,
        time_to_expiry=0.1,
        risk_free_rate=0.0,
        market_price=5,
    )

    assert result.quality == "below_intrinsic"
    assert result.implied_volatility is None
