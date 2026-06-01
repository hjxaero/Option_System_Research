from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ExpiryForwardQuality:
    expiry_date: str
    forward: float | None
    forward_pair_count: int
    forward_iqr: float | None
    ok_iv_count: int
    total_contracts: int
    iv_success_ratio: float


@dataclass(frozen=True)
class OptionChainQualityReport:
    timestamp: str
    underlying: str
    total_contracts: int
    expiries: int
    call_put_pair_coverage: float
    atm_coverage_ratio: float
    valid_quote_ratio: float
    iv_success_ratio: float
    no_price_ratio: float
    wide_spread_ratio: float
    stale_quote_ratio: float
    focus_expiries: int
    focus_total_contracts: int
    focus_iv_success_ratio: float
    focus_no_price_ratio: float
    focus_atm_coverage_ratio: float
    focus_wide_spread_ratio: float
    median_spread_bps: float | None
    atm_iv_gap_median: float | None
    forward_quality_by_expiry: list[ExpiryForwardQuality]
    research_ok: bool
    surface_ok: bool
    backtest_ok: bool
    strategy_scan_ok: bool
    execution_ok: bool
    overall_grade: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["forward_quality_by_expiry"] = [asdict(item) for item in self.forward_quality_by_expiry]
        payload["reasons"] = list(self.reasons)
        return payload


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def _finite_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    parsed = float(value)
    return parsed if isfinite(parsed) else None


def _infer_underlying(frame: pd.DataFrame) -> str:
    if "underlying" in frame.columns:
        values = frame["underlying"].dropna().unique()
        if len(values) == 1:
            return str(values[0])
    if "underlying_symbol" in frame.columns:
        values = frame["underlying_symbol"].dropna().unique()
        if len(values) == 1:
            return str(values[0])
    symbols = frame.get("symbol", pd.Series(dtype=object)).dropna().astype(str)
    if not symbols.empty:
        first = symbols.iloc[0]
        if "." in first:
            first = first.split(".", 1)[1]
        return first.split("-", 1)[0][:2]
    return "unknown"


def _call_put_pair_coverage(frame: pd.DataFrame) -> float:
    grouped = frame.groupby(["expiry_date", "strike_price"])["option_type"].agg(lambda s: set(s.dropna()))
    if grouped.empty:
        return 0.0
    paired = grouped.map(lambda rights: {"call", "put"}.issubset(rights))
    return _ratio(int(paired.sum()), len(grouped))


def _atm_coverage_ratio(frame: pd.DataFrame) -> float:
    if "forward" not in frame.columns:
        return 0.0
    covered = 0
    total = 0
    for _, group in frame.groupby("expiry_date"):
        forward = _finite_float(group["forward"].dropna().iloc[0]) if group["forward"].notna().any() else None
        if forward is None:
            continue
        total += 1
        atm_strike = min(group["strike_price"].dropna().unique(), key=lambda strike: abs(float(strike) - forward))
        atm = group[group["strike_price"] == atm_strike]
        rights = set(atm["option_type"].dropna())
        ok_iv = int((atm.get("raw_iv_quality", "") == "ok").sum())
        if {"call", "put"}.issubset(rights) and ok_iv >= 1:
            covered += 1
    return _ratio(covered, total)


def _atm_iv_gap_median(frame: pd.DataFrame) -> float | None:
    if "forward" not in frame.columns or "raw_iv" not in frame.columns:
        return None
    gaps: list[float] = []
    ok = frame[frame.get("raw_iv_quality", "") == "ok"].copy()
    for _, group in ok.groupby("expiry_date"):
        if group.empty or not group["forward"].notna().any():
            continue
        forward = float(group["forward"].dropna().iloc[0])
        atm_strike = min(group["strike_price"].dropna().unique(), key=lambda strike: abs(float(strike) - forward))
        atm = group[group["strike_price"] == atm_strike]
        calls = atm[atm["option_type"] == "call"]["raw_iv"].dropna()
        puts = atm[atm["option_type"] == "put"]["raw_iv"].dropna()
        if not calls.empty and not puts.empty:
            gaps.append(abs(float(calls.iloc[0]) - float(puts.iloc[0])))
    if not gaps:
        return None
    return float(pd.Series(gaps).median())


def _forward_quality(frame: pd.DataFrame) -> list[ExpiryForwardQuality]:
    result: list[ExpiryForwardQuality] = []
    for expiry, group in frame.groupby("expiry_date"):
        forwards = group.get("forward", pd.Series(dtype=float)).dropna().astype(float)
        forward = float(forwards.iloc[0]) if not forwards.empty else None
        iqr = None
        if "forward" in group.columns and group["forward"].dropna().nunique() > 1:
            q75 = group["forward"].dropna().astype(float).quantile(0.75)
            q25 = group["forward"].dropna().astype(float).quantile(0.25)
            iqr = float(q75 - q25)
        ok_iv_count = int((group.get("raw_iv_quality", "") == "ok").sum())
        total = len(group)
        pair_count = int(group.get("forward_pairs", pd.Series([0])).dropna().iloc[0]) if "forward_pairs" in group else 0
        result.append(
            ExpiryForwardQuality(
                expiry_date=str(expiry),
                forward=forward,
                forward_pair_count=pair_count,
                forward_iqr=iqr,
                ok_iv_count=ok_iv_count,
                total_contracts=total,
                iv_success_ratio=_ratio(ok_iv_count, total),
            )
        )
    return result


def _grade_and_flags(
    *,
    iv_success_ratio: float,
    no_price_ratio: float,
    wide_spread_ratio: float,
    stale_quote_ratio: float,
    atm_coverage_ratio: float,
    call_put_pair_coverage: float,
    median_spread_bps: float | None,
    forward_quality: list[ExpiryForwardQuality],
) -> tuple[str, dict[str, bool], tuple[str, ...]]:
    reasons: list[str] = []
    min_forward_pairs = min((item.forward_pair_count for item in forward_quality), default=0)

    if iv_success_ratio < 0.5:
        reasons.append("iv_success_ratio_below_50pct")
    if no_price_ratio > 0.4:
        reasons.append("no_price_ratio_above_40pct")
    if atm_coverage_ratio < 0.8:
        reasons.append("atm_coverage_below_80pct")
    if min_forward_pairs < 6:
        reasons.append("low_forward_pair_count")
    if wide_spread_ratio > 0.35:
        reasons.append("wide_spread_ratio_above_35pct")
    if stale_quote_ratio > 0.1:
        reasons.append("stale_quote_ratio_above_10pct")

    research_ok = iv_success_ratio >= 0.45 and atm_coverage_ratio >= 0.5
    surface_ok = iv_success_ratio >= 0.6 and atm_coverage_ratio >= 0.75 and min_forward_pairs >= 8
    backtest_ok = iv_success_ratio >= 0.55 and no_price_ratio <= 0.45 and call_put_pair_coverage >= 0.9
    strategy_scan_ok = (
        iv_success_ratio >= 0.7
        and no_price_ratio <= 0.25
        and wide_spread_ratio <= 0.25
        and atm_coverage_ratio >= 0.9
    )
    execution_ok = (
        strategy_scan_ok
        and stale_quote_ratio <= 0.02
        and median_spread_bps is not None
        and median_spread_bps <= 300
    )

    if execution_ok and surface_ok:
        grade = "A"
    elif surface_ok and backtest_ok:
        grade = "B"
    elif research_ok:
        grade = "C"
    else:
        grade = "D"

    return (
        grade,
        {
            "research_ok": research_ok,
            "surface_ok": surface_ok,
            "backtest_ok": backtest_ok,
            "strategy_scan_ok": strategy_scan_ok,
            "execution_ok": execution_ok,
        },
        tuple(reasons),
    )


def _front_expiry_frame(frame: pd.DataFrame, focus_expiries: int) -> pd.DataFrame:
    expiries = sorted(frame["expiry_date"].dropna().unique())[:focus_expiries]
    return frame[frame["expiry_date"].isin(expiries)].copy()


def evaluate_pricing_frame(frame: pd.DataFrame, *, focus_expiries: int = 2) -> OptionChainQualityReport:
    required = {"timestamp", "symbol", "expiry_date", "option_type", "strike_price"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"pricing frame missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("pricing frame is empty")

    total = len(frame)
    focus_expiries = max(int(focus_expiries), 1)
    focus = _front_expiry_frame(frame, focus_expiries)
    focus_total = len(focus)
    timestamp = str(pd.Timestamp(frame["timestamp"].dropna().iloc[0])) if frame["timestamp"].notna().any() else "unknown"
    quote_quality = frame.get("quote_quality", pd.Series([""] * total, index=frame.index)).fillna("")
    iv_quality = frame.get("raw_iv_quality", pd.Series([""] * total, index=frame.index)).fillna("")
    spread = frame.get("spread_bps", pd.Series(dtype=float)).dropna()
    focus_quote_quality = focus.get("quote_quality", pd.Series([""] * focus_total, index=focus.index)).fillna("")
    focus_iv_quality = focus.get("raw_iv_quality", pd.Series([""] * focus_total, index=focus.index)).fillna("")

    iv_success_ratio = _ratio(int((iv_quality == "ok").sum()), total)
    no_price_ratio = _ratio(int((iv_quality == "no_price").sum()), total)
    wide_spread_ratio = _ratio(int((quote_quality == "wide_spread").sum()), total)
    stale_quote_ratio = _ratio(int((quote_quality == "stale_quote").sum()), total)
    valid_quote_ratio = _ratio(int((quote_quality.isin(["ok", "wide_spread"])).sum()), total)
    median_spread_bps = float(spread.astype(float).median()) if not spread.empty else None
    focus_iv_success_ratio = _ratio(int((focus_iv_quality == "ok").sum()), focus_total)
    focus_no_price_ratio = _ratio(int((focus_iv_quality == "no_price").sum()), focus_total)
    focus_wide_spread_ratio = _ratio(int((focus_quote_quality == "wide_spread").sum()), focus_total)
    focus_atm_coverage = _atm_coverage_ratio(focus)

    pair_coverage = _call_put_pair_coverage(frame)
    atm_coverage = _atm_coverage_ratio(frame)
    atm_gap = _atm_iv_gap_median(frame)
    forward_quality = _forward_quality(frame)

    grade, flags, reasons = _grade_and_flags(
        iv_success_ratio=focus_iv_success_ratio,
        no_price_ratio=focus_no_price_ratio,
        wide_spread_ratio=focus_wide_spread_ratio,
        stale_quote_ratio=stale_quote_ratio,
        atm_coverage_ratio=focus_atm_coverage,
        call_put_pair_coverage=pair_coverage,
        median_spread_bps=median_spread_bps,
        forward_quality=_forward_quality(focus),
    )

    return OptionChainQualityReport(
        timestamp=timestamp,
        underlying=_infer_underlying(frame),
        total_contracts=total,
        expiries=int(frame["expiry_date"].nunique()),
        call_put_pair_coverage=pair_coverage,
        atm_coverage_ratio=atm_coverage,
        valid_quote_ratio=valid_quote_ratio,
        iv_success_ratio=iv_success_ratio,
        no_price_ratio=no_price_ratio,
        wide_spread_ratio=wide_spread_ratio,
        stale_quote_ratio=stale_quote_ratio,
        focus_expiries=focus_expiries,
        focus_total_contracts=focus_total,
        focus_iv_success_ratio=focus_iv_success_ratio,
        focus_no_price_ratio=focus_no_price_ratio,
        focus_atm_coverage_ratio=focus_atm_coverage,
        focus_wide_spread_ratio=focus_wide_spread_ratio,
        median_spread_bps=median_spread_bps,
        atm_iv_gap_median=atm_gap,
        forward_quality_by_expiry=forward_quality,
        research_ok=flags["research_ok"],
        surface_ok=flags["surface_ok"],
        backtest_ok=flags["backtest_ok"],
        strategy_scan_ok=flags["strategy_scan_ok"],
        execution_ok=flags["execution_ok"],
        overall_grade=grade,
        reasons=reasons,
    )
