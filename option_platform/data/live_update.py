from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from option_platform.data.sources.tq_minute_quotes import (
    build_daily_minute_quotes,
    build_symbol_range_minute_quotes,
)
from option_platform.data.storage.state import UpdateState, save_state, state_path
from option_platform.data.storage.upsert import upsert_parquet


def minute_quote_path(data_root: str | Path, product: str, symbol: str, trade_date: str) -> Path:
    safe_symbol = symbol.replace(".", "_")
    return (
        Path(data_root)
        / "quotes"
        / "minute"
        / product.upper()
        / safe_symbol
        / f"{trade_date}.parquet"
    )


def should_skip_minute_quote_update(
    path: str | Path,
    *,
    min_rows: int = 200,
    min_ok_ratio: float = 0.70,
) -> bool:
    """Skip re-download when an on-disk minute quote file already looks usable."""
    parquet_path = Path(path)
    if not parquet_path.exists():
        return False
    try:
        frame = pd.read_parquet(parquet_path)
    except Exception:
        return False
    if len(frame) < min_rows or "quote_quality" not in frame.columns:
        return False
    ok_ratio = float((frame["quote_quality"] == "ok").mean())
    return ok_ratio >= min_ok_ratio


@dataclass(frozen=True)
class MinuteQuoteUpdateResult:
    output_path: Path
    state_path: Path
    rows_written: int
    max_target_time: str | None
    max_quote_time: str | None
    quality_counts: dict[str, int]


@dataclass(frozen=True)
class BatchMinuteQuoteUpdateResult:
    total_symbols: int
    succeeded: int
    failed: int
    results: list[MinuteQuoteUpdateResult]
    errors: dict[str, str]


def recent_window(
    trade_date: str,
    end_time: datetime | None,
    window_minutes: int | None,
) -> tuple[datetime | None, datetime | None]:
    if not window_minutes or window_minutes <= 0:
        return None, None

    if end_time is None:
        end_time = datetime.now()
    if end_time.strftime("%Y-%m-%d") != trade_date:
        end_time = datetime.strptime(f"{trade_date} 15:00:00", "%Y-%m-%d %H:%M:%S")
    start_time = end_time - timedelta(minutes=window_minutes - 1)
    return start_time.replace(second=0, microsecond=0), end_time.replace(second=0, microsecond=0)


def update_daily_minute_quotes(
    api: object,
    data_root: str | Path,
    product: str,
    symbol: str,
    trade_date: str,
    max_quote_age_ms: int = 60_000,
    target_start_time: datetime | None = None,
    target_end_time: datetime | None = None,
    quote_lookback_minutes: int = 30,
) -> MinuteQuoteUpdateResult:
    output = minute_quote_path(data_root, product, symbol, trade_date)

    incoming = build_daily_minute_quotes(
        api,
        symbol=symbol,
        trade_date=trade_date,
        max_quote_age_ms=max_quote_age_ms,
        target_start_time=target_start_time,
        target_end_time=target_end_time,
        quote_lookback_minutes=quote_lookback_minutes,
    )
    merged = upsert_parquet(output, incoming)

    max_target = None
    max_quote = None
    if not merged.empty:
        max_target = pd.Timestamp(merged["target_time"].max()).isoformat()
        valid_quotes = merged["quote_time"].dropna()
        if len(valid_quotes) > 0:
            max_quote = pd.Timestamp(valid_quotes.max()).isoformat()

    counts = {
        str(k): int(v)
        for k, v in merged["quote_quality"].value_counts(dropna=False).to_dict().items()
    }
    state_file = state_path(data_root, product, symbol, trade_date)
    save_state(
        state_file,
        UpdateState(
            product=product.upper(),
            symbol=symbol,
            trade_date=trade_date,
            last_target_time=max_target,
            last_quote_time=max_quote,
            rows=len(merged),
        ),
    )

    return MinuteQuoteUpdateResult(
        output_path=output,
        state_path=state_file,
        rows_written=len(merged),
        max_target_time=max_target,
        max_quote_time=max_quote,
        quality_counts=counts,
    )


def update_batch_minute_quotes(
    api: object,
    data_root: str | Path,
    product: str,
    symbols: list[str],
    trade_date: str,
    max_quote_age_ms: int = 60_000,
    target_start_time: datetime | None = None,
    target_end_time: datetime | None = None,
    quote_lookback_minutes: int = 30,
    skip_if_complete: bool = False,
    min_ok_ratio: float = 0.70,
) -> BatchMinuteQuoteUpdateResult:
    results: list[MinuteQuoteUpdateResult] = []
    errors: dict[str, str] = {}
    skipped = 0

    for idx, symbol in enumerate(symbols, 1):
        output = minute_quote_path(data_root, product, symbol, trade_date)
        if skip_if_complete and should_skip_minute_quote_update(output, min_ok_ratio=min_ok_ratio):
            skipped += 1
            print(f"[{idx}/{len(symbols)}] skip {symbol} (complete)", flush=True)
            continue
        print(f"[{idx}/{len(symbols)}] update {symbol}", flush=True)
        try:
            result = update_daily_minute_quotes(
                api=api,
                data_root=data_root,
                product=product,
                symbol=symbol,
                trade_date=trade_date,
                max_quote_age_ms=max_quote_age_ms,
                target_start_time=target_start_time,
                target_end_time=target_end_time,
                quote_lookback_minutes=quote_lookback_minutes,
            )
            results.append(result)
        except Exception as exc:
            errors[symbol] = str(exc)
            print(f"[FAIL] {symbol}: {exc}")

    if skipped:
        print(f"skipped_complete={skipped}", flush=True)

    return BatchMinuteQuoteUpdateResult(
        total_symbols=len(symbols),
        succeeded=len(results),
        failed=len(errors),
        results=results,
        errors=errors,
    )


def save_minute_quote_frame(
    frame: pd.DataFrame,
    data_root: str | Path,
    product: str,
    symbol: str,
    trade_date: str,
) -> MinuteQuoteUpdateResult:
    output = minute_quote_path(data_root, product, symbol, trade_date)
    merged = upsert_parquet(output, frame)

    max_target = None
    max_quote = None
    if not merged.empty:
        max_target = pd.Timestamp(merged["target_time"].max()).isoformat()
        valid_quotes = merged["quote_time"].dropna()
        if len(valid_quotes) > 0:
            max_quote = pd.Timestamp(valid_quotes.max()).isoformat()

    counts = {
        str(k): int(v)
        for k, v in merged["quote_quality"].value_counts(dropna=False).to_dict().items()
    }
    state_file = state_path(data_root, product, symbol, trade_date)
    save_state(
        state_file,
        UpdateState(
            product=product.upper(),
            symbol=symbol,
            trade_date=trade_date,
            last_target_time=max_target,
            last_quote_time=max_quote,
            rows=len(merged),
        ),
    )
    return MinuteQuoteUpdateResult(
        output_path=output,
        state_path=state_file,
        rows_written=len(merged),
        max_target_time=max_target,
        max_quote_time=max_quote,
        quality_counts=counts,
    )


def update_symbol_range_minute_quotes(
    api: object,
    data_root: str | Path,
    product: str,
    symbol: str,
    trade_dates: list[str],
    max_quote_age_ms: int = 60_000,
    skip_if_complete: bool = False,
    min_ok_ratio: float = 0.70,
) -> tuple[int, int, list[str]]:
    """Return (saved_days, skipped_days, failures)."""
    frames = build_symbol_range_minute_quotes(
        api,
        symbol=symbol,
        trade_dates=trade_dates,
        max_quote_age_ms=max_quote_age_ms,
    )
    saved = 0
    skipped = 0
    failures: list[str] = []
    for trade_date, frame in frames.items():
        output = minute_quote_path(data_root, product, symbol, trade_date)
        if skip_if_complete and should_skip_minute_quote_update(output, min_ok_ratio=min_ok_ratio):
            skipped += 1
            continue
        try:
            save_minute_quote_frame(frame, data_root, product, symbol, trade_date)
            saved += 1
        except Exception as exc:
            failures.append(f"{trade_date}: {exc}")
    return saved, skipped, failures

