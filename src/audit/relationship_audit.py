from __future__ import annotations

LOGICAL_RELATIONSHIPS = [
    ("Product_Category", "Product", "CategoryID", "Product_Category", "CategoryID"),
    ("Product_Brand", "Product", "BrandID", "Brand", "BrandID"),
    ("Customer_Region", "Customer", "RegionID", "Region", "RegionID"),
    ("Store_Region", "Store", "RegionID", "Region", "RegionID"),
    ("CustomerPreferences_Customer", "Customer_Preferences", "CustomerID", "Customer", "CustomerID"),
    ("CustomerPreferences_Category", "Customer_Preferences", "FavoriteCategoryID", "Product_Category", "CategoryID"),
    ("CustomerPreferences_Brand", "Customer_Preferences", "FavoriteBrandID", "Brand", "BrandID"),
    ("Browsing_Customer", "Browsing_Events", "CustomerID", "Customer", "CustomerID"),
    ("Browsing_Product", "Browsing_Events", "ProductID", "Product", "ProductID"),
    ("Cart_Customer", "Cart_Events", "CustomerID", "Customer", "CustomerID"),
    ("Cart_Product", "Cart_Events", "ProductID", "Product", "ProductID"),
    ("Search_Customer", "Search_Events", "CustomerID", "Customer", "CustomerID"),
    ("Search_ClickedProduct", "Search_Events", "ClickedProductID", "Product", "ProductID"),
    ("SalesOrder_Customer", "Sales_Order", "CustomerID", "Customer", "CustomerID"),
    ("SalesOrder_Store", "Sales_Order", "StoreID", "Store", "StoreID"),
    ("SalesLine_Order", "Sales_Order_Line", "OrderID", "Sales_Order", "OrderID"),
    ("SalesLine_Product", "Sales_Order_Line", "ProductID", "Product", "ProductID"),
    ("SalesLine_Promotion", "Sales_Order_Line", "PromotionID", "Promotions", "PromotionID"),
    ("Ratings_Customer", "Ratings", "CustomerID", "Customer", "CustomerID"),
    ("Ratings_Product", "Ratings", "ProductID", "Product", "ProductID"),
    ("Wishlist_Customer", "Wishlist", "CustomerID", "Customer", "CustomerID"),
    ("Wishlist_Product", "Wishlist", "ProductID", "Product", "ProductID"),
    ("Recommendation_Customer", "Recommendation_Log", "CustomerID", "Customer", "CustomerID"),
    ("Recommendation_Product", "Recommendation_Log", "ProductID", "Product", "ProductID"),
    ("Recommendation_Promotion", "Recommendation_Log", "PromotionID", "Promotions", "PromotionID"),
    ("Response_Recommendation", "Recommendation_Response", "RecommendationID", "Recommendation_Log", "RecommendationID"),
    ("Response_Order", "Recommendation_Response", "OrderID", "Sales_Order", "OrderID"),
    ("Weather_Region", "Weather", "RegionID", "Region", "RegionID"),
    ("Holiday_Region", "Holiday", "RegionID", "Region", "RegionID"),
]


def relationship_audit(db, schema: str = "dbo") -> dict:
    declared = db.rows("""SELECT fk.name foreign_key, OBJECT_NAME(fk.parent_object_id) child_table,
      COL_NAME(fkc.parent_object_id,fkc.parent_column_id) child_column,
      OBJECT_NAME(fk.referenced_object_id) parent_table,
      COL_NAME(fkc.referenced_object_id,fkc.referenced_column_id) parent_column
      FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
      WHERE SCHEMA_NAME(OBJECTPROPERTY(fk.parent_object_id,'SchemaId'))=? ORDER BY fk.name""", [schema])
    duplicates = {}
    pks = db.rows("""SELECT tc.TABLE_NAME table_name, kcu.COLUMN_NAME column_name
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
       ON tc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME AND tc.TABLE_SCHEMA=kcu.TABLE_SCHEMA
      WHERE tc.TABLE_SCHEMA=? AND tc.CONSTRAINT_TYPE='PRIMARY KEY' ORDER BY tc.TABLE_NAME,kcu.ORDINAL_POSITION""", [schema])
    grouped = {}
    for row in pks: grouped.setdefault(row["table_name"], []).append(row["column_name"])
    for table, cols in grouped.items():
        select_cols = ",".join(f"[{c}]" for c in cols)
        duplicates[table] = db.row(f"SELECT COUNT_BIG(*) duplicate_groups FROM (SELECT {select_cols} FROM [{schema}].[{table}] GROUP BY {select_cols} HAVING COUNT_BIG(*)>1) x")["duplicate_groups"]
    orphans={}
    for fk in declared:
        key=fk["foreign_key"]
        orphans[key]=db.row(f"""SELECT COUNT_BIG(*) orphan_count FROM [{schema}].[{fk['child_table']}] c
          LEFT JOIN [{schema}].[{fk['parent_table']}] p ON p.[{fk['parent_column']}]=c.[{fk['child_column']}]
          WHERE c.[{fk['child_column']}] IS NOT NULL AND p.[{fk['parent_column']}] IS NULL""")["orphan_count"]
    logical=[]
    for name,child_table,child_column,parent_table,parent_column in LOGICAL_RELATIONSHIPS:
        counts=db.row(f"""SELECT COUNT_BIG(*) child_rows,
          SUM(CASE WHEN c.[{child_column}] IS NOT NULL THEN 1 ELSE 0 END) non_null_keys,
          SUM(CASE WHEN c.[{child_column}] IS NOT NULL AND p.[{parent_column}] IS NULL THEN 1 ELSE 0 END) orphan_count
          FROM [{schema}].[{child_table}] c LEFT JOIN [{schema}].[{parent_table}] p
           ON p.[{parent_column}]=c.[{child_column}]""")
        logical.append({"relationship":name,"child_table":child_table,"child_column":child_column,
          "parent_table":parent_table,"parent_column":parent_column,**counts,
          "status":"PASS" if counts["orphan_count"]==0 else "FAIL"})
    return {"declared_foreign_keys": declared, "declared_foreign_key_count": len(declared),
            "declared_foreign_key_orphans":orphans,"duplicate_primary_key_groups": duplicates,
            "logical_relationship_count":len(logical),"logical_relationships":logical,
            "logical_relationship_orphan_total":sum(x["orphan_count"] for x in logical),
            "logical_relationship_status":"PASS" if all(x["status"]=="PASS" for x in logical) else "FAIL"}
