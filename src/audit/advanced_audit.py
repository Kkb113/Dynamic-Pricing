from __future__ import annotations

from .price_variation_audit import PRICE_BUCKET_CASE


def target_segment_profile(db, schema: str = "dbo") -> list[dict]:
    dimensions = {
        "month": "CONVERT(char(7),d.DecisionTime,120)", "channel": "d.Channel", "store": "d.StoreID",
        "region": "s.RegionID", "category": "p.CategoryID", "brand": "p.BrandID", "season": "p.Season",
        "price_change_bucket": PRICE_BUCKET_CASE.replace("CurrentPrice", "d.CurrentPrice").replace("AppliedPrice", "d.AppliedPrice"),
    }
    output = []
    for name, expression in dimensions.items():
        rows = db.rows(f"""SELECT ? segment_type, COALESCE(CAST({expression} AS nvarchar(100)),'NULL') segment_value,
          COUNT_BIG(*) decision_count, SUM(CASE WHEN d.PurchasedFlag=1 THEN 1 ELSE 0 END) purchase_count,
          AVG(CAST(d.PurchasedFlag AS float)) purchase_rate
          FROM [{schema}].[Pricing_Decision_Log] d
          LEFT JOIN [{schema}].[Product] p ON p.ProductID=d.ProductID
          LEFT JOIN [{schema}].[Store] s ON s.StoreID=d.StoreID
          GROUP BY {expression}""", [name])
        output.extend(rows)
    output.extend(db.rows(f"""SELECT 'promotion_state' segment_type,
      CASE WHEN active_promo.covered=1 THEN 'ACTIVE' ELSE 'NONE' END segment_value,COUNT_BIG(*) decision_count,
      SUM(CASE WHEN d.PurchasedFlag=1 THEN 1 ELSE 0 END) purchase_count,AVG(CAST(d.PurchasedFlag AS float)) purchase_rate
      FROM [{schema}].[Pricing_Decision_Log] d OUTER APPLY (SELECT TOP(1) 1 covered
       FROM [{schema}].[Product_Price_History] h JOIN [{schema}].[Promotions] p ON p.PromotionID=h.PromotionID
       WHERE h.ProductID=d.ProductID AND h.EffectiveFrom<=d.DecisionTime AND (h.EffectiveTo IS NULL OR d.DecisionTime<h.EffectiveTo)
        AND CAST(d.DecisionTime AS date) BETWEEN p.StartDate AND p.EndDate) active_promo
      GROUP BY CASE WHEN active_promo.covered=1 THEN 'ACTIVE' ELSE 'NONE' END"""))
    return output


def dimension_price_support(db, schema: str = "dbo") -> dict[str, list[dict]]:
    dimensions = {"category":"p.CategoryID", "brand":"p.BrandID", "store":"d.StoreID", "channel":"d.Channel", "season":"p.Season"}
    result = {}
    for name, expr in dimensions.items():
        result[name] = db.rows(f"""SELECT CAST({expr} AS nvarchar(100)) entity_id, COUNT_BIG(*) decision_count,
          COUNT(DISTINCT d.CurrentPrice) unique_current_price_count, COUNT(DISTINCT d.AppliedPrice) unique_applied_price_count,
          MIN(d.AppliedPrice) min_applied_price, MAX(d.AppliedPrice) max_applied_price,
          AVG(CAST(d.AppliedPrice AS float)) mean_applied_price, STDEV(CAST(d.AppliedPrice AS float)) std_applied_price,
          MAX(d.AppliedPrice)-MIN(d.AppliedPrice) applied_price_range,
          STDEV(CAST(d.AppliedPrice AS float))/NULLIF(AVG(CAST(d.AppliedPrice AS float)),0) applied_price_cv,
          SUM(CASE WHEN d.AppliedPrice<>d.CurrentPrice THEN 1 ELSE 0 END)*1.0/COUNT_BIG(*) pct_changed
          FROM [{schema}].[Pricing_Decision_Log] d LEFT JOIN [{schema}].[Product] p ON p.ProductID=d.ProductID
          GROUP BY {expr} ORDER BY {expr}""")
    return result


def price_history_audit(db, schema: str = "dbo") -> dict:
    quality = db.row(f"""SELECT COUNT_BIG(*) intervals,
      SUM(CASE WHEN EffectiveTo IS NOT NULL AND EffectiveFrom>=EffectiveTo THEN 1 ELSE 0 END) invalid_interval_order,
      SUM(CASE WHEN BasePrice IS NULL OR SellingPrice IS NULL THEN 1 ELSE 0 END) missing_prices,
      SUM(CASE WHEN BasePrice<=0 OR SellingPrice<=0 THEN 1 ELSE 0 END) nonpositive_prices,
      SUM(CASE WHEN DiscountPct<0 OR DiscountPct>100 THEN 1 ELSE 0 END) invalid_discount_pct
      FROM [{schema}].[Product_Price_History]""")
    overlaps = db.row(f"""SELECT COUNT_BIG(*) overlap_pairs FROM [{schema}].[Product_Price_History] a
      JOIN [{schema}].[Product_Price_History] b ON a.PriceHistoryID<b.PriceHistoryID
       AND a.ProductID=b.ProductID AND ISNULL(a.StoreID,'')=ISNULL(b.StoreID,'') AND ISNULL(a.Channel,'')=ISNULL(b.Channel,'')
       AND a.EffectiveFrom < ISNULL(b.EffectiveTo,CONVERT(datetime2,'9999-12-31'))
       AND b.EffectiveFrom < ISNULL(a.EffectiveTo,CONVERT(datetime2,'9999-12-31'))""")
    coverage = db.row(f"""SELECT COUNT_BIG(*) decisions,
      SUM(CASE WHEN active_price.covered=1 THEN 1 ELSE 0 END) covered_decisions,
      SUM(CASE WHEN active_price.match_count>1 THEN 1 ELSE 0 END) duplicate_active_decisions
      FROM [{schema}].[Pricing_Decision_Log] d OUTER APPLY (
       SELECT TOP (1) 1 covered, COUNT_BIG(*) OVER() match_count
       FROM [{schema}].[Product_Price_History] h WHERE h.ProductID=d.ProductID
        AND (h.StoreID=d.StoreID OR h.StoreID IS NULL) AND (h.Channel=d.Channel OR h.Channel IS NULL)
        AND h.EffectiveFrom<=d.DecisionTime AND (h.EffectiveTo IS NULL OR d.DecisionTime<h.EffectiveTo)
       ORDER BY CASE WHEN h.StoreID=d.StoreID THEN 0 ELSE 1 END, CASE WHEN h.Channel=d.Channel THEN 0 ELSE 1 END
      ) active_price""")
    coverage["coverage_rate"] = coverage["covered_decisions"] / coverage["decisions"] if coverage["decisions"] else None
    return {"quality":quality,"overlaps":overlaps,"decision_coverage":coverage,"interval_rule":"[EffectiveFrom, EffectiveTo)"}


def promotion_audit(db, schema: str = "dbo") -> dict:
    promotions = db.row(f"""SELECT COUNT_BIG(*) promotions,
      SUM(CASE WHEN StartDate>EndDate THEN 1 ELSE 0 END) invalid_windows,
      SUM(CASE WHEN DiscountPct<0 OR DiscountPct>100 THEN 1 ELSE 0 END) invalid_discounts,
      SUM(CASE WHEN ActiveFlag=1 THEN 1 ELSE 0 END) active_flag_count,
      COUNT(DISTINCT CategoryID) category_coverage, MIN(DiscountPct) min_discount, MAX(DiscountPct) max_discount,
      AVG(CAST(DiscountPct AS float)) mean_discount FROM [{schema}].[Promotions]""")
    history = db.row(f"""SELECT COUNT_BIG(*) price_intervals,
      SUM(CASE WHEN h.PromotionID IS NOT NULL THEN 1 ELSE 0 END) intervals_with_promotion,
      SUM(CASE WHEN h.PromotionID IS NOT NULL AND p.PromotionID IS NULL THEN 1 ELSE 0 END) orphan_promotion_ids,
      SUM(CASE WHEN h.PromotionID IS NOT NULL AND p.PromotionID IS NOT NULL AND
        (CAST(h.EffectiveFrom AS date)>p.EndDate OR CAST(ISNULL(h.EffectiveTo,h.EffectiveFrom) AS date)<p.StartDate)
        THEN 1 ELSE 0 END) stale_or_inactive_associations
      FROM [{schema}].[Product_Price_History] h LEFT JOIN [{schema}].[Promotions] p ON p.PromotionID=h.PromotionID""")
    decision = db.row(f"""SELECT COUNT_BIG(*) decisions,
      SUM(CASE WHEN active_promo.covered=1 THEN 1 ELSE 0 END) active_promotion_decisions
      FROM [{schema}].[Pricing_Decision_Log] d OUTER APPLY (
       SELECT TOP(1) 1 covered FROM [{schema}].[Product_Price_History] h JOIN [{schema}].[Promotions] p ON p.PromotionID=h.PromotionID
       WHERE h.ProductID=d.ProductID AND h.EffectiveFrom<=d.DecisionTime AND (h.EffectiveTo IS NULL OR d.DecisionTime<h.EffectiveTo)
        AND CAST(d.DecisionTime AS date) BETWEEN p.StartDate AND p.EndDate
      ) active_promo""")
    decision["coverage_rate"] = decision["active_promotion_decisions"] / decision["decisions"] if decision["decisions"] else None
    return {"promotions":promotions,"price_history_associations":history,"decision_coverage":decision}


def probability_diagnostics(db, schema: str = "dbo") -> list[dict]:
    return db.rows(f"""WITH scored AS (SELECT PurchaseProbability,PurchasedFlag,
      NTILE(10) OVER (ORDER BY PurchaseProbability) probability_decile FROM [{schema}].[Pricing_Decision_Log])
      SELECT probability_decile,COUNT_BIG(*) decision_count,MIN(PurchaseProbability) min_probability,
       MAX(PurchaseProbability) max_probability,AVG(CAST(PurchaseProbability AS float)) mean_probability,
       SUM(CASE WHEN PurchasedFlag=1 THEN 1 ELSE 0 END) purchase_count,AVG(CAST(PurchasedFlag AS float)) purchase_rate
      FROM scored GROUP BY probability_decile ORDER BY probability_decile""")


def cardinality_sparsity(db, low_frequency: int = 5, schema: str = "dbo") -> list[dict]:
    dimensions = {"ProductID":"d.ProductID","CategoryID":"p.CategoryID","BrandID":"p.BrandID","StoreID":"d.StoreID",
      "RegionID":"s.RegionID","Channel":"d.Channel","CustomerSegment":"c.CustomerSegment","LoyaltyTier":"c.LoyaltyTier",
      "Season":"p.Season"}
    output=[]
    for name, expr in dimensions.items():
        row=db.row(f"""WITH counts AS (SELECT {expr} entity,COUNT_BIG(*) n FROM [{schema}].[Pricing_Decision_Log] d
          LEFT JOIN [{schema}].[Product] p ON p.ProductID=d.ProductID LEFT JOIN [{schema}].[Store] s ON s.StoreID=d.StoreID
          LEFT JOIN [{schema}].[Customer] c ON c.CustomerID=d.CustomerID WHERE {expr} IS NOT NULL GROUP BY {expr}), stats AS (
          SELECT entity,n,PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY n) OVER() median_n,
           PERCENTILE_CONT(0.9) WITHIN GROUP(ORDER BY n) OVER() p90_n FROM counts)
          SELECT ? dimension,COUNT_BIG(*) unique_values,SUM(n) row_coverage,MIN(n) min_observations,MAX(median_n) median_observations,
           MAX(p90_n) p90_observations,MAX(n) max_observations,SUM(CASE WHEN n=1 THEN 1 ELSE 0 END) singleton_count,
           SUM(CASE WHEN n<? THEN 1 ELSE 0 END) low_frequency_count FROM stats""",[name,low_frequency])
        output.append(row)
    row=db.row(f"""WITH counts AS (SELECT PromotionID entity,COUNT_BIG(*) n FROM [{schema}].[Product_Price_History]
      WHERE PromotionID IS NOT NULL GROUP BY PromotionID),stats AS (SELECT entity,n,
       PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY n) OVER() median_n,PERCENTILE_CONT(0.9) WITHIN GROUP(ORDER BY n) OVER() p90_n FROM counts)
      SELECT 'PromotionID' dimension,COUNT_BIG(*) unique_values,SUM(n) row_coverage,MIN(n) min_observations,MAX(median_n) median_observations,
       MAX(p90_n) p90_observations,MAX(n) max_observations,SUM(CASE WHEN n=1 THEN 1 ELSE 0 END) singleton_count,
       SUM(CASE WHEN n<? THEN 1 ELSE 0 END) low_frequency_count FROM stats""",[low_frequency])
    output.append(row)
    return output


def missingness_profile(db, schema: str = "dbo") -> list[dict]:
    sources={"Pricing_Decision_Log":["DecisionTime","CustomerID","SessionID","ProductID","StoreID","Channel","CurrentPrice","AppliedPrice","PurchasedFlag"],
      "Product":["CategoryID","BrandID","BasePrice","CostPrice","MarginPct","Season"],
      "Customer":["RegionID","LoyaltyTier","CustomerSegment","PreferredChannel"],
      "Customer_Preferences":["PriceSensitivity","CategoryAffinityScore","BrandAffinityScore"]}
    output=[]
    for table,cols in sources.items():
        for col in cols:
            row=db.row(f"""SELECT ? source_table,? column_name,COUNT_BIG(*) row_count,
             SUM(CASE WHEN [{col}] IS NULL THEN 1 ELSE 0 END) null_count,COUNT(DISTINCT [{col}]) distinct_count
             FROM [{schema}].[{table}]""",[table,col])
            row["null_percentage"] = row["null_count"]*100.0/row["row_count"] if row["row_count"] else None
            output.append(row)
    return output


def numeric_profile(db, schema: str = "dbo") -> list[dict]:
    sources={"Pricing_Decision_Log":["CurrentPrice","AppliedPrice"],"Product":["BasePrice","CostPrice","MarginPct"],
      "Customer_Preferences":["CategoryAffinityScore","BrandAffinityScore"],"Competitor_Price":["CompetitorPrice"],
      "Product_Price_History":["BasePrice","SellingPrice","DiscountPct"]}
    output=[]
    for table,columns in sources.items():
      for col in columns:
        row=db.row(f"""WITH x AS (SELECT CAST([{col}] AS float) value,
          PERCENTILE_CONT(0.01) WITHIN GROUP(ORDER BY [{col}]) OVER() p01,
          PERCENTILE_CONT(0.05) WITHIN GROUP(ORDER BY [{col}]) OVER() p05,
          PERCENTILE_CONT(0.50) WITHIN GROUP(ORDER BY [{col}]) OVER() p50,
          PERCENTILE_CONT(0.95) WITHIN GROUP(ORDER BY [{col}]) OVER() p95,
          PERCENTILE_CONT(0.99) WITHIN GROUP(ORDER BY [{col}]) OVER() p99 FROM [{schema}].[{table}] WHERE [{col}] IS NOT NULL)
          SELECT ? source_table,? column_name,COUNT_BIG(*) non_null_count,MIN(value) min_value,MAX(value) max_value,
           AVG(value) mean_value,STDEV(value) std_value,MAX(p01) p01,MAX(p05) p05,MAX(p50) p50,MAX(p95) p95,MAX(p99) p99 FROM x""",[table,col])
        output.append(row)
    return output


def behavioral_coverage(db, windows_hours: list[int], schema: str = "dbo") -> dict:
    specs={"browsing":("Browsing_Events","EventTime","e.ProductID=d.ProductID AND e.CustomerID=d.CustomerID"),
      "cart":("Cart_Events","EventTime","e.ProductID=d.ProductID AND e.CustomerID=d.CustomerID"),
      "search_clicked_product":("Search_Events","EventTime","e.ClickedProductID=d.ProductID AND e.CustomerID=d.CustomerID")}
    out={}
    for feature,(table,time_col,join) in specs.items():
        out[feature]={}
        for hours in windows_hours:
            row=db.row(f"""SELECT COUNT_BIG(*) decisions,SUM(CASE WHEN prior.covered=1 THEN 1 ELSE 0 END) covered_decisions
              FROM [{schema}].[Pricing_Decision_Log] d OUTER APPLY (SELECT TOP(1) 1 covered FROM [{schema}].[{table}] e
               WHERE {join} AND e.[{time_col}]<=d.DecisionTime AND e.[{time_col}]>=DATEADD(hour,-{int(hours)},d.DecisionTime)
               ORDER BY e.[{time_col}] DESC) prior""")
            row["coverage_rate"]=row["covered_decisions"]/row["decisions"] if row["decisions"] else None
            out[feature][str(hours)]=row
    return out


def temporal_split_proposal(db, schema: str = "dbo") -> dict:
    bounds=db.row(f"""WITH ordered AS (SELECT DecisionTime,ROW_NUMBER() OVER(ORDER BY DecisionTime,PricingDecisionID) rn,
      COUNT_BIG(*) OVER() total FROM [{schema}].[Pricing_Decision_Log])
      SELECT MIN(DecisionTime) min_time,MAX(DecisionTime) max_time,
       MAX(CASE WHEN rn=CAST(CEILING(total*0.70) AS bigint) THEN DecisionTime END) train_end,
       MAX(CASE WHEN rn=CAST(CEILING(total*0.85) AS bigint) THEN DecisionTime END) validation_end FROM ordered""")
    ranges=[]
    definitions=[("train",None,bounds["train_end"]),("validation",bounds["train_end"],bounds["validation_end"]),("test",bounds["validation_end"],None)]
    for name,start,end in definitions:
        clauses=[];params=[]
        if start is not None: clauses.append("d.DecisionTime>?");params.append(start)
        if end is not None: clauses.append("d.DecisionTime<=?");params.append(end)
        where=" AND ".join(clauses) or "1=1"
        row=db.row(f"""SELECT ? split,MIN(d.DecisionTime) start_time,MAX(d.DecisionTime) end_time,COUNT_BIG(*) row_count,
          SUM(CASE WHEN d.PurchasedFlag=1 THEN 1 ELSE 0 END) purchase_count,SUM(CASE WHEN d.PurchasedFlag=0 THEN 1 ELSE 0 END) non_purchase_count,
          COUNT(DISTINCT d.ProductID) product_coverage,COUNT(DISTINCT p.CategoryID) category_coverage,COUNT(DISTINCT d.StoreID) store_coverage
          FROM [{schema}].[Pricing_Decision_Log] d LEFT JOIN [{schema}].[Product] p ON p.ProductID=d.ProductID WHERE {where}""",[name,*params])
        ranges.append(row)
    return {"policy":"chronological; no random row split","boundaries":bounds,"splits":ranges}
