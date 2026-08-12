from datetime import datetime, timedelta

from audit.temporal_audit import is_prior_or_equal, promotion_active


def test_future_competitor_observation_is_excluded():
    decision = datetime(2025, 6, 1, 12)
    assert not is_prior_or_equal(decision + timedelta(seconds=1), decision)
    assert is_prior_or_equal(decision, decision)
    assert is_prior_or_equal(decision - timedelta(days=30), decision)


def test_promotion_requires_temporal_overlap():
    decision = datetime(2025, 6, 15)
    assert promotion_active(datetime(2025, 6, 1), datetime(2025, 6, 30), decision)
    assert not promotion_active(datetime(2025, 6, 16), datetime(2025, 6, 30), decision)
    assert not promotion_active(datetime(2025, 5, 1), datetime(2025, 6, 14), decision)
