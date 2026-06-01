from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from option_platform.pricing import black76_price_and_greeks, implied_volatility_black76


def _positive(value: object) -> bool:
    return value is not None and not pd.isna(value) and float(value) > 0


def choose_timestamp(frame: pd.DataFrame) -> pd.Timestamp:
    quality = (
        frame.groupby("timestamp")
        .agg(
            rows=("symbol", "size"),
            marks=("mark_price", lambda s: s.notna().sum()),
            ok_quotes=("quote_quality", lambda s: (s == "ok").sum()),
            wide_quotes=("quote_quality", lambda s: (s == "wide_spread").sum()),
        )
        .sort_values(["ok_quotes", "marks"], ascending=False)
    )
    return pd.Timestamp(quality.index[0])


def business_time_to_expiry(timestamp: pd.Timestamp, expiry_date: object) -> float:
    expiry = pd.Timestamp(expiry_date).date()
    current = timestamp.date()
    if current > expiry:
        return 1 / 252
    days = pd.bdate_range(current, expiry)
    elapsed_fraction = 0.0
    if timestamp.time() >= pd.Timestamp("15:00").time():
        elapsed_fraction = 1.0
    return max((len(days) - elapsed_fraction) / 252, 1 / (252 * 240))


def infer_forwards(snapshot: pd.DataFrame, risk_free_rate: float) -> pd.DataFrame:
    rows = []
    for expiry, group in snapshot.groupby("expiry_date"):
        calls = group[group["option_type"] == "call"].set_index("strike_price")
        puts = group[group["option_type"] == "put"].set_index("strike_price")
        common_strikes = sorted(set(calls.index) & set(puts.index))
        t_years = business_time_to_expiry(pd.Timestamp(group["timestamp"].iloc[0]), expiry)
        discount = __import__("math").exp(-risk_free_rate * t_years)

        candidates = []
        for strike in common_strikes:
            call_price = calls.loc[strike, "mark_price"]
            put_price = puts.loc[strike, "mark_price"]
            if _positive(call_price) and _positive(put_price):
                candidates.append(float(strike) + (float(call_price) - float(put_price)) / discount)

        if candidates:
            rows.append(
                {
                    "expiry_date": expiry,
                    "forward": float(pd.Series(candidates).median()),
                    "forward_pairs": len(candidates),
                    "t_years": t_years,
                }
            )
    return pd.DataFrame(rows)


def run_experiment(
    *,
    snapshot_path: Path,
    timestamp: str | None,
    risk_free_rate: float,
    output_path: Path,
) -> pd.DataFrame:
    frame = pd.read_parquet(snapshot_path)
    target_ts = pd.Timestamp(timestamp) if timestamp else choose_timestamp(frame)
    snapshot = frame[pd.to_datetime(frame["timestamp"]) == target_ts].copy()
    if snapshot.empty:
        raise ValueError(f"No rows found for timestamp {target_ts}")

    forwards = infer_forwards(snapshot, risk_free_rate)
    if forwards.empty:
        raise ValueError("Could not infer any expiry forward from paired call/put mark prices")

    forward_by_expiry = forwards.set_index("expiry_date").to_dict("index")
    output_rows = []
    for _, row in snapshot.iterrows():
        expiry = row["expiry_date"]
        forward_info = forward_by_expiry.get(expiry)
        if not forward_info:
            continue
        market_price = row.get("mark_price")
        right = row["option_type"]
        strike = float(row["strike_price"])
        forward = float(forward_info["forward"])
        t_years = float(forward_info["t_years"])
        iv = implied_volatility_black76(
            right=right,
            forward=forward,
            strike=strike,
            time_to_expiry=t_years,
            risk_free_rate=risk_free_rate,
            market_price=None if pd.isna(market_price) else float(market_price),
        )
        greeks = None
        if iv.implied_volatility is not None:
            greeks = black76_price_and_greeks(
                right=right,
                forward=forward,
                strike=strike,
                time_to_expiry=t_years,
                risk_free_rate=risk_free_rate,
                volatility=iv.implied_volatility,
            )

        output_rows.append(
            {
                "timestamp": target_ts,
                "symbol": row["symbol"],
                "expiry_date": expiry,
                "option_type": right,
                "strike_price": strike,
                "forward": forward,
                "forward_pairs": int(forward_info["forward_pairs"]),
                "t_years": t_years,
                "mark_price": market_price,
                "quote_quality": row.get("quote_quality"),
                "price_source": row.get("price_source"),
                "spread_bps": row.get("spread_bps"),
                "raw_iv": iv.implied_volatility,
                "raw_iv_quality": iv.quality,
                "raw_delta": None if greeks is None else greeks.delta,
                "raw_gamma": None if greeks is None else greeks.gamma,
                "raw_theta": None if greeks is None else greeks.theta,
                "raw_vega": None if greeks is None else greeks.vega,
                "pricing_error": iv.pricing_error,
            }
        )

    result = pd.DataFrame(output_rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Black-76 pricing experiment on a four-term snapshot.")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--risk-free-rate", type=float, default=0.02)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = run_experiment(
        snapshot_path=args.snapshot,
        timestamp=args.timestamp,
        risk_free_rate=args.risk_free_rate,
        output_path=args.output,
    )
    print(f"rows={len(result)}")
    print(f"timestamp={result['timestamp'].iloc[0]}")
    print("iv_quality_counts:")
    print(result["raw_iv_quality"].value_counts(dropna=False).to_string())
    print("forward_by_expiry:")
    print(
        result.groupby("expiry_date")
        .agg(forward=("forward", "first"), pairs=("forward_pairs", "first"), ok_iv=("raw_iv_quality", lambda s: (s == "ok").sum()))
        .to_string()
    )
    ok = result[result["raw_iv_quality"] == "ok"].copy()
    if not ok.empty:
        print("sample_ok_rows:")
        print(
            ok[
                [
                    "symbol",
                    "option_type",
                    "strike_price",
                    "mark_price",
                    "forward",
                    "raw_iv",
                    "raw_delta",
                    "raw_vega",
                    "quote_quality",
                ]
            ]
            .head(12)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
