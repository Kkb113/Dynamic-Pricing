from datetime import date, datetime, timedelta

from audit.sales_coverage_audit import is_completed_previous_calendar_day, sales_coverage
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


def test_date_only_sales_require_completed_previous_calendar_day():
    decision = datetime(2025, 6, 10, 23, 59)
    assert is_completed_previous_calendar_day(date(2025, 6, 9), decision)
    assert not is_completed_previous_calendar_day(date(2025, 6, 10), decision)
    assert not is_completed_previous_calendar_day(date(2025, 6, 11), decision)


def test_sales_audit_sql_excludes_same_day_orders():
    class CaptureDb:
        sql = []
        def row(self, sql):
            self.sql.append(sql)
            return {"decisions":1,"covered_7d":0}

    db=CaptureDb()
    sales_coverage(db,[7])
    assert len(db.sql)==5
    assert all("o.OrderDate<CAST(d.DecisionTime AS date)" in sql for sql in db.sql)
    assert all("DATEADD(day,-7,CAST(d.DecisionTime AS date))" in sql for sql in db.sql)
