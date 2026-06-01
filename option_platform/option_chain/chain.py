from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from option_platform.core.models import (
    OptionChainRow,
    OptionRight,
    UnderlyingQuote,
    normalize_option_right,
)


def _as_date(value: date | datetime | str | None, fallback: datetime | None) -> date:
    if value is None:
        if fallback is not None:
            return fallback.date()
        return datetime.utcnow().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _in_range(value: float | int | None, bounds: tuple[float | int | None, float | int | None] | None) -> bool:
    if bounds is None:
        return True
    if value is None:
        return False
    lower, upper = bounds
    if lower is not None and value < lower:
        return False
    if upper is not None and value > upper:
        return False
    return True


@dataclass(frozen=True)
class OptionChain:
    underlying: UnderlyingQuote
    rows: tuple[OptionChainRow, ...]
    as_of: date

    def __init__(
        self,
        *,
        underlying: UnderlyingQuote,
        rows: Iterable[OptionChainRow],
        as_of: date | datetime | str | None = None,
    ) -> None:
        sorted_rows = tuple(sorted(rows, key=lambda row: (row.expiration, row.strike)))
        object.__setattr__(self, "underlying", underlying)
        object.__setattr__(self, "rows", sorted_rows)
        object.__setattr__(self, "as_of", _as_date(as_of, underlying.timestamp))

    def expirations(self) -> list[date]:
        return sorted({row.expiration for row in self.rows})

    def strikes(self, expiration: date | datetime | str | None = None) -> list[float]:
        rows = self.by_expiration(expiration) if expiration is not None else self.rows
        return sorted({row.strike for row in rows})

    def by_expiration(self, expiration: date | datetime | str) -> list[OptionChainRow]:
        target = _as_date(expiration, None)
        return [row for row in self.rows if row.expiration == target]

    def get_row(self, expiration: date | datetime | str, strike: float) -> OptionChainRow | None:
        target = _as_date(expiration, None)
        for row in self.rows:
            if row.expiration == target and row.strike == float(strike):
                return row
        return None

    def dte(self, expiration: date | datetime | str) -> int:
        target = _as_date(expiration, None)
        return max((target - self.as_of).days, 0)

    def get_atm(self, expiration: date | datetime | str) -> OptionChainRow | None:
        rows = self.by_expiration(expiration)
        if not rows:
            return None
        return min(rows, key=lambda row: abs(row.strike - self.underlying.price))

    def filter(
        self,
        *,
        expiration: date | datetime | str | None = None,
        dte: tuple[int | None, int | None] | None = None,
        right: OptionRight | None = None,
        delta: tuple[float | None, float | None] | None = None,
        min_volume: float | None = None,
        min_open_interest: float | None = None,
        max_spread_bps: float | None = None,
        moneyness: tuple[float | None, float | None] | None = None,
    ) -> list[OptionChainRow]:
        rows = self.by_expiration(expiration) if expiration is not None else list(self.rows)
        normalized_right = normalize_option_right(right) if right is not None else None
        selected = []

        for row in rows:
            if not _in_range(self.dte(row.expiration), dte):
                continue
            if not _in_range(row.strike / self.underlying.price, moneyness):
                continue
            if normalized_right is not None:
                quote = row.quote(normalized_right)
                greeks = row.greeks(normalized_right)
                if quote is None:
                    continue
                if delta is not None and not _in_range(getattr(greeks, "delta", None), delta):
                    continue
                if min_volume is not None and (quote.volume is None or quote.volume < min_volume):
                    continue
                if min_open_interest is not None and (
                    quote.open_interest is None or quote.open_interest < min_open_interest
                ):
                    continue
                if max_spread_bps is not None and (
                    quote.spread_bps is None or quote.spread_bps > max_spread_bps
                ):
                    continue
            selected.append(row)

        return selected
