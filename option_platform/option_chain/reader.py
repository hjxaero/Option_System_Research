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
    prepare_strategy_candidates_for_storage,
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
    "remaining_trading_minutes",
    "trading_days_to_expiry",
    "expiry_phase",
    "expiry_phase_rank",
    "expiry_phase_reason",
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
    "bucket_target_delta",
    "bucket_delta_error",
    "bucket_quality",
    "bucket_quality_reason",
    "is_atm_straddle_candidate",
    "straddle_candidate_id",
]


def _as_filter_set(value: str | Iterable[str] | None) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}


def _filter_in(frame: pd.DataFrame, column: str, value: str | Iterable[str] | None) -> pd.DataFrame:
    values = _as_filter_set(value)
    if values is None:
        return frame
    if column not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame[frame[column].astype("string").isin(values)].copy()


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

    def strategy_candidates_path(self, product: str, trade_date: str) -> Path:
        return self.snapshot_path(product, trade_date).with_suffix(".strategy_candidates.parquet")

    def strategy_quality_path(self, product: str, trade_date: str) -> Path:
        return self.snapshot_path(product, trade_date).with_suffix(".strategy_quality.parquet")

    def available_strategy_candidate_dates(
        self,
        product: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> list[str]:
        root = self.data_root / "snapshots" / self.snapshot_kind / product.upper()
        dates = sorted(path.name.split(".strategy_candidates.parquet")[0] for path in root.glob("*.strategy_candidates.parquet"))
        if start is not None:
            dates = [date for date in dates if date >= start]
        if end is not None:
            dates = [date for date in dates if date <= end]
        return dates

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

        try:
            frame = pd.read_parquet(self.snapshot_path(product, trade_date), columns=list(columns) if columns else None)
        except Exception:
            if columns is None:
                raise
            frame = pd.read_parquet(self.snapshot_path(product, trade_date))
            for column in columns:
                if column not in frame.columns:
                    frame[column] = pd.NA
            frame = frame[list(columns)]
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

    def get_strategy_candidates_for_storage(
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
        return prepare_strategy_candidates_for_storage(candidates)

    def load_strategy_candidates_sidecar(
        self,
        product: str,
        trade_date: str,
        *,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        try:
            return pd.read_parquet(self.strategy_candidates_path(product, trade_date), columns=list(columns) if columns else None)
        except Exception:
            if columns is None:
                raise
            frame = pd.read_parquet(self.strategy_candidates_path(product, trade_date))
            for column in columns:
                if column not in frame.columns:
                    frame[column] = pd.NA
            return frame[list(columns)]

    def get_strategy_candidates_by_pool(
        self,
        product: str,
        trade_date: str,
        candidate_pool: str,
        *,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        requested = list(columns) if columns is not None else None
        read_columns = requested
        if read_columns is not None and "candidate_pool" not in read_columns:
            read_columns = [*read_columns, "candidate_pool"]
        frame = self.load_strategy_candidates_sidecar(product, trade_date, columns=read_columns)
        if "candidate_pool" not in frame.columns:
            frame["candidate_pool"] = pd.NA
        result = frame[frame["candidate_pool"] == candidate_pool].copy()
        return result[requested] if requested is not None else result

    def load_strategy_candidates_filtered(
        self,
        product: str,
        *,
        start: str | None = None,
        end: str | None = None,
        trade_dates: Iterable[str] | None = None,
        candidate_pool: str | Iterable[str] | None = None,
        structure_type: str | Iterable[str] | None = None,
        term_role: str | Iterable[str] | None = None,
        candidate_quality: str | Iterable[str] | None = None,
        candidate_expiry_phase: str | Iterable[str] | None = None,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        requested = list(columns) if columns is not None else None
        filter_columns = [
            "trade_date",
            "candidate_pool",
            "structure_type",
            "term_role",
            "candidate_quality",
            "candidate_expiry_phase",
        ]
        read_columns = requested
        if read_columns is not None:
            read_columns = list(dict.fromkeys([*read_columns, *filter_columns]))

        dates = list(trade_dates) if trade_dates is not None else self.available_strategy_candidate_dates(product, start=start, end=end)
        frames = []
        for trade_date in dates:
            path = self.strategy_candidates_path(product, trade_date)
            if not path.exists():
                continue
            frame = self.load_strategy_candidates_sidecar(product, trade_date, columns=read_columns)
            if "trade_date" not in frame.columns:
                frame["trade_date"] = trade_date
            frame = _filter_in(frame, "candidate_pool", candidate_pool)
            frame = _filter_in(frame, "structure_type", structure_type)
            frame = _filter_in(frame, "term_role", term_role)
            frame = _filter_in(frame, "candidate_quality", candidate_quality)
            frame = _filter_in(frame, "candidate_expiry_phase", candidate_expiry_phase)
            if not frame.empty:
                frames.append(frame)

        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=read_columns or None)
        if requested is not None:
            for column in requested:
                if column not in result.columns:
                    result[column] = pd.NA
            result = result[requested]
        return result

    def get_primary_strategy_candidates(
        self,
        product: str,
        trade_date: str,
        *,
        structure_type: str | Iterable[str] | None = None,
        term_role: str | Iterable[str] | None = None,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        return self.load_strategy_candidates_filtered(
            product,
            trade_dates=[trade_date],
            candidate_pool="primary_pool",
            structure_type=structure_type,
            term_role=term_role,
            columns=columns,
        )

    def get_research_strategy_candidates(
        self,
        product: str,
        trade_date: str,
        *,
        structure_type: str | Iterable[str] | None = None,
        term_role: str | Iterable[str] | None = None,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        return self.load_strategy_candidates_filtered(
            product,
            trade_dates=[trade_date],
            candidate_pool="research_pool",
            structure_type=structure_type,
            term_role=term_role,
            columns=columns,
        )

    def load_strategy_quality_sidecar(
        self,
        product: str,
        trade_date: str,
        *,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        return pd.read_parquet(self.strategy_quality_path(product, trade_date), columns=list(columns) if columns else None)
