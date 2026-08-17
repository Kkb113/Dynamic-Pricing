from __future__ import annotations

import pandas as pd

from inventory_policy.inventory_loader import freeze_status_mapping, validate_inventory
from inventory_policy.inventory_policy import resolve_current_inventory
from inventory_policy.markdown_policy import markdown_eligibility
from promotions.promotion_loader import validate_promotions
from promotions.promotion_resolver import resolve_promotion


def test_promotion_conflict_and_equal_overlap():
    promotions = validate_promotions(pd.DataFrame([
        {"PromotionID": "P2", "PromotionName": "two", "CategoryID": "C1", "DiscountPct": 10, "Season": "All", "StartDate": "2025-01-01", "EndDate": "2025-12-31", "ActiveFlag": True},
        {"PromotionID": "P1", "PromotionName": "one", "CategoryID": "C1", "DiscountPct": 20, "Season": "All", "StartDate": "2025-01-01", "EndDate": "2025-12-31", "ActiveFlag": True},
    ]))
    result = resolve_promotion(promotions=promotions, category_id="C1", decision_date="2025-06-01", base_price=100)
    assert result["PromotionAction"] == "PROMOTION_CONFLICT_REVIEW"


def test_inventory_and_markdown_guards():
    inventory = validate_inventory(pd.DataFrame([{
        "InventoryID": "I1", "StoreID": "S1", "ProductID": "P1", "SnapshotDate": "2025-12-31",
        "OpeningQty": 10, "ReceivedQty": 0, "SoldQty": 10, "ReturnedQty": 0, "AdjustmentQty": 0, "ReservedQty": 0,
        "OnHandQty": 0, "AvailableQty": 0, "StockStatus": "OUT_OF_STOCK",
    }]))
    mapping = freeze_status_mapping(inventory["StockStatus"])
    result = resolve_current_inventory(inventory, product_id="P1", store_id="S1", as_of_date="2025-12-31", status_mapping=mapping)
    assert result["status"] == "OUT_OF_STOCK_NO_PRICE_ACTION"
    assert markdown_eligibility(mode="CURRENT_INVENTORY_MODE", seasonal=True, slow_moving=True, high_inventory_or_overstock=True, available_qty=0, stock_status="OVERSTOCK")["markdown_eligible"] is False
