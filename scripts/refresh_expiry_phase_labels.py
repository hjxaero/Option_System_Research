from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.enrichment import _expiry_timing_fields
from option_platform.option_chain.reader import OptionChainSnapshotReader
from scripts.enrich_four_term_snapshots import build_quality_frame, iter_dates, quality_path, write_parquet_atomic


def _snapshot_path(data_root: Path, snapshot_kind: str, product: str, trade_date: str) -> Path:
    return data_root / "snapshots" / snapshot_kind / product.upper() / f"{trade_date}.parquet"


def _refresh_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "t_years" not in result.columns:
        raise ValueError("snapshot does not contain t_years; cannot refresh expiry phase labels")

    fields = result["t_years"].apply(_expiry_timing_fields).apply(pd.Series)
    for column in fields.columns:
        result[column] = fields[column]
    return result


def refresh_day(data_root: Path, snapshot_kind: str, product: str, trade_date: str) -> dict[str, object]:
    snapshot = _snapshot_path(data_root, snapshot_kind, product, trade_date)
    frame = pd.read_parquet(snapshot)
    refreshed = _refresh_snapshot(frame)
    write_parquet_atomic(refreshed, snapshot)

    quality = build_quality_frame(refreshed, product=product, trade_date=trade_date)
    write_parquet_atomic(quality, quality_path(snapshot))

    reader = OptionChainSnapshotReader(data_root=data_root, snapshot_kind=snapshot_kind)
    candidates = reader.get_strategy_candidates_for_storage(product, trade_date)
    candidate_path = reader.strategy_candidates_path(product, trade_date)
    write_parquet_atomic(candidates, candidate_path)
    strategy_quality = reader.get_strategy_candidate_quality_report(product, trade_date)
    write_parquet_atomic(strategy_quality, reader.strategy_quality_path(product, trade_date))

    return {
        "trade_date": trade_date,
        "rows": int(len(refreshed)),
        "candidate_count": int(len(candidates)),
        "expiry_phase": refreshed["expiry_phase"].value_counts(dropna=False).to_dict(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh expiry-phase labels without repricing IV/Greeks.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--snapshot-kind", default="four_term_enriched_month_trial")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--max-days", type=int, default=0)
    args = parser.parse_args()

    dates = iter_dates(args.data_root, args.product, args.start, args.end)
    if args.max_days > 0:
        dates = dates[: args.max_days]
    for trade_date in dates:
        snapshot = _snapshot_path(args.data_root, args.snapshot_kind, args.product, trade_date)
        if not snapshot.exists():
            continue
        result = refresh_day(args.data_root, args.snapshot_kind, args.product, trade_date)
        print(
            f"{result['trade_date']} rows={result['rows']} "
            f"candidates={result['candidate_count']} expiry_phase={result['expiry_phase']}"
        )


if __name__ == "__main__":
    main()
