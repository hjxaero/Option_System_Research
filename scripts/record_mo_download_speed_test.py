#!/usr/bin/env python3
"""Run a reproducible MO download speed test and append JSON record."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_MONTH = PROJECT_ROOT / "scripts" / "build_month_four_term_minute_quotes.py"
DEFAULT_RECORD = PROJECT_ROOT / "data_store" / "quality" / "MO" / "network_benchmark" / "speed_tests.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MO download speed test with JSONL record.")
    parser.add_argument("--label", required=True, help="e.g. vpn_blacklist_on")
    parser.add_argument("--note", default="", help="Free-form note (VPN settings, etc.)")
    parser.add_argument("--start", default="2022-11-09")
    parser.add_argument("--end", default="2022-11-10")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-contracts", type=int, default=36)
    parser.add_argument("--record-file", type=Path, default=DEFAULT_RECORD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    data_root = PROJECT_ROOT / "data_store" / f"speed_test_{args.label}_{stamp}"
    log_path = args.record_file.parent / f"{args.label}_{stamp}.log"

    args.record_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(BUILD_MONTH),
        "--start",
        args.start,
        "--end",
        args.end,
        "--workers",
        str(args.workers),
        "--max-contracts",
        str(args.max_contracts),
        "--no-skip-complete",
        "--retry-attempts",
        "2",
        "--retry-sleep-seconds",
        "2",
        "--report-prefix",
        f"SPEED_{args.label}_{stamp}",
        "--output-dir",
        str(data_root / "quality" / "MO"),
    ]
    env = {"OPTION_DATA_ROOT": str(data_root), **dict(__import__("os").environ)}

    print(f"label={args.label} data_root={data_root}", flush=True)
    print(" ".join(cmd), flush=True)
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = round(time.perf_counter() - t0, 2)
    log_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")

    saved_days = 0
    failed_symbols = 0
    for line in (proc.stdout + proc.stderr).splitlines():
        if "done saved_days=" in line:
            parts = line.split("done saved_days=")[-1]
            saved_days = int(parts.split()[0])
            if "failed_symbols=" in parts:
                failed_symbols = int(parts.split("failed_symbols=")[-1].split()[0])

    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "note": args.note,
        "start": args.start,
        "end": args.end,
        "workers": args.workers,
        "max_contracts": args.max_contracts,
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "saved_days": saved_days,
        "failed_symbols": failed_symbols,
        "data_root": str(data_root),
        "log_path": str(log_path),
    }
    with args.record_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary_path = args.record_file.parent / f"{args.label}_{stamp}_summary.json"
    summary_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
    print(f"record={args.record_file}", flush=True)
    print(f"summary={summary_path}", flush=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
