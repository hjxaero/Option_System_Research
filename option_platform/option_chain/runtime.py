from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from math import exp
from pathlib import Path
from typing import Iterator

import pandas as pd

from option_platform.option_chain.adapters import chain_from_snapshot_frame
from option_platform.option_chain.chain import OptionChain
from option_platform.option_chain.quality import OptionChainQualityReport, evaluate_pricing_frame
from option_platform.pricing import black76_price_and_greeks, implied_volatility_black76


SNAPSHOT_COLUMNS = [
    "timestamp",
    "term_role",
    "underlying_symbol",
    "underlying_price",
    "futures_symbol",
    "futures_price",
    "expiry_date",
    "symbol",
    "option_type",
    "strike_price",
    "mark_price",
    "price_source",
    "last_price",
    "bid_price1",
    "ask_price1",
    "bid_volume1",
    "ask_volume1",
    "spread_bps",
    "quote_quality",
    "open_interest",
    "volume",
    "volume_multiple",
]


@dataclass(frozen=True)
class OptionChainRuntimeResult:
    product: str
    trade_date: str
    timestamp: pd.Timestamp
    chain: OptionChain
    pricing_frame: pd.DataFrame
    quality_report: OptionChainQualityReport


def _positive(value: object) -> bool:
    return value is not None and not pd.isna(value) and float(value) > 0


def _snapshot_path(data_root: str | Path, product: str, trade_date: str) -> Path:
    return Path(data_root) / "snapshots" / "four_term" / product.upper() / f"{trade_date}.parquet"


def choose_best_timestamp(frame: pd.DataFrame) -> pd.Timestamp:
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
    elapsed_fraction = 1.0 if timestamp.time() >= pd.Timestamp("15:00").time() else 0.0
    return max((len(days) - elapsed_fraction) / 252, 1 / (252 * 240))


def infer_forwards(snapshot: pd.DataFrame, risk_free_rate: float) -> pd.DataFrame:
    rows = []
    for expiry, group in snapshot.groupby("expiry_date"):
        calls = group[group["option_type"] == "call"].set_index("strike_price")
        puts = group[group["option_type"] == "put"].set_index("strike_price")
        common_strikes = sorted(set(calls.index) & set(puts.index))
        t_years = business_time_to_expiry(pd.Timestamp(group["timestamp"].iloc[0]), expiry)
        discount = exp(-risk_free_rate * t_years)

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


def build_pricing_frame(snapshot: pd.DataFrame, *, risk_free_rate: float) -> pd.DataFrame:
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
                "timestamp": pd.Timestamp(row["timestamp"]),
                "underlying_symbol": row.get("underlying_symbol"),
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
                "open_interest": row.get("open_interest"),
                "volume": row.get("volume"),
                "raw_iv": iv.implied_volatility,
                "raw_iv_quality": iv.quality,
                "raw_delta": None if greeks is None else greeks.delta,
                "raw_gamma": None if greeks is None else greeks.gamma,
                "raw_theta": None if greeks is None else greeks.theta,
                "raw_vega": None if greeks is None else greeks.vega,
                "pricing_error": iv.pricing_error,
            }
        )
    return pd.DataFrame(output_rows)


class OptionChainRuntimeService:
    def __init__(
        self,
        *,
        data_root: str | Path = "data_store",
        risk_free_rate: float = 0.02,
        focus_expiries: int = 2,
        max_cache_items: int = 64,
    ) -> None:
        self.data_root = Path(data_root)
        self.risk_free_rate = float(risk_free_rate)
        self.focus_expiries = int(focus_expiries)
        self.max_cache_items = int(max_cache_items)
        self._cache: OrderedDict[tuple[str, str, str, float, int], OptionChainRuntimeResult] = OrderedDict()

    def _cache_key(self, product: str, trade_date: str, timestamp: pd.Timestamp) -> tuple[str, str, str, float, int]:
        return (
            product.upper(),
            trade_date,
            pd.Timestamp(timestamp).isoformat(),
            self.risk_free_rate,
            self.focus_expiries,
        )

    def _read_snapshot(self, product: str, trade_date: str) -> pd.DataFrame:
        path = _snapshot_path(self.data_root, product, trade_date)
        return pd.read_parquet(path, columns=SNAPSHOT_COLUMNS)

    def get_result(
        self,
        product: str,
        trade_date: str,
        timestamp: str | pd.Timestamp | None = None,
    ) -> OptionChainRuntimeResult:
        frame = self._read_snapshot(product, trade_date)
        target_ts = pd.Timestamp(timestamp) if timestamp is not None else choose_best_timestamp(frame)
        key = self._cache_key(product, trade_date, target_ts)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        snapshot = frame[pd.to_datetime(frame["timestamp"]) == target_ts].copy()
        if snapshot.empty:
            raise ValueError(f"No snapshot rows found for {product} {trade_date} {target_ts}")

        pricing_frame = build_pricing_frame(snapshot, risk_free_rate=self.risk_free_rate)
        quality_report = evaluate_pricing_frame(pricing_frame, focus_expiries=self.focus_expiries)

        chain_input = snapshot.copy()
        chain_input["futures_price"] = chain_input["expiry_date"].map(
            pricing_frame.groupby("expiry_date")["forward"].first().to_dict()
        )
        chain_input["iv"] = chain_input["symbol"].map(pricing_frame.set_index("symbol")["raw_iv"].to_dict())
        chain_input["delta"] = chain_input["symbol"].map(pricing_frame.set_index("symbol")["raw_delta"].to_dict())
        chain_input["gamma"] = chain_input["symbol"].map(pricing_frame.set_index("symbol")["raw_gamma"].to_dict())
        chain_input["theta"] = chain_input["symbol"].map(pricing_frame.set_index("symbol")["raw_theta"].to_dict())
        chain_input["vega"] = chain_input["symbol"].map(pricing_frame.set_index("symbol")["raw_vega"].to_dict())
        chain = chain_from_snapshot_frame(chain_input, timestamp=target_ts, as_of=trade_date)

        result = OptionChainRuntimeResult(
            product=product.upper(),
            trade_date=trade_date,
            timestamp=target_ts,
            chain=chain,
            pricing_frame=pricing_frame,
            quality_report=quality_report,
        )
        self._cache[key] = result
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_cache_items:
            self._cache.popitem(last=False)
        return result

    def get_chain(self, product: str, trade_date: str, timestamp: str | pd.Timestamp | None = None) -> OptionChain:
        return self.get_result(product, trade_date, timestamp).chain

    def get_pricing_frame(
        self,
        product: str,
        trade_date: str,
        timestamp: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        return self.get_result(product, trade_date, timestamp).pricing_frame

    def get_quality_report(
        self,
        product: str,
        trade_date: str,
        timestamp: str | pd.Timestamp | None = None,
    ) -> OptionChainQualityReport:
        return self.get_result(product, trade_date, timestamp).quality_report

    def iter_snapshots(
        self,
        product: str,
        trade_date: str,
        timestamps: list[str | pd.Timestamp] | None = None,
    ) -> Iterator[OptionChainRuntimeResult]:
        frame = self._read_snapshot(product, trade_date)
        selected = [pd.Timestamp(item) for item in timestamps] if timestamps else sorted(pd.to_datetime(frame["timestamp"]).unique())
        for timestamp in selected:
            yield self.get_result(product, trade_date, pd.Timestamp(timestamp))
