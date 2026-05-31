import pytest

from option_platform.data.time_to_expiry import (
    TRADING_DAYS_PER_YEAR,
    TRADING_MINUTES_PER_DAY,
    calculate_t_years_by_trading_minutes,
    trading_minutes_elapsed_in_day,
)


def test_trading_minutes_elapsed_in_day_uses_240_minute_convention():
    assert trading_minutes_elapsed_in_day("2026-05-28 09:30") == 0
    assert trading_minutes_elapsed_in_day("2026-05-28 10:00") == 30
    assert trading_minutes_elapsed_in_day("2026-05-28 11:30") == 120
    assert trading_minutes_elapsed_in_day("2026-05-28 12:30") == 120
    assert trading_minutes_elapsed_in_day("2026-05-28 13:01") == 121
    assert trading_minutes_elapsed_in_day("2026-05-28 15:00") == 240
    assert trading_minutes_elapsed_in_day("2026-05-28 16:00") == 240


def test_t_years_does_not_jump_overnight_at_next_open():
    trading_days = ["2026-05-27", "2026-05-28", "2026-05-29"]

    yesterday_close = calculate_t_years_by_trading_minutes(
        "2026-05-27 15:00",
        "2026-05-29",
        trading_days,
    )
    today_open = calculate_t_years_by_trading_minutes(
        "2026-05-28 09:30",
        "2026-05-29",
        trading_days,
    )

    assert today_open == pytest.approx(yesterday_close)


def test_t_years_decays_by_one_minute_during_session():
    trading_days = ["2026-05-28", "2026-05-29"]
    t_0930 = calculate_t_years_by_trading_minutes(
        "2026-05-28 09:30",
        "2026-05-29",
        trading_days,
    )
    t_0931 = calculate_t_years_by_trading_minutes(
        "2026-05-28 09:31",
        "2026-05-29",
        trading_days,
    )

    one_minute = 1 / (TRADING_DAYS_PER_YEAR * TRADING_MINUTES_PER_DAY)
    assert t_0930 - t_0931 == pytest.approx(one_minute)

