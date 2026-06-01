from __future__ import annotations

import re

_MO_MONTH_RE = re.compile(r"\.MO(\d{4})[-.]", re.IGNORECASE)
_IM_MONTH_RE = re.compile(r"\.IM(\d{4})$", re.IGNORECASE)


def mo_contract_month(symbol: str) -> str | None:
    """Extract YYMM from ``CFFEX.MO2601-C-6000`` -> ``2601``."""
    if not symbol:
        return None
    match = _MO_MONTH_RE.search(symbol)
    return match.group(1) if match else None


def im_contract_month(symbol: str) -> str | None:
    """Extract YYMM from ``CFFEX.IM2601`` -> ``2601``."""
    if not symbol:
        return None
    match = _IM_MONTH_RE.search(symbol)
    return match.group(1) if match else None


def im_symbol_for_month(contract_month: str, exchange: str = "CFFEX") -> str:
    return f"{exchange}.IM{contract_month}"
