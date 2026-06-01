from __future__ import annotations

from math import exp, log

import pandas as pd

from option_platform.data.time_to_expiry import calculate_t_years_by_trading_minutes
from option_platform.pricing import black76_price_and_greeks, implied_volatility_black76


def _positive(value: object) -> bool:
    return value is not None and not pd.isna(value) and float(value) > 0


def infer_forwards(
    snapshot: pd.DataFrame,
    risk_free_rate: float,
    *,
    trading_days: list[str] | None = None,
) -> pd.DataFrame:
    rows = []
    for expiry, group in snapshot.groupby("expiry_date"):
        calls = group[group["option_type"] == "call"].set_index("strike_price")
        puts = group[group["option_type"] == "put"].set_index("strike_price")
        common_strikes = sorted(set(calls.index) & set(puts.index))
        timestamp = pd.Timestamp(group["timestamp"].iloc[0])
        t_years = calculate_t_years_by_trading_minutes(
            timestamp,
            expiry,
            trading_days or pd.bdate_range(timestamp.date(), pd.Timestamp(expiry).date()).strftime("%Y-%m-%d"),
        )
        discount = exp(-risk_free_rate * t_years)

        candidates = []
        for strike in common_strikes:
            call_price = calls.loc[strike, "mark_price"]
            put_price = puts.loc[strike, "mark_price"]
            if _positive(call_price) and _positive(put_price):
                candidates.append(float(strike) + (float(call_price) - float(put_price)) / discount)

        if candidates:
            series = pd.Series(candidates, dtype="float64")
            rows.append(
                {
                    "expiry_date": expiry,
                    "forward": float(series.median()),
                    "forward_pairs": int(len(series)),
                    "forward_iqr": float(series.quantile(0.75) - series.quantile(0.25)),
                    "t_years": t_years,
                }
            )
    return pd.DataFrame(rows)


def enrich_snapshot_timestamp(
    snapshot: pd.DataFrame,
    *,
    risk_free_rate: float = 0.02,
    pricing_model: str = "black76",
    trading_days: list[str] | None = None,
) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot.copy()

    result = snapshot.copy()
    forwards = infer_forwards(result, risk_free_rate, trading_days=trading_days)
    if forwards.empty:
        for column in _enriched_columns():
            if column not in result.columns:
                result[column] = pd.NA
        result["iv_method"] = "none"
        result["iv_quality"] = "no_forward"
        result["pricing_model"] = pricing_model
        return result

    forward_by_expiry = forwards.set_index("expiry_date").to_dict("index")
    enriched_rows = []
    for _, row in result.iterrows():
        expiry = row["expiry_date"]
        forward_info = forward_by_expiry.get(expiry)
        if not forward_info:
            enriched_rows.append(_empty_pricing_fields("no_forward", pricing_model))
            continue

        forward = float(forward_info["forward"])
        t_years = float(forward_info["t_years"])
        strike = float(row["strike_price"])
        right = row["option_type"]
        market_price = None if pd.isna(row.get("mark_price")) else float(row.get("mark_price"))

        iv = implied_volatility_black76(
            right=right,
            forward=forward,
            strike=strike,
            time_to_expiry=t_years,
            risk_free_rate=risk_free_rate,
            market_price=market_price,
        )
        greeks = None
        if iv.implied_volatility is not None:
            greeks = black76_price_and_greeks(
                right=right,
                forward=forward,
                strike=strike,
                time_to_expiry=t_years,
                risk_free_rate=risk_free_rate,
                volatility=iv.implied_volatility,
            )

        moneyness = strike / forward if forward > 0 else None
        enriched_rows.append(
            {
                "forward": forward,
                "forward_pairs": int(forward_info["forward_pairs"]),
                "forward_iqr": float(forward_info["forward_iqr"]),
                "t_years": t_years,
                "iv": iv.implied_volatility,
                "delta": None if greeks is None else greeks.delta,
                "gamma": None if greeks is None else greeks.gamma,
                "theta": None if greeks is None else greeks.theta,
                "vega": None if greeks is None else greeks.vega,
                "rho": None if greeks is None else greeks.rho,
                "theoretical_price": None if greeks is None else greeks.price,
                "iv_method": iv.method,
                "iv_quality": iv.quality,
                "pricing_model": pricing_model,
                "pricing_error": iv.pricing_error,
                "moneyness": moneyness,
                "log_moneyness": None if moneyness is None or moneyness <= 0 else log(moneyness),
                "atm_distance": abs(strike - forward),
            }
        )

    enriched = pd.DataFrame(enriched_rows, index=result.index)
    for column in enriched.columns:
        result[column] = enriched[column]
    return result


def enrich_snapshot_frame(
    frame: pd.DataFrame,
    *,
    risk_free_rate: float = 0.02,
    pricing_model: str = "black76",
    trading_days: list[str] | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    frames = [
        enrich_snapshot_timestamp(
            group,
            risk_free_rate=risk_free_rate,
            pricing_model=pricing_model,
            trading_days=trading_days,
        )
        for _, group in frame.groupby("timestamp", sort=True)
    ]
    return pd.concat(frames, ignore_index=True, sort=False)


def _empty_pricing_fields(iv_quality: str, pricing_model: str) -> dict[str, object]:
    return {
        "forward": None,
        "forward_pairs": 0,
        "forward_iqr": None,
        "t_years": None,
        "iv": None,
        "delta": None,
        "gamma": None,
        "theta": None,
        "vega": None,
        "rho": None,
        "theoretical_price": None,
        "iv_method": "none",
        "iv_quality": iv_quality,
        "pricing_model": pricing_model,
        "pricing_error": None,
        "moneyness": None,
        "log_moneyness": None,
        "atm_distance": None,
    }


def _enriched_columns() -> tuple[str, ...]:
    return tuple(_empty_pricing_fields("none", "black76"))
