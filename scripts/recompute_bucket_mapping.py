from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.enrichment import recompute_bucket_mapping
from scripts.enrich_four_term_snapshots import build_quality_frame, quality_path, write_parquet_atomic


def snapshot_path(data_root: Path, kind: str, product: str, trade_date: str) -> Path:
    return data_root / "snapshots" / kind / product.upper() / f"{trade_date}.parquet"


def meta_path(snapshot_output: Path) -> Path:
    return snapshot_output.with_suffix(".meta.json")


def write_json_atomic(payload: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(output)


def value_counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame.columns:
        return {}
    result: dict[str, int] = {}
    for key, value in frame[column].value_counts(dropna=False).to_dict().items():
        label = "null" if pd.isna(key) else str(key)
        result[label] = result.get(label, 0) + int(value)
    return result


def count_equal(frame: pd.DataFrame, column: str, value: object) -> int:
    if column not in frame.columns:
        return 0
    return int((frame[column].fillna("") == value).sum())


def available_dates(data_root: Path, snapshot_kind: str, product: str) -> list[str]:
    root = data_root / "snapshots" / snapshot_kind / product.upper()
    return sorted(
        path.stem
        for path in root.glob("*.parquet")
        if len(path.stem) == 10 and path.stem[:4].isdigit() and path.stem[4] == "-" and path.stem[7] == "-"
    )


def select_dates(dates: list[str], start: str | None, end: str | None, max_days: int) -> list[str]:
    selected = [item for item in dates if (start is None or item >= start) and (end is None or item <= end)]
    return selected[:max_days] if max_days > 0 else selected


def refresh_meta(output: Path, frame: pd.DataFrame) -> None:
    path = meta_path(output)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {}
    payload.update(
        {
            "output": str(output),
            "quality_output": str(quality_path(output)),
            "row_count": int(len(frame)),
            "timestamp_count": int(frame["timestamp"].nunique()) if "timestamp" in frame else 0,
            "expiry_count": int(frame["expiry_date"].nunique()) if "expiry_date" in frame else 0,
            "bucket_primary_distribution": value_counts(frame, "bucket_primary"),
            "delta_bucket_distribution": value_counts(frame, "delta_bucket"),
            "bucket_quality_distribution": value_counts(frame, "bucket_quality"),
            "bucket_quality_reason_distribution": value_counts(frame, "bucket_quality_reason"),
            "atm_straddle_candidate_rows": count_equal(frame, "is_atm_straddle_candidate", True),
            "atm_straddle_candidate_count": int(frame.get("straddle_candidate_id", pd.Series(dtype=object)).dropna().nunique()),
            "bucket_mapping_refreshed_at_utc": datetime.now(timezone.utc).isoformat(),
            "bucket_mapping_refresh_mode": "fast_recompute_from_enriched_snapshot",
        }
    )
    payload["output_size_bytes"] = int(output.stat().st_size)
    qpath = quality_path(output)
    if qpath.exists():
        payload["quality_size_bytes"] = int(qpath.stat().st_size)
    write_json_atomic(payload, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast-recompute bucket mapping from enriched option-chain snapshots.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--snapshot-kind", default="four_term_enriched_month_trial")
    parser.add_argument("--output-kind")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--no-sidecars", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output_kind = args.output_kind or args.snapshot_kind
    dates = select_dates(available_dates(args.data_root, args.snapshot_kind, args.product), args.start, args.end, args.max_days)

    for trade_date in dates:
        source = snapshot_path(args.data_root, args.snapshot_kind, args.product, trade_date)
        output = snapshot_path(args.data_root, output_kind, args.product, trade_date)
        if output.exists() and output != source and not args.force:
            print(f"{trade_date} skipped existing {output}")
            continue
        frame = pd.read_parquet(source)
        recomputed = recompute_bucket_mapping(frame)
        write_parquet_atomic(recomputed, output)
        if not args.no_sidecars:
            quality = build_quality_frame(recomputed, product=args.product, trade_date=trade_date)
            write_parquet_atomic(quality, quality_path(output))
            refresh_meta(output, recomputed)
        bucket_rows = int(recomputed.get("bucket_primary", pd.Series(dtype=object)).notna().sum())
        straddles = int(recomputed.get("straddle_candidate_id", pd.Series(dtype=object)).dropna().nunique())
        print(f"{trade_date} rows={len(recomputed)} bucket_rows={bucket_rows} atm_straddles={straddles} output={output}")


if __name__ == "__main__":
    main()
