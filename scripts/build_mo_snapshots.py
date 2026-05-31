from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.snapshots.legacy_tq_mo import (
    LegacyMoSnapshotJob,
    run_legacy_mo_snapshot_job,
)
from option_platform.data.storage.layout import snapshot_location


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MO option minute snapshots.")
    parser.add_argument("--legacy-root", default=r"E:\Option_Sell_Research")
    parser.add_argument("--start", default="2022-07-22")
    parser.add_argument("--end", required=True)
    parser.add_argument("--include-next-month", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    location = snapshot_location(paths.data_root, "MO", args.include_next_month)
    output_dir = Path(args.output).resolve() if args.output else location.directory

    job = LegacyMoSnapshotJob(
        legacy_root=Path(args.legacy_root),
        output_dir=output_dir,
        start_date=args.start,
        end_date=args.end,
        include_next_month=args.include_next_month,
        force=args.force,
        dry_run=args.dry_run,
    )
    generated = run_legacy_mo_snapshot_job(job)
    print(f"generated={len(generated)} output={output_dir}")


if __name__ == "__main__":
    main()
