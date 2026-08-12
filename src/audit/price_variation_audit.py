from __future__ import annotations


PRICE_BUCKET_CASE = """CASE
 WHEN CurrentPrice IS NULL OR CurrentPrice=0 OR AppliedPrice IS NULL THEN 'UNKNOWN'
 WHEN (AppliedPrice-CurrentPrice)/CurrentPrice <= -0.20 THEN '<= -20%'
 WHEN (AppliedPrice-CurrentPrice)/CurrentPrice <= -0.10 THEN '-20% to -10%'
 WHEN (AppliedPrice-CurrentPrice)/CurrentPrice <= -0.05 THEN '-10% to -5%'
 WHEN (AppliedPrice-CurrentPrice)/CurrentPrice < 0 THEN '-5% to 0%'
 WHEN AppliedPrice=CurrentPrice THEN '0%'
 WHEN (AppliedPrice-CurrentPrice)/CurrentPrice <= 0.05 THEN '0% to +5%'
 WHEN (AppliedPrice-CurrentPrice)/CurrentPrice <= 0.10 THEN '+5% to +10%'
 WHEN (AppliedPrice-CurrentPrice)/CurrentPrice <= 0.20 THEN '+10% to +20%'
 ELSE '> +20%' END"""


def product_price_support(db, schema: str = "dbo") -> list[dict]:
    return db.rows(f"""
      SELECT ProductID, COUNT_BIG(*) decision_count,
       COUNT(DISTINCT CurrentPrice) unique_current_price_count,
       COUNT(DISTINCT AppliedPrice) unique_applied_price_count,
       MIN(AppliedPrice) min_applied_price, MAX(AppliedPrice) max_applied_price,
       AVG(CAST(AppliedPrice AS float)) mean_applied_price, STDEV(CAST(AppliedPrice AS float)) std_applied_price,
       MAX(AppliedPrice)-MIN(AppliedPrice) applied_price_range,
       STDEV(CAST(AppliedPrice AS float))/NULLIF(AVG(CAST(AppliedPrice AS float)),0) applied_price_cv,
       SUM(CASE WHEN AppliedPrice<>CurrentPrice THEN 1 ELSE 0 END)*1.0/COUNT_BIG(*) pct_changed
      FROM [{schema}].[Pricing_Decision_Log] GROUP BY ProductID ORDER BY ProductID
    """)


def price_variation_summary(db, schema: str = "dbo") -> dict:
    support = db.row(f"""
      WITH p AS (SELECT ProductID, COUNT_BIG(*) n, COUNT(DISTINCT AppliedPrice) prices
       FROM [{schema}].[Pricing_Decision_Log] GROUP BY ProductID)
      SELECT COUNT_BIG(*) products,
       SUM(CASE WHEN n>=2 THEN 1 ELSE 0 END) products_ge_2_decisions,
       SUM(CASE WHEN n>=5 THEN 1 ELSE 0 END) products_ge_5_decisions,
       SUM(CASE WHEN n>=10 THEN 1 ELSE 0 END) products_ge_10_decisions,
       SUM(CASE WHEN n>=20 THEN 1 ELSE 0 END) products_ge_20_decisions,
       SUM(CASE WHEN prices>=2 THEN 1 ELSE 0 END) products_ge_2_prices,
       SUM(CASE WHEN prices>=3 THEN 1 ELSE 0 END) products_ge_3_prices,
       SUM(CASE WHEN prices>=5 THEN 1 ELSE 0 END) products_ge_5_prices FROM p
    """)
    buckets = db.rows(f"""
      SELECT price_bucket, COUNT_BIG(*) decision_count, SUM(CASE WHEN PurchasedFlag=1 THEN 1 ELSE 0 END) purchase_count,
       AVG(CAST(PurchasedFlag AS float)) purchase_rate, AVG(CAST(QuantityPurchased AS float)) avg_quantity,
       AVG(CAST(ActualRevenue AS float)) avg_actual_revenue, COUNT(DISTINCT ProductID) product_coverage
      FROM (SELECT *, {PRICE_BUCKET_CASE} price_bucket FROM [{schema}].[Pricing_Decision_Log]) d
      GROUP BY price_bucket ORDER BY MIN(CASE price_bucket WHEN '<= -20%' THEN 1 WHEN '-20% to -10%' THEN 2
       WHEN '-10% to -5%' THEN 3 WHEN '-5% to 0%' THEN 4 WHEN '0%' THEN 5 WHEN '0% to +5%' THEN 6
       WHEN '+5% to +10%' THEN 7 WHEN '+10% to +20%' THEN 8 WHEN '> +20%' THEN 9 ELSE 10 END)
    """)
    policy = db.row(f"""SELECT COUNT_BIG(*) decisions,
       SUM(CASE WHEN RecommendedPrice=AppliedPrice THEN 1 ELSE 0 END) recommended_equals_applied,
       SUM(CASE WHEN RecommendedPrice<>AppliedPrice THEN 1 ELSE 0 END) recommended_differs_applied,
       AVG(ABS(CAST(RecommendedPrice AS float)-CAST(AppliedPrice AS float))) mean_absolute_difference
       FROM [{schema}].[Pricing_Decision_Log]""")
    policy_by={}
    dimensions={"pricing_rule":"d.PricingRuleID","category":"p.CategoryID","store":"d.StoreID","channel":"d.Channel"}
    for name,expr in dimensions.items():
        policy_by[name]=db.rows(f"""SELECT CAST({expr} AS nvarchar(100)) entity_id,COUNT_BIG(*) decisions,
          SUM(CASE WHEN d.RecommendedPrice=d.AppliedPrice THEN 1 ELSE 0 END) equal_count,
          SUM(CASE WHEN d.RecommendedPrice<>d.AppliedPrice THEN 1 ELSE 0 END) different_count,
          AVG(ABS(CAST(d.RecommendedPrice AS float)-CAST(d.AppliedPrice AS float))) mean_absolute_difference,
          AVG(ABS(CAST(d.RecommendedPrice AS float)-CAST(d.AppliedPrice AS float))/NULLIF(CAST(d.RecommendedPrice AS float),0)) mean_absolute_pct_difference
          FROM [{schema}].[Pricing_Decision_Log] d LEFT JOIN [{schema}].[Product] p ON p.ProductID=d.ProductID GROUP BY {expr}""")
    return {"product_support_summary": support, "price_change_buckets": buckets,
            "recommended_applied_policy": policy, "recommended_applied_by_dimension":policy_by,
            "causal_warning": "Observed associations only; not causal elasticity."}
