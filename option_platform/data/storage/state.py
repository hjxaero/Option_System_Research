from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UpdateState:
    product: str
    symbol: str
    trade_date: str
    last_target_time: str | None = None
    last_quote_time: str | None = None
    rows: int = 0
    updated_at: str = ""


def state_path(data_root: str | Path, product: str, symbol: str, trade_date: str) -> Path:
    safe_symbol = symbol.replace(".", "_")
    return Path(data_root) / "quality" / product.upper() / safe_symbol / f"{trade_date}.state.json"


def load_state(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(path: str | Path, state: UpdateState) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    payload["updated_at"] = payload["updated_at"] or datetime.now().isoformat(timespec="seconds")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p

