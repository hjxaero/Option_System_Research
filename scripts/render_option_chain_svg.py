from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


COLORS = {
    "call": "#d97706",
    "put": "#2563eb",
    "forward": "#111827",
    "grid": "#e5e7eb",
    "text": "#111827",
    "muted": "#6b7280",
}


def _float(value: str) -> float | None:
    try:
        if value == "":
            return None
        return float(value)
    except ValueError:
        return None


def load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("raw_iv_quality") != "ok":
                continue
            rows.append(
                {
                    "expiry_date": row["expiry_date"],
                    "option_type": row["option_type"],
                    "strike_price": _float(row["strike_price"]),
                    "mark_price": _float(row["mark_price"]),
                    "forward": _float(row["forward"]),
                    "raw_iv": _float(row["raw_iv"]),
                    "raw_delta": _float(row["raw_delta"]),
                }
            )
    return [row for row in rows if row["strike_price"] is not None and row["raw_iv"] is not None]


def _scale(value: float, domain: tuple[float, float], range_: tuple[float, float]) -> float:
    low, high = domain
    start, end = range_
    if high == low:
        return (start + end) / 2
    return start + (value - low) / (high - low) * (end - start)


def _polyline(points: list[tuple[float, float]], color: str) -> str:
    if not points:
        return ""
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />'


def render_svg(rows: list[dict[str, object]], output: Path) -> None:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["expiry_date"])].append(row)

    expiries = sorted(grouped)
    width = 1400
    panel_w = 640
    panel_h = 300
    gap_x = 50
    gap_y = 70
    margin_x = 60
    margin_y = 100
    height = margin_y + 2 * panel_h + gap_y + 80

    timestamp = "unknown"
    title = "MO Option Chain - Black76 Raw IV Smile"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff" />',
        f'<text x="60" y="48" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="{COLORS["text"]}">{title}</text>',
        f'<text x="60" y="76" font-family="Arial, sans-serif" font-size="14" fill="{COLORS["muted"]}">Call and put raw implied volatility by strike. Vertical line = parity-implied forward.</text>',
    ]

    for idx, expiry in enumerate(expiries[:4]):
        col = idx % 2
        row_idx = idx // 2
        x0 = margin_x + col * (panel_w + gap_x)
        y0 = margin_y + row_idx * (panel_h + gap_y)
        data = grouped[expiry]
        strikes = [float(item["strike_price"]) for item in data]
        ivs = [float(item["raw_iv"]) for item in data]
        forward = float(data[0]["forward"])
        x_domain = (min(strikes), max(strikes))
        y_domain = (max(min(ivs) - 0.01, 0), max(ivs) + 0.01)
        chart_left = x0 + 55
        chart_right = x0 + panel_w - 25
        chart_top = y0 + 45
        chart_bottom = y0 + panel_h - 45

        parts.append(f'<rect x="{x0}" y="{y0}" width="{panel_w}" height="{panel_h}" rx="8" fill="#f9fafb" stroke="#d1d5db" />')
        parts.append(f'<text x="{x0 + 22}" y="{y0 + 30}" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="{COLORS["text"]}">Expiry {expiry}</text>')
        parts.append(f'<text x="{x0 + panel_w - 190}" y="{y0 + 30}" font-family="Arial, sans-serif" font-size="13" fill="{COLORS["muted"]}">Forward {forward:.2f}</text>')

        for step in range(5):
            y = chart_bottom - step * (chart_bottom - chart_top) / 4
            iv = y_domain[0] + step * (y_domain[1] - y_domain[0]) / 4
            parts.append(f'<line x1="{chart_left}" y1="{y:.1f}" x2="{chart_right}" y2="{y:.1f}" stroke="{COLORS["grid"]}" />')
            parts.append(f'<text x="{chart_left - 45}" y="{y + 4:.1f}" font-family="Arial, sans-serif" font-size="11" fill="{COLORS["muted"]}">{iv * 100:.1f}%</text>')

        for step in range(5):
            x = chart_left + step * (chart_right - chart_left) / 4
            strike = x_domain[0] + step * (x_domain[1] - x_domain[0]) / 4
            parts.append(f'<line x1="{x:.1f}" y1="{chart_top}" x2="{x:.1f}" y2="{chart_bottom}" stroke="{COLORS["grid"]}" />')
            parts.append(f'<text x="{x - 18:.1f}" y="{chart_bottom + 22}" font-family="Arial, sans-serif" font-size="11" fill="{COLORS["muted"]}">{strike:.0f}</text>')

        forward_x = _scale(forward, x_domain, (chart_left, chart_right))
        parts.append(f'<line x1="{forward_x:.1f}" y1="{chart_top}" x2="{forward_x:.1f}" y2="{chart_bottom}" stroke="{COLORS["forward"]}" stroke-width="1.8" stroke-dasharray="5,5" />')

        for option_type in ("call", "put"):
            series = sorted(
                [item for item in data if item["option_type"] == option_type],
                key=lambda item: float(item["strike_price"]),
            )
            points = [
                (
                    _scale(float(item["strike_price"]), x_domain, (chart_left, chart_right)),
                    _scale(float(item["raw_iv"]), y_domain, (chart_bottom, chart_top)),
                )
                for item in series
            ]
            parts.append(_polyline(points, COLORS[option_type]))
            for x, y in points:
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{COLORS[option_type]}" />')

        parts.append(f'<text x="{chart_right - 145}" y="{chart_top + 18}" font-family="Arial, sans-serif" font-size="12" fill="{COLORS["call"]}">Call IV</text>')
        parts.append(f'<text x="{chart_right - 80}" y="{chart_top + 18}" font-family="Arial, sans-serif" font-size="12" fill="{COLORS["put"]}">Put IV</text>')
        parts.append(f'<text x="{chart_left}" y="{chart_bottom + 40}" font-family="Arial, sans-serif" font-size="12" fill="{COLORS["muted"]}">Strike</text>')
    parts.append("</svg>")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render option-chain pricing experiment as SVG.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = load_rows(args.input)
    if not rows:
        raise SystemExit("No ok IV rows found.")
    render_svg(rows, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
