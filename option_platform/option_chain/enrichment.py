from __future__ import annotations

from math import ceil, exp, isfinite, log

import pandas as pd

from option_platform.data.time_to_expiry import calculate_t_years_by_trading_minutes
from option_platform.pricing import black76_price_and_greeks, implied_volatility_black76


def _positive(value: object) -> bool:
    return value is not None and not pd.isna(value) and float(value) > 0


def _value_or_none(value: object) -> object:
    return None if value is None or pd.isna(value) else value


def _contract_multiplier_fields(row: pd.Series) -> dict[str, object]:
    multiplier = row.get("contract_multiplier")
    if not _positive(multiplier):
        multiplier = row.get("volume_multiple")
    if not _positive(multiplier):
        multiplier = 1
    multiplier = int(float(multiplier))
    return {
        "contract_multiplier": multiplier,
        "standard_contract_multiplier": multiplier,
        "adjusted_contract_multiplier": None,
        "multiplier_source": "contract_master" if _positive(row.get("volume_multiple")) else "default",
        "multiplier_effective_date": row.get("timestamp").strftime("%Y-%m-%d")
        if isinstance(row.get("timestamp"), pd.Timestamp)
        else None,
        "contract_adjustment_flag": False,
        "contract_adjustment_reason": None,
        "deliverable_description": None,
    }


def _mark_quality(row: pd.Series) -> str:
    if not _positive(row.get("mark_price")):
        return "no_mark_price"

    quote_quality = str(row.get("quote_quality") or "")
    price_source = str(row.get("price_source") or "")
    if quote_quality == "ok" and price_source in {"mid", "micro"}:
        return "ok"
    if quote_quality == "wide_spread":
        return "wide_spread"
    if quote_quality == "stale_quote":
        return "stale_quote"
    if quote_quality in {"invalid_bid_ask", "crossed_market", "missing"}:
        return quote_quality
    if price_source == "last_inside_spread":
        return "last_inside_spread"
    if price_source == "last":
        return "degraded_last"
    return "degraded"


def _mark_missing_reason(row: pd.Series) -> str | None:
    if _positive(row.get("mark_price")):
        return None

    bid_ok = _positive(row.get("bid_price1"))
    ask_ok = _positive(row.get("ask_price1"))
    last_ok = _positive(row.get("last_price"))
    quote_quality = str(row.get("quote_quality") or "")

    if quote_quality == "stale_quote" and (bid_ok or ask_ok):
        return "stale_one_sided" if bid_ok != ask_ok else "stale_bid_ask"
    if quote_quality in {"invalid_bid_ask", "crossed_market"}:
        return quote_quality
    if not bid_ok and not ask_ok and not last_ok:
        return "missing_bid_ask_last"
    if not bid_ok and not ask_ok:
        return "missing_bid_ask"
    if not bid_ok:
        return "missing_bid"
    if not ask_ok:
        return "missing_ask"
    if not last_ok:
        return "missing_last"
    return "unknown"


def _pricing_quality(row: pd.Series, mark_quality: str) -> str:
    if mark_quality == "ok":
        return "ok"
    if mark_quality in {"wide_spread", "last_inside_spread"}:
        return "wide_spread_pricing"
    if mark_quality == "stale_quote":
        return "stale_pricing"
    if mark_quality == "no_mark_price":
        return "no_mark_price"
    if mark_quality in {"invalid_bid_ask", "crossed_market", "missing"}:
        return "invalid_quote"
    if mark_quality in {"degraded_last", "degraded"}:
        return "degraded_pricing"
    return str(row.get("quote_quality") or "unknown")


def _tradability_quality(row: pd.Series, mark_quality: str) -> str:
    bid_ok = _positive(row.get("bid_price1"))
    ask_ok = _positive(row.get("ask_price1"))
    bid_volume_ok = _positive(row.get("bid_volume1"))
    ask_volume_ok = _positive(row.get("ask_volume1"))
    volume_ok = _positive(row.get("volume"))
    open_interest_ok = _positive(row.get("open_interest"))

    if bid_ok and ask_ok and bid_volume_ok and ask_volume_ok:
        if mark_quality == "ok":
            return "liquid_tight"
        if mark_quality in {"wide_spread", "last_inside_spread"}:
            return "liquid_wide"
        return "thin_but_quoted"
    if bid_ok or ask_ok:
        return "one_sided"
    if volume_ok or open_interest_ok:
        return "historical_interest_not_quoted"
    return "not_quoted"


def _market_phase_fields(row: pd.Series) -> dict[str, object]:
    timestamp = row.get("timestamp")
    current = pd.Timestamp(timestamp).normalize() if not pd.isna(timestamp) else None
    product_launch = pd.Timestamp("2022-07-22")
    expiry = pd.Timestamp(row.get("expiry_date")) if not pd.isna(row.get("expiry_date")) else None
    days_since_product_launch = None
    days_since_contract_listing = None
    market_phase = "unknown"
    contract_listing_phase = "unknown"

    if current is not None:
        days_since_product_launch = int((current - product_launch).days)
        market_phase = "early_listing" if days_since_product_launch < 90 else "normal"
        if expiry is not None:
            # Conservative proxy until exchange listing-date metadata is wired in.
            estimated_listing = max(product_launch, expiry - pd.Timedelta(days=180))
            days_since_contract_listing = max(int((current - estimated_listing).days), 0)
            contract_listing_phase = "new_contract" if days_since_contract_listing < 20 else "seasoned_contract"

    return {
        "market_phase": market_phase,
        "days_since_product_launch": days_since_product_launch,
        "days_since_contract_listing": days_since_contract_listing,
        "contract_listing_phase": contract_listing_phase,
    }


def _row_quality_fields(row: pd.Series) -> dict[str, object]:
    mark_quality = _mark_quality(row)
    return {
        "mark_quality": mark_quality,
        "mark_missing_reason": _mark_missing_reason(row),
        "pricing_quality": _pricing_quality(row, mark_quality),
        "tradability_quality": _tradability_quality(row, mark_quality),
        **_market_phase_fields(row),
    }


def _expiry_timing_fields(t_years: float | None) -> dict[str, object]:
    if t_years is None or pd.isna(t_years):
        return {
            "remaining_trading_minutes": None,
            "trading_days_to_expiry": None,
            "expiry_phase": "unknown",
            "expiry_phase_rank": None,
            "expiry_phase_reason": "missing_time_to_expiry",
        }

    remaining_minutes = max(int(round(float(t_years) * 252 * 240)), 0)
    trading_days = int(ceil(remaining_minutes / 240)) if remaining_minutes > 0 else 0
    if remaining_minutes <= 240:
        phase = "final_trading_day"
        rank = 2
        reason = "remaining_trading_minutes_lte_240"
    elif remaining_minutes <= 3 * 240:
        phase = "last_3_trading_days"
        rank = 1
        reason = "remaining_trading_minutes_lte_720"
    else:
        phase = "normal"
        rank = 0
        reason = "remaining_trading_minutes_gt_720"

    return {
        "remaining_trading_minutes": remaining_minutes,
        "trading_days_to_expiry": trading_days,
        "expiry_phase": phase,
        "expiry_phase_rank": rank,
        "expiry_phase_reason": reason,
    }


def _strategy_candidate_fields(
    *,
    row_quality: dict[str, object],
    greeks_quality: str,
    forward_info: dict[str, object] | None,
    row: pd.Series,
) -> dict[str, object]:
    pricing_quality = str(row_quality.get("pricing_quality") or "")
    tradability_quality = str(row_quality.get("tradability_quality") or "")
    term_role = str(row.get("term_role") or "")
    forward_consistency = "" if forward_info is None else str(forward_info.get("forward_consistency_quality") or "")
    forward_quality = "" if forward_info is None else str(forward_info.get("forward_quality") or "")

    if greeks_quality != "ok":
        return {
            "strategy_candidate_ok": False,
            "strategy_candidate_tier": "excluded",
            "strategy_candidate_reason": f"greeks_{greeks_quality}",
        }
    if forward_quality in {"no_forward", "basis_warning", "basis_severe"} or forward_consistency in {
        "basis_warning",
        "basis_severe",
        "both_degraded",
        "no_forward",
    }:
        return {
            "strategy_candidate_ok": False,
            "strategy_candidate_tier": "excluded",
            "strategy_candidate_reason": f"forward_{forward_consistency or forward_quality}",
        }
    if pricing_quality not in {"ok", "wide_spread_pricing"}:
        return {
            "strategy_candidate_ok": False,
            "strategy_candidate_tier": "excluded",
            "strategy_candidate_reason": f"pricing_{pricing_quality}",
        }
    if tradability_quality not in {"liquid_tight", "liquid_wide"}:
        return {
            "strategy_candidate_ok": False,
            "strategy_candidate_tier": "excluded",
            "strategy_candidate_reason": f"tradability_{tradability_quality}",
        }

    front_term = term_role in {"current_month", "next_month"}
    if front_term and pricing_quality == "ok" and tradability_quality == "liquid_tight":
        return {
            "strategy_candidate_ok": True,
            "strategy_candidate_tier": "standard",
            "strategy_candidate_reason": "front_term_liquid_tight",
        }

    if pricing_quality == "wide_spread_pricing" or tradability_quality == "liquid_wide":
        reason = "front_term_liquid_wide" if front_term else "far_term_liquid_wide"
        return {
            "strategy_candidate_ok": True,
            "strategy_candidate_tier": "conditional",
            "strategy_candidate_reason": reason,
        }

    return {
        "strategy_candidate_ok": True,
        "strategy_candidate_tier": "conditional" if not front_term else "standard",
        "strategy_candidate_reason": "far_term_liquid_tight" if not front_term else "front_term_liquid_tight",
    }


def _bucket_label(term_role: str, name: str, right: str) -> str:
    return f"{term_role}_{name}_{right}"


def _bucket_quality(delta_error: float | None) -> tuple[str | None, str | None]:
    if delta_error is None or pd.isna(delta_error):
        return None, None
    if delta_error <= 0.05:
        return "ok", "delta_error_lte_0.05"
    if delta_error <= 0.10:
        return "loose", "delta_error_lte_0.10"
    return "bad", "delta_error_gt_0.10"


def _append_bucket(
    result: pd.DataFrame,
    index: object,
    bucket_id: str,
    delta_bucket: str,
    rank: int,
    target_delta: float,
    reason: str,
) -> None:
    existing = result.at[index, "bucket_ids"]
    result.at[index, "bucket_ids"] = bucket_id if pd.isna(existing) or not existing else f"{existing};{bucket_id}"
    result.at[index, "bucket_count"] = int(result.at[index, "bucket_count"]) + 1
    if pd.isna(result.at[index, "bucket_primary"]):
        delta = result.at[index, "delta"]
        delta_error = None if delta is None or pd.isna(delta) else abs(float(delta) - float(target_delta))
        quality, quality_reason = _bucket_quality(delta_error)
        result.at[index, "bucket_primary"] = bucket_id
        result.at[index, "delta_bucket"] = delta_bucket
        result.at[index, "bucket_selection_rank"] = rank
        result.at[index, "bucket_selection_reason"] = reason
        result.at[index, "bucket_target_delta"] = float(target_delta)
        result.at[index, "bucket_delta_error"] = delta_error
        result.at[index, "bucket_quality"] = quality
        result.at[index, "bucket_quality_reason"] = quality_reason


def _bucket_candidate_score(frame: pd.DataFrame, target_delta: float) -> pd.Series:
    tier_rank = frame["strategy_candidate_tier"].map({"standard": 0, "conditional": 1}).fillna(9)
    return (frame["delta"].astype(float) - target_delta).abs() + tier_rank


def _resolved_forward(group: pd.DataFrame) -> float | None:
    for column in ("resolved_forward", "forward", "futures_forward", "synthetic_forward", "underlying_price", "futures_price"):
        if column not in group.columns:
            continue
        values = pd.to_numeric(group[column], errors="coerce").dropna()
        values = values[values > 0]
        if not values.empty:
            return float(values.iloc[0])
    return None


def _atm_strike_pair(eligible: pd.DataFrame, forward: float | None) -> tuple[object, object] | None:
    calls = eligible[eligible["option_type"] == "call"]
    puts = eligible[eligible["option_type"] == "put"]
    common_strikes = sorted(set(calls["strike_price"].astype(float)) & set(puts["strike_price"].astype(float)))
    if not common_strikes:
        return None

    if forward is not None:
        strike = min(common_strikes, key=lambda value: abs(float(value) - forward))
    else:
        strike = min(
            common_strikes,
            key=lambda value: (
                abs(float(calls[calls["strike_price"].astype(float) == float(value)]["delta"].iloc[0]) - 0.50)
                + abs(float(puts[puts["strike_price"].astype(float) == float(value)]["delta"].iloc[0]) + 0.50)
            ),
        )

    call_index = calls[calls["strike_price"].astype(float) == float(strike)].index[0]
    put_index = puts[puts["strike_price"].astype(float) == float(strike)].index[0]
    return call_index, put_index


BUCKET_MAPPING_COLUMNS = [
    "bucket_ids",
    "bucket_primary",
    "bucket_count",
    "delta_bucket",
    "bucket_selection_rank",
    "bucket_selection_reason",
    "bucket_target_delta",
    "bucket_delta_error",
    "bucket_quality",
    "bucket_quality_reason",
    "is_atm_straddle_candidate",
    "straddle_candidate_id",
]


def _assign_bucket_mapping(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in BUCKET_MAPPING_COLUMNS:
        result[column] = False if column == "is_atm_straddle_candidate" else 0 if column == "bucket_count" else pd.NA

    if result.empty or "delta" not in result.columns:
        return result

    bucket_specs = (
        ("50D", "call", 0.50, "50D_call"),
        ("50D", "put", -0.50, "50D_put"),
        ("25D", "call", 0.25, "25D_call"),
        ("25D", "put", -0.25, "25D_put"),
    )

    for expiry, expiry_group in result.groupby("expiry_date", sort=False):
        term_role = str(expiry_group["term_role"].dropna().iloc[0]) if expiry_group["term_role"].notna().any() else "term"
        eligible = expiry_group[
            (expiry_group["strategy_candidate_ok"] == True)  # noqa: E712
            & (expiry_group["greeks_quality"] == "ok")
            & expiry_group["delta"].notna()
        ]
        if eligible.empty:
            continue

        for name, right, target_delta, delta_bucket in bucket_specs:
            side = eligible[eligible["option_type"] == right].copy()
            if side.empty:
                continue
            selected_index = _bucket_candidate_score(side, target_delta).idxmin()
            bucket_id = _bucket_label(term_role, name, right)
            _append_bucket(result, selected_index, bucket_id, delta_bucket, 1, target_delta, "delta_closest")

        atm_pair = _atm_strike_pair(eligible, _resolved_forward(expiry_group))
        if atm_pair is not None:
            call_index, put_index = atm_pair
            _append_bucket(result, call_index, _bucket_label(term_role, "ATM", "call"), "ATM_call", 1, 0.50, "forward_nearest_common_strike")
            _append_bucket(result, put_index, _bucket_label(term_role, "ATM", "put"), "ATM_put", 1, -0.50, "forward_nearest_common_strike")
            strike = float(result.loc[call_index, "strike_price"])
            timestamp = pd.Timestamp(result.loc[call_index, "timestamp"]).strftime("%Y%m%d%H%M%S")
            straddle_id = f"{timestamp}_{term_role}_{pd.Timestamp(expiry).strftime('%Y%m%d')}_{strike:g}_ATM_straddle"
            for index in (call_index, put_index):
                result.at[index, "is_atm_straddle_candidate"] = True
                result.at[index, "straddle_candidate_id"] = straddle_id

    return result


def recompute_bucket_mapping(frame: pd.DataFrame) -> pd.DataFrame:
    """Recompute only bucket-mapping fields for an enriched snapshot frame.

    This is intentionally separated from IV/Greeks enrichment so bucket,
    straddle, and strategy-selection rule changes can be replayed quickly
    without repricing the option chain.
    """
    if frame.empty:
        return frame.copy()
    if "timestamp" not in frame.columns:
        return _assign_bucket_mapping(frame)

    original_columns = list(frame.columns)
    frames = [_assign_bucket_mapping(group) for _, group in frame.groupby("timestamp", sort=True)]
    result = pd.concat(frames, ignore_index=True, sort=False)
    for column in original_columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result[list(dict.fromkeys([*original_columns, *BUCKET_MAPPING_COLUMNS]))]


def _greeks_quality(
    *,
    iv_value: float | None,
    iv_quality: str,
    t_years: float | None,
    moneyness: float | None,
) -> str:
    if iv_value is None:
        return "no_iv"
    if iv_quality != "ok":
        return f"iv_{iv_quality}"
    if t_years is not None and t_years <= 1 / (252 * 240):
        return "near_expiry_unstable"
    if moneyness is not None:
        if moneyness <= 0.5:
            return "deep_itm_unstable"
        if moneyness >= 1.5:
            return "deep_otm_unstable"
    return "ok"


def _median_abs_deviation(series: pd.Series) -> float | None:
    if series.empty:
        return None
    median = float(series.median())
    return float((series - median).abs().median())


def _basis_quality(forward_basis_bps: float | None) -> str:
    if forward_basis_bps is None or not isfinite(forward_basis_bps):
        return "no_basis"
    value = abs(forward_basis_bps)
    if value <= 5:
        return "ok"
    if value <= 15:
        return "minor_basis"
    if value <= 30:
        return "basis_warning"
    return "basis_severe"


def _synthetic_forward_quality(
    synthetic_forward: float | None,
    pair_count: int,
    synthetic_forward_iqr: float | None,
) -> str:
    if synthetic_forward is None:
        return "no_synthetic"
    if pair_count >= 4 and (
        synthetic_forward_iqr is None
        or synthetic_forward_iqr / synthetic_forward * 10000 <= 30
    ):
        return "ok"
    return "synthetic_degraded"


def _resolve_forward(
    *,
    futures_forward: float | None,
    futures_quote_quality: object,
    synthetic_forward: float | None,
    synthetic_forward_quality: str,
    forward_basis_bps: float | None,
) -> dict[str, object]:
    futures_ok = futures_forward is not None and futures_quote_quality == "ok"
    futures_degraded = futures_forward is not None and not futures_ok
    synthetic_ok = synthetic_forward is not None and synthetic_forward_quality == "ok"
    basis_quality = _basis_quality(forward_basis_bps)

    if futures_ok and synthetic_ok:
        forward_quality = "ok" if basis_quality in {"ok", "minor_basis"} else basis_quality
        return {
            "forward": futures_forward,
            "resolved_forward": futures_forward,
            "forward_source": "futures",
            "forward_quality": forward_quality,
            "forward_consistency_quality": basis_quality,
            "forward_resolver_reason": "futures_and_synthetic_ok",
        }

    if futures_ok:
        return {
            "forward": futures_forward,
            "resolved_forward": futures_forward,
            "forward_source": "futures",
            "forward_quality": "ok",
            "forward_consistency_quality": "synthetic_degraded",
            "forward_resolver_reason": "futures_ok_synthetic_degraded",
        }

    if synthetic_ok:
        return {
            "forward": synthetic_forward,
            "resolved_forward": synthetic_forward,
            "forward_source": "synthetic_parity",
            "forward_quality": "synthetic_ok",
            "forward_consistency_quality": "futures_degraded",
            "forward_resolver_reason": "synthetic_ok_futures_degraded",
        }

    if futures_degraded:
        return {
            "forward": None,
            "resolved_forward": None,
            "forward_source": "none",
            "forward_quality": "no_forward",
            "forward_consistency_quality": "both_degraded",
            "forward_resolver_reason": "futures_and_synthetic_degraded",
        }

    if synthetic_forward is not None:
        return {
            "forward": synthetic_forward,
            "resolved_forward": synthetic_forward,
            "forward_source": "synthetic_parity",
            "forward_quality": "synthetic_degraded",
            "forward_consistency_quality": "futures_degraded",
            "forward_resolver_reason": "synthetic_degraded_no_futures",
        }

    return {
        "forward": None,
        "resolved_forward": None,
        "forward_source": "none",
        "forward_quality": "no_forward",
        "forward_consistency_quality": "no_forward",
        "forward_resolver_reason": "no_forward_inputs",
    }


def _trading_days_covering_expiry(
    current_time: pd.Timestamp,
    expiry: object,
    trading_days: list[str] | None,
) -> list[str]:
    expiry_ts = pd.Timestamp(expiry)
    fallback = pd.bdate_range(current_time.date(), expiry_ts.date()).strftime("%Y-%m-%d").tolist()
    if not trading_days:
        return fallback

    days = {str(day)[:10] for day in trading_days}
    days.update(fallback)
    return sorted(days)


def infer_forwards(
    snapshot: pd.DataFrame,
    risk_free_rate: float,
    *,
    trading_days: list[str] | None = None,
    futures_frame: pd.DataFrame | None = None,
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
            _trading_days_covering_expiry(timestamp, expiry, trading_days),
        )
        discount = exp(-risk_free_rate * t_years)

        candidates = []
        for strike in common_strikes:
            call_price = calls.loc[strike, "mark_price"]
            put_price = puts.loc[strike, "mark_price"]
            if _positive(call_price) and _positive(put_price):
                candidates.append(float(strike) + (float(call_price) - float(put_price)) / discount)

        synthetic_forward = None
        synthetic_forward_iqr = None
        synthetic_forward_mad = None
        if candidates:
            series = pd.Series(candidates, dtype="float64")
            synthetic_forward = float(series.median())
            synthetic_forward_iqr = float(series.quantile(0.75) - series.quantile(0.25))
            synthetic_forward_mad = _median_abs_deviation(series)

        futures = _select_futures_forward(futures_frame, timestamp, expiry)
        futures_forward = futures["futures_forward"]
        forward_basis_error = None
        forward_basis_abs = None
        forward_basis_bps = None
        if futures_forward is not None and synthetic_forward is not None:
            forward_basis_error = synthetic_forward - futures_forward
            forward_basis_abs = abs(forward_basis_error)
            forward_basis_bps = forward_basis_error / futures_forward * 10000

        synthetic_quality = _synthetic_forward_quality(
            synthetic_forward,
            len(candidates),
            synthetic_forward_iqr,
        )
        resolved = _resolve_forward(
            futures_forward=futures_forward,
            futures_quote_quality=futures["futures_quote_quality"],
            synthetic_forward=synthetic_forward,
            synthetic_forward_quality=synthetic_quality,
            forward_basis_bps=forward_basis_bps,
        )

        rows.append(
            {
                "expiry_date": expiry,
                "forward": resolved["forward"],
                "resolved_forward": resolved["resolved_forward"],
                "forward_source": resolved["forward_source"],
                "forward_quality": resolved["forward_quality"],
                "forward_consistency_quality": resolved["forward_consistency_quality"],
                "forward_resolver_reason": resolved["forward_resolver_reason"],
                "futures_symbol": futures["futures_symbol"],
                "futures_forward": futures_forward,
                "futures_forward_source_price": futures["futures_forward_source_price"],
                "futures_price": futures_forward,
                "futures_quote_quality": futures["futures_quote_quality"],
                "synthetic_forward": synthetic_forward,
                "synthetic_forward_pairs": int(len(candidates)),
                "synthetic_forward_iqr": synthetic_forward_iqr,
                "synthetic_forward_mad": synthetic_forward_mad,
                "synthetic_forward_quality": synthetic_quality,
                "parity_forward": synthetic_forward,
                "parity_forward_pairs": int(len(candidates)),
                "parity_forward_iqr": synthetic_forward_iqr,
                "forward_pairs": int(len(candidates)),
                "forward_iqr": synthetic_forward_iqr,
                "forward_basis_error": forward_basis_error,
                "forward_basis_abs": forward_basis_abs,
                "forward_basis_bps": forward_basis_bps,
                "t_years": t_years,
            }
        )
    return pd.DataFrame(rows)


def _select_futures_forward(
    futures_frame: pd.DataFrame | None,
    timestamp: pd.Timestamp,
    expiry_date: object,
) -> dict[str, object]:
    result = {
        "futures_symbol": None,
        "futures_forward": None,
        "futures_forward_source_price": None,
        "futures_quote_quality": None,
    }
    if futures_frame is None or futures_frame.empty:
        return result

    frame = futures_frame
    time_col = "target_time" if "target_time" in frame.columns else "timestamp"
    subset = frame[
        (pd.to_datetime(frame[time_col]) == timestamp)
        & (frame["expiry_date"].astype(str) == str(expiry_date))
    ]
    if subset.empty:
        return result

    row = subset.iloc[0]
    for column in ("micro_price", "mid_price", "last_price"):
        value = row.get(column)
        if _positive(value):
            result["futures_forward"] = float(value)
            result["futures_forward_source_price"] = column
            break
    result["futures_symbol"] = row.get("symbol")
    result["futures_quote_quality"] = row.get("quote_quality")
    return result


def enrich_snapshot_timestamp(
    snapshot: pd.DataFrame,
    *,
    risk_free_rate: float = 0.02,
    pricing_model: str = "black76",
    trading_days: list[str] | None = None,
    futures_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot.copy()

    result = snapshot.copy()
    forwards = infer_forwards(
        result,
        risk_free_rate,
        trading_days=trading_days,
        futures_frame=futures_frame,
    )
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
        if not forward_info or not _positive(forward_info.get("forward")):
            fields = _empty_pricing_fields("no_forward", pricing_model)
            if forward_info:
                fields.update(_forward_diagnostic_fields(forward_info))
                fields["t_years"] = forward_info["t_years"]
                fields.update(_expiry_timing_fields(forward_info["t_years"]))
            fields.update(_contract_multiplier_fields(row))
            row_quality = _row_quality_fields(row)
            fields.update(row_quality)
            fields["greeks_quality"] = "no_iv"
            fields.update(
                _strategy_candidate_fields(
                    row_quality=row_quality,
                    greeks_quality="no_iv",
                    forward_info=forward_info,
                    row=row,
                )
            )
            enriched_rows.append(fields)
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
        greeks_quality = _greeks_quality(
            iv_value=iv.implied_volatility,
            iv_quality=iv.quality,
            t_years=t_years,
            moneyness=moneyness,
        )
        row_quality = _row_quality_fields(row)
        enriched_rows.append(
            {
                **_contract_multiplier_fields(row),
                **row_quality,
                **_forward_diagnostic_fields(forward_info),
                **_strategy_candidate_fields(
                    row_quality=row_quality,
                    greeks_quality=greeks_quality,
                    forward_info=forward_info,
                    row=row,
                ),
                "t_years": t_years,
                **_expiry_timing_fields(t_years),
                "iv": iv.implied_volatility,
                "delta": None if greeks is None else greeks.delta,
                "gamma": None if greeks is None else greeks.gamma,
                "theta": None if greeks is None else greeks.theta,
                "vega": None if greeks is None else greeks.vega,
                "rho": None if greeks is None else greeks.rho,
                "theoretical_price": None if greeks is None else greeks.price,
                "iv_method": iv.method,
                "iv_quality": iv.quality,
                "greeks_quality": greeks_quality,
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
    return _assign_bucket_mapping(result)


def enrich_snapshot_frame(
    frame: pd.DataFrame,
    *,
    risk_free_rate: float = 0.02,
    pricing_model: str = "black76",
    trading_days: list[str] | None = None,
    futures_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    frames = [
        enrich_snapshot_timestamp(
            group,
            risk_free_rate=risk_free_rate,
            pricing_model=pricing_model,
            trading_days=trading_days,
            futures_frame=futures_frame,
        )
        for _, group in frame.groupby("timestamp", sort=True)
    ]
    columns = list(dict.fromkeys(column for item in frames for column in item.columns))
    normalized = [item.dropna(axis=1, how="all") for item in frames]
    result = pd.concat(normalized, ignore_index=True, sort=False)
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result[columns]


def _forward_diagnostic_fields(forward_info: dict[str, object]) -> dict[str, object]:
    return {
        "forward": forward_info["forward"],
        "resolved_forward": forward_info["resolved_forward"],
        "forward_source": forward_info["forward_source"],
        "forward_quality": forward_info["forward_quality"],
        "forward_consistency_quality": forward_info["forward_consistency_quality"],
        "forward_resolver_reason": forward_info["forward_resolver_reason"],
        "futures_symbol": forward_info["futures_symbol"],
        "futures_forward": forward_info["futures_forward"],
        "futures_forward_source_price": forward_info["futures_forward_source_price"],
        "futures_price": forward_info["futures_price"],
        "futures_quote_quality": forward_info["futures_quote_quality"],
        "synthetic_forward": forward_info["synthetic_forward"],
        "synthetic_forward_pairs": int(forward_info["synthetic_forward_pairs"]),
        "synthetic_forward_iqr": forward_info["synthetic_forward_iqr"],
        "synthetic_forward_mad": forward_info["synthetic_forward_mad"],
        "synthetic_forward_quality": forward_info["synthetic_forward_quality"],
        "parity_forward": forward_info["parity_forward"],
        "parity_forward_pairs": int(forward_info["parity_forward_pairs"]),
        "parity_forward_iqr": forward_info["parity_forward_iqr"],
        "forward_pairs": int(forward_info["forward_pairs"]),
        "forward_iqr": forward_info["forward_iqr"],
        "forward_basis_error": forward_info["forward_basis_error"],
        "forward_basis_abs": forward_info["forward_basis_abs"],
        "forward_basis_bps": forward_info["forward_basis_bps"],
    }


def _empty_pricing_fields(iv_quality: str, pricing_model: str) -> dict[str, object]:
    return {
        "forward": None,
        "resolved_forward": None,
        "forward_source": None,
        "forward_quality": None,
        "forward_consistency_quality": None,
        "forward_resolver_reason": None,
        "futures_symbol": None,
        "futures_forward": None,
        "futures_forward_source_price": None,
        "futures_price": None,
        "futures_quote_quality": None,
        "synthetic_forward": None,
        "synthetic_forward_pairs": 0,
        "synthetic_forward_iqr": None,
        "synthetic_forward_mad": None,
        "synthetic_forward_quality": None,
        "parity_forward": None,
        "parity_forward_pairs": 0,
        "parity_forward_iqr": None,
        "forward_pairs": 0,
        "forward_iqr": None,
        "forward_basis_error": None,
        "forward_basis_abs": None,
        "forward_basis_bps": None,
        "t_years": None,
        "remaining_trading_minutes": None,
        "trading_days_to_expiry": None,
        "expiry_phase": None,
        "expiry_phase_rank": None,
        "expiry_phase_reason": None,
        "contract_multiplier": None,
        "standard_contract_multiplier": None,
        "adjusted_contract_multiplier": None,
        "multiplier_source": None,
        "multiplier_effective_date": None,
        "contract_adjustment_flag": None,
        "contract_adjustment_reason": None,
        "deliverable_description": None,
        "iv": None,
        "delta": None,
        "gamma": None,
        "theta": None,
        "vega": None,
        "rho": None,
        "theoretical_price": None,
        "iv_method": "none",
        "iv_quality": iv_quality,
        "mark_quality": None,
        "mark_missing_reason": None,
        "pricing_quality": None,
        "tradability_quality": None,
        "market_phase": None,
        "days_since_product_launch": None,
        "days_since_contract_listing": None,
        "contract_listing_phase": None,
        "greeks_quality": None,
        "strategy_candidate_ok": None,
        "strategy_candidate_tier": None,
        "strategy_candidate_reason": None,
        "bucket_ids": None,
        "bucket_primary": None,
        "bucket_count": 0,
        "delta_bucket": None,
        "bucket_selection_rank": None,
        "bucket_selection_reason": None,
        "bucket_target_delta": None,
        "bucket_delta_error": None,
        "bucket_quality": None,
        "bucket_quality_reason": None,
        "is_atm_straddle_candidate": False,
        "straddle_candidate_id": None,
        "pricing_model": pricing_model,
        "pricing_error": None,
        "moneyness": None,
        "log_moneyness": None,
        "atm_distance": None,
    }


def _enriched_columns() -> tuple[str, ...]:
    return tuple(_empty_pricing_fields("none", "black76"))
