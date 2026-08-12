from __future__ import annotations


def sales_coverage(db, windows: list[int], schema: str = "dbo") -> dict:
    result = {"rule": "Only orders with OrderDate < DecisionTime qualify", "grains": {}}
    grains={
      "product":"l.ProductID=d.ProductID",
      "product_store":"l.ProductID=d.ProductID AND o.StoreID=d.StoreID",
      "product_region":"l.ProductID=d.ProductID AND sale_store.RegionID=decision_store.RegionID",
      "category_store":"sale_product.CategoryID=decision_product.CategoryID AND o.StoreID=d.StoreID",
      "category":"sale_product.CategoryID=decision_product.CategoryID",
    }
    for grain,condition in grains.items():
        aggregates=",\n".join(f"SUM(CASE WHEN prior_sale.OrderDate>=DATEADD(day,-{int(days)},d.DecisionTime) THEN 1 ELSE 0 END) covered_{int(days)}d" for days in windows)
        row = db.row(f"""
          SELECT COUNT_BIG(*) decisions,{aggregates}
          FROM [{schema}].[Pricing_Decision_Log] d
          LEFT JOIN [{schema}].[Product] decision_product ON decision_product.ProductID=d.ProductID
          LEFT JOIN [{schema}].[Store] decision_store ON decision_store.StoreID=d.StoreID
          OUTER APPLY (SELECT TOP (1) o.OrderDate FROM [{schema}].[Sales_Order_Line] l
             JOIN [{schema}].[Sales_Order] o ON o.OrderID=l.OrderID
             LEFT JOIN [{schema}].[Product] sale_product ON sale_product.ProductID=l.ProductID
             LEFT JOIN [{schema}].[Store] sale_store ON sale_store.StoreID=o.StoreID
             WHERE {condition} AND o.OrderDate<d.DecisionTime
             ORDER BY o.OrderDate DESC) prior_sale
        """)
        result["grains"][grain]={}
        for days in windows:
            covered=row[f"covered_{int(days)}d"]
            result["grains"][grain][str(days)]={"decisions":row["decisions"],"covered_decisions":covered,
              "coverage_rate":covered/row["decisions"] if row["decisions"] else None}
    result["product"]=result["grains"]["product"]
    return result
