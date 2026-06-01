from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Iterable

import pandas as pd

from option_platform.option_chain.adapters import chain_from_snapshot_frame
from option_platform.option_chain.chain import OptionChain
from option_platform.option_chain.quality import OptionChainQualityReport, evaluate_pricing_frame


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
