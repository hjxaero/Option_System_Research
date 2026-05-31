from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SnapshotLocation:
    product: str
    mode: str
    root: Path

    @property
    def directory(self) -> Path:
        return self.root / self.mode / self.product

    def period_file(self, pricing_symbol: str, start_date: str, expiry_date: str) -> Path:
        product = pricing_symbol.split(".")[-1]
        start = start_date.replace("-", "")
        expiry = expiry_date.replace("-", "")
        return self.directory / f"{product}_{start}_{expiry}.parquet"


def snapshot_location(data_root: str | Path, product: str, include_next_month: bool) -> SnapshotLocation:
    mode = "dual_month" if include_next_month else "single_month"
    return SnapshotLocation(product=product.upper(), mode=mode, root=Path(data_root) / "snapshots")

