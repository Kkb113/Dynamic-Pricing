from __future__ import annotations

from datetime import datetime


TEMPORAL_COLUMNS = {
    "Browsing_Events": ["EventTime"], "Cart_Events": ["EventTime"],
    "Competitor_Price": ["ObservedDateTime"], "Pricing_Decision_Log": ["DecisionTime", "OutcomeTime"],
    "Product_Price_History": ["EffectiveFrom", "EffectiveTo"], "Promotions": ["StartDate", "EndDate"],
    "Ratings": ["RatingDate"], "Recommendation_Log": ["ServedTime"],
    "Recommendation_Response": ["ResponseTime"], "Sales_Order": ["OrderDate"],
    "Search_Events": ["EventTime"], "Weather": ["Date"], "Wishlist": ["AddedDate", "RemovedDate"],
    "Customer": ["CreatedDate"], "Inventory": ["SnapshotDate"], "Holiday": ["Date"],
}


def is_prior_or_equal(observed_at: datetime, decision_at: datetime) -> bool:
    return observed_at <= decision_at


def price_interval_active(effective_from: datetime, effective_to: datetime | None, decision_at: datetime) -> bool:
    return effective_from <= decision_at and (effective_to is None or decision_at < effective_to)


def promotion_active(start: datetime, end: datetime, decision_at: datetime) -> bool:
    return start <= decision_at <= end


def temporal_coverage(db, existing: set[tuple[str, str]], schema: str = "dbo") -> list[dict]:
    output = []
    for table, columns in TEMPORAL_COLUMNS.items():
        for column in columns:
            if (table, column) not in existing:
                output.append({"table": table, "column": column, "status": "MISSING"}); continue
            q = f"""WITH dates AS (SELECT DISTINCT CAST([{column}] AS date) active_date FROM [{schema}].[{table}] WHERE [{column}] IS NOT NULL),
                     gaps AS (SELECT DATEDIFF(day,LAG(active_date) OVER(ORDER BY active_date),active_date) gap_days FROM dates)
                     SELECT COUNT_BIG(*) row_count, MIN([{column}]) min_timestamp, MAX([{column}]) max_timestamp,
                     COUNT(DISTINCT CAST([{column}] AS date)) distinct_active_dates,
                     (SELECT MAX(gap_days) FROM gaps) max_gap_days
                     FROM [{schema}].[{table}]"""
            output.append({"table": table, "column": column, "status": "AVAILABLE", **db.row(q)})
    return output


def temporal_monthly_distribution(db, existing: set[tuple[str, str]], schema: str = "dbo") -> list[dict]:
    output=[]
    for table,columns in TEMPORAL_COLUMNS.items():
        for column in columns:
            if (table,column) not in existing: continue
            output.extend(db.rows(f"""SELECT ? source_table,? source_column,CONVERT(char(7),[{column}],120) month,COUNT_BIG(*) row_count
              FROM [{schema}].[{table}] WHERE [{column}] IS NOT NULL GROUP BY CONVERT(char(7),[{column}],120)
              ORDER BY month""",[table,column]))
    return output
