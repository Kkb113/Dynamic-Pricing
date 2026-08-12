from __future__ import annotations


def competitor_coverage(db, windows: list[int], schema: str = "dbo") -> dict:
    output = {"rule": "ObservedDateTime <= DecisionTime; future observations excluded", "windows": {}}
    for days in windows:
        lower = "CAST(d.DecisionTime AS date)" if days == 0 else f"DATEADD(day,-{int(days)},d.DecisionTime)"
        same_day = "AND CAST(c.ObservedDateTime AS date)=CAST(d.DecisionTime AS date)" if days == 0 else ""
        row = db.row(f"""
          SELECT COUNT_BIG(*) decisions,
           SUM(CASE WHEN prior_observation.covered=1 THEN 1 ELSE 0 END) covered_decisions
          FROM [{schema}].[Pricing_Decision_Log] d LEFT JOIN [{schema}].[Store] s ON s.StoreID=d.StoreID
          OUTER APPLY (SELECT TOP (1) 1 covered FROM [{schema}].[Competitor_Price] c
             WHERE c.ProductID=d.ProductID AND c.RegionID=s.RegionID AND c.Channel=d.Channel
             AND c.ObservedDateTime<=d.DecisionTime
             AND c.ObservedDateTime>={lower} {same_day}
             ORDER BY c.ObservedDateTime DESC) prior_observation
        """)
        row["coverage_rate"] = row["covered_decisions"] / row["decisions"] if row["decisions"] else None
        output["windows"][str(days)] = row
    output["quality"] = db.row(f"""SELECT COUNT_BIG(*) observations,
      SUM(CASE WHEN CompetitorPrice<=0 THEN 1 ELSE 0 END) nonpositive_prices,
      COUNT(DISTINCT CompetitorName) competitor_count,
      SUM(CASE WHEN AvailabilityFlag=1 THEN 1 ELSE 0 END) available_observations,
      AVG(CAST(CompetitorPrice AS float)) mean_price, STDEV(CAST(CompetitorPrice AS float)) price_std
      FROM [{schema}].[Competitor_Price]""")
    output["price_gap_buckets_30d"] = db.rows(f"""SELECT gap_bucket,COUNT_BIG(*) decision_count,
      SUM(CASE WHEN PurchasedFlag=1 THEN 1 ELSE 0 END) purchase_count,AVG(CAST(PurchasedFlag AS float)) purchase_rate
      FROM (SELECT d.PurchasedFlag,CASE WHEN prior.CompetitorPrice IS NULL OR prior.CompetitorPrice=0 THEN 'NO_PRIOR_PRICE'
       WHEN (d.AppliedPrice-prior.CompetitorPrice)/prior.CompetitorPrice<=-0.10 THEN 'far below competitor'
       WHEN (d.AppliedPrice-prior.CompetitorPrice)/prior.CompetitorPrice<-0.02 THEN 'slightly below competitor'
       WHEN (d.AppliedPrice-prior.CompetitorPrice)/prior.CompetitorPrice<=0.02 THEN 'near competitor'
       WHEN (d.AppliedPrice-prior.CompetitorPrice)/prior.CompetitorPrice<=0.10 THEN 'slightly above competitor'
       ELSE 'far above competitor' END gap_bucket
       FROM [{schema}].[Pricing_Decision_Log] d LEFT JOIN [{schema}].[Store] s ON s.StoreID=d.StoreID
       OUTER APPLY (SELECT TOP(1) c.CompetitorPrice FROM [{schema}].[Competitor_Price] c
        WHERE c.ProductID=d.ProductID AND c.RegionID=s.RegionID AND c.Channel=d.Channel
         AND c.ObservedDateTime<=d.DecisionTime AND c.ObservedDateTime>=DATEADD(day,-30,d.DecisionTime)
        ORDER BY c.ObservedDateTime DESC) prior) x GROUP BY gap_bucket""")
    return output


def competitor_dimension_coverage(db, schema: str = "dbo", days: int = 30) -> dict[str, list[dict]]:
    dimensions={"product":"d.ProductID","category":"p.CategoryID","region":"s.RegionID","channel":"d.Channel"}
    result={}
    for name,expr in dimensions.items():
        result[name]=db.rows(f"""SELECT CAST({expr} AS nvarchar(100)) entity_id,COUNT_BIG(*) decisions,
          SUM(CASE WHEN prior.covered=1 THEN 1 ELSE 0 END) covered_decisions,
          AVG(CASE WHEN prior.covered=1 THEN 1.0 ELSE 0.0 END) coverage_rate
          FROM [{schema}].[Pricing_Decision_Log] d LEFT JOIN [{schema}].[Store] s ON s.StoreID=d.StoreID
          LEFT JOIN [{schema}].[Product] p ON p.ProductID=d.ProductID
          OUTER APPLY (SELECT TOP(1) 1 covered FROM [{schema}].[Competitor_Price] c
           WHERE c.ProductID=d.ProductID AND c.RegionID=s.RegionID AND c.Channel=d.Channel
            AND c.ObservedDateTime<=d.DecisionTime AND c.ObservedDateTime>=DATEADD(day,-{int(days)},d.DecisionTime)
           ORDER BY c.ObservedDateTime DESC) prior GROUP BY {expr} ORDER BY {expr}""")
    return result
