import pytest

from option_platform.data.quality.snapshot_checks import CompletenessResult
from option_platform.data.pricing import choose_mark_price
from option_platform.data.term_selection import select_four_terms


def test_completeness_result_flag():
    assert CompletenessResult("complete").is_complete
    assert not CompletenessResult("missing").is_complete


def test_select_four_terms_uses_distinct_quarter_expiries():
    terms = select_four_terms(
        ["2026-03-20", "2026-04-17", "2026-06-19", "2026-09-18", "2026-12-18"],
        "2026-03-01",
    )

    assert [term.role for term in terms] == [
        "current_month",
        "next_month",
        "current_quarter",
        "next_quarter",
    ]
    assert [term.expiry_date for term in terms] == [
        "2026-03-20",
        "2026-04-17",
        "2026-06-19",
        "2026-09-18",
    ]


def test_choose_mark_price_prefers_depth_weighted_micro_price():
    mark = choose_mark_price(
        bid_price1=10,
        ask_price1=10.2,
        bid_volume1=3,
        ask_volume1=1,
        last_price=11.8,
    )

    assert mark.source == "micro"
    assert mark.price == pytest.approx(10.15)
    assert mark.quality == "ok"


def test_choose_mark_price_tags_last_fallback():
    mark = choose_mark_price(
        bid_price1=None,
        ask_price1=None,
        last_price=9.5,
    )

    assert mark.source == "last"
    assert mark.quality == "last_fallback"
