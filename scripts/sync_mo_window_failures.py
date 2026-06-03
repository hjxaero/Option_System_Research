#!/usr/bin/env python3
"""Sync MO window failure CSVs after a failures_retry build_month run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.quality.failure_records import (
    sync_resolved_retry_batches,
    sync_window_failures_after_retry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync MO failures CSV after repair retry.")
    parser.add_argument("--batch-dir", help="Default: data_store/quality/MO/batch_10d")
    parser.add_argument("--window-tag", help="Window tag YYYYMMDD_YYYYMMDD for a single sync")
    parser.add_argument(
        "--all-resolved-retries",
        action="store_true",
        help="Sync every window that has *_failures_retry_summary.json and no retry failures file.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    batch_dir = Path(args.batch_dir) if args.batch_dir else paths.data_root / "quality" / "MO" / "batch_10d"

    if args.all_resolved_retries:
        results = sync_resolved_retry_batches(batch_dir, dry_run=args.dry_run)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"synced_windows={len(results)} dry_run={args.dry_run}", flush=True)
        return

    if not args.window_tag:
        raise SystemExit("Provide --window-tag or --all-resolved-retries")

    result = sync_window_failures_after_retry(batch_dir, args.window_tag, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
