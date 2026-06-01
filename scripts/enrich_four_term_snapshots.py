from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.enrichment import enrich_snapshot_frame


def snapshot_path(data_root: Path, kind: str, product: str, trade_date: str) -> Path:
    return data_root / "snapshots" / kind / product.upper() / f"{trade_date}.parquet"


def iter_dates(data_root: Path, product: str, start: str | None, end: str | None) -> list[str]:
    root = data_root / "snapshots" / "four_term" / product.upper()
    dates = [path.stem for path in sorted(root.glob("*.parquet"))]
    if start:
        dates = [item for item in dates if item >= start]
    if end:
        dates = [item for item in dates if item <= end]
    return dates


def all_snapshot_dates(data_root: Path, product: str) -> list[str]:
    root = data_root / "snapshots" / "four_term" / product.upper()
    return [path.stem for path in sorted(root.glob("*.parquet"))]


def write_parquet_atomic(frame: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    tmp.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create engine-ready enriched four-term option-chain snapshots.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--risk-free-rate", type=float, default=0.02)
    parser.add_argument("--output-kind", default="four_term_enriched")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    trading_days = all_snapshot_dates(args.data_root, args.product)
    dates = iter_dates(args.data_root, args.product, args.start, args.end)
    if args.max_days > 0:
        dates = dates[: args.max_days]
    if not dates:
        raise SystemExit("No source snapshots found.")

    for trade_date in dates:
        source = snapshot_path(args.data_root, "four_term", args.product, trade_date)
        output = snapshot_path(args.data_root, args.output_kind, args.product, trade_date)
        if output.exists() and not args.force:
            print(f"{trade_date} skipped existing {output}")
            continue

        frame = pd.read_parquet(source)
        enriched = enrich_snapshot_frame(
            frame,
            risk_free_rate=args.risk_free_rate,
            trading_days=trading_days,
        )
        write_parquet_atomic(enriched, output)

        ok_iv = int((enriched["iv_quality"] == "ok").sum()) if "iv_quality" in enriched else 0
        total = len(enriched)
        print(
            f"{trade_date} rows={total} ok_iv={ok_iv} "
            f"ok_iv_ratio={(ok_iv / total if total else 0):.2%} output={output}"
        )


if __name__ == "__main__":
    main()
