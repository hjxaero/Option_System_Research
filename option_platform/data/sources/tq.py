from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from option_platform.common.settings import TqSettings


@contextmanager
def tq_api(settings: TqSettings | None = None) -> Iterator[object]:
    try:
        from tqsdk import TqApi, TqAuth
    except ImportError as exc:
        raise RuntimeError("tqsdk is not installed. Install requirements.txt first.") from exc

    cfg = settings or TqSettings.from_env()
    api = TqApi(auth=TqAuth(cfg.username, cfg.password))
    try:
        yield api
    finally:
        api.close()

