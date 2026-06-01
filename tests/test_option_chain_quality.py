import pandas as pd

from option_platform.option_chain.quality import evaluate_pricing_frame


def test_evaluate_pricing_frame_reports_quality_flags():
    frame = pd.DataFrame(
        {
            "timestamp": ["2022-08-31 09:47:00"] * 8,
            "symbol": [
                "MO-C-100",
                "MO-P-100",
                "MO-C-105",
                "MO-P-105",
                "MO-C-100X",
                "MO-P-100X",
                "MO-C-105X",
                "MO-P-105X",
            ],
            "expiry_date": ["2022-09-16"] * 4 + ["2022-10-21"] * 4,
            "option_type": ["call", "put", "call", "put"] * 2,
            "strike_price": [100, 100, 105, 105, 100, 100, 105, 105],
            "forward": [102, 102, 102, 102, 103, 103, 103, 103],
            "forward_pairs": [2] * 8,
            "mark_price": [4, 2, 2, 4, 5, 3, 3, 5],
            "quote_quality": ["ok"] * 6 + ["wide_spread", "wide_spread"],
            "spread_bps": [100, 120, 150, 140, 90, 110, 600, 650],
            "raw_iv_quality": ["ok"] * 6 + ["no_price", "no_price"],
            "raw_iv": [0.2, 0.21, 0.22, 0.23, 0.2, 0.21, None, None],
        }
    )

    report = evaluate_pricing_frame(frame, focus_expiries=2)

    assert report.total_contracts == 8
    assert report.expiries == 2
    assert report.call_put_pair_coverage == 1
    assert report.iv_success_ratio == 0.75
    assert report.no_price_ratio == 0.25
    assert report.focus_iv_success_ratio == 0.75
    assert report.focus_no_price_ratio == 0.25
    assert report.research_ok is True
    assert report.execution_ok is False
    assert report.overall_grade in {"C", "D"}


def test_evaluate_pricing_frame_rejects_missing_columns():
    frame = pd.DataFrame({"timestamp": ["2022-08-31 09:47:00"]})

    try:
        evaluate_pricing_frame(frame)
    except ValueError as exc:
        assert "missing required columns" in str(exc)
    else:
        raise AssertionError("expected ValueError")
