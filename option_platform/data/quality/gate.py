from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QualityGateThresholds:
    min_ok_ratio: float = 0.60
    min_usable_ratio: float = 0.75
    max_stale_ratio: float = 0.20
    max_missing_ratio: float = 0.10
    max_invalid_ratio: float = 0.05
    max_p95_quote_age_ms: float = 60_000
    max_p95_spread_bps: float = 2_000


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, Any]


def load_quality_summary(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_quality_gate(
    summary: dict[str, Any],
    thresholds: QualityGateThresholds = QualityGateThresholds(),
) -> QualityGateResult:
    failures: list[str] = []

    def metric(name: str, default: float = 0.0) -> float:
        value = summary.get(name)
        if value is None:
            return default
        return float(value)

    if metric("ok_ratio") < thresholds.min_ok_ratio:
        failures.append(f"ok_ratio<{thresholds.min_ok_ratio}")
    if metric("usable_ratio") < thresholds.min_usable_ratio:
        failures.append(f"usable_ratio<{thresholds.min_usable_ratio}")
    if metric("stale_ratio") > thresholds.max_stale_ratio:
        failures.append(f"stale_ratio>{thresholds.max_stale_ratio}")
    if metric("missing_ratio") > thresholds.max_missing_ratio:
        failures.append(f"missing_ratio>{thresholds.max_missing_ratio}")
    if metric("invalid_ratio") > thresholds.max_invalid_ratio:
        failures.append(f"invalid_ratio>{thresholds.max_invalid_ratio}")

    p95_age = summary.get("p95_quote_age_ms")
    if p95_age is not None and float(p95_age) > thresholds.max_p95_quote_age_ms:
        failures.append(f"p95_quote_age_ms>{thresholds.max_p95_quote_age_ms}")

    p95_spread = summary.get("p95_spread_bps")
    if p95_spread is not None and float(p95_spread) > thresholds.max_p95_spread_bps:
        failures.append(f"p95_spread_bps>{thresholds.max_p95_spread_bps}")

    return QualityGateResult(
        passed=not failures,
        failures=tuple(failures),
        metrics=summary,
    )
