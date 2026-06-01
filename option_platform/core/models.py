from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite, log
from typing import Literal


OptionRight = Literal["call", "put"]


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _as_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def normalize_option_right(value: object) -> OptionRight:
    text = str(value).strip().lower()
    if text in {"c", "call", "calls"}:
        return "call"
    if text in {"p", "put", "puts"}:
        return "put"
    raise ValueError(f"Unsupported option right: {value!r}")


def _positive_number(value: float | None) -> bool:
    return value is not None and isfinite(float(value)) and float(value) > 0


@dataclass(frozen=True)
class UnderlyingQuote:
    symbol: str
    price: float
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if not _positive_number(self.price):
            raise ValueError("underlying price must be positive")
        object.__setattr__(self, "price", float(self.price))
        object.__setattr__(self, "timestamp", _as_datetime(self.timestamp))


@dataclass(frozen=True)
class OptionContractRef:
    contract_id: str
    underlying_symbol: str
    expiration: date | str
    strike: float
    right: OptionRight
    multiplier: int = 1
    exchange: str = ""
    style: str = ""

    def __post_init__(self) -> None:
        if not self.contract_id:
            raise ValueError("contract_id is required")
        if not self.underlying_symbol:
            raise ValueError("underlying_symbol is required")
        if not _positive_number(self.strike):
            raise ValueError("strike must be positive")
        if int(self.multiplier) <= 0:
            raise ValueError("multiplier must be positive")
        object.__setattr__(self, "expiration", _as_date(self.expiration))
        object.__setattr__(self, "strike", float(self.strike))
        object.__setattr__(self, "right", normalize_option_right(self.right))
        object.__setattr__(self, "multiplier", int(self.multiplier))

    def dte(self, as_of: date | datetime | str) -> int:
        return max((self.expiration - _as_date(as_of)).days, 0)

    def intrinsic_value(self, underlying_price: float) -> float:
        if self.right == "call":
            return max(float(underlying_price) - self.strike, 0.0)
        return max(self.strike - float(underlying_price), 0.0)

    def moneyness(self, underlying_price: float) -> float:
        return self.strike / float(underlying_price)

    def log_moneyness(self, underlying_price: float) -> float:
        return log(self.moneyness(underlying_price))


@dataclass(frozen=True)
class OptionQuote:
    contract_id: str
    timestamp: datetime | str | None = None
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    mark: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    implied_volatility: float | None = None
    quote_quality: str = ""

    def __post_init__(self) -> None:
        if not self.contract_id:
            raise ValueError("contract_id is required")
        object.__setattr__(self, "timestamp", _as_datetime(self.timestamp))

    @property
    def mid(self) -> float | None:
        if _positive_number(self.bid) and _positive_number(self.ask):
            return (float(self.bid) + float(self.ask)) / 2
        return None

    @property
    def effective_price(self) -> float | None:
        if _positive_number(self.mark):
            return float(self.mark)
        if self.mid is not None:
            return self.mid
        if _positive_number(self.last):
            return float(self.last)
        return None

    @property
    def spread(self) -> float | None:
        if _positive_number(self.bid) and _positive_number(self.ask):
            return float(self.ask) - float(self.bid)
        return None

    @property
    def spread_bps(self) -> float | None:
        mid = self.mid
        spread = self.spread
        if mid is None or spread is None or mid <= 0:
            return None
        return spread / mid * 10000


@dataclass(frozen=True)
class OptionGreeks:
    contract_id: str
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    theoretical_price: float | None = None
    model_iv: float | None = None


@dataclass(frozen=True)
class OptionChainRow:
    expiration: date
    strike: float
    call_contract: OptionContractRef | None = None
    put_contract: OptionContractRef | None = None
    call_quote: OptionQuote | None = None
    put_quote: OptionQuote | None = None
    call_greeks: OptionGreeks | None = None
    put_greeks: OptionGreeks | None = None

    def contract(self, right: OptionRight) -> OptionContractRef | None:
        return self.call_contract if normalize_option_right(right) == "call" else self.put_contract

    def quote(self, right: OptionRight) -> OptionQuote | None:
        return self.call_quote if normalize_option_right(right) == "call" else self.put_quote

    def greeks(self, right: OptionRight) -> OptionGreeks | None:
        return self.call_greeks if normalize_option_right(right) == "call" else self.put_greeks
