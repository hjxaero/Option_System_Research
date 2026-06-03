import pandas as pd
import pytest

from option_platform.option_chain.enrichment import _assign_bucket_mapping, enrich_snapshot_frame, recompute_bucket_mapping
from option_platform.option_chain.reader import OptionChainSnapshotReader


def _snapshot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2022-07-22 10:00:00"] * 4),
            "term_role": ["current_month"] * 4,
            "underlying_symbol": ["MO"] * 4,
            "underlying_price": [pd.NA] * 4,
            "futures_symbol": ["MO"] * 4,
            "futures_price": [pd.NA] * 4,
            "expiry_date": ["2022-08-19"] * 4,
            "symbol": ["C100", "P100", "C105", "P105"],
            "option_type": ["call", "put", "call", "put"],
            "strike_price": [100.0, 100.0, 105.0, 105.0],
            "mark_price": [5.0, 3.0, 3.0, 6.0],
            "price_source": ["mid"] * 4,
            "last_price": [5.0, 3.0, 3.0, 6.0],
            "bid_price1": [4.9, 2.9, 2.9, 5.9],
            "ask_price1": [5.1, 3.1, 3.1, 6.1],
            "bid_volume1": [1] * 4,
            "ask_volume1": [1] * 4,
            "mid_price": [5.0, 3.0, 3.0, 6.0],
            "micro_price": [5.0, 3.0, 3.0, 6.0],
            "spread": [0.2] * 4,
            "spread_bps": [100.0] * 4,
            "quote_time": pd.to_datetime(["2022-07-22 10:00:00"] * 4),
            "quote_age_ms": [0] * 4,
            "quote_quality": ["ok"] * 4,
            "open_interest": [100] * 4,
            "volume": [10] * 4,
            "volume_multiple": [100] * 4,
        }
    )


def _snapshot_frame_with_four_pairs() -> pd.DataFrame:
    extra = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2022-07-22 10:00:00"] * 4),
            "term_role": ["current_month"] * 4,
            "underlying_symbol": ["MO"] * 4,
            "underlying_price": [pd.NA] * 4,
            "futures_symbol": ["MO"] * 4,
            "futures_price": [pd.NA] * 4,
            "expiry_date": ["2022-08-19"] * 4,
            "symbol": ["C90", "P90", "C95", "P95"],
            "option_type": ["call", "put", "call", "put"],
            "strike_price": [90.0, 90.0, 95.0, 95.0],
            "mark_price": [13.0, 1.0, 8.0, 1.0],
            "price_source": ["mid"] * 4,
            "last_price": [13.0, 1.0, 8.0, 1.0],
            "bid_price1": [12.9, 0.9, 7.9, 0.9],
            "ask_price1": [13.1, 1.1, 8.1, 1.1],
            "bid_volume1": [1] * 4,
            "ask_volume1": [1] * 4,
            "mid_price": [13.0, 1.0, 8.0, 1.0],
            "micro_price": [13.0, 1.0, 8.0, 1.0],
            "spread": [0.2] * 4,
            "spread_bps": [100.0] * 4,
            "quote_time": pd.to_datetime(["2022-07-22 10:00:00"] * 4),
            "quote_age_ms": [0] * 4,
            "quote_quality": ["ok"] * 4,
            "open_interest": [100] * 4,
            "volume": [10] * 4,
            "volume_multiple": [100] * 4,
        }
    )
    return pd.concat([_snapshot_frame(), extra], ignore_index=True)


def test_enrich_snapshot_frame_writes_engine_ready_fields():
    enriched = enrich_snapshot_frame(_snapshot_frame(), risk_free_rate=0.0)

    assert "forward" in enriched.columns
    assert "rho" in enriched.columns
    assert "theoretical_price" in enriched.columns
    assert "pricing_model" in enriched.columns
    assert "contract_multiplier" in enriched.columns
    assert "mark_quality" in enriched.columns
    assert "mark_missing_reason" in enriched.columns
    assert "pricing_quality" in enriched.columns
    assert "tradability_quality" in enriched.columns
    assert "market_phase" in enriched.columns
    assert "days_since_contract_listing" in enriched.columns
    assert "greeks_quality" in enriched.columns
    assert "strategy_candidate_ok" in enriched.columns
    assert "strategy_candidate_tier" in enriched.columns
    assert "strategy_candidate_reason" in enriched.columns
    assert "bucket_ids" in enriched.columns
    assert "bucket_primary" in enriched.columns
    assert "delta_bucket" in enriched.columns
    assert "bucket_target_delta" in enriched.columns
    assert "bucket_delta_error" in enriched.columns
    assert "bucket_quality" in enriched.columns
    assert "bucket_quality_reason" in enriched.columns
    assert "is_atm_straddle_candidate" in enriched.columns
    assert "straddle_candidate_id" in enriched.columns
    assert enriched["forward"].iloc[0] == pytest.approx(102.0)
    assert enriched["contract_multiplier"].dropna().unique().tolist() == [100]
    assert enriched["standard_contract_multiplier"].dropna().unique().tolist() == [100]
    assert enriched["contract_adjustment_flag"].dropna().unique().tolist() == [False]
    assert enriched["multiplier_source"].dropna().unique().tolist() == ["contract_master"]
    assert enriched["mark_quality"].dropna().unique().tolist() == ["ok"]
    assert enriched["pricing_quality"].dropna().unique().tolist() == ["ok"]
    assert enriched["tradability_quality"].dropna().unique().tolist() == ["liquid_tight"]
    assert enriched["market_phase"].dropna().unique().tolist() == ["early_listing"]
    assert (enriched["iv_quality"] == "ok").sum() >= 2
    assert (enriched["greeks_quality"] == "ok").sum() >= 2
    assert (enriched["strategy_candidate_tier"] == "standard").sum() >= 2
    assert enriched["pricing_model"].dropna().unique().tolist() == ["black76"]


def test_enrich_snapshot_frame_assigns_bucket_mapping_and_straddle_candidate():
    enriched = enrich_snapshot_frame(_snapshot_frame_with_four_pairs(), risk_free_rate=0.0)

    bucket_ids = ";".join(enriched["bucket_ids"].dropna().astype(str).tolist())

    assert (enriched["bucket_primary"].notna()).sum() >= 3
    assert "current_month_25D_call" in bucket_ids
    assert "current_month_25D_put" in bucket_ids
    assert "current_month_50D_call" in bucket_ids
    assert "current_month_50D_put" in bucket_ids
    assert int(enriched["is_atm_straddle_candidate"].sum()) == 2
    assert enriched["straddle_candidate_id"].dropna().nunique() == 1
    assert set(enriched["bucket_quality"].dropna().unique()) <= {"ok", "loose", "bad"}


def test_bucket_mapping_selects_atm_straddle_by_forward_nearest_common_strike():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2022-07-22 10:00:00"] * 4),
            "expiry_date": ["2022-08-19"] * 4,
            "term_role": ["current_month"] * 4,
            "symbol": ["C100", "P100", "C105", "P105"],
            "option_type": ["call", "put", "call", "put"],
            "strike_price": [100.0, 100.0, 105.0, 105.0],
            "delta": [0.61, -0.31, 0.48, -0.52],
            "resolved_forward": [100.8] * 4,
            "strategy_candidate_ok": [True] * 4,
            "strategy_candidate_tier": ["standard"] * 4,
            "greeks_quality": ["ok"] * 4,
        }
    )

    mapped = _assign_bucket_mapping(frame)
    straddle = mapped[mapped["is_atm_straddle_candidate"]]
    bucket_ids = ";".join(straddle["bucket_ids"].astype(str).tolist())

    assert straddle["strike_price"].unique().tolist() == [100.0]
    assert sorted(straddle["option_type"].tolist()) == ["call", "put"]
    assert "current_month_ATM_call" in bucket_ids
    assert "current_month_ATM_put" in bucket_ids
    assert "current_month_50D_call" not in bucket_ids
    call = straddle[straddle["option_type"] == "call"].iloc[0]
    put = straddle[straddle["option_type"] == "put"].iloc[0]
    assert call["bucket_target_delta"] == pytest.approx(0.50)
    assert call["bucket_delta_error"] == pytest.approx(0.11)
    assert call["bucket_quality"] == "bad"
    assert put["bucket_target_delta"] == pytest.approx(-0.25)
    assert put["bucket_delta_error"] == pytest.approx(0.06)
    assert put["bucket_quality"] == "loose"


def test_recompute_bucket_mapping_preserves_pricing_fields():
    enriched = enrich_snapshot_frame(_snapshot_frame_with_four_pairs(), risk_free_rate=0.0)
    stale = enriched.copy()
    stale["bucket_ids"] = pd.NA
    stale["bucket_primary"] = pd.NA
    stale["bucket_count"] = 0
    stale["delta_bucket"] = pd.NA
    stale["bucket_target_delta"] = pd.NA
    stale["bucket_delta_error"] = pd.NA
    stale["bucket_quality"] = pd.NA
    stale["bucket_quality_reason"] = pd.NA
    stale["is_atm_straddle_candidate"] = False
    stale["straddle_candidate_id"] = pd.NA

    recomputed = recompute_bucket_mapping(stale)

    for column in ("iv", "delta", "gamma", "theta", "vega", "rho", "forward", "resolved_forward", "t_years"):
        pd.testing.assert_series_equal(recomputed[column], stale[column], check_names=False)
    assert recomputed["bucket_primary"].notna().sum() > 0
    assert recomputed["bucket_quality"].notna().sum() > 0
    assert int(recomputed["is_atm_straddle_candidate"].sum()) == 2


def test_enrich_snapshot_frame_marks_degraded_mark_quality():
    frame = _snapshot_frame().copy()
    frame.loc[0, "quote_quality"] = "wide_spread"
    frame.loc[1, "price_source"] = "last"

    enriched = enrich_snapshot_frame(frame, risk_free_rate=0.0)

    assert enriched["mark_quality"].iloc[0] == "wide_spread"
    assert enriched["mark_quality"].iloc[1] == "degraded_last"
    assert enriched["pricing_quality"].iloc[0] == "wide_spread_pricing"
    assert enriched["tradability_quality"].iloc[0] == "liquid_wide"
    if enriched["greeks_quality"].iloc[0] == "ok":
        assert enriched["strategy_candidate_ok"].iloc[0]
        assert enriched["strategy_candidate_tier"].iloc[0] == "conditional"


def test_enrich_snapshot_frame_explains_missing_and_one_sided_marks():
    frame = _snapshot_frame().copy()
    frame.loc[0, ["mark_price", "bid_price1", "ask_price1", "last_price", "bid_volume1", "ask_volume1", "volume", "open_interest"]] = [
        pd.NA,
        pd.NA,
        pd.NA,
        pd.NA,
        0,
        0,
        0,
        0,
    ]
    frame.loc[0, "price_source"] = "none"
    frame.loc[0, "quote_quality"] = "missing"
    frame.loc[1, ["mark_price", "ask_price1", "ask_volume1", "last_price"]] = [pd.NA, pd.NA, 0, pd.NA]
    frame.loc[1, "price_source"] = "none"
    frame.loc[1, "quote_quality"] = "invalid_bid_ask"

    enriched = enrich_snapshot_frame(frame, risk_free_rate=0.0)

    assert enriched["mark_missing_reason"].iloc[0] == "missing_bid_ask_last"
    assert enriched["pricing_quality"].iloc[0] == "no_mark_price"
    assert enriched["tradability_quality"].iloc[0] == "not_quoted"
    assert not enriched["strategy_candidate_ok"].iloc[0]
    assert enriched["strategy_candidate_tier"].iloc[0] == "excluded"
    assert enriched["mark_missing_reason"].iloc[1] == "invalid_bid_ask"
    assert enriched["tradability_quality"].iloc[1] == "one_sided"


def test_enrich_snapshot_frame_uses_trading_minute_time_decay():
    frame = pd.concat(
        [
            _snapshot_frame().assign(timestamp=pd.Timestamp("2022-07-22 09:30:00")),
            _snapshot_frame().assign(timestamp=pd.Timestamp("2022-07-22 09:31:00")),
        ],
        ignore_index=True,
    )

    enriched = enrich_snapshot_frame(
        frame,
        risk_free_rate=0.0,
        trading_days=["2022-07-22", "2022-07-25", "2022-07-26", "2022-08-19"],
    )

    t_0930 = enriched[enriched["timestamp"] == pd.Timestamp("2022-07-22 09:30:00")]["t_years"].iloc[0]
    t_0931 = enriched[enriched["timestamp"] == pd.Timestamp("2022-07-22 09:31:00")]["t_years"].iloc[0]

    assert t_0930 - t_0931 == pytest.approx(1 / (252 * 240))


def test_enrich_snapshot_frame_tags_last_three_trading_days():
    enriched = enrich_snapshot_frame(
        _snapshot_frame().assign(timestamp=pd.Timestamp("2022-08-17 09:30:00")),
        risk_free_rate=0.0,
        trading_days=["2022-08-17", "2022-08-18", "2022-08-19"],
    )

    assert enriched["remaining_trading_minutes"].iloc[0] == 720
    assert enriched["trading_days_to_expiry"].iloc[0] == 3
    assert enriched["expiry_phase"].dropna().unique().tolist() == ["last_3_trading_days"]
    assert enriched["expiry_phase_rank"].dropna().unique().tolist() == [1]


def test_enrich_snapshot_frame_extends_trading_days_to_cover_far_expiry():
    enriched = enrich_snapshot_frame(
        _snapshot_frame().assign(expiry_date="2022-12-16"),
        risk_free_rate=0.0,
        trading_days=["2022-07-22"],
    )

    assert enriched["t_years"].iloc[0] > 0.3


def test_enrich_snapshot_frame_prefers_futures_forward_when_available():
    futures = pd.DataFrame(
        {
            "target_time": pd.to_datetime(["2022-07-22 10:00:00"]),
            "expiry_date": ["2022-08-19"],
            "symbol": ["CFFEX.IM2208"],
            "micro_price": [101.0],
            "mid_price": [101.2],
            "last_price": [101.4],
            "quote_quality": ["ok"],
        }
    )

    enriched = enrich_snapshot_frame(
        _snapshot_frame_with_four_pairs(),
        risk_free_rate=0.0,
        futures_frame=futures,
    )

    assert enriched["forward"].iloc[0] == pytest.approx(101.0)
    assert enriched["resolved_forward"].iloc[0] == pytest.approx(101.0)
    assert enriched["forward_source"].dropna().unique().tolist() == ["futures"]
    assert enriched["forward_quality"].dropna().unique().tolist() == ["basis_severe"]
    assert enriched["forward_consistency_quality"].dropna().unique().tolist() == ["basis_severe"]
    assert enriched["forward_resolver_reason"].dropna().unique().tolist() == ["futures_and_synthetic_ok"]
    assert enriched["futures_symbol"].dropna().unique().tolist() == ["CFFEX.IM2208"]
    assert enriched["futures_forward"].iloc[0] == pytest.approx(101.0)
    assert enriched["futures_forward_source_price"].dropna().unique().tolist() == ["micro_price"]
    assert enriched["synthetic_forward"].iloc[0] == pytest.approx(102.0)
    assert enriched["synthetic_forward_pairs"].iloc[0] == 4
    assert enriched["parity_forward"].iloc[0] == pytest.approx(102.0)
    assert enriched["forward_basis_error"].iloc[0] == pytest.approx(1.0)
    assert enriched["forward_basis_abs"].iloc[0] == pytest.approx(1.0)
    assert enriched["forward_basis_bps"].iloc[0] == pytest.approx(1.0 / 101.0 * 10000)


def test_enrich_snapshot_frame_uses_synthetic_when_futures_quote_is_degraded():
    futures = pd.DataFrame(
        {
            "target_time": pd.to_datetime(["2022-07-22 10:00:00"]),
            "expiry_date": ["2022-08-19"],
            "symbol": ["CFFEX.IM2208"],
            "micro_price": [101.0],
            "mid_price": [101.2],
            "last_price": [101.4],
            "quote_quality": ["stale"],
        }
    )

    enriched = enrich_snapshot_frame(
        _snapshot_frame_with_four_pairs(),
        risk_free_rate=0.0,
        futures_frame=futures,
    )

    assert enriched["forward"].iloc[0] == pytest.approx(102.0)
    assert enriched["forward_source"].dropna().unique().tolist() == ["synthetic_parity"]
    assert enriched["forward_quality"].dropna().unique().tolist() == ["synthetic_ok"]
    assert enriched["forward_consistency_quality"].dropna().unique().tolist() == ["futures_degraded"]


def test_snapshot_reader_uses_enriched_snapshot_without_repricing(monkeypatch):
    enriched = enrich_snapshot_frame(_snapshot_frame(), risk_free_rate=0.0)
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: enriched.copy())

    reader = OptionChainSnapshotReader(data_root="data_store")
    chain = reader.get_chain("MO", "2022-07-22", "2022-07-22 10:00:00")
    report = reader.get_quality_report("MO", "2022-07-22", "2022-07-22 10:00:00")

    assert len(chain.rows) == 2
    assert chain.get_row("2022-08-19", 100).call_greeks.delta is not None
    assert report.total_contracts == 4
