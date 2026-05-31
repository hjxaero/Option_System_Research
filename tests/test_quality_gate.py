from option_platform.data.quality.gate import (
    QualityGateThresholds,
    evaluate_quality_gate,
)


def test_quality_gate_counts_wide_spread_as_usable_but_not_ok():
    result = evaluate_quality_gate(
        {
            "ok_ratio": 0.66,
            "wide_spread_ratio": 0.10,
            "usable_ratio": 0.76,
            "stale_ratio": 0.03,
            "missing_ratio": 0.18,
            "invalid_ratio": 0.01,
            "p95_quote_age_ms": 50_000,
            "p95_spread_bps": 1_800,
        },
        QualityGateThresholds(max_missing_ratio=0.20),
    )

    assert result.passed


def test_quality_gate_fails_low_usable_ratio():
    result = evaluate_quality_gate(
        {
            "ok_ratio": 0.60,
            "wide_spread_ratio": 0.05,
            "usable_ratio": 0.65,
            "stale_ratio": 0.03,
            "missing_ratio": 0.10,
            "invalid_ratio": 0.01,
        }
    )

    assert not result.passed
    assert "usable_ratio<0.75" in result.failures
