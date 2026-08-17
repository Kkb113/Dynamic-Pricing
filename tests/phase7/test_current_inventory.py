from __future__ import annotations

import pandas as pd

from inventory_policy.inventory_loader import freeze_status_mapping, validate_inventory
from inventory_policy.inventory_policy import resolve_current_inventory


def test_missing_product_store_is_manual_review():
    inventory = validate_inventory(pd.DataFrame([{
        "InventoryID": "I1", "StoreID": "S1", "ProductID": "P1", "SnapshotDate": "2025-12-31",
        "OpeningQty": 10, "ReceivedQty": 0, "SoldQty": 2, "ReturnedQty": 0, "AdjustmentQty": 0,
        "ReservedQty": 0, "OnHandQty": 8, "AvailableQty": 8, "StockStatus": "In Stock",
    }]))
    result = resolve_current_inventory(
        inventory, product_id="P2", store_id="S1", as_of_date="2025-12-31",
        status_mapping=freeze_status_mapping(inventory["StockStatus"]),
    )
    assert result["status"] == "MANUAL_REVIEW_INVENTORY_UNAVAILABLE"


def test_historical_snapshot_is_not_used_for_current_lookup():
    inventory = validate_inventory(pd.DataFrame([{
        "InventoryID": "I1", "StoreID": "S1", "ProductID": "P1", "SnapshotDate": "2025-12-31",
        "OpeningQty": 10, "ReceivedQty": 0, "SoldQty": 2, "ReturnedQty": 0, "AdjustmentQty": 0,
        "ReservedQty": 0, "OnHandQty": 8, "AvailableQty": 8, "StockStatus": "In Stock",
    }]))
    result = resolve_current_inventory(
        inventory, product_id="P1", store_id="S1", as_of_date="2025-11-30",
        status_mapping=freeze_status_mapping(inventory["StockStatus"]),
    )
    assert result["status"] == "MANUAL_REVIEW_INVENTORY_UNAVAILABLE"
