from __future__ import annotations


def target_profile(db, schema: str = "dbo") -> dict:
    return db.row(f"""
        SELECT COUNT_BIG(*) total_pricing_decisions,
          SUM(CASE WHEN PurchasedFlag IS NULL THEN 1 ELSE 0 END) null_count,
          SUM(CASE WHEN PurchasedFlag IS NOT NULL THEN 1 ELSE 0 END) non_null_count,
          SUM(CASE WHEN PurchasedFlag=1 THEN 1 ELSE 0 END) purchase_count,
          SUM(CASE WHEN PurchasedFlag=0 THEN 1 ELSE 0 END) non_purchase_count,
          CAST(AVG(CASE WHEN PurchasedFlag IS NOT NULL THEN CAST(PurchasedFlag AS float) END) AS decimal(18,6)) purchase_rate
        FROM [{schema}].[Pricing_Decision_Log]
    """)


def quantity_profile(db, schema: str = "dbo") -> dict:
    rows = db.rows(f"""
        WITH q AS (
          SELECT PurchasedFlag, QuantityPurchased,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY QuantityPurchased) OVER (PARTITION BY PurchasedFlag) median,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY QuantityPurchased) OVER (PARTITION BY PurchasedFlag) p75,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY QuantityPurchased) OVER (PARTITION BY PurchasedFlag) p90,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY QuantityPurchased) OVER (PARTITION BY PurchasedFlag) p95,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY QuantityPurchased) OVER (PARTITION BY PurchasedFlag) p99
          FROM [{schema}].[Pricing_Decision_Log]
        )
        SELECT COALESCE(CAST(PurchasedFlag AS varchar(8)),'NULL') outcome_group,
          COUNT_BIG(*) row_count, SUM(CASE WHEN QuantityPurchased IS NULL THEN 1 ELSE 0 END) null_count,
          SUM(CASE WHEN QuantityPurchased=0 THEN 1 ELSE 0 END) zero_count,
          SUM(CASE WHEN QuantityPurchased>0 THEN 1 ELSE 0 END) positive_count,
          MIN(QuantityPurchased) min_value, MAX(QuantityPurchased) max_value,
          AVG(CAST(QuantityPurchased AS float)) mean_value, STDEV(CAST(QuantityPurchased AS float)) std_value,
          MAX(median) median, MAX(p75) p75, MAX(p90) p90, MAX(p95) p95, MAX(p99) p99
        FROM q GROUP BY PurchasedFlag
    """)
    return {"groups": rows}


def outcome_consistency(db, schema: str = "dbo") -> dict:
    return db.row(f"""
      SELECT
       SUM(CASE WHEN PurchasedFlag=0 AND QuantityPurchased>0 THEN 1 ELSE 0 END) nonpurchase_positive_quantity,
       SUM(CASE WHEN PurchasedFlag=0 AND ActualRevenue>0 THEN 1 ELSE 0 END) nonpurchase_positive_revenue,
       SUM(CASE WHEN PurchasedFlag=1 AND (QuantityPurchased IS NULL OR QuantityPurchased<=0) THEN 1 ELSE 0 END) purchase_nonpositive_quantity,
       SUM(CASE WHEN PurchasedFlag=1 AND (ActualRevenue IS NULL OR ActualRevenue<=0) THEN 1 ELSE 0 END) purchase_nonpositive_revenue,
       SUM(CASE WHEN OutcomeTime < DecisionTime THEN 1 ELSE 0 END) outcome_before_decision
      FROM [{schema}].[Pricing_Decision_Log]
    """)
