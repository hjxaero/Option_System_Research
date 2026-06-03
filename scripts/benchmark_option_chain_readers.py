from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.reader import OptionChainSnapshotReader


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


def median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000


def measure(label: str, fn, *, repeats: int) -> tuple[str, float, object]:
    samples = []
    result = None
    for _ in range(repeats):
        start = perf_counter()
        result = fn()
        samples.append(perf_counter() - start)
    return label, median_ms(samples), result


def row_count(value: object) -> int:
    if isinstance(value, pd.DataFrame):
        return int(len(value))
    if isinstance(value, list):
        return len(value)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark option-chain enriched snapshot and sidecar readers.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--snapshot-kind", default="four_term_enriched_month_trial")
    parser.add_argument("--trade-date", default="2022-08-10")
    parser.add_argument("--timestamp", default="2022-08-10 10:00:00")
    parser.add_argument("--start", default="2022-07-22")
    parser.add_argument("--end", default="2022-08-19")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    dates = selected_dates(available_dates(args.data_root, args.snapshot_kind, args.product), args.start, args.end, args.max_days)
    reader = OptionChainSnapshotReader(data_root=args.data_root, snapshot_kind=args.snapshot_kind, max_cache_items=0)

    candidate_columns = [
        "timestamp",
        "structure_type",
        "term_role",
        "candidate_quality",
        "net_mark",
        "net_delta",
        "net_vega",
    ]
    quality_columns = ["scope", "structure_type", "term_role", "candidate_count", "ok_ratio"]

    benchmarks = [
        measure(
            "single timestamp bucket rows from enriched",
            lambda: reader.get_bucket_rows(args.product, args.trade_date, args.timestamp, front_terms_only=True),
            repeats=args.repeats,
        ),
        measure(
            "single day candidates generated from enriched",
            lambda: reader.get_strategy_candidates_for_day(args.product, args.trade_date),
            repeats=max(1, min(args.repeats, 3)),
        ),
        measure(
            "single day candidates sidecar selected columns",
            lambda: reader.load_strategy_candidates_sidecar(args.product, args.trade_date, columns=candidate_columns),
            repeats=args.repeats,
        ),
        measure(
            "single day quality sidecar selected columns",
            lambda: reader.load_strategy_quality_sidecar(args.product, args.trade_date, columns=quality_columns),
            repeats=args.repeats,
        ),
        measure(
            "month candidates sidecars selected columns",
            lambda: pd.concat(
                [reader.load_strategy_candidates_sidecar(args.product, date, columns=candidate_columns) for date in dates],
                ignore_index=True,
            ),
            repeats=max(1, min(args.repeats, 3)),
        ),
        measure(
            "month quality sidecars selected columns",
            lambda: pd.concat(
                [reader.load_strategy_quality_sidecar(args.product, date, columns=quality_columns) for date in dates],
                ignore_index=True,
            ),
            repeats=args.repeats,
        ),
    ]

    print("benchmark,median_ms,rows")
    for label, ms, result in benchmarks:
        print(f"{label},{ms:.2f},{row_count(result)}")


if __name__ == "__main__":
    main()
