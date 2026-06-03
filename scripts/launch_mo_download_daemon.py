#!/usr/bin/env python3
"""Detached launcher for the MO P0 download stack.

Starts (or restarts) three long-lived processes fully detached from the
calling shell's session, so they survive the parent terminal exiting:

1. windowed download  (build_windowed_four_term_minute_quotes.py)
2. self-healing watchdog (monitor_mo_download_watchdog.py)
3. orphan worker monitor (monitor_mo_orphan_workers.sh)

macOS has no ``setsid``; we use ``start_new_session=True`` (os.setsid in the
child) so a SIGHUP to the launcher's process group never reaches the daemons.

With ``--restart`` it first kills any running download/watchdog/month
processes AND leftover ProcessPoolExecutor workers (PPID=1) before relaunching.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_PY = PROJECT_ROOT / "Normal" / "bin" / "python"
BATCH_DIR = PROJECT_ROOT / "data_store" / "quality" / "MO" / "batch_10d"
LOG = BATCH_DIR / "full_history.log"
WATCHDOG_LOG = BATCH_DIR / "watchdog.log"
ORPHAN_LOG = BATCH_DIR / "orphan_monitor.log"

DOWNLOAD_SCRIPT = "scripts/build_windowed_four_term_minute_quotes.py"
WATCHDOG_SCRIPT = "scripts/monitor_mo_download_watchdog.py"
ORPHAN_SCRIPT = PROJECT_ROOT / "scripts" / "monitor_mo_orphan_workers.sh"

DOWNLOAD_PROC = "build_windowed_four_term_minute_quotes.py"
MONTH_PROC = "build_month_four_term_minute_quotes.py"
WATCHDOG_PROC = "monitor_mo_download_watchdog.py"
ORPHAN_MONITOR_PROC = "monitor_mo_orphan_workers.sh"


def _orphan_worker_pattern() -> str:
    return f"{VENV_PY} -c from multiprocessing"


def _pgrep(pattern: str) -> list[int]:
    proc = subprocess.run(
        ["pgrep", "-f", pattern],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return [int(x) for x in proc.stdout.split() if x.strip().isdigit()]


def _pkill(pattern: str) -> None:
    subprocess.run(["pkill", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _download_workers() -> list[str]:
    return [DOWNLOAD_PROC, MONTH_PROC]


def _download_running() -> bool:
    return any(_pgrep(p) for p in _download_workers())


def _kill_orphan_workers() -> int:
    pids = _pgrep(_orphan_worker_pattern())
    if not pids:
        return 0
    _pkill(_orphan_worker_pattern())
    time.sleep(0.5)
    return len(pids)


def _stop_existing(verbose: bool = True) -> None:
    for pattern in (DOWNLOAD_PROC, MONTH_PROC, WATCHDOG_PROC, ORPHAN_MONITOR_PROC):
        _pkill(pattern)
    time.sleep(2)
    cleaned = _kill_orphan_workers()
    if verbose:
        print(f"stopped existing; cleaned_orphan_workers={cleaned}", flush=True)


def _download_argv(workers: int) -> list[str]:
    return [
        "caffeinate",
        "-dims",
        str(VENV_PY),
        DOWNLOAD_SCRIPT,
        "--start",
        "2022-07-22",
        "--end",
        "2026-05-30",
        "--window-days",
        "10",
        "--workers",
        str(workers),
        "--min-workers",
        str(workers),
        "--auto-reduce-workers",
        "--skip-complete",
        "--infer-first-valid",
        "--first-valid-date-cache",
        "data_store/contracts/MO/first_valid_dates.json",
    ]


def _download_restart_command(workers: int) -> str:
    """Shell command the watchdog uses to relaunch the download."""
    argv = _download_argv(workers)
    quoted = " ".join(argv)
    return (
        f"cd '{PROJECT_ROOT}' && exec {quoted} "
        f">>'{LOG}' 2>&1"
    )


def _watchdog_argv(interval: int, grace: int, cooldown: int, workers: int) -> list[str]:
    return [
        str(VENV_PY),
        WATCHDOG_SCRIPT,
        "--interval-seconds",
        str(interval),
        "--grace-seconds",
        str(grace),
        "--auto-restart",
        "--restart-after-window",
        "--restart-cooldown-seconds",
        str(cooldown),
        "--restart-after-window-delay-seconds",
        "2",
        "--restart-command",
        _download_restart_command(workers),
    ]


def _spawn_detached(argv: list[str], log_path: Path, append: bool = True) -> int:
    """Start argv in a brand-new session, fully detached from this process."""
    mode = "a" if append else "w"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, mode)
    proc = subprocess.Popen(
        argv,
        cwd=str(PROJECT_ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return proc.pid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "4")))
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--grace-seconds", type=int, default=600)
    parser.add_argument("--restart-cooldown-seconds", type=int, default=60)
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Kill existing download/watchdog + orphan workers, then relaunch.",
    )
    args = parser.parse_args()

    if not VENV_PY.exists():
        print(f"ALERT venv_python_missing path={VENV_PY}", flush=True)
        return 2

    BATCH_DIR.mkdir(parents=True, exist_ok=True)

    if args.restart:
        _stop_existing()

    if _download_running():
        print("download already running; skip", flush=True)
    else:
        pid = _spawn_detached(_download_argv(args.workers), LOG)
        print(f"download_pid={pid}", flush=True)

    if _pgrep(WATCHDOG_PROC):
        print("watchdog already running; skip", flush=True)
    else:
        pid = _spawn_detached(
            _watchdog_argv(
                args.interval_seconds,
                args.grace_seconds,
                args.restart_cooldown_seconds,
                args.workers,
            ),
            WATCHDOG_LOG,
        )
        print(f"watchdog_pid={pid}", flush=True)

    if _pgrep(ORPHAN_MONITOR_PROC):
        print("orphan_monitor already running; skip", flush=True)
    else:
        pid = _spawn_detached(["/bin/bash", str(ORPHAN_SCRIPT), str(ORPHAN_LOG)], ORPHAN_LOG)
        print(f"orphan_monitor_pid={pid}", flush=True)

    print(f"logs: {LOG} | {WATCHDOG_LOG} | {ORPHAN_LOG}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
