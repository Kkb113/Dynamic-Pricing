from __future__ import annotations


def rule_audit(db, schema: str = "dbo") -> dict:
    rules = db.row(f"""SELECT COUNT_BIG(*) rule_count,
      SUM(CASE WHEN MinPrice IS NOT NULL AND MaxPrice IS NOT NULL AND MinPrice>MaxPrice THEN 1 ELSE 0 END) invalid_price_ranges,
      SUM(CASE WHEN MinMarginPct<0 OR MinMarginPct>100 THEN 1 ELSE 0 END) invalid_margin_ranges,
      SUM(CASE WHEN MaxDiscountPct<0 OR MaxDiscountPct>100 THEN 1 ELSE 0 END) invalid_discount_ranges,
      SUM(CASE WHEN MaxPriceChangePct<0 OR MaxPriceChangePct>100 THEN 1 ELSE 0 END) invalid_price_change_ranges,
      SUM(CASE WHEN EffectiveTo IS NOT NULL AND EffectiveFrom>=EffectiveTo THEN 1 ELSE 0 END) invalid_intervals,
      SUM(CASE WHEN ActiveFlag=1 THEN 1 ELSE 0 END) active_rules,MIN(Priority) min_priority,MAX(Priority) max_priority,
      SUM(CASE WHEN ProductID IS NOT NULL THEN 1 ELSE 0 END) product_scoped,
      SUM(CASE WHEN CategoryID IS NOT NULL THEN 1 ELSE 0 END) category_scoped,
      SUM(CASE WHEN StoreID IS NOT NULL THEN 1 ELSE 0 END) store_scoped
      FROM [{schema}].[Pricing_Rules]""")
    decisions = db.row(f"""SELECT COUNT_BIG(*) decisions,
      SUM(CASE WHEN PricingRuleID IS NULL THEN 1 ELSE 0 END) without_rule,
      SUM(CASE WHEN PricingRuleID IS NOT NULL THEN 1 ELSE 0 END) with_rule
      FROM [{schema}].[Pricing_Decision_Log]""")
    compliance = db.row(f"""SELECT COUNT_BIG(*) referenced_decisions,
      SUM(CASE WHEN r.PricingRuleID IS NOT NULL AND (r.MinPrice IS NULL OR d.AppliedPrice>=r.MinPrice)
       AND (r.MaxPrice IS NULL OR d.AppliedPrice<=r.MaxPrice)
       AND (r.MaxPriceChangePct IS NULL OR ABS(d.AppliedPrice-d.CurrentPrice)/NULLIF(d.CurrentPrice,0)*100<=r.MaxPriceChangePct)
       THEN 1 ELSE 0 END) compliant_decisions,
      SUM(CASE WHEN r.PricingRuleID IS NULL THEN 1 ELSE 0 END) orphan_rule_references
      FROM [{schema}].[Pricing_Decision_Log] d LEFT JOIN [{schema}].[Pricing_Rules] r ON r.PricingRuleID=d.PricingRuleID""")
    compliance["compliance_rate"] = compliance["compliant_decisions"] / compliance["referenced_decisions"] if compliance["referenced_decisions"] else None
    return {"rules": rules, "decision_references": decisions, "applied_price_compliance":compliance}
