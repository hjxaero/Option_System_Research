from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.download_windows import iter_download_windows

BUILD_MONTH_SCRIPT = PROJECT_ROOT / "scripts" / "build_month_four_term_minute_quotes.py"
INFER_FIRST_VALID_SCRIPT = PROJECT_ROOT / "scripts" / "infer_first_valid_dates.py"
DONE_RE = re.compile(r"done saved_days=(\d+) skipped_days=(\d+) failed_symbols=(\d+)")
ROWS_RE = re.compile(r"rows=(\d+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download MO four-term minute quotes in fixed calendar windows (default 10 days)."
    )
    parser.add_argument("--start", required=True, help="Overall range start, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Overall range end, YYYY-MM-DD")
    parser.add_argument("--window-days", type=int, default=10, help="Calendar days per chunk (default: 10).")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-contracts", type=int, default=0)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=3.0)
    parser.add_argument("--max-quote-age-ms", type=int, default=60_000)
    parser.add_argument(
        "--auto-reduce-workers",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When slowdown/failures are detected, reduce workers for later windows (default: true).",
    )
    parser.add_argument("--min-workers", type=int, default=2, help="Lower bound for auto-reduced workers.")
    parser.add_argument(
        "--performance-factor",
        type=float,
        default=2.0,
        help="Slowdown threshold multiplier vs median baseline window time (default: 2.0).",
    )
    parser.add_argument(
        "--performance-floor-seconds",
        type=float,
        default=30.0,
        help="Minimum absolute seconds before slowdown warning is triggered (default: 30).",
    )
    parser.add_argument(
        "--first-valid-date-cache",
        help="Path to first_valid_dates.json; enabled after the first completed window when --infer-first-valid is on.",
    )
    parser.add_argument(
        "--refresh-contracts",
        action="store_true",
        help="Refresh TQ contract cache before the first window only (unless --refresh-contracts-every-window).",
    )
    parser.add_argument(
        "--refresh-contracts-every-window",
        action="store_true",
        help="Pass --refresh-contracts to every window (slow; normally only the first window refreshes).",
    )
    parser.add_argument(
        "--infer-first-valid",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="After each window, merge inferred first valid quote dates into cache (default: true).",
    )
    parser.add_argument(
        "--skip-complete",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print windows and subprocess commands.")
    parser.add_argument(
        "--from-window",
        type=int,
        default=1,
        help="1-based window index to start from (for manual resume).",
    )
    parser.add_argument(
        "--manifest",
        help="JSON manifest of completed windows; default under data_store/quality/PRODUCT/batch_10d/",
    )
    parser.add_argument(
        "--output-dir",
        help="Quality report directory passed to each window download.",
    )
    parser.add_argument(
        "--stop-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stop the batch when a window subprocess fails (default: true).",
    )
    return parser.parse_args()


def _default_manifest_path(paths: PlatformPaths, product: str, start: str, end: str, window_days: int) -> Path:
    label = (
        f"{product.upper()}_{start.replace('-', '')}_{end.replace('-', '')}_w{window_days}"
    )
    return paths.data_root / "quality" / product.upper() / "batch_10d" / f"{label}_manifest.json"


def _load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"completed": [], "window_metrics": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _window_key(window_start: str, window_end: str) -> str:
    return f"{window_start}_{window_end}"


def _is_completed(manifest: dict, window_start: str, window_end: str) -> bool:
    key = _window_key(window_start, window_end)
    return key in set(manifest.get("completed", []))


def _mark_completed(manifest: dict, window_start: str, window_end: str) -> None:
    key = _window_key(window_start, window_end)
    completed = set(manifest.get("completed", []))
    completed.add(key)
    manifest["completed"] = sorted(completed)


def _run_subprocess(cmd: list[str], dry_run: bool) -> tuple[int, str]:
    printable = " ".join(cmd)
    print(f"$ {printable}", flush=True)
    if dry_run:
        return 0, ""
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr, flush=True)
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    return int(result.returncode), output


def _parse_download_metrics(output: str) -> dict[str, int | None]:
    done = DONE_RE.search(output)
    rows = ROWS_RE.search(output)
    return {
        "saved_days": int(done.group(1)) if done else None,
        "skipped_days": int(done.group(2)) if done else None,
        "failed_symbols": int(done.group(3)) if done else None,
        "rows": int(rows.group(1)) if rows else None,
    }


def _detect_slowdown(
    *,
    current_key: str,
    current: dict,
    metrics: dict,
    factor: float,
    floor_seconds: float,
) -> str | None:
    if current.get("exit_code") != 0:
        return "window_failed"
    elapsed = float(current.get("elapsed_s") or 0.0)
    saved = int(current.get("saved_days") or 0)
    skipped = int(current.get("skipped_days") or 0)

    history = []
    for key, row in metrics.items():
        if key == current_key:
            continue
        if int(row.get("exit_code", 1)) != 0:
            continue
        history.append(row)

    if saved == 0 and skipped > 0:
        baselines = [
            float(row.get("elapsed_s", 0.0))
            for row in history
            if int(row.get("saved_days", 0)) == 0 and int(row.get("skipped_days", 0)) > 0
        ]
        if baselines:
            threshold = max(floor_seconds, statistics.median(baselines) * factor)
            if elapsed > threshold:
                return f"slow_skip_window>{threshold:.1f}s"
        return None

    if saved > 0:
        throughputs = []
        for row in history:
            old_saved = int(row.get("saved_days", 0))
            old_elapsed = float(row.get("elapsed_s", 0.0))
            if old_saved > 0 and old_elapsed > 0:
                throughputs.append(old_saved / old_elapsed)
        if len(throughputs) >= 2 and elapsed > 0:
            current_tp = saved / elapsed
            baseline_tp = statistics.median(throughputs)
            if current_tp < baseline_tp * 0.6:
                return f"slow_download_tp<{baseline_tp * 0.6:.4f}"
    return None


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    python = sys.executable
    windows = iter_download_windows(args.start, args.end, args.window_days)
    if not windows:
        raise SystemExit("No windows to process; check --start/--end.")

    manifest_path = (
        Path(args.manifest)
        if args.manifest
        else _default_manifest_path(paths, args.product, args.start, args.end, args.window_days)
    )
    manifest = _load_manifest(manifest_path)
    manifest.setdefault("range", {"start": args.start, "end": args.end, "window_days": args.window_days})
    manifest.setdefault("completed", [])
    manifest.setdefault("window_metrics", {})

    first_valid_cache = args.first_valid_date_cache or str(
        paths.data_root / "contracts" / args.product.upper() / "first_valid_dates.json"
    )
    report_dir = args.output_dir or str(
        paths.data_root / "quality" / args.product.upper() / "batch_10d"
    )

    print(
        f"windows={len(windows)} window_days={args.window_days} "
        f"manifest={manifest_path}",
        flush=True,
    )

    contracts_refreshed = False
    current_workers = args.workers
    for index, (window_start, window_end) in enumerate(windows, start=1):
        if index < args.from_window:
            continue
        if _is_completed(manifest, window_start, window_end):
            print(f"[{index}/{len(windows)}] skip completed {window_start}..{window_end}", flush=True)
            continue

        print(f"[{index}/{len(windows)}] window {window_start} .. {window_end}", flush=True)
        download_cmd = [
            python,
            str(BUILD_MONTH_SCRIPT),
            "--start",
            window_start,
            "--end",
            window_end,
            "--product",
            args.product,
            "--workers",
            str(current_workers),
            "--max-contracts",
            str(args.max_contracts),
            "--retry-attempts",
            str(args.retry_attempts),
            "--retry-sleep-seconds",
            str(args.retry_sleep_seconds),
            "--max-quote-age-ms",
            str(args.max_quote_age_ms),
            "--output-dir",
            report_dir,
        ]
        if args.skip_complete:
            download_cmd.append("--skip-complete")
        else:
            download_cmd.append("--no-skip-complete")

        refresh = args.refresh_contracts_every_window or (
            args.refresh_contracts and not contracts_refreshed
        )
        if refresh:
            download_cmd.append("--refresh-contracts")
            contracts_refreshed = True

        if Path(first_valid_cache).exists():
            download_cmd.extend(["--first-valid-date-cache", first_valid_cache])

        t0 = time.perf_counter()
        exit_code, output = _run_subprocess(download_cmd, args.dry_run)
        elapsed_s = round(time.perf_counter() - t0, 2)
        parsed = _parse_download_metrics(output)
        window_key = _window_key(window_start, window_end)
        metric = {
            "index": index,
            "start": window_start,
            "end": window_end,
            "workers": current_workers,
            "elapsed_s": elapsed_s,
            "exit_code": exit_code,
            **parsed,
        }
        manifest["window_metrics"][window_key] = metric
        slowdown = _detect_slowdown(
            current_key=window_key,
            current=metric,
            metrics=manifest["window_metrics"],
            factor=max(args.performance_factor, 1.0),
            floor_seconds=max(args.performance_floor_seconds, 0.0),
        )
        if slowdown:
            print(f"[warn] window {window_start}..{window_end} {slowdown}", flush=True)

        should_reduce = (
            args.auto_reduce_workers
            and current_workers > max(args.min_workers, 1)
            and (
                exit_code != 0
                or int(parsed.get("failed_symbols") or 0) > 0
                or slowdown is not None
            )
        )
        if should_reduce:
            current_workers -= 1
            print(f"[adaptive] reduce workers -> {current_workers}", flush=True)

        if exit_code != 0:
            print(f"window failed exit_code={exit_code} {window_start}..{window_end}", flush=True)
            if not args.dry_run:
                manifest["last_failed_at"] = datetime.now(timezone.utc).isoformat()
                manifest["last_window"] = window_key
                _save_manifest(manifest_path, manifest)
            if args.stop_on_error:
                raise SystemExit(exit_code)

        if args.infer_first_valid and not args.dry_run:
            infer_cmd = [
                python,
                str(INFER_FIRST_VALID_SCRIPT),
                "--product",
                args.product,
                "--start",
                window_start,
                "--end",
                window_end,
                "--output",
                first_valid_cache,
            ]
            infer_exit, _ = _run_subprocess(infer_cmd, dry_run=False)
            if infer_exit != 0:
                print(f"infer_first_valid failed exit_code={infer_exit}", flush=True)
                if args.stop_on_error:
                    raise SystemExit(infer_exit)

        if not args.dry_run:
            _mark_completed(manifest, window_start, window_end)
            manifest["last_completed_at"] = datetime.now(timezone.utc).isoformat()
            manifest["last_window"] = window_key
            _save_manifest(manifest_path, manifest)

    print(f"batch_done manifest={manifest_path} completed={len(manifest.get('completed', []))}", flush=True)


if __name__ == "__main__":
    main()
