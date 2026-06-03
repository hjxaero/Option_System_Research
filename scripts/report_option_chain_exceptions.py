from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.reader import OptionChainSnapshotReader


def _read_sidecars(reader: OptionChainSnapshotReader, product: str, dates: list[str]) -> pd.DataFrame:
    frames = []
    columns = [
        "product",
        "trade_date",
        "timestamp",
        "structure_type",
        "term_role",
        "candidate_quality",
        "candidate_reason",
        "candidate_expiry_phase",
        "candidate_expiry_phase_rank",
        "candidate_pool",
        "candidate_pool_reason",
        "net_delta",
        "net_mark",
    ]
    for trade_date in dates:
        path = reader.strategy_candidates_path(product, trade_date)
        if not path.exists():
            continue
        try:
            frame = pd.read_parquet(path, columns=columns)
        except Exception:
            frame = pd.read_parquet(path)
            for column in columns:
                if column not in frame.columns:
                    frame[column] = pd.NA
            frame = frame[columns]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _date_range(reader: OptionChainSnapshotReader, product: str, start: str | None, end: str | None) -> list[str]:
    root = reader.data_root / "snapshots" / reader.snapshot_kind / product.upper()
    dates = sorted(path.name.split(".strategy_candidates.parquet")[0] for path in root.glob("*.strategy_candidates.parquet"))
    if start is not None:
        dates = [date for date in dates if date >= start]
    if end is not None:
        dates = [date for date in dates if date <= end]
    return dates


def _ratio(count: int, total: int) -> float:
    return 0.0 if total == 0 else count / total


def _with_quality_scope(candidates: pd.DataFrame, quality_scope: str) -> pd.DataFrame:
    if "candidate_expiry_phase" not in candidates.columns:
        result = candidates.copy()
    elif quality_scope == "normal_phase":
        result = candidates[candidates["candidate_expiry_phase"].fillna("").isin(["normal"])].copy()
    elif quality_scope == "near_expiry_phase":
        result = candidates[candidates["candidate_expiry_phase"].fillna("").isin(["last_3_trading_days", "final_trading_day"])].copy()
    else:
        result = candidates.copy()
    result["quality_scope"] = quality_scope
    return result


def _scoped_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frames = [
        _with_quality_scope(candidates, "all_phase"),
        _with_quality_scope(candidates, "normal_phase"),
        _with_quality_scope(candidates, "near_expiry_phase"),
    ]
    return pd.concat(frames, ignore_index=True)


def _daily_summary(candidates: pd.DataFrame, *, quality_scope: str) -> pd.DataFrame:
    rows = []
    for trade_date, group in candidates.groupby("trade_date", sort=True):
        total = int(len(group))
        ok = int((group["candidate_quality"] == "ok").sum())
        conditional = int((group["candidate_quality"] == "conditional").sum())
        rejected = int((group["candidate_quality"] == "rejected").sum())
        rows.append(
            {
                "trade_date": str(trade_date),
                "quality_scope": quality_scope,
                "candidate_count": total,
                "ok_count": ok,
                "conditional_count": conditional,
                "rejected_count": rejected,
                "ok_ratio": _ratio(ok, total),
                "conditional_ratio": _ratio(conditional, total),
                "rejected_ratio": _ratio(rejected, total),
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame, columns: list[str], *, percent_columns: set[str] | None = None, limit: int | None = None) -> str:
    if frame.empty:
        return "_none_"
    percent_columns = percent_columns or set()
    view = frame[columns].head(limit).copy() if limit is not None else frame[columns].copy()
    for column in percent_columns & set(view.columns):
        view[column] = view[column].map(lambda value: f"{float(value):.2%}")
    lines = [
        "| " + " | ".join(str(column) for column in view.columns) + " |",
        "| " + " | ".join("---" for _ in view.columns) + " |",
    ]
    for _, row in view.iterrows():
        values = ["" if pd.isna(row[column]) else str(row[column]) for column in view.columns]
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    return "\n".join(lines)


def build_report(
    candidates: pd.DataFrame,
    *,
    product: str,
    start: str,
    end: str,
    ok_ratio_floor: float,
    rejected_ratio_floor: float,
) -> tuple[str, pd.DataFrame]:
    scoped = _scoped_candidates(candidates)
    daily_frames = [
        _daily_summary(scoped[scoped["quality_scope"] == quality_scope], quality_scope=quality_scope)
        for quality_scope in ("all_phase", "normal_phase", "near_expiry_phase")
    ]
    daily = pd.concat(daily_frames, ignore_index=True)
    if daily.empty:
        return f"# {product} option-chain exception report\n\nNo strategy candidate sidecars found.\n", daily

    normal_daily = daily[daily["quality_scope"] == "normal_phase"].copy()
    exceptions = normal_daily[
        (normal_daily["ok_ratio"] < ok_ratio_floor) | (normal_daily["rejected_ratio"] > rejected_ratio_floor)
    ].copy()
    reason = (
        scoped.groupby(["quality_scope", "candidate_quality", "candidate_reason"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["quality_scope", "count"], ascending=[True, False])
    )
    structure = (
        scoped.groupby(["quality_scope", "structure_type", "candidate_quality"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    phase = (
        candidates.groupby(["candidate_expiry_phase", "candidate_quality"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reset_index()
        .sort_values("candidate_expiry_phase")
    )
    pool = (
        candidates.groupby(["candidate_pool", "candidate_quality"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reset_index()
        .sort_values("candidate_pool")
    )
    quality = candidates["candidate_quality"].value_counts(dropna=False)
    scope_summary = (
        daily.groupby("quality_scope", sort=False)[["candidate_count", "ok_count", "conditional_count", "rejected_count"]]
        .sum()
        .reset_index()
    )
    scope_summary["ok_ratio"] = scope_summary.apply(lambda row: _ratio(int(row["ok_count"]), int(row["candidate_count"])), axis=1)
    scope_summary["rejected_ratio"] = scope_summary.apply(
        lambda row: _ratio(int(row["rejected_count"]), int(row["candidate_count"])),
        axis=1,
    )

    lines = [
        f"# {product.upper()} option-chain exception report",
        "",
        f"Range: {start} to {end}",
        "",
        "## Overall",
        "",
        f"- trading_days: {daily['trade_date'].nunique()}",
        f"- candidate_count: {len(candidates)}",
        f"- ok: {int(quality.get('ok', 0))}",
        f"- conditional: {int(quality.get('conditional', 0))}",
        f"- rejected: {int(quality.get('rejected', 0))}",
        "",
        "## Standard Quality Scopes",
        "",
        _markdown_table(
            scope_summary,
            ["quality_scope", "candidate_count", "ok_ratio", "rejected_ratio"],
            percent_columns={"ok_ratio", "rejected_ratio"},
        ),
        "",
        "## Exception Days (Normal Phase)",
        "",
        _markdown_table(
            exceptions.sort_values(["ok_ratio", "rejected_ratio"], ascending=[True, False]),
            ["trade_date", "quality_scope", "candidate_count", "ok_ratio", "conditional_ratio", "rejected_ratio"],
            percent_columns={"ok_ratio", "conditional_ratio", "rejected_ratio"},
        ),
        "",
        "## Top Reasons By Scope",
        "",
        _markdown_table(reason, ["quality_scope", "candidate_quality", "candidate_reason", "count"], limit=25),
        "",
        "## Structure Quality By Scope",
        "",
        _markdown_table(structure, list(structure.columns)),
        "",
        "## Expiry Phase Quality",
        "",
        _markdown_table(phase, list(phase.columns)),
        "",
        "## Candidate Pool Quality",
        "",
        _markdown_table(pool, list(pool.columns)),
        "",
    ]
    return "\n".join(lines), exceptions


def main() -> None:
    parser = argparse.ArgumentParser(description="Build option-chain strategy exception report from sidecars.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--snapshot-kind", default="four_term_enriched_month_trial")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--ok-ratio-floor", type=float, default=0.60)
    parser.add_argument("--rejected-ratio-floor", type=float, default=0.02)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--csv-output", type=Path, default=None)
    args = parser.parse_args()

    reader = OptionChainSnapshotReader(data_root=args.data_root, snapshot_kind=args.snapshot_kind)
    dates = _date_range(reader, args.product, args.start, args.end)
    candidates = _read_sidecars(reader, args.product, dates)
    start = args.start or (dates[0] if dates else "")
    end = args.end or (dates[-1] if dates else "")
    report, exceptions = build_report(
        candidates,
        product=args.product,
        start=start,
        end=end,
        ok_ratio_floor=args.ok_ratio_floor,
        rejected_ratio_floor=args.rejected_ratio_floor,
    )

    output = args.output or Path(f"artifacts/option_chain/{args.product.lower()}_exception_report_{start}_{end}.md")
    csv_output = args.csv_output or output.with_suffix(".csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    exceptions.to_csv(csv_output, index=False)
    print(output)
    print(csv_output)


if __name__ == "__main__":
    main()
