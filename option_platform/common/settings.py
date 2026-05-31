from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TqSettings:
    username: str
    password: str

    @classmethod
    def from_env(cls) -> "TqSettings":
        username = os.getenv("TQ_USER", "").strip()
        password = os.getenv("TQ_PASS", "").strip()
        if not username or not password:
            raise RuntimeError(
                "Missing TQ credentials. Set TQ_USER and TQ_PASS before running data jobs."
            )
        return cls(username=username, password=password)


@dataclass(frozen=True)
class PlatformPaths:
    root: Path
    data_root: Path
    snapshots_root: Path
    catalog_path: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "PlatformPaths":
        root_path = Path(root).resolve()
        data_root = Path(os.getenv("OPTION_DATA_ROOT", root_path / "data_store")).resolve()
        return cls(
            root=root_path,
            data_root=data_root,
            snapshots_root=data_root / "snapshots",
            catalog_path=root_path / "configs" / "data_catalog.json",
        )

