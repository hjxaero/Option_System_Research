from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Iterable

import pandas as pd

from option_platform.option_chain.adapters import chain_from_snapshot_frame
from option_platform.option_chain.chain import OptionChain
from option_platform.option_chain.quality import OptionChainQualityReport, evaluate_pricing_frame
from option_platform.option_chain.strategy_candidates import (
    build_strategy_candidate_quality_report,
    build_strategy_candidates,
)


BUCKET_READER_COLUMNS = [
    "timestamp",
    "term_role",
    "underlying_symbol",
    "expiry_date",
    "symbol",
    "option_type",
    "strike_price",
    "mark_price",
    "iv",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "iv_quality",
    "greeks_quality",
    "mark_quality",
    "pricing_quality",
    "tradability_quality",
    "strategy_candidate_ok",
    "strategy_candidate_tier",
    "strategy_candidate_reason",
    "forward_consistency_quality",
    "bucket_ids",
    "bucket_primary",
    "bucket_count",
    "delta_bucket",
    "bucket_selection_rank",
    "bucket_selection_reason",
    "is_atm_straddle_candidate",
    "straddle_candidate_id",
]


class OptionChainSnapshotReader:
    def __init__(
        self,
        *,
        data_root: str | Path = "data_store",
        snapshot_kind: str = "four_term_enriched",
        focus_expiries: int = 2,
        max_cache_items: int = 64,
    ) -> None:
        self.data_root = Path(data_root)
        self.snapshot_kind = snapshot_kind
        self.focus_expiries = int(focus_expiries)
        self.max_cache_items = int(max_cache_items)
        self._cache: OrderedDict[tuple[object, ...], pd.DataFrame] = OrderedDict()

    def snapshot_path(self, product: str, trade_date: str) -> Path:
        return self.data_root / "snapshots" / self.snapshot_kind / product.upper() / f"{trade_date}.parquet"

    def load_frame(
        self,
        product: str,
        trade_date: str,
        timestamp: str | pd.Timestamp | None = None,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        column_key = tuple(columns) if columns is not None else None
        timestamp_key = None if timestamp is None else pd.Timestamp(timestamp).isoformat()
        key = (product.upper(), trade_date, timestamp_key, column_key)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key].copy()

        frame = pd.read_parquet(self.snapshot_path(product, trade_date), columns=list(columns) if columns else None)
        if timestamp is not None:
            target = pd.Timestamp(timestamp)
            frame = frame[pd.to_datetime(frame["timestamp"]) == target].copy()

        self._cache[key] = frame
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_cache_items:
            self._cache.popitem(last=False)
        return frame.copy()

    def get_chain(self, product: str, trade_date: str, timestamp: str | pd.Timestamp) -> OptionChain:
        frame = self.load_frame(product, trade_date, timestamp)
        return chain_from_snapshot_frame(frame, timestamp=timestamp, as_of=trade_date)

    def get_quality_report(
        self,
        product: str,
        trade_date: str,
        timestamp: str | pd.Timestamp,
    ) -> OptionChainQualityReport:
        frame = self.load_frame(product, trade_date, timestamp)
        pricing_frame = frame.rename(
            columns={
                "iv": "raw_iv",
                "iv_quality": "raw_iv_quality",
                "delta": "raw_delta",
                "gamma": "raw_gamma",
                "theta": "raw_theta",
                "vega": "raw_vega",
            }
        )
        return evaluate_pricing_frame(pricing_frame, focus_expiries=self.focus_expiries)

    def iter_timestamps(self, product: str, trade_date: str) -> list[pd.Timestamp]:
        frame = self.load_frame(product, trade_date, columns=["timestamp"])
        return sorted(pd.to_datetime(frame["timestamp"]).dropna().unique())

    def load_bucket_frame(
        self,
        product: str,
        trade_date: str,
        timestamp: str | pd.Timestamp,
    ) -> pd.DataFrame:
        return self.load_frame(product, trade_date, timestamp, columns=BUCKET_READER_COLUMNS)

    def get_bucket_rows(
        self,
        product: str,
        trade_date: str,
        timestamp: str | pd.Timestamp,
        *,
        bucket_id: str | None = None,
        term_role: str | None = None,
        delta_bucket: str | None = None,
        front_terms_only: bool = False,
    ) -> pd.DataFrame:
        frame = self.load_bucket_frame(product, trade_date, timestamp)
        frame = frame[frame["bucket_ids"].notna()].copy()
        if bucket_id is not None:
            bucket = str(bucket_id)
            frame = frame[
                frame["bucket_ids"].fillna("").astype(str).str.split(";").apply(lambda values: bucket in values)
            ].copy()
        if term_role is not None:
            frame = frame[frame["term_role"] == term_role].copy()
        if delta_bucket is not None:
            frame = frame[frame["delta_bucket"] == delta_bucket].copy()
        if front_terms_only:
            frame = frame[frame["term_role"].isin(["current_month", "next_month"])].copy()
        return frame.sort_values(["term_role", "expiry_date", "bucket_selection_rank", "bucket_primary", "symbol"]).reset_index(
            drop=True
        )

    def get_strategy_candidates(
        self,
        product: str,
        trade_date: str,
        timestamp: str | pd.Timestamp,
        *,
        structures: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        frame = self.load_bucket_frame(product, trade_date, timestamp)
        return build_strategy_candidates(frame, product=product, trade_date=trade_date, structures=structures)

    def get_strategy_candidates_for_day(
        self,
        product: str,
        trade_date: str,
        *,
        timestamps: Iterable[str | pd.Timestamp] | None = None,
        structures: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        frame = self.load_frame(product, trade_date, columns=BUCKET_READER_COLUMNS)
        selected = None if timestamps is None else {pd.Timestamp(item) for item in timestamps}
        rows = []
        for timestamp, group in frame.groupby("timestamp", sort=True):
            target = pd.Timestamp(timestamp)
            if selected is not None and target not in selected:
                continue
            candidates = build_strategy_candidates(group.copy(), product=product, trade_date=trade_date, structures=structures)
            if not candidates.empty:
                rows.append(candidates)
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    def get_strategy_candidate_quality_report(
        self,
        product: str,
        trade_date: str,
        *,
        timestamps: Iterable[str | pd.Timestamp] | None = None,
        structures: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        candidates = self.get_strategy_candidates_for_day(
            product,
            trade_date,
            timestamps=timestamps,
            structures=structures,
        )
        return build_strategy_candidate_quality_report(candidates, product=product, trade_date=trade_date)
