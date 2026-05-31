from __future__ import annotations

import numpy as np
import pandas as pd


def build_raw_surface_nodes(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Build raw IV surface nodes from cleaned option snapshots.

    This function does not smooth or fill missing IV. It only projects cleaned
    snapshot rows into the surface schema.
    """
    if snapshot.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "expiry_date",
                "term_role",
                "strike_price",
                "option_type",
                "moneyness",
                "log_moneyness",
                "delta",
                "t_years",
                "raw_iv",
                "smooth_iv",
                "iv_quality",
                "surface_quality",
            ]
        )

    required = ["timestamp", "expiry_date", "strike_price", "option_type", "iv", "iv_quality"]
    missing = [col for col in required if col not in snapshot.columns]
    if missing:
        raise ValueError(f"snapshot missing columns: {missing}")

    result = pd.DataFrame()
    result["timestamp"] = snapshot["timestamp"]
    result["expiry_date"] = snapshot["expiry_date"]
    result["term_role"] = snapshot.get("term_role", "")
    result["strike_price"] = snapshot["strike_price"]
    result["option_type"] = snapshot["option_type"]

    forward = pd.to_numeric(snapshot.get("futures_price", snapshot.get("underlying_price")), errors="coerce")
    strike = pd.to_numeric(snapshot["strike_price"], errors="coerce")
    result["moneyness"] = strike / forward
    result.loc[~np.isfinite(result["moneyness"]) | (result["moneyness"] <= 0), "moneyness"] = np.nan
    result["log_moneyness"] = np.log(result["moneyness"])
    result["delta"] = snapshot.get("delta", np.nan)
    result["t_years"] = snapshot.get("t_years", np.nan)
    result["raw_iv"] = snapshot["iv"]
    result["smooth_iv"] = np.nan
    result["iv_quality"] = snapshot["iv_quality"]
    result["surface_quality"] = snapshot["iv_quality"]
    return result

