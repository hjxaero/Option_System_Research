from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from option_platform.data.contracts import TermRole


QUARTER_MONTHS = {3, 6, 9, 12}


@dataclass(frozen=True)
class TermSelection:
    role: TermRole
    expiry_date: str


def _parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _is_quarter_expiry(expiry: date) -> bool:
    return expiry.month in QUARTER_MONTHS


def select_four_terms(
    expiry_dates: Iterable[str],
    as_of: str | date | datetime,
) -> list[TermSelection]:
    """Select current month, next month, current quarter and next quarter expiries.

    The returned expiries are unique. If a monthly role overlaps a quarter role,
    the quarter role advances to the next available quarterly expiry so the
    snapshot universe still contains four distinct expiry dates when the market
    lists enough terms.
    """
    as_of_date = _parse_date(as_of)
    expiries = sorted({_parse_date(d) for d in expiry_dates if _parse_date(d) >= as_of_date})
    if len(expiries) < 2:
        return [
            TermSelection("current_month", e.strftime("%Y-%m-%d"))
            for e in expiries[:1]
        ]

    selected: list[TermSelection] = [
        TermSelection("current_month", expiries[0].strftime("%Y-%m-%d")),
        TermSelection("next_month", expiries[1].strftime("%Y-%m-%d")),
    ]
    used = {item.expiry_date for item in selected}

    quarter_expiries = [e for e in expiries if _is_quarter_expiry(e)]
    for role in ("current_quarter", "next_quarter"):
        chosen = None
        for expiry in quarter_expiries:
            expiry_str = expiry.strftime("%Y-%m-%d")
            if expiry_str not in used:
                chosen = expiry_str
                break
        if chosen is None:
            break
        selected.append(TermSelection(role, chosen))
        used.add(chosen)

    return selected


def term_role_map(selections: Iterable[TermSelection]) -> dict[str, TermRole]:
    return {item.expiry_date: item.role for item in selections}

