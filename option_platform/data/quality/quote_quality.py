from __future__ import annotations

import pandas as pd


def valid_bid_ask_frame(frame: pd.DataFrame) -> pd.Series:
    bid = frame["bid_price1"]
    ask = frame["ask_price1"]
    return bid.notna() & ask.notna() & (bid > 0) & (ask > 0) & (ask >= bid)


def add_quote_quality_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    valid = valid_bid_ask_frame(result)
    result["quote_valid"] = valid
    result["mid_price"] = pd.NA
    result.loc[valid, "mid_price"] = (
        result.loc[valid, "bid_price1"] + result.loc[valid, "ask_price1"]
    ) / 2
    result["spread"] = pd.NA
    result.loc[valid, "spread"] = result.loc[valid, "ask_price1"] - result.loc[valid, "bid_price1"]
    result["spread_bps"] = pd.NA
    nonzero_mid = valid & (result["mid_price"] > 0)
    result.loc[nonzero_mid, "spread_bps"] = result.loc[nonzero_mid, "spread"] / result.loc[nonzero_mid, "mid_price"] * 10000

    has_depth = valid & (result["bid_volume1"] > 0) & (result["ask_volume1"] > 0)
    result["micro_price"] = pd.NA
    result.loc[has_depth, "micro_price"] = (
        result.loc[has_depth, "ask_price1"] * result.loc[has_depth, "bid_volume1"]
        + result.loc[has_depth, "bid_price1"] * result.loc[has_depth, "ask_volume1"]
    ) / (result.loc[has_depth, "bid_volume1"] + result.loc[has_depth, "ask_volume1"])
    return result

