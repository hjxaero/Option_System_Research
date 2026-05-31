from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from option_platform.common.settings import TqSettings
from option_platform.data.sources.tq import tq_api


@dataclass(frozen=True)
class LegacyMoSnapshotJob:
    legacy_root: Path
    output_dir: Path
    start_date: str
    end_date: str
    include_next_month: bool = False
    force: bool = False
    dry_run: bool = False
    kline_duration: int = 60
    risk_free_rate: float = 0.025


def run_legacy_mo_snapshot_job(job: LegacyMoSnapshotJob) -> list[Path]:
    """Run the old MO snapshot engine behind the new platform boundary."""
    legacy_root = job.legacy_root.resolve()
    if not legacy_root.exists():
        raise FileNotFoundError(f"Legacy project root not found: {legacy_root}")

    legacy_root_str = str(legacy_root)
    if legacy_root_str not in sys.path:
        sys.path.insert(0, legacy_root_str)

    from data.data_loader import TQDataLoader
    from data.snapshot_builder import SnapshotBuilder
    from option_platform.data.quality.snapshot_checks import check_snapshot_completeness

    output_dir = job.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    with tq_api(TqSettings.from_env()) as api:
        loader = TQDataLoader(api)
        loader.download_options_filtered(underlying_product="MO", type="future", batch_size=100)

        contracts = [c for c in loader._all_options if c.expiry_date >= job.start_date]
        periods = loader.classify_trading_periods_by_expiry(
            contracts,
            start_date=job.start_date,
            end_date=None if job.include_next_month else job.end_date,
        )

        builder = SnapshotBuilder(
            api=api,
            kline_duration=job.kline_duration,
            risk_free_rate=job.risk_free_rate,
        )

        for idx, period in enumerate(periods):
            futures_symbol = builder._derive_futures_symbol(period.tradable_contracts, "MO")
            pricing_symbol = futures_symbol or period.underlying_symbol
            product = pricing_symbol.split(".")[-1]
            filepath = output_dir / (
                f"{product}_{period.start_date.replace('-', '')}_"
                f"{period.expiry_date.replace('-', '')}.parquet"
            )

            completeness = check_snapshot_completeness(filepath, period.expiry_date, job.end_date)
            should_skip = completeness.is_complete and not job.force
            if should_skip:
                print(f"[SKIP] {filepath.name} {completeness.detail}")
            elif job.dry_run:
                print(f"[TODO] {filepath.name} {completeness.status} {completeness.detail}")
            else:
                next_period = periods[idx + 1] if job.include_next_month and idx + 1 < len(periods) else None
                next_futures_symbol = (
                    builder._derive_futures_symbol(next_period.tradable_contracts, "MO")
                    if next_period
                    else None
                )
                built_path = builder._build_period(
                    period,
                    str(output_dir),
                    futures_symbol,
                    next_period=next_period,
                    next_futures_symbol=next_futures_symbol,
                )
                if built_path:
                    generated.append(Path(built_path))

            if period.expiry_date >= job.end_date:
                break

    return generated

