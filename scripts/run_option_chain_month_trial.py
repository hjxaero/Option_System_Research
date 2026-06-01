from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.runtime import OptionChainRuntimeService


def _snapshot_dates(data_root: Path, product: str, start: str | None, end: str | None) -> list[str]:
    root = data_root / "snapshots" / "four_term" / product.upper()
    dates = [path.stem for path in sorted(root.glob("*.parquet"))]
    if start:
        dates = [item for item in dates if item >= start]
    if end:
        dates = [item for item in dates if item <= end]
    return dates


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an on-demand option-chain trial over a month of snapshots.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--focus-expiries", type=int, default=2)
    parser.add_argument("--risk-free-rate", type=float, default=0.02)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    dates = _snapshot_dates(args.data_root, args.product, args.start, args.end)
    if args.max_days > 0:
        dates = dates[: args.max_days]
    if not dates:
        raise SystemExit("No snapshot dates found.")

    service = OptionChainRuntimeService(
        data_root=args.data_root,
        risk_free_rate=args.risk_free_rate,
        focus_expiries=args.focus_expiries,
        max_cache_items=8,
    )

    rows = []
    reports = {}
    for trade_date in dates:
        result = service.get_result(args.product, trade_date)
        report = result.quality_report
        rows.append(
            {
                "trade_date": trade_date,
                "timestamp": str(result.timestamp),
                "grade": report.overall_grade,
                "contracts": report.total_contracts,
                "expiries": report.expiries,
                "iv_success_ratio": report.iv_success_ratio,
                "no_price_ratio": report.no_price_ratio,
                "focus_iv_success_ratio": report.focus_iv_success_ratio,
                "focus_no_price_ratio": report.focus_no_price_ratio,
                "focus_atm_coverage_ratio": report.focus_atm_coverage_ratio,
                "strategy_scan_ok": report.strategy_scan_ok,
                "execution_ok": report.execution_ok,
                "reasons": ",".join(report.reasons),
            }
        )
        reports[trade_date] = report.to_dict()
        print(
            f"{trade_date} {result.timestamp} grade={report.overall_grade} "
            f"focus_iv={report.focus_iv_success_ratio:.2%} "
            f"focus_no_price={report.focus_no_price_ratio:.2%} "
            f"strategy={report.strategy_scan_ok}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / f"{args.product.upper()}_{dates[0]}_{dates[-1]}_runtime_summary.csv"
    report_path = args.output_dir / f"{args.product.upper()}_{dates[0]}_{dates[-1]}_quality_reports.json"

    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"summary={summary_path}")
    print(f"reports={report_path}")


if __name__ == "__main__":
    main()
