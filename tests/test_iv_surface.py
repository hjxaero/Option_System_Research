import pandas as pd
import pytest

from option_platform.data.iv_surface import build_raw_surface_nodes


def test_build_raw_surface_nodes_projects_snapshot_fields():
    snapshot = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-05-27 09:30"]),
            "expiry_date": ["2026-06-19"],
            "term_role": ["current_month"],
            "strike_price": [100.0],
            "option_type": ["call"],
            "futures_price": [105.0],
            "delta": [0.6],
            "t_years": [0.05],
            "iv": [0.2],
            "iv_quality": ["ok"],
        }
    )

    nodes = build_raw_surface_nodes(snapshot)

    assert nodes.iloc[0]["moneyness"] == pytest.approx(100 / 105)
    assert nodes.iloc[0]["raw_iv"] == 0.2
    assert pd.isna(nodes.iloc[0]["smooth_iv"])
    assert nodes.iloc[0]["surface_quality"] == "ok"


def test_build_raw_surface_nodes_requires_core_columns():
    with pytest.raises(ValueError):
        build_raw_surface_nodes(pd.DataFrame({"timestamp": [pd.Timestamp("2026-05-27 09:30")]}))
