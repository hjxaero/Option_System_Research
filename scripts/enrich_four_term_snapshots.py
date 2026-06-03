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
    frame.to_parquet(tmp, index=False, compression="zstd")
    tmp.replace(output)


def write_json_atomic(payload: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(output)


def meta_path(snapshot_output: Path) -> Path:
    return snapshot_output.with_suffix(".meta.json")


def quality_path(snapshot_output: Path) -> Path:
    return snapshot_output.with_suffix(".quality.parquet")


def futures_minute_path(data_root: Path, futures_product: str, trade_date: str) -> Path:
    return data_root / "futures" / futures_product.upper() / "minute" / f"{trade_date}.parquet"


def load_futures_frame(data_root: Path, futures_product: str, trade_date: str) -> pd.DataFrame | None:
    path = futures_minute_path(data_root, futures_product, trade_date)
    if not path.exists():
        return None
    return pd.read_parquet(path)


def ratio(numerator: int | float, denominator: int | float) -> float:
    return 0.0 if denominator == 0 else float(numerator) / float(denominator)


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


def first_two_expiries(frame: pd.DataFrame) -> list[str]:
    return sorted(frame["expiry_date"].dropna().astype(str).unique())[:2]


def quality_row(
    frame: pd.DataFrame,
    *,
    product: str,
    trade_date: str,
    scope: str,
    expiry_date: str | None = None,
    term_rank: int | None = None,
) -> dict[str, object]:
    total = len(frame)
    iv_quality = frame.get("iv_quality", pd.Series([""] * total, index=frame.index)).fillna("")
    quote_quality = frame.get("quote_quality", pd.Series([""] * total, index=frame.index)).fillna("")
    forward_basis_bps = pd.to_numeric(frame.get("forward_basis_bps", pd.Series(dtype=float)), errors="coerce").abs()
    return {
        "product": product.upper(),
        "trade_date": trade_date,
        "scope": scope,
        "expiry_date": expiry_date,
        "term_rank": term_rank,
        "rows": total,
        "iv_ok": int((iv_quality == "ok").sum()),
        "iv_ok_ratio": ratio(int((iv_quality == "ok").sum()), total),
        "no_price": int((iv_quality == "no_price").sum()),
        "no_price_ratio": ratio(int((iv_quality == "no_price").sum()), total),
        "below_intrinsic": int((iv_quality == "below_intrinsic").sum()),
        "below_intrinsic_ratio": ratio(int((iv_quality == "below_intrinsic").sum()), total),
        "no_forward": int((iv_quality == "no_forward").sum()),
        "no_forward_ratio": ratio(int((iv_quality == "no_forward").sum()), total),
        "quote_ok_ratio": ratio(int((quote_quality == "ok").sum()), total),
        "wide_spread_ratio": ratio(int((quote_quality == "wide_spread").sum()), total),
        "stale_quote_ratio": ratio(int((quote_quality == "stale_quote").sum()), total),
        "forward_source_futures": count_equal(frame, "forward_source", "futures"),
        "forward_source_synthetic": count_equal(frame, "forward_source", "synthetic_parity"),
        "forward_source_none": count_equal(frame, "forward_source", "none"),
        "basis_ok": count_equal(frame, "forward_consistency_quality", "ok"),
        "basis_minor": count_equal(frame, "forward_consistency_quality", "minor_basis"),
        "basis_warning": count_equal(frame, "forward_consistency_quality", "basis_warning"),
        "basis_severe": count_equal(frame, "forward_consistency_quality", "basis_severe"),
        "futures_degraded": count_equal(frame, "forward_consistency_quality", "futures_degraded"),
        "synthetic_degraded": count_equal(frame, "forward_consistency_quality", "synthetic_degraded"),
        "both_degraded": count_equal(frame, "forward_consistency_quality", "both_degraded"),
        "strategy_candidate_standard": count_equal(frame, "strategy_candidate_tier", "standard"),
        "strategy_candidate_conditional": count_equal(frame, "strategy_candidate_tier", "conditional"),
        "strategy_candidate_excluded": count_equal(frame, "strategy_candidate_tier", "excluded"),
        "strategy_candidate_ok_ratio": ratio(count_equal(frame, "strategy_candidate_ok", True), total),
        "bucket_candidate_rows": int(frame.get("bucket_primary", pd.Series(dtype=object)).notna().sum()),
        "bucket_quality_ok": count_equal(frame, "bucket_quality", "ok"),
        "bucket_quality_loose": count_equal(frame, "bucket_quality", "loose"),
        "bucket_quality_bad": count_equal(frame, "bucket_quality", "bad"),
        "atm_straddle_candidate_rows": count_equal(frame, "is_atm_straddle_candidate", True),
        "atm_straddle_candidate_count": int(frame.get("straddle_candidate_id", pd.Series(dtype=object)).dropna().nunique()),
        "expiry_phase_normal": count_equal(frame, "expiry_phase", "normal"),
        "expiry_phase_last_3_trading_days": count_equal(frame, "expiry_phase", "last_3_trading_days"),
        "expiry_phase_final_trading_day": count_equal(frame, "expiry_phase", "final_trading_day"),
        "median_abs_forward_basis_bps": None if forward_basis_bps.dropna().empty else float(forward_basis_bps.median()),
        "p95_abs_forward_basis_bps": None if forward_basis_bps.dropna().empty else float(forward_basis_bps.quantile(0.95)),
    }


def build_quality_frame(enriched: pd.DataFrame, *, product: str, trade_date: str) -> pd.DataFrame:
    rows = [quality_row(enriched, product=product, trade_date=trade_date, scope="overall")]
    front_expiries = first_two_expiries(enriched)
    front = enriched[enriched["expiry_date"].astype(str).isin(front_expiries)]
    rows.append(quality_row(front, product=product, trade_date=trade_date, scope="front_two"))
    for term_rank, expiry in enumerate(sorted(enriched["expiry_date"].dropna().astype(str).unique()), start=1):
        expiry_frame = enriched[enriched["expiry_date"].astype(str) == expiry]
        rows.append(
            quality_row(
                expiry_frame,
                product=product,
                trade_date=trade_date,
                scope="expiry",
                expiry_date=expiry,
                term_rank=term_rank,
            )
        )
    return pd.DataFrame(rows)


def build_meta(
    enriched: pd.DataFrame,
    *,
    product: str,
    trade_date: str,
    source: Path,
    output: Path,
    risk_free_rate: float,
    futures_product: str,
    futures_available: bool,
) -> dict[str, object]:
    return {
        "schema_version": "research_option_chain_snapshot.v0",
        "model_version": "black76_forward_consistency.v0",
        "product": product.upper(),
        "trade_date": trade_date,
        "source": str(source),
        "output": str(output),
        "quality_output": str(quality_path(output)),
        "compression": "zstd",
        "pricing_model": "black76",
        "risk_free_rate": risk_free_rate,
        "futures_product": futures_product.upper(),
        "futures_available": futures_available,
        "row_count": int(len(enriched)),
        "timestamp_count": int(enriched["timestamp"].nunique()) if "timestamp" in enriched else 0,
        "expiry_count": int(enriched["expiry_date"].nunique()) if "expiry_date" in enriched else 0,
        "iv_quality_distribution": value_counts(enriched, "iv_quality"),
        "mark_quality_distribution": value_counts(enriched, "mark_quality"),
        "mark_missing_reason_distribution": value_counts(enriched, "mark_missing_reason"),
        "pricing_quality_distribution": value_counts(enriched, "pricing_quality"),
        "tradability_quality_distribution": value_counts(enriched, "tradability_quality"),
        "greeks_quality_distribution": value_counts(enriched, "greeks_quality"),
        "strategy_candidate_ok_distribution": value_counts(enriched, "strategy_candidate_ok"),
        "strategy_candidate_tier_distribution": value_counts(enriched, "strategy_candidate_tier"),
        "strategy_candidate_reason_distribution": value_counts(enriched, "strategy_candidate_reason"),
        "bucket_primary_distribution": value_counts(enriched, "bucket_primary"),
        "delta_bucket_distribution": value_counts(enriched, "delta_bucket"),
        "bucket_quality_distribution": value_counts(enriched, "bucket_quality"),
        "bucket_quality_reason_distribution": value_counts(enriched, "bucket_quality_reason"),
        "atm_straddle_candidate_rows": count_equal(enriched, "is_atm_straddle_candidate", True),
        "atm_straddle_candidate_count": int(enriched.get("straddle_candidate_id", pd.Series(dtype=object)).dropna().nunique()),
        "market_phase_distribution": value_counts(enriched, "market_phase"),
        "contract_listing_phase_distribution": value_counts(enriched, "contract_listing_phase"),
        "expiry_phase_distribution": value_counts(enriched, "expiry_phase"),
        "expiry_phase_reason_distribution": value_counts(enriched, "expiry_phase_reason"),
        "forward_source_distribution": value_counts(enriched, "forward_source"),
        "forward_consistency_distribution": value_counts(enriched, "forward_consistency_quality"),
        "contract_multiplier_distribution": value_counts(enriched, "contract_multiplier"),
        "adjusted_contract_count": count_equal(enriched, "contract_adjustment_flag", True),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create engine-ready enriched four-term option-chain snapshots.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--risk-free-rate", type=float, default=0.02)
    parser.add_argument("--futures-product", default="IM")
    parser.add_argument("--no-futures", action="store_true")
    parser.add_argument("--output-kind", default="four_term_enriched")
    parser.add_argument("--no-sidecars", action="store_true")
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
        futures_frame = None if args.no_futures else load_futures_frame(args.data_root, args.futures_product, trade_date)
        if output.exists() and not args.force:
            print(f"{trade_date} skipped existing {output}")
            continue

        frame = pd.read_parquet(source)
        enriched = enrich_snapshot_frame(
            frame,
            risk_free_rate=args.risk_free_rate,
            trading_days=trading_days,
            futures_frame=futures_frame,
        )
        write_parquet_atomic(enriched, output)
        if not args.no_sidecars:
            quality = build_quality_frame(enriched, product=args.product, trade_date=trade_date)
            write_parquet_atomic(quality, quality_path(output))
            meta = build_meta(
                enriched,
                product=args.product,
                trade_date=trade_date,
                source=source,
                output=output,
                risk_free_rate=args.risk_free_rate,
                futures_product=args.futures_product,
                futures_available=futures_frame is not None,
            )
            meta["output_size_bytes"] = int(output.stat().st_size)
            meta["quality_size_bytes"] = int(quality_path(output).stat().st_size)
            write_json_atomic(meta, meta_path(output))

        ok_iv = int((enriched["iv_quality"] == "ok").sum()) if "iv_quality" in enriched else 0
        total = len(enriched)
        forward_sources = (
            enriched["forward_source"].value_counts(dropna=False).to_dict()
            if "forward_source" in enriched
            else {}
        )
        print(
            f"{trade_date} rows={total} ok_iv={ok_iv} "
            f"ok_iv_ratio={(ok_iv / total if total else 0):.2%} "
            f"forward_sources={forward_sources} output={output}"
        )


if __name__ == "__main__":
    main()
