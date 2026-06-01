from option_platform.data.download_windows import iter_download_windows


def test_iter_download_windows_splits_calendar_range():
    windows = iter_download_windows("2022-07-22", "2022-08-04", window_days=10)
    assert windows == [
        ("2022-07-22", "2022-07-31"),
        ("2022-08-01", "2022-08-04"),
    ]


def test_iter_download_windows_single_day():
    assert iter_download_windows("2026-01-19", "2026-01-19", window_days=10) == [
        ("2026-01-19", "2026-01-19"),
    ]


def test_iter_download_windows_empty_when_start_after_end():
    assert iter_download_windows("2026-02-01", "2026-01-01", window_days=10) == []
