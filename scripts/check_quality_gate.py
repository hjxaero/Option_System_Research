from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.data.quality.gate import (
    QualityGateThresholds,
    evaluate_quality_gate,
    load_quality_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether a quote quality summary passes download gate.")
    parser.add_argument("summary_json")
    parser.add_argument("--min-ok-ratio", type=float, default=0.60)
    parser.add_argument("--min-usable-ratio", type=float, default=0.75)
    parser.add_argument("--max-stale-ratio", type=float, default=0.20)
    parser.add_argument("--max-missing-ratio", type=float, default=0.10)
    parser.add_argument("--max-invalid-ratio", type=float, default=0.05)
    parser.add_argument("--max-p95-quote-age-ms", type=float, default=60_000)
    parser.add_argument("--max-p95-spread-bps", type=float, default=2_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = load_quality_summary(args.summary_json)
    result = evaluate_quality_gate(
        summary,
        QualityGateThresholds(
            min_ok_ratio=args.min_ok_ratio,
            min_usable_ratio=args.min_usable_ratio,
            max_stale_ratio=args.max_stale_ratio,
            max_missing_ratio=args.max_missing_ratio,
            max_invalid_ratio=args.max_invalid_ratio,
            max_p95_quote_age_ms=args.max_p95_quote_age_ms,
            max_p95_spread_bps=args.max_p95_spread_bps,
        ),
    )
    print(f"passed={result.passed} failures={list(result.failures)}")
    if not result.passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
