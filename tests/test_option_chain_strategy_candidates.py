from __future__ import annotations

import pandas as pd
import pytest

from option_platform.option_chain.reader import OptionChainSnapshotReader
from option_platform.option_chain.strategy_candidates import (
    build_strategy_candidate_quality_report,
    build_strategy_candidates,
)


def _leg(
    *,
    timestamp: str,
    term_role: str,
    expiry_date: str,
    symbol: str,
    option_type: str,
    strike_price: float,
    mark_price: float,
    delta: float,
    bucket_ids: str,
    bucket_primary: str,
    delta_bucket: str,
    straddle_candidate_id: str | None = None,
) -> dict[str, object]:
    return {
        "timestamp": pd.Timestamp(timestamp),
        "term_role": term_role,
        "underlying_symbol": "MO",
        "expiry_date": expiry_date,
        "symbol": symbol,
        "option_type": option_type,
        "strike_price": strike_price,
        "mark_price": mark_price,
        "iv": 0.22,
        "delta": delta,
        "gamma": 0.01,
        "theta": -0.10,
        "vega": 1.20,
        "rho": 0.05,
        "iv_quality": "ok",
        "greeks_quality": "ok",
        "mark_quality": "ok",
        "pricing_quality": "ok",
        "tradability_quality": "liquid_tight",
        "strategy_candidate_ok": True,
        "strategy_candidate_tier": "standard" if term_role in {"current_month", "next_month"} else "conditional",
        "strategy_candidate_reason": "front_term_liquid_tight",
        "forward_consistency_quality": "ok",
        "bucket_ids": bucket_ids,
        "bucket_primary": bucket_primary,
        "bucket_count": len(bucket_ids.split(";")),
        "delta_bucket": delta_bucket,
        "bucket_selection_rank": 1,
        "bucket_selection_reason": "delta_closest",
        "is_atm_straddle_candidate": straddle_candidate_id is not None,
        "straddle_candidate_id": straddle_candidate_id,
    }


def _bucket_frame() -> pd.DataFrame:
    timestamp = "2022-08-10 10:00:00"
    return pd.DataFrame(
        [
            _leg(
                timestamp=timestamp,
                term_role="current_month",
                expiry_date="2022-08-19",
                symbol="MO2208-C-100",
                option_type="call",
                strike_price=100,
                mark_price=5.0,
                delta=0.51,
                bucket_ids="current_month_50D_call;current_month_ATM_call",
                bucket_primary="current_month_50D_call",
                delta_bucket="50D_call",
                straddle_candidate_id="20220810100000_current_month_20220819_100_ATM_straddle",
            ),
            _leg(
                timestamp=timestamp,
                term_role="current_month",
                expiry_date="2022-08-19",
                symbol="MO2208-P-100",
                option_type="put",
                strike_price=100,
                mark_price=4.5,
                delta=-0.49,
                bucket_ids="current_month_50D_put;current_month_ATM_put",
                bucket_primary="current_month_50D_put",
                delta_bucket="50D_put",
                straddle_candidate_id="20220810100000_current_month_20220819_100_ATM_straddle",
            ),
            _leg(
                timestamp=timestamp,
                term_role="current_month",
                expiry_date="2022-08-19",
                symbol="MO2208-C-110",
                option_type="call",
                strike_price=110,
                mark_price=1.5,
                delta=0.25,
                bucket_ids="current_month_25D_call",
                bucket_primary="current_month_25D_call",
                delta_bucket="25D_call",
            ),
            _leg(
                timestamp=timestamp,
                term_role="current_month",
                expiry_date="2022-08-19",
                symbol="MO2208-P-90",
                option_type="put",
                strike_price=90,
                mark_price=1.1,
                delta=-0.25,
                bucket_ids="current_month_25D_put",
                bucket_primary="current_month_25D_put",
                delta_bucket="25D_put",
            ),
            _leg(
                timestamp=timestamp,
                term_role="next_month",
                expiry_date="2022-09-16",
                symbol="MO2209-C-101",
                option_type="call",
                strike_price=101,
                mark_price=7.2,
                delta=0.50,
                bucket_ids="next_month_50D_call;next_month_ATM_call",
                bucket_primary="next_month_50D_call",
                delta_bucket="50D_call",
                straddle_candidate_id="20220810100000_next_month_20220916_101_ATM_straddle",
            ),
            _leg(
                timestamp=timestamp,
                term_role="next_month",
                expiry_date="2022-09-16",
                symbol="MO2209-P-101",
                option_type="put",
                strike_price=101,
                mark_price=6.8,
                delta=-0.50,
                bucket_ids="next_month_50D_put;next_month_ATM_put",
                bucket_primary="next_month_50D_put",
                delta_bucket="50D_put",
                straddle_candidate_id="20220810100000_next_month_20220916_101_ATM_straddle",
            ),
            _leg(
                timestamp=timestamp,
                term_role="next_month",
                expiry_date="2022-09-16",
                symbol="MO2209-C-112",
                option_type="call",
                strike_price=112,
                mark_price=2.0,
                delta=0.24,
                bucket_ids="next_month_25D_call",
                bucket_primary="next_month_25D_call",
                delta_bucket="25D_call",
            ),
            _leg(
                timestamp=timestamp,
                term_role="next_month",
                expiry_date="2022-09-16",
                symbol="MO2209-P-91",
                option_type="put",
                strike_price=91,
                mark_price=1.7,
                delta=-0.26,
                bucket_ids="next_month_25D_put",
                bucket_primary="next_month_25D_put",
                delta_bucket="25D_put",
            ),
        ]
    )


def _two_timestamp_bucket_frame() -> pd.DataFrame:
    later = _bucket_frame().copy()
    later["timestamp"] = pd.Timestamp("2022-08-10 10:01:00")
    later["straddle_candidate_id"] = later["straddle_candidate_id"].astype("string").str.replace(
        "20220810100000",
        "20220810100100",
        regex=False,
    )
    return pd.concat([_bucket_frame(), later], ignore_index=True)


def test_build_strategy_candidates_from_bucket_frame():
    candidates = build_strategy_candidates(_bucket_frame(), product="MO", trade_date="2022-08-10")

    assert set(candidates["structure_type"]) == {
        "atm_straddle",
        "25d_strangle",
        "25d_risk_reversal",
        "atm_call_calendar",
        "atm_put_calendar",
    }
    assert len(candidates[candidates["structure_type"] == "atm_straddle"]) == 2

    current_strangle = candidates[
        (candidates["structure_type"] == "25d_strangle") & (candidates["term_role"] == "current_month")
    ].iloc[0]
    assert current_strangle["net_mark"] == pytest.approx(2.6)
    assert current_strangle["candidate_quality"] == "ok"
    assert len(current_strangle["legs"]) == 2

    risk_reversal = candidates[
        (candidates["structure_type"] == "25d_risk_reversal") & (candidates["term_role"] == "current_month")
    ].iloc[0]
    assert risk_reversal["net_mark"] == pytest.approx(0.4)

    call_calendar = candidates[candidates["structure_type"] == "atm_call_calendar"].iloc[0]
    assert call_calendar["net_mark"] == pytest.approx(2.2)
    assert call_calendar["term_role"] == "current_next_month"


def test_build_strategy_candidate_quality_report_summarizes_candidates():
    first = build_strategy_candidates(_bucket_frame(), product="MO", trade_date="2022-08-10")
    second_frame = _bucket_frame().copy()
    second_frame["timestamp"] = pd.Timestamp("2022-08-10 10:01:00")
    second_frame["straddle_candidate_id"] = second_frame["straddle_candidate_id"].astype("string").str.replace(
        "20220810100000",
        "20220810100100",
        regex=False,
    )
    second = build_strategy_candidates(second_frame, product="MO", trade_date="2022-08-10")
    candidates = pd.concat([first, second], ignore_index=True)
    report = build_strategy_candidate_quality_report(candidates, product="MO", trade_date="2022-08-10")

    overall = report[report["scope"] == "overall"].iloc[0]
    assert overall["timestamp_count"] == 2
    assert overall["candidate_count"] == 16
    assert overall["ok_count"] == 16
    assert overall["ok_ratio"] == pytest.approx(1.0)

    structure = report[(report["scope"] == "structure") & (report["structure_type"] == "atm_straddle")].iloc[0]
    assert structure["candidate_count"] == 4
    assert structure["median_abs_net_delta"] == pytest.approx(0.01)

    structure_term = report[
        (report["scope"] == "structure_term")
        & (report["structure_type"] == "25d_strangle")
        & (report["term_role"] == "next_month")
    ].iloc[0]
    assert structure_term["candidate_count"] == 2
    assert structure_term["median_net_mark"] == pytest.approx(3.7)


def test_snapshot_reader_loads_bucket_rows_and_strategy_candidates(tmp_path):
    root = tmp_path / "snapshots" / "four_term_enriched_test" / "MO"
    root.mkdir(parents=True)
    _bucket_frame().to_parquet(root / "2022-08-10.parquet")

    reader = OptionChainSnapshotReader(data_root=tmp_path, snapshot_kind="four_term_enriched_test")

    atm_call = reader.get_bucket_rows(
        "MO",
        "2022-08-10",
        "2022-08-10 10:00:00",
        bucket_id="current_month_ATM_call",
    )
    assert atm_call["symbol"].tolist() == ["MO2208-C-100"]

    front_25d = reader.get_bucket_rows(
        "MO",
        "2022-08-10",
        "2022-08-10 10:00:00",
        delta_bucket="25D_call",
        front_terms_only=True,
    )
    assert front_25d["symbol"].tolist() == ["MO2208-C-110", "MO2209-C-112"]

    candidates = reader.get_strategy_candidates("MO", "2022-08-10", "2022-08-10 10:00:00")
    assert len(candidates) == 8
    assert candidates["candidate_quality"].unique().tolist() == ["ok"]


def test_snapshot_reader_builds_daily_strategy_candidate_quality_report(tmp_path):
    root = tmp_path / "snapshots" / "four_term_enriched_test" / "MO"
    root.mkdir(parents=True)
    _two_timestamp_bucket_frame().to_parquet(root / "2022-08-10.parquet")

    reader = OptionChainSnapshotReader(data_root=tmp_path, snapshot_kind="four_term_enriched_test")

    candidates = reader.get_strategy_candidates_for_day("MO", "2022-08-10")
    report = reader.get_strategy_candidate_quality_report("MO", "2022-08-10")

    assert len(candidates) == 16
    overall = report[report["scope"] == "overall"].iloc[0]
    assert overall["timestamp_count"] == 2
    assert overall["candidate_count"] == 16
    assert overall["ok_ratio"] == pytest.approx(1.0)
