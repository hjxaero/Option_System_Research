from __future__ import annotations

import signal
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def run_process_pool(
    fn: Callable[[T], R],
    payloads: list[T],
    *,
    max_workers: int,
) -> list[R]:
    """Run ``fn`` over ``payloads`` with a process pool that shuts down cleanly.

    Registers SIGTERM/SIGINT handlers so a watchdog ``pkill`` does not leave
    orphaned worker processes when the parent is interrupted mid-window.
    """
    if not payloads:
        return []
    if max_workers <= 1:
        return [fn(payload) for payload in payloads]

    executor: ProcessPoolExecutor | None = None
    interrupted = False

    def _handle_stop(signum: int, _frame: object | None) -> None:
        nonlocal executor, interrupted
        interrupted = True
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
            executor = None
        raise SystemExit(128 + signum)

    prev_term = signal.signal(signal.SIGTERM, _handle_stop)
    prev_int = signal.signal(signal.SIGINT, _handle_stop)
    results: list[R] = []
    try:
        executor = ProcessPoolExecutor(max_workers=max_workers)
        futures = [executor.submit(fn, payload) for payload in payloads]
        for future in as_completed(futures):
            results.append(future.result())
        return results
    finally:
        signal.signal(signal.SIGTERM, prev_term)
        signal.signal(signal.SIGINT, prev_int)
        if executor is not None and not interrupted:
            executor.shutdown(wait=True, cancel_futures=False)
