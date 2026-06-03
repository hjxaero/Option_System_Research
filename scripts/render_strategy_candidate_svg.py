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
    "atm": "#111827",
    "bucket": "#059669",
    "calendar": "#7c3aed",
    "ok": "#15803d",
    "conditional": "#b45309",
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


def _text(x: float, y: float, text: str, *, size: int = 13, weight: str = "400", color: str | None = None) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{color or COLORS["text"]}">'
        f"{html.escape(text)}</text>"
    )


def _line(x1: float, y1: float, x2: float, y2: float, *, color: str, width: float = 1.0, dash: str | None = None) -> str:
    dash_attr = "" if dash is None else f' stroke-dasharray="{dash}"'
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{dash_attr} />'


def _polyline(points: list[tuple[float, float]], color: str) -> str:
    if not points:
        return ""
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />'


def _circle(x: float, y: float, r: float, *, fill: str, stroke: str = "#ffffff", width: float = 1.2) -> str:
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" />'


def _rect(x: float, y: float, w: float, h: float, *, fill: str, stroke: str = "#d1d5db", radius: int = 8) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius}" fill="{fill}" stroke="{stroke}" />'


def _term_panel(parts: list[str], frame: pd.DataFrame, *, term_role: str, x0: float, y0: float, w: float, h: float) -> None:
    term = frame[(frame["term_role"] == term_role) & frame["iv"].notna()].copy()
    if term.empty:
        parts.append(_rect(x0, y0, w, h, fill=COLORS["panel"]))
        parts.append(_text(x0 + 22, y0 + 32, f"{term_role}: no data", size=18, weight="700"))
        return

    expiry = str(term["expiry_date"].iloc[0])[:10]
    strikes = pd.to_numeric(term["strike_price"], errors="coerce").dropna()
    ivs = pd.to_numeric(term["iv"], errors="coerce").dropna()
    x_domain = (float(strikes.min()), float(strikes.max()))
    y_domain = (max(float(ivs.min()) - 0.01, 0.0), float(ivs.max()) + 0.01)
    chart_left = x0 + 62
    chart_right = x0 + w - 28
    chart_top = y0 + 62
    chart_bottom = y0 + h - 54

    parts.append(_rect(x0, y0, w, h, fill=COLORS["panel"]))
    parts.append(_text(x0 + 22, y0 + 32, f"{term_role}  {expiry}", size=18, weight="700"))
    parts.append(_text(x0 + w - 190, y0 + 32, "IV smile by strike", size=13, color=COLORS["muted"]))

    for step in range(5):
        y = chart_bottom - step * (chart_bottom - chart_top) / 4
        iv = y_domain[0] + step * (y_domain[1] - y_domain[0]) / 4
        parts.append(_line(chart_left, y, chart_right, y, color=COLORS["grid"]))
        parts.append(_text(chart_left - 50, y + 4, f"{iv * 100:.1f}%", size=11, color=COLORS["muted"]))
    for step in range(5):
        x = chart_left + step * (chart_right - chart_left) / 4
        strike = x_domain[0] + step * (x_domain[1] - x_domain[0]) / 4
        parts.append(_line(x, chart_top, x, chart_bottom, color=COLORS["grid"]))
        parts.append(_text(x - 22, chart_bottom + 24, f"{strike:.0f}", size=11, color=COLORS["muted"]))

    forward = pd.to_numeric(term.get("forward"), errors="coerce").dropna()
    if not forward.empty:
        fx = _scale(float(forward.iloc[0]), x_domain, (chart_left, chart_right))
        parts.append(_line(fx, chart_top, fx, chart_bottom, color=COLORS["axis"], width=1.6, dash="5,5"))
        parts.append(_text(fx + 6, chart_top + 14, f"F {_fmt(forward.iloc[0], 1)}", size=11, color=COLORS["axis"]))

    point_lookup: dict[str, tuple[float, float]] = {}
    for option_type in ("call", "put"):
        side = term[term["option_type"] == option_type].sort_values("strike_price")
        points = []
        for _, row in side.iterrows():
            strike = float(row["strike_price"])
            iv = float(row["iv"])
            x = _scale(strike, x_domain, (chart_left, chart_right))
            y = _scale(iv, y_domain, (chart_bottom, chart_top))
            points.append((x, y))
            point_lookup[str(row["symbol"])] = (x, y)
        parts.append(_polyline(points, COLORS[option_type]))
        for x, y in points:
            parts.append(_circle(x, y, 2.4, fill=COLORS[option_type], stroke=COLORS[option_type], width=0.5))

    bucket_rows = term[term["bucket_ids"].notna()].copy()
    for _, row in bucket_rows.iterrows():
        point = point_lookup.get(str(row["symbol"]))
        if point is None:
            continue
        x, y = point
        bucket_ids = str(row["bucket_ids"])
        is_atm = "ATM" in bucket_ids
        fill = COLORS["atm"] if is_atm else COLORS["bucket"]
        radius = 7.0 if is_atm else 5.4
        parts.append(_circle(x, y, radius, fill=fill, stroke="#ffffff", width=2.0))
        label = "ATM" if is_atm else str(row["delta_bucket"]).replace("_", " ")
        dy = -12 if row["option_type"] == "call" else 22
        parts.append(_text(x + 8, y + dy, label, size=11, weight="700", color=fill))

    atm = bucket_rows[bucket_rows["is_atm_straddle_candidate"] == True]  # noqa: E712
    if len(atm) == 2:
        points = [point_lookup.get(str(symbol)) for symbol in atm["symbol"]]
        if all(point is not None for point in points):
            parts.append(_line(points[0][0], points[0][1], points[1][0], points[1][1], color=COLORS["atm"], width=2.0, dash="4,4"))

    parts.append(_text(chart_right - 150, chart_top + 18, "Call", size=12, weight="700", color=COLORS["call"]))
    parts.append(_text(chart_right - 92, chart_top + 18, "Put", size=12, weight="700", color=COLORS["put"]))
    parts.append(_text(chart_left, chart_bottom + 42, "Strike", size=12, color=COLORS["muted"]))


def _candidate_cards(parts: list[str], candidates: pd.DataFrame, *, x0: float, y0: float) -> None:
    front = candidates[
        candidates["structure_type"].isin(["atm_straddle", "25d_strangle", "25d_risk_reversal", "atm_call_calendar", "atm_put_calendar"])
    ].copy()
    order = {
        "atm_straddle": 0,
        "25d_strangle": 1,
        "25d_risk_reversal": 2,
        "atm_call_calendar": 3,
        "atm_put_calendar": 4,
    }
    front["order"] = front["structure_type"].map(order).fillna(99)
    front = front.sort_values(["order", "term_role"]).head(8)

    parts.append(_text(x0, y0 - 20, "Strategy candidate structures", size=20, weight="700"))
    card_w = 350
    card_h = 92
    gap = 18
    for idx, (_, row) in enumerate(front.iterrows()):
        col = idx % 4
        line = idx // 4
        x = x0 + col * (card_w + gap)
        y = y0 + line * (card_h + gap)
        quality = str(row.get("candidate_quality", ""))
        accent = COLORS["ok"] if quality == "ok" else COLORS["conditional"]
        parts.append(_rect(x, y, card_w, card_h, fill="#ffffff", stroke="#d4d4d8", radius=8))
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="5" height="{card_h:.1f}" rx="2" fill="{accent}" />')
        parts.append(_text(x + 16, y + 24, str(row["structure_type"]), size=14, weight="700"))
        parts.append(_text(x + 220, y + 24, quality, size=12, weight="700", color=accent))
        parts.append(_text(x + 16, y + 45, str(row["term_role"]), size=12, color=COLORS["muted"]))
        parts.append(
            _text(
                x + 16,
                y + 68,
                f"net mark {_fmt(row.get('net_mark'), 1)}   delta {_fmt(row.get('net_delta'), 3)}   vega {_fmt(row.get('net_vega'), 0)}",
                size=12,
                color=COLORS["text"],
            )
        )


def render(product: str, trade_date: str, timestamp: str, snapshot_kind: str, data_root: Path, output: Path) -> None:
    reader = OptionChainSnapshotReader(data_root=data_root, snapshot_kind=snapshot_kind)
    columns = list(dict.fromkeys([*reader.load_bucket_frame(product, trade_date, timestamp).columns, "forward"]))
    frame = pd.read_parquet(reader.snapshot_path(product, trade_date), columns=columns)
    frame = frame[pd.to_datetime(frame["timestamp"]) == pd.Timestamp(timestamp)].copy()
    candidates = reader.get_strategy_candidates(product, trade_date, timestamp)

    width = 1500
    height = 950
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{COLORS["background"]}" />',
        _text(44, 48, "MO candidate structure map", size=28, weight="700"),
        _text(44, 76, f"{trade_date}  {pd.Timestamp(timestamp).strftime('%H:%M')}  |  ATM, 25D, straddle and calendar legs", size=14, color=COLORS["muted"]),
        _text(1140, 52, "black = ATM / straddle", size=12, color=COLORS["atm"]),
        _text(1140, 72, "green = 25D bucket", size=12, color=COLORS["bucket"]),
    ]
    _term_panel(parts, frame, term_role="current_month", x0=44, y0=105, w=700, h=360)
    _term_panel(parts, frame, term_role="next_month", x0=780, y0=105, w=670, h=360)
    _candidate_cards(parts, candidates, x0=44, y0=535)
    parts.append("</svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render option-chain strategy candidate structure map as SVG.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--trade-date", default="2022-08-10")
    parser.add_argument("--timestamp", default="2022-08-10 10:00:00")
    parser.add_argument("--snapshot-kind", default="four_term_enriched_month_trial")
    parser.add_argument("--data-root", type=Path, default=Path("data_store"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/option_chain/mo_candidate_structure_2022-08-10_1000.svg"))
    args = parser.parse_args()
    render(args.product, args.trade_date, args.timestamp, args.snapshot_kind, args.data_root, args.output)


if __name__ == "__main__":
    main()
