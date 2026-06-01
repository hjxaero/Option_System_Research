from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv_if_present() -> None:
    """Load project-root ``.env`` when env vars are not already set."""
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


@dataclass(frozen=True)
class TqSettings:
    username: str
    password: str

    @classmethod
    def from_env(cls) -> "TqSettings":
        _load_dotenv_if_present()
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

