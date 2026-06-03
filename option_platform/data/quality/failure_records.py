from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path


def _window_tag_from_failures_path(path: Path) -> str | None:
    """Parse ``MO_YYYYMMDD_YYYYMMDD`` tag from a failures filename."""
    stem = path.name.replace(".resolved.csv", "").replace(".csv", "")
    if stem.endswith("_failures"):
        stem = stem[: -len("_failures")]
    elif stem.endswith("_retry_failures"):
        stem = stem[: -len("_retry_failures")]
    elif "_retry" in stem and stem.endswith("_failures"):
        stem = stem.replace("_retry_failures", "").replace("_failures", "")
    if stem.startswith("MO_"):
        stem = stem[3:]
    parts = stem.split("_")
    if len(parts) >= 2 and len(parts[0]) == 8 and len(parts[1]) == 8:
        return f"{parts[0]}_{parts[1]}"
    return None


def _related_failure_paths(batch_dir: Path, window_tag: str) -> list[Path]:
    names = [
        f"MO_{window_tag}_failures.csv",
        f"MO_{window_tag}_retry_failures.csv",
        f"MO_{window_tag}_retry3_failures.csv",
    ]
    return [batch_dir / name for name in names if (batch_dir / name).exists()]


def _archive_path(path: Path) -> Path:
    if path.name.endswith(".resolved.csv"):
        return path
    if path.suffix == ".csv":
        return path.with_name(f"{path.stem}.resolved.csv")
    return path.with_name(f"{path.name}.resolved.csv")


def _archive_file(path: Path, *, dry_run: bool = False) -> Path | None:
    if not path.exists():
        return None
    target = _archive_path(path)
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = target.with_name(f"{target.stem}_{stamp}.csv")
    if dry_run:
        return target
    path.rename(target)
    return target


def sync_window_failures_after_retry(
    batch_dir: str | Path,
    window_tag: str,
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    """Update MO failure CSVs after a ``*_failures_retry`` build_month run.

    - All symbols repaired: archive active failure lists to ``*.resolved.csv``.
    - Remaining failures: overwrite canonical ``MO_{tag}_failures.csv`` with retry output.
    """
    batch = Path(batch_dir)
    retry_failures = batch / f"MO_{window_tag}_failures_retry_failures.csv"
    canonical = batch / f"MO_{window_tag}_failures.csv"

    if retry_failures.exists():
        if dry_run:
            return {
                "action": "updated",
                "canonical": str(canonical),
                "remaining_rows": sum(1 for _ in retry_failures.open(encoding="utf-8-sig")) - 1,
            }
        shutil.copy2(retry_failures, canonical)
        return {
            "action": "updated",
            "canonical": str(canonical),
            "remaining_rows": max(sum(1 for _ in canonical.open(encoding="utf-8-sig")) - 1, 0),
        }

    archived: list[str] = []
    for path in _related_failure_paths(batch, window_tag):
        target = _archive_file(path, dry_run=dry_run)
        if target is not None:
            archived.append(str(target if dry_run else target))

    return {"action": "resolved", "archived": archived}


def sync_resolved_retry_batches(batch_dir: str | Path, *, dry_run: bool = False) -> list[dict[str, object]]:
    """Archive failure lists for windows whose retry batch finished with zero failures."""
    batch = Path(batch_dir)
    results: list[dict[str, object]] = []
    for summary in sorted(batch.glob("MO_*_failures_retry_summary.json")):
        tag = summary.name.replace("MO_", "").replace("_failures_retry_summary.json", "")
        retry_failures = batch / f"MO_{tag}_failures_retry_failures.csv"
        if retry_failures.exists():
            continue
        results.append(
            {
                "window_tag": tag,
                **sync_window_failures_after_retry(batch, tag, dry_run=dry_run),
            }
        )
    return results
