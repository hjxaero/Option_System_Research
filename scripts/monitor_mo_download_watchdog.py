from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout.strip()


def _is_running() -> bool:
    code, out = _run(
        [
            "pgrep",
            "-fl",
            r"build_windowed_four_term_minute_quotes|build_month_four_term_minute_quotes",
        ]
    )
    return code == 0 and bool(out)


def _kill_download_processes() -> None:
    # Only target the two known download entrypoints.
    _run(["pkill", "-f", "build_windowed_four_term_minute_quotes.py"])
    _run(["pkill", "-f", "build_month_four_term_minute_quotes.py"])


def _orphan_worker_pattern() -> str:
    return f"{PROJECT_ROOT}/Normal/bin/python -c from multiprocessing"


def _count_orphan_multiprocessing_workers() -> int:
    code, out = _run(["pgrep", "-fl", _orphan_worker_pattern()])
    if code != 0 or not out:
        return 0
    return len(out.splitlines())


def _kill_orphan_multiprocessing_workers() -> int:
    """Kill leftover ProcessPoolExecutor workers (PPID=1) from prior download runs."""
    count = _count_orphan_multiprocessing_workers()
    if count == 0:
        return 0
    _run(["pkill", "-f", _orphan_worker_pattern()])
    time.sleep(0.5)
    return count


def _stop_download_for_restart() -> None:
    _kill_download_processes()
    orphans = _kill_orphan_multiprocessing_workers()
    if orphans:
        print(f"HEARTBEAT cleaned_orphan_workers={orphans}", flush=True)


def _restart_download(command: str) -> tuple[int, str]:
    # Detached login shell: avoid PIPE backpressure and survive watchdog parent signals.
    proc = subprocess.Popen(
        ["/bin/zsh", "-lc", command],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return 0, f"spawned pid={proc.pid}"


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # examples: 2026-06-02T05:58:47.163734+00:00
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Watchdog: alert when MO download stops unexpectedly.")
    parser.add_argument(
        "--manifest",
        default=str(
            PROJECT_ROOT
            / "data_store"
            / "quality"
            / "MO"
            / "batch_10d"
            / "MO_20220722_20260530_w10_manifest.json"
        ),
        help="Path to manifest json",
    )
    parser.add_argument("--expected-windows", type=int, default=141)
    parser.add_argument("--interval-seconds", type=int, default=120, help="Polling interval")
    parser.add_argument(
        "--grace-seconds",
        type=int,
        default=600,
        help="Allow this many seconds since last_completed_at before alerting when not running",
    )
    parser.add_argument(
        "--auto-restart",
        action="store_true",
        help="When download is not running, kill only download processes then restart.",
    )
    parser.add_argument(
        "--restart-command",
        default="",
        help=(
            "Shell command to restart the MO download. Example: "
            "\"cd ... && source Normal/bin/activate && caffeinate -dims python scripts/build_windowed_four_term_minute_quotes.py ...\""
        ),
    )
    parser.add_argument(
        "--restart-cooldown-seconds",
        type=int,
        default=300,
        help="Minimum seconds between consecutive restarts to avoid loops.",
    )
    parser.add_argument(
        "--restart-after-window",
        action="store_true",
        help="Restart download once whenever a new window is completed (completed count increases).",
    )
    parser.add_argument(
        "--restart-after-window-delay-seconds",
        type=int,
        default=2,
        help="Wait this many seconds before restarting after window completion.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ALERT manifest_not_found path={manifest_path}", flush=True)
        return 2

    last_completed = -1
    last_window = None
    last_restart_at: datetime | None = None

    while True:
        try:
            m = _load_manifest(manifest_path)
        except Exception as exc:
            print(f"ALERT manifest_read_error error={exc}", flush=True)
            time.sleep(max(args.interval_seconds, 5))
            continue

        completed = len(m.get("completed", []) or [])
        running = _is_running()

        last_completed_at = _parse_iso_utc(m.get("last_completed_at"))
        age_s = None
        if last_completed_at is not None:
            age_s = int((_utc_now() - last_completed_at).total_seconds())

        cur_last_window = m.get("last_window")
        completed_increased = last_completed >= 0 and completed > last_completed
        if completed != last_completed or cur_last_window != last_window:
            print(
                f"HEARTBEAT completed={completed}/{args.expected_windows} "
                f"running={int(running)} last_window={cur_last_window} age_s={age_s}",
                flush=True,
            )
            last_completed = completed
            last_window = cur_last_window

        if args.restart_after_window and completed_increased and args.restart_command:
            now = _utc_now()
            cooldown_ok = (
                last_restart_at is None
                or (now - last_restart_at).total_seconds() >= args.restart_cooldown_seconds
            )
            if cooldown_ok:
                print(
                    f"HEARTBEAT restart_after_window=1 last_window={cur_last_window}",
                    flush=True,
                )
                _stop_download_for_restart()
                time.sleep(max(int(args.restart_after_window_delay_seconds), 0))
                _restart_download(args.restart_command)
                last_restart_at = now

        if not running:
            # When stopped, only alert if we haven't completed recently.
            if age_s is None or age_s > args.grace_seconds:
                print(
                    f"ALERT download_not_running completed={completed}/{args.expected_windows} "
                    f"last_window={cur_last_window} age_s={age_s}",
                    flush=True,
                )
                if args.auto_restart:
                    now = _utc_now()
                    cooldown_ok = (
                        last_restart_at is None
                        or (now - last_restart_at).total_seconds() >= args.restart_cooldown_seconds
                    )
                    if not args.restart_command:
                        print("ALERT auto_restart_missing_command", flush=True)
                    elif not cooldown_ok:
                        pass
                    else:
                        _stop_download_for_restart()
                        time.sleep(1)
                        if _is_running():
                            print("HEARTBEAT restart_skipped_already_running=1", flush=True)
                        else:
                            _restart_download(args.restart_command)
                            last_restart_at = now
                            print("HEARTBEAT auto_restarted=1", flush=True)

        time.sleep(max(args.interval_seconds, 5))


if __name__ == "__main__":
    raise SystemExit(main())

