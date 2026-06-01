from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.quality import evaluate_pricing_frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate option-chain quality from a pricing experiment CSV.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--focus-expiries", type=int, default=2)
    args = parser.parse_args()

    frame = pd.read_csv(args.input)
    report = evaluate_pricing_frame(frame, focus_expiries=args.focus_expiries)
    payload = report.to_dict()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"grade={report.overall_grade}")
    print(f"timestamp={report.timestamp}")
    print(f"contracts={report.total_contracts} expiries={report.expiries}")
    print(f"iv_success_ratio={report.iv_success_ratio:.2%}")
    print(f"no_price_ratio={report.no_price_ratio:.2%}")
    print(f"atm_coverage_ratio={report.atm_coverage_ratio:.2%}")
    print(f"focus_expiries={report.focus_expiries}")
    print(f"focus_iv_success_ratio={report.focus_iv_success_ratio:.2%}")
    print(f"focus_no_price_ratio={report.focus_no_price_ratio:.2%}")
    print(f"focus_atm_coverage_ratio={report.focus_atm_coverage_ratio:.2%}")
    print(f"call_put_pair_coverage={report.call_put_pair_coverage:.2%}")
    print(
        "flags="
        f"research:{report.research_ok} "
        f"surface:{report.surface_ok} "
        f"backtest:{report.backtest_ok} "
        f"strategy:{report.strategy_scan_ok} "
        f"execution:{report.execution_ok}"
    )
    if report.reasons:
        print("reasons=" + ",".join(report.reasons))
    print(args.output)


if __name__ == "__main__":
    main()
