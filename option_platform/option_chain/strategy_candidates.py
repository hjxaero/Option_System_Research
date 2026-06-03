from __future__ import annotations

from collections.abc import Iterable
import json

import pandas as pd


GREEK_COLUMNS = ("delta", "gamma", "theta", "vega", "rho")
FRONT_TERM_ROLES = ("current_month", "next_month")
CANDIDATE_REPORT_COLUMNS = [
    "product",
    "trade_date",
    "quality_scope",
    "scope",
    "structure_type",
    "term_role",
    "candidate_expiry_phase",
    "timestamp_count",
    "candidate_count",
    "ok_count",
    "conditional_count",
    "rejected_count",
    "ok_ratio",
    "conditional_ratio",
    "rejected_ratio",
    "median_net_mark",
    "median_abs_net_delta",
    "median_net_vega",
    "p95_abs_net_delta",
]
NET_DELTA_LIMITS = {
    "atm_straddle": (0.10, 0.20),
    "25d_strangle": (0.15, 0.30),
    "atm_call_calendar": (0.15, 0.30),
    "atm_put_calendar": (0.15, 0.30),
}
NORMAL_EXPIRY_PHASES = {"normal"}
NEAR_EXPIRY_PHASES = {"last_3_trading_days", "final_trading_day"}
PRIMARY_TERM_ROLES = {"current_month", "next_month", "current_next_month"}


def _has_bucket(row: pd.Series, bucket_id: str) -> bool:
    bucket_ids = row.get("bucket_ids")
    if bucket_ids is None or pd.isna(bucket_ids):
        return False
    return bucket_id in str(bucket_ids).split(";")


def _bucket_frame(frame: pd.DataFrame, bucket_id: str) -> pd.DataFrame:
    if "bucket_ids" not in frame.columns:
        return pd.DataFrame(columns=frame.columns)
    mask = frame.apply(lambda row: _has_bucket(row, bucket_id), axis=1)
    return frame[mask].copy()


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _quality(
    rows: Iterable[pd.Series],
    *,
    structure_type: str,
    net_delta: float | None,
) -> tuple[str, str]:
    tiers = []
    conditional_reasons = []
    for row in rows:
        if row.get("strategy_candidate_ok") != True:  # noqa: E712
            return "rejected", "leg_not_strategy_ok"
        tiers.append(str(row.get("strategy_candidate_tier", "")))
        for column in ("iv_quality", "greeks_quality"):
            if str(row.get(column, "")) != "ok":
                return "rejected", f"leg_{column}_{row.get(column)}"
        forward_quality = str(row.get("forward_consistency_quality", ""))
        if forward_quality in {"basis_warning", "basis_severe", "both_degraded", "no_forward"}:
            return "rejected", f"forward_{forward_quality}"
        if "bucket_quality" in row.index:
            bucket_quality = str(row.get("bucket_quality", ""))
            if bucket_quality == "bad":
                return "rejected", "leg_bucket_bad"
            if bucket_quality == "loose":
                conditional_reasons.append("contains_loose_bucket")
    if "conditional" in tiers:
        conditional_reasons.append("contains_conditional_leg")

    limits = NET_DELTA_LIMITS.get(structure_type)
    if limits is not None and net_delta is not None:
        ok_limit, conditional_limit = limits
        abs_net_delta = abs(float(net_delta))
        if abs_net_delta > conditional_limit:
            return "rejected", f"net_delta_bad>{conditional_limit:.2f}"
        if abs_net_delta > ok_limit:
            conditional_reasons.append(f"net_delta_loose>{ok_limit:.2f}")

    if conditional_reasons:
        return "conditional", ";".join(dict.fromkeys(conditional_reasons))
    return "ok", "all_legs_ok"


def _signed_sum(rows: list[pd.Series], quantities: list[int], column: str) -> float | None:
    total = 0.0
    seen = False
    for row, quantity in zip(rows, quantities):
        value = _optional_float(row.get(column))
        if value is None:
            continue
        seen = True
        total += quantity * value
    return total if seen else None


def _candidate_expiry_phase(rows: list[pd.Series]) -> tuple[str | None, int | None]:
    phases = []
    for row in rows:
        phase = row.get("expiry_phase")
        rank = row.get("expiry_phase_rank")
        if phase is None or pd.isna(phase):
            continue
        rank_value = -1 if rank is None or pd.isna(rank) else int(rank)
        phases.append((rank_value, str(phase)))
    if not phases:
        return None, None
    rank, phase = max(phases, key=lambda item: item[0])
    return phase, rank


def _candidate_pool(
    *,
    quality: str,
    term_role: str,
    expiry_phase: str | None,
) -> tuple[str, str]:
    if quality == "rejected":
        return "excluded_pool", "candidate_quality_rejected"
    if expiry_phase in NEAR_EXPIRY_PHASES:
        return "research_pool", f"expiry_phase_{expiry_phase}"
    if term_role not in PRIMARY_TERM_ROLES:
        return "research_pool", f"term_role_{term_role}"
    if quality == "ok" and expiry_phase == "normal":
        return "primary_pool", "normal_front_term_quality_ok"
    if quality == "conditional":
        return "research_pool", "candidate_quality_conditional"
    return "research_pool", f"candidate_quality_{quality or 'unknown'}"


def _leg_payload(row: pd.Series, quantity: int, leg_role: str) -> dict[str, object]:
    return {
        "leg_role": leg_role,
        "quantity": quantity,
        "symbol": row.get("symbol"),
        "option_type": row.get("option_type"),
        "term_role": row.get("term_role"),
        "expiry_date": str(row.get("expiry_date")),
        "strike_price": _optional_float(row.get("strike_price")),
        "mark_price": _optional_float(row.get("mark_price")),
        "iv": _optional_float(row.get("iv")),
        "delta": _optional_float(row.get("delta")),
        "gamma": _optional_float(row.get("gamma")),
        "theta": _optional_float(row.get("theta")),
        "vega": _optional_float(row.get("vega")),
        "rho": _optional_float(row.get("rho")),
        "bucket_ids": row.get("bucket_ids"),
        "bucket_primary": row.get("bucket_primary"),
        "bucket_target_delta": _optional_float(row.get("bucket_target_delta")),
        "bucket_delta_error": _optional_float(row.get("bucket_delta_error")),
        "bucket_quality": row.get("bucket_quality"),
        "bucket_quality_reason": row.get("bucket_quality_reason"),
        "remaining_trading_minutes": _optional_float(row.get("remaining_trading_minutes")),
        "trading_days_to_expiry": _optional_float(row.get("trading_days_to_expiry")),
        "expiry_phase": row.get("expiry_phase"),
    }


def _candidate_row(
    *,
    product: str,
    trade_date: str,
    structure_type: str,
    candidate_id: str,
    rows: list[pd.Series],
    quantities: list[int],
    leg_roles: list[str],
    term_role: str,
) -> dict[str, object]:
    first = rows[0]
    timestamp = pd.Timestamp(first["timestamp"])
    legs = [_leg_payload(row, quantity, leg_role) for row, quantity, leg_role in zip(rows, quantities, leg_roles)]
    net_delta = _signed_sum(rows, quantities, "delta")
    quality, reason = _quality(rows, structure_type=structure_type, net_delta=net_delta)
    expiry_phase, expiry_phase_rank = _candidate_expiry_phase(rows)
    pool, pool_reason = _candidate_pool(quality=quality, term_role=term_role, expiry_phase=expiry_phase)
    result = {
        "candidate_id": candidate_id,
        "product": product.upper(),
        "trade_date": trade_date,
        "timestamp": timestamp,
        "structure_type": structure_type,
        "term_role": term_role,
        "expiry_date": str(first.get("expiry_date")),
        "leg_count": len(rows),
        "net_mark": _signed_sum(rows, quantities, "mark_price"),
        "candidate_quality": quality,
        "candidate_reason": reason,
        "candidate_expiry_phase": expiry_phase,
        "candidate_expiry_phase_rank": expiry_phase_rank,
        "candidate_pool": pool,
        "candidate_pool_reason": pool_reason,
        "legs": legs,
    }
    for greek in GREEK_COLUMNS:
        result[f"net_{greek}"] = net_delta if greek == "delta" else _signed_sum(rows, quantities, greek)
    return result


def _first_by_bucket(frame: pd.DataFrame, bucket_id: str) -> pd.Series | None:
    bucket_rows = _bucket_frame(frame, bucket_id)
    if bucket_rows.empty:
        return None
    return bucket_rows.sort_values(["bucket_selection_rank", "strike_price", "symbol"]).iloc[0]


def _straddle_candidates(frame: pd.DataFrame, *, product: str, trade_date: str) -> list[dict[str, object]]:
    if "straddle_candidate_id" not in frame.columns:
        return []
    rows = []
    if "is_atm_straddle_candidate" not in frame.columns:
        return rows
    straddles = frame[frame["is_atm_straddle_candidate"] == True]  # noqa: E712
    for straddle_id, group in straddles.groupby("straddle_candidate_id", sort=False):
        if pd.isna(straddle_id) or len(group) != 2:
            continue
        calls = group[group["option_type"] == "call"]
        puts = group[group["option_type"] == "put"]
        if len(calls) != 1 or len(puts) != 1:
            continue
        legs = [calls.iloc[0], puts.iloc[0]]
        rows.append(
            _candidate_row(
                product=product,
                trade_date=trade_date,
                structure_type="atm_straddle",
                candidate_id=str(straddle_id),
                rows=legs,
                quantities=[1, 1],
                leg_roles=["long_call", "long_put"],
                term_role=str(legs[0].get("term_role")),
            )
        )
    return rows


def _same_term_candidates(frame: pd.DataFrame, *, product: str, trade_date: str) -> list[dict[str, object]]:
    rows = []
    term_roles = [role for role in FRONT_TERM_ROLES if role in set(frame.get("term_role", pd.Series(dtype=object)).dropna())]
    for term_role in term_roles:
        term = frame[frame["term_role"] == term_role].copy()
        call_25d = _first_by_bucket(term, f"{term_role}_25D_call")
        put_25d = _first_by_bucket(term, f"{term_role}_25D_put")
        if call_25d is not None and put_25d is not None:
            expiry = pd.Timestamp(call_25d["expiry_date"]).strftime("%Y%m%d")
            timestamp = pd.Timestamp(call_25d["timestamp"]).strftime("%Y%m%d%H%M%S")
            legs = [call_25d, put_25d]
            rows.append(
                _candidate_row(
                    product=product,
                    trade_date=trade_date,
                    structure_type="25d_strangle",
                    candidate_id=f"{timestamp}_{term_role}_{expiry}_25D_strangle",
                    rows=legs,
                    quantities=[1, 1],
                    leg_roles=["long_25d_call", "long_25d_put"],
                    term_role=term_role,
                )
            )
            rows.append(
                _candidate_row(
                    product=product,
                    trade_date=trade_date,
                    structure_type="25d_risk_reversal",
                    candidate_id=f"{timestamp}_{term_role}_{expiry}_25D_risk_reversal",
                    rows=legs,
                    quantities=[1, -1],
                    leg_roles=["long_25d_call", "short_25d_put"],
                    term_role=term_role,
                )
            )
    return rows


def _calendar_candidates(frame: pd.DataFrame, *, product: str, trade_date: str) -> list[dict[str, object]]:
    rows = []
    for right in ("call", "put"):
        near = _first_by_bucket(frame, f"current_month_ATM_{right}")
        far = _first_by_bucket(frame, f"next_month_ATM_{right}")
        if near is None or far is None:
            continue
        timestamp = pd.Timestamp(near["timestamp"]).strftime("%Y%m%d%H%M%S")
        rows.append(
            _candidate_row(
                product=product,
                trade_date=trade_date,
                structure_type=f"atm_{right}_calendar",
                candidate_id=f"{timestamp}_current_next_month_ATM_{right}_calendar",
                rows=[far, near],
                quantities=[1, -1],
                leg_roles=[f"long_next_month_{right}", f"short_current_month_{right}"],
                term_role="current_next_month",
            )
        )
    return rows


def build_strategy_candidates(
    frame: pd.DataFrame,
    *,
    product: str,
    trade_date: str,
    structures: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Build strategy-ready candidates from one enriched timestamp slice."""
    if frame.empty:
        return pd.DataFrame()

    selected = set(structures or ("atm_straddle", "25d_strangle", "25d_risk_reversal", "atm_calendar"))
    rows: list[dict[str, object]] = []
    if "atm_straddle" in selected:
        rows.extend(_straddle_candidates(frame, product=product, trade_date=trade_date))
    if "25d_strangle" in selected or "25d_risk_reversal" in selected:
        same_term = _same_term_candidates(frame, product=product, trade_date=trade_date)
        rows.extend(row for row in same_term if row["structure_type"] in selected)
    if {"atm_calendar", "atm_call_calendar", "atm_put_calendar"} & selected:
        calendar = _calendar_candidates(frame, product=product, trade_date=trade_date)
        rows.extend(row for row in calendar if "atm_calendar" in selected or row["structure_type"] in selected)
    return pd.DataFrame(rows)


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else float(numerator) / float(denominator)


def _median(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return None if values.empty else float(values.median())


def _p95_abs(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").abs().dropna()
    return None if values.empty else float(values.quantile(0.95))


def _report_row(
    frame: pd.DataFrame,
    *,
    product: str,
    trade_date: str,
    quality_scope: str,
    scope: str,
    structure_type: str | None = None,
    term_role: str | None = None,
    candidate_expiry_phase: str | None = None,
) -> dict[str, object]:
    total = int(len(frame))
    quality = frame.get("candidate_quality", pd.Series(dtype=object)).fillna("")
    ok_count = int((quality == "ok").sum())
    conditional_count = int((quality == "conditional").sum())
    rejected_count = int((quality == "rejected").sum())
    return {
        "product": product.upper(),
        "trade_date": trade_date,
        "quality_scope": quality_scope,
        "scope": scope,
        "structure_type": structure_type,
        "term_role": term_role,
        "candidate_expiry_phase": candidate_expiry_phase,
        "timestamp_count": int(pd.to_datetime(frame.get("timestamp", pd.Series(dtype=object))).dropna().nunique()),
        "candidate_count": total,
        "ok_count": ok_count,
        "conditional_count": conditional_count,
        "rejected_count": rejected_count,
        "ok_ratio": _ratio(ok_count, total),
        "conditional_ratio": _ratio(conditional_count, total),
        "rejected_ratio": _ratio(rejected_count, total),
        "median_net_mark": _median(frame.get("net_mark", pd.Series(dtype=float))),
        "median_abs_net_delta": _median(pd.to_numeric(frame.get("net_delta", pd.Series(dtype=float)), errors="coerce").abs()),
        "median_net_vega": _median(frame.get("net_vega", pd.Series(dtype=float))),
        "p95_abs_net_delta": _p95_abs(frame.get("net_delta", pd.Series(dtype=float))),
    }


def build_strategy_candidate_quality_report(
    candidates: pd.DataFrame,
    *,
    product: str,
    trade_date: str,
) -> pd.DataFrame:
    """Summarize strategy candidate coverage and quality."""
    if candidates.empty:
        return pd.DataFrame(
            [
                _report_row(
                    pd.DataFrame(),
                    product=product,
                    trade_date=trade_date,
                    quality_scope="all_phase",
                    scope="overall",
                )
            ],
            columns=CANDIDATE_REPORT_COLUMNS,
        )

    rows = []
    for quality_scope, scoped in _quality_scope_frames(candidates):
        rows.append(_report_row(scoped, product=product, trade_date=trade_date, quality_scope=quality_scope, scope="overall"))
        for structure_type, group in scoped.groupby("structure_type", sort=True):
            rows.append(
                _report_row(
                    group,
                    product=product,
                    trade_date=trade_date,
                    quality_scope=quality_scope,
                    scope="structure",
                    structure_type=str(structure_type),
                )
            )
        for (structure_type, term_role), group in scoped.groupby(["structure_type", "term_role"], sort=True):
            rows.append(
                _report_row(
                    group,
                    product=product,
                    trade_date=trade_date,
                    quality_scope=quality_scope,
                    scope="structure_term",
                    structure_type=str(structure_type),
                    term_role=str(term_role),
                )
            )
        if "candidate_expiry_phase" in scoped.columns:
            for candidate_expiry_phase, group in scoped.groupby("candidate_expiry_phase", dropna=False, sort=True):
                rows.append(
                    _report_row(
                        group,
                        product=product,
                        trade_date=trade_date,
                        quality_scope=quality_scope,
                        scope="expiry_phase",
                        candidate_expiry_phase=None if pd.isna(candidate_expiry_phase) else str(candidate_expiry_phase),
                    )
                )
    return pd.DataFrame(rows, columns=CANDIDATE_REPORT_COLUMNS)


def _quality_scope_frames(candidates: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    frames = [("all_phase", candidates)]
    if "candidate_expiry_phase" not in candidates.columns:
        return frames
    phase = candidates["candidate_expiry_phase"].fillna("")
    normal = candidates[phase.isin(NORMAL_EXPIRY_PHASES)].copy()
    near_expiry = candidates[phase.isin(NEAR_EXPIRY_PHASES)].copy()
    frames.append(("normal_phase", normal))
    frames.append(("near_expiry_phase", near_expiry))
    return frames


def prepare_strategy_candidates_for_storage(candidates: pd.DataFrame) -> pd.DataFrame:
    """Normalize candidate rows for Parquet sidecar storage."""
    result = candidates.copy()
    if result.empty:
        return result
    if "legs" in result.columns:
        result["legs_json"] = result["legs"].apply(lambda value: json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True))
        result = result.drop(columns=["legs"])
    return result


def _jsonable(value: object) -> object:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
