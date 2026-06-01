import pandas as pd
import pytest

from option_platform.option_chain.enrichment import enrich_snapshot_frame
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


def test_enrich_snapshot_frame_writes_engine_ready_fields():
    enriched = enrich_snapshot_frame(_snapshot_frame(), risk_free_rate=0.0)

    assert "forward" in enriched.columns
    assert "rho" in enriched.columns
    assert "theoretical_price" in enriched.columns
    assert "pricing_model" in enriched.columns
    assert enriched["forward"].iloc[0] == pytest.approx(102.0)
    assert (enriched["iv_quality"] == "ok").sum() >= 2
    assert enriched["pricing_model"].dropna().unique().tolist() == ["black76"]


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


def test_snapshot_reader_uses_enriched_snapshot_without_repricing(monkeypatch):
    enriched = enrich_snapshot_frame(_snapshot_frame(), risk_free_rate=0.0)
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: enriched.copy())

    reader = OptionChainSnapshotReader(data_root="data_store")
    chain = reader.get_chain("MO", "2022-07-22", "2022-07-22 10:00:00")
    report = reader.get_quality_report("MO", "2022-07-22", "2022-07-22 10:00:00")

    assert len(chain.rows) == 2
    assert chain.get_row("2022-08-19", 100).call_greeks.delta is not None
    assert report.total_contracts == 4
