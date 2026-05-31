import pandas as pd

from option_platform.data.contract_dates import (
    filter_dates_by_first_valid,
    infer_first_valid_dates_from_quote_root,
    load_first_valid_date_cache,
    save_first_valid_date_cache,
)


def test_filter_dates_by_first_valid():
    dates = ["2022-07-22", "2022-07-25", "2022-07-26"]
    cache = {"CFFEX.MO2208-C-8100": "2022-07-26"}

    assert filter_dates_by_first_valid("CFFEX.MO2208-C-8100", dates, cache) == ["2022-07-26"]
    assert filter_dates_by_first_valid("CFFEX.MO2208-C-6200", dates, cache) == dates


def test_first_valid_date_cache_roundtrip(tmp_path):
    path = tmp_path / "first_valid.json"
    save_first_valid_date_cache({"b": "2022-07-25", "a": "2022-07-22"}, path)

    assert load_first_valid_date_cache(path) == {"a": "2022-07-22", "b": "2022-07-25"}


def test_infer_first_valid_dates_from_quote_root(tmp_path):
    root = tmp_path / "quotes" / "minute" / "MO" / "CFFEX_MO2208-C-6200"
    root.mkdir(parents=True)
    pd.DataFrame(
        {
            "symbol": ["CFFEX.MO2208-C-6200"],
            "quote_quality": ["missing"],
        }
    ).to_parquet(root / "2022-07-22.parquet", index=False)
    pd.DataFrame(
        {
            "symbol": ["CFFEX.MO2208-C-6200"],
            "quote_quality": ["ok"],
        }
    ).to_parquet(root / "2022-07-25.parquet", index=False)

    assert infer_first_valid_dates_from_quote_root(tmp_path, "MO") == {
        "CFFEX.MO2208-C-6200": "2022-07-25"
    }
