from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.reader import OptionChainSnapshotReader


def strategy_quality_path(snapshot_path: Path) -> Path:
    return snapshot_path.with_suffix(".strategy_quality.parquet")


def write_parquet_atomic(frame: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    frame.to_parquet(temp, index=False, compression="zstd")
    temp.replace(output)


def available_dates(data_root: Path, snapshot_kind: str, product: str) -> list[str]:
    root = data_root / "snapshots" / snapshot_kind / product.upper()
    return sorted(
        path.stem
        for path in root.glob("*.parquet")
        if len(path.stem) == 10 and path.stem[:4].isdigit() and path.stem[4] == "-" and path.stem[7] == "-"
    )


def selected_dates(dates: list[str], start: str | None, end: str | None, max_days: int) -> list[str]:
    selected = [date for date in dates if (start is None or date >= start) and (end is None or date <= end)]
    return selected[:max_days] if max_days > 0 else selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Build strategy-candidate quality reports from enriched snapshots.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--snapshot-kind", default="four_term_enriched_month_trial")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    reader = OptionChainSnapshotReader(data_root=args.data_root, snapshot_kind=args.snapshot_kind)
    dates = selected_dates(available_dates(args.data_root, args.snapshot_kind, args.product), args.start, args.end, args.max_days)

    for trade_date in dates:
        snapshot_path = reader.snapshot_path(args.product, trade_date)
        output = strategy_quality_path(snapshot_path)
        if output.exists() and not args.force:
            print(f"{trade_date} skipped existing {output}")
            continue
        report = reader.get_strategy_candidate_quality_report(args.product, trade_date)
        write_parquet_atomic(report, output)
        overall = report[report["scope"] == "overall"].iloc[0] if not report.empty else {}
        print(
            f"{trade_date} candidates={int(overall.get('candidate_count', 0))} "
            f"ok_ratio={float(overall.get('ok_ratio', 0.0)):.2%} output={output}"
        )


if __name__ == "__main__":
    main()
