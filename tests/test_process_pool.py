from __future__ import annotations

import os

import pytest

from option_platform.common.process_pool import run_process_pool


def _add_one(value: int) -> int:
    return value + 1


def test_run_process_pool_serial_path() -> None:
    assert run_process_pool(_add_one, [1, 2, 3], max_workers=1) == [2, 3, 4]


def test_run_process_pool_parallel_path() -> None:
    if os.cpu_count() is None or os.cpu_count() < 2:
        pytest.skip("need at least 2 CPUs")
    try:
        results = run_process_pool(_add_one, list(range(8)), max_workers=2)
    except (PermissionError, NotImplementedError):
        pytest.skip("ProcessPoolExecutor unavailable in this environment")
    assert sorted(results) == list(range(1, 9))
