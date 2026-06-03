from __future__ import annotations

from pathlib import Path

import pytest

from option_platform.data.quality.failure_records import sync_window_failures_after_retry


def test_sync_archives_failures_when_retry_has_no_remaining(tmp_path: Path) -> None:
    batch = tmp_path
    tag = "20220930_20221009"
    original = batch / f"MO_{tag}_failures.csv"
    original.write_text("symbol,trade_date,error,failure\nCFFEX.MO2211-C-7900,,timeout,\n", encoding="utf-8-sig")
    (batch / f"MO_{tag}_failures_retry_summary.json").write_text("{}", encoding="utf-8")

    result = sync_window_failures_after_retry(batch, tag)

    assert result["action"] == "resolved"
    assert not original.exists()
    assert (batch / f"MO_{tag}_failures.resolved.csv").exists()


def test_sync_overwrites_canonical_when_retry_still_has_failures(tmp_path: Path) -> None:
    batch = tmp_path
    tag = "20230528_20230606"
    canonical = batch / f"MO_{tag}_failures.csv"
    canonical.write_text("symbol,trade_date,error,failure\nOLD,,,\n", encoding="utf-8-sig")
    retry_failures = batch / f"MO_{tag}_failures_retry_failures.csv"
    retry_failures.write_text(
        "symbol,trade_date,error,failure\nCFFEX.MO2312-P-7400,,still bad,\n",
        encoding="utf-8-sig",
    )

    result = sync_window_failures_after_retry(batch, tag)

    assert result["action"] == "updated"
    assert "OLD" not in canonical.read_text(encoding="utf-8-sig")
    assert "CFFEX.MO2312-P-7400" in canonical.read_text(encoding="utf-8-sig")
