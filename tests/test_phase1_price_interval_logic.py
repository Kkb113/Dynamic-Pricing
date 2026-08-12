from datetime import datetime, timedelta

from audit.temporal_audit import price_interval_active


def test_half_open_price_interval():
    start = datetime(2025, 1, 1)
    end = datetime(2025, 2, 1)
    assert price_interval_active(start, end, start)
    assert price_interval_active(start, end, end - timedelta(microseconds=1))
    assert not price_interval_active(start, end, end)


def test_open_ended_price_interval():
    start = datetime(2025, 1, 1)
    assert price_interval_active(start, None, datetime(2030, 1, 1))
    assert not price_interval_active(start, None, datetime(2024, 12, 31))
