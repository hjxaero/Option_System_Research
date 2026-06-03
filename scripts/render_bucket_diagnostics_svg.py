from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.option_chain.reader import OptionChainSnapshotReader


COLORS = {
    "background": "#ffffff",
    "panel": "#f8fafc",
    "grid": "#e5e7eb",
    "axis": "#475569",
    "text": "#111827",
    "muted": "#64748b",
    "call": "#c2410c",
    "put": "#2563eb",
    "forward": "#111827",
    "ok": "#15803d",
    "loose": "#b45309",
    "bad": "#b91c1c",
    "atm": "#7c3aed",
}


def _scale(value: float, domain: tuple[float, float], range_: tuple[float, float]) -> float:
    low, high = domain
    start, end = range_
    if high == low:
        return (start + end) / 2
    return start + (value - low) / (high - low) * (end - start)


def _fmt(value: object, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.{digits}f}"


def _text(x: float, y: float, value: str, *, size: int = 12, weight: str = "400", color: str | None = None) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{color or COLORS["text"]}">'
        f"{html.escape(value)}</text>"
    )


def _line(x1: float, y1: float, x2: float, y2: float, *, color: str, width: float = 1.0, dash: str | None = None) -> str:
    dash_attr = "" if dash is None else f' stroke-dasharray="{dash}"'
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{dash_attr} />'


def _rect(x: float, y: float, w: float, h: float, *, fill: str, stroke: str = "#d1d5db", radius: int = 8) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius}" fill="{fill}" stroke="{stroke}" />'


def _circle(x: float, y: float, r: float, *, fill: str, stroke: str = "#ffffff", width: float = 1.5) -> str:
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" />'


def _quality_color(value: object) -> str:
    quality = str(value)
    return COLORS.get(quality, COLORS["muted"])


def _axis_panel(parts: list[str], frame: pd.DataFrame, *, term_role: str, x0: float, y0: float, w: float, h: float) -> None:
    term = frame[(frame["term_role"] == term_role) & frame["bucket_primary"].notna()].copy()
    parts.append(_rect(x0, y0, w, h, fill=COLORS["panel"]))
    if term.empty:
        parts.append(_text(x0 + 22, y0 + 34, f"{term_role}: no bucket rows", size=18, weight="700"))
        return

    expiry = str(term["expiry_date"].iloc[0])[:10]
    forward = float(pd.to_numeric(term["resolved_forward"].fillna(term["forward"]), errors="coerce").dropna().iloc[0])
    strikes = pd.to_numeric(term["strike_price"], errors="coerce").dropna()
    x_domain = (min(float(strikes.min()), forward) - 80, max(float(strikes.max()), forward) + 80)
    chart_left = x0 + 68
    chart_right = x0 + w - 32
    chart_top = y0 + 70
    chart_bottom = y0 + h - 78
    y_call = chart_top + 44
    y_put = chart_bottom - 44

    parts.append(_text(x0 + 22, y0 + 34, f"{term_role}  {expiry}", size=18, weight="700"))
    parts.append(_text(x0 + w - 190, y0 + 34, f"forward {_fmt(forward, 1)}", size=13, color=COLORS["muted"]))

    for step in range(5):
        x = chart_left + step * (chart_right - chart_left) / 4
        strike = x_domain[0] + step * (x_domain[1] - x_domain[0]) / 4
        parts.append(_line(x, chart_top, x, chart_bottom, color=COLORS["grid"]))
        parts.append(_text(x - 20, chart_bottom + 28, f"{strike:.0f}", size=11, color=COLORS["muted"]))

    parts.append(_line(chart_left, y_call, chart_right, y_call, color=COLORS["call"], width=1.5))
    parts.append(_line(chart_left, y_put, chart_right, y_put, color=COLORS["put"], width=1.5))
    parts.append(_text(chart_left - 48, y_call + 4, "Call", size=12, weight="700", color=COLORS["call"]))
    parts.append(_text(chart_left - 40, y_put + 4, "Put", size=12, weight="700", color=COLORS["put"]))

    fx = _scale(forward, x_domain, (chart_left, chart_right))
    parts.append(_line(fx, chart_top, fx, chart_bottom, color=COLORS["forward"], width=2.0, dash="5,5"))
    parts.append(_text(fx + 6, chart_top + 15, "F", size=13, weight="700", color=COLORS["forward"]))

    order = {"25D_call": 1, "50D_call": 2, "ATM_call": 3, "ATM_put": 4, "50D_put": 5, "25D_put": 6}
    term["order"] = term["delta_bucket"].map(order).fillna(99)
    for _, row in term.sort_values(["order", "strike_price"]).iterrows():
        x = _scale(float(row["strike_price"]), x_domain, (chart_left, chart_right))
        y = y_call if row["option_type"] == "call" else y_put
        color = _quality_color(row.get("bucket_quality"))
        is_atm = "ATM" in str(row.get("bucket_ids"))
        radius = 8.0 if is_atm else 6.0
        parts.append(_line(x, y - 36, x, y + 36, color=color, width=1.0, dash="3,3"))
        parts.append(_circle(x, y, radius, fill=COLORS["atm"] if is_atm else color, stroke="#ffffff", width=2.0))
        label = f"{row['delta_bucket']} K{float(row['strike_price']):.0f}"
        detail = f"δ {_fmt(row['delta'], 3)} tgt {_fmt(row['bucket_target_delta'], 2)} err {_fmt(row['bucket_delta_error'], 3)} {row['bucket_quality']}"
        dy = -46 if row["option_type"] == "call" else 56
        parts.append(_text(x - 48, y + dy, label, size=11, weight="700", color=COLORS["text"]))
        parts.append(_text(x - 48, y + dy + 15, detail, size=10, color=color))

    atm = term[term["is_atm_straddle_candidate"] == True]  # noqa: E712
    if len(atm) == 2:
        xs = [_scale(float(value), x_domain, (chart_left, chart_right)) for value in atm["strike_price"]]
        if abs(xs[0] - xs[1]) < 0.01:
            parts.append(_line(xs[0], y_call, xs[1], y_put, color=COLORS["atm"], width=2.0, dash="6,4"))
            parts.append(_text(xs[0] + 8, (y_call + y_put) / 2, "ATM straddle", size=11, weight="700", color=COLORS["atm"]))


def _summary_table(parts: list[str], frame: pd.DataFrame, *, x0: float, y0: float, w: float) -> None:
    bucket = frame[frame["bucket_primary"].notna()].copy()
    parts.append(_text(x0, y0, "Bucket diagnostics table", size=20, weight="700"))
    headers = ["term", "bucket", "symbol", "K", "delta", "target", "error", "quality"]
    widths = [120, 90, 190, 70, 70, 70, 70, 80]
    y = y0 + 26
    parts.append(_rect(x0, y, w, 28, fill="#f1f5f9", stroke="#cbd5e1", radius=4))
    x = x0 + 10
    for header, width in zip(headers, widths):
        parts.append(_text(x, y + 19, header, size=11, weight="700", color=COLORS["muted"]))
        x += width
    y += 34
    view = bucket[bucket["term_role"].isin(["current_month", "next_month"])].sort_values(["term_role", "option_type", "strike_price"])
    for _, row in view.head(14).iterrows():
        parts.append(_line(x0, y + 7, x0 + w, y + 7, color="#e2e8f0"))
        x = x0 + 10
        values = [
            str(row["term_role"]),
            str(row["delta_bucket"]),
            str(row["symbol"]).replace("CFFEX.", ""),
            f"{float(row['strike_price']):.0f}",
            _fmt(row["delta"], 3),
            _fmt(row["bucket_target_delta"], 2),
            _fmt(row["bucket_delta_error"], 3),
            str(row["bucket_quality"]),
        ]
        for value, width in zip(values, widths):
            color = _quality_color(row["bucket_quality"]) if value == str(row["bucket_quality"]) else COLORS["text"]
            parts.append(_text(x, y + 24, value, size=11, color=color, weight="700" if value == str(row["bucket_quality"]) else "400"))
            x += width
        y += 26


def render(product: str, trade_date: str, timestamp: str, snapshot_kind: str, data_root: Path, output: Path) -> None:
    reader = OptionChainSnapshotReader(data_root=data_root, snapshot_kind=snapshot_kind)
    columns = [
        "timestamp",
        "term_role",
        "expiry_date",
        "symbol",
        "option_type",
        "strike_price",
        "forward",
        "resolved_forward",
        "delta",
        "bucket_ids",
        "bucket_primary",
        "delta_bucket",
        "bucket_target_delta",
        "bucket_delta_error",
        "bucket_quality",
        "is_atm_straddle_candidate",
    ]
    frame = reader.load_frame(product, trade_date, timestamp, columns=columns)

    width = 1500
    height = 960
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{COLORS["background"]}" />',
        _text(44, 48, "MO bucket rule diagnostics", size=28, weight="700"),
        _text(44, 76, f"{trade_date}  {pd.Timestamp(timestamp).strftime('%H:%M')}  |  target delta, actual delta, error and quality", size=14, color=COLORS["muted"]),
        _text(1120, 52, "green ok", size=12, weight="700", color=COLORS["ok"]),
        _text(1120, 72, "amber loose", size=12, weight="700", color=COLORS["loose"]),
        _text(1220, 72, "red bad", size=12, weight="700", color=COLORS["bad"]),
    ]
    _axis_panel(parts, frame, term_role="current_month", x0=44, y0=110, w=700, h=360)
    _axis_panel(parts, frame, term_role="next_month", x0=780, y0=110, w=670, h=360)
    _summary_table(parts, frame, x0=44, y0=535, w=900)
    parts.append(_text(980, 560, "Reading guide", size=20, weight="700"))
    parts.append(_text(980, 590, "ATM is selected by forward-nearest common strike.", size=13, color=COLORS["text"]))
    parts.append(_text(980, 616, "50D and 25D are selected by closest delta.", size=13, color=COLORS["text"]))
    parts.append(_text(980, 642, "ATM and 50D may be different strikes.", size=13, color=COLORS["text"]))
    parts.append(_text(980, 680, "This chart is for rule calibration, not signal generation.", size=13, color=COLORS["muted"]))
    parts.append("</svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render bucket rule diagnostics as SVG.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--trade-date", default="2022-08-10")
    parser.add_argument("--timestamp", default="2022-08-10 10:00:00")
    parser.add_argument("--snapshot-kind", default="four_term_enriched_month_trial")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/option_chain/mo_bucket_diagnostics_2022-08-10_1000.svg"))
    args = parser.parse_args()
    render(args.product, args.trade_date, args.timestamp, args.snapshot_kind, args.data_root, args.output)


if __name__ == "__main__":
    main()
