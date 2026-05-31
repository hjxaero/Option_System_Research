from option_platform.data.sources.tq_contracts import extract_product_code, filter_option_symbols


def test_extract_product_code():
    assert extract_product_code("CFFEX.MO2606-C-6000") == "MO"
    assert extract_product_code("CFFEX.IM2606") == "IM"
    assert extract_product_code("SSE.000852") == ""


def test_filter_option_symbols_matches_product_prefix():
    symbols = [
        "CFFEX.MO2606-C-6000",
        "CFFEX.IO2606-C-4000",
        "SHFE.rb2606C3500",
        "CFFEX.MO2609-P-5000",
    ]

    assert filter_option_symbols(symbols, "MO") == [
        "CFFEX.MO2606-C-6000",
        "CFFEX.MO2609-P-5000",
    ]

