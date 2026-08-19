from __future__ import annotations

import pandas as pd

from inventory_policy.inventory_loader import freeze_status_mapping, validate_inventory
from inventory_policy.inventory_policy import resolve_current_inventory
from phase7.runner import _inventory_category_thresholds


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


def test_inventory_p75_is_category_specific():
    inventory = pd.DataFrame([
        {"ProductID": "P1", "StoreID": "S1", "AvailableQty": 10},
        {"ProductID": "P2", "StoreID": "S1", "AvailableQty": 20},
        {"ProductID": "P3", "StoreID": "S1", "AvailableQty": 100},
        {"ProductID": "P4", "StoreID": "S1", "AvailableQty": 120},
    ])
    product = pd.DataFrame([
        {"ProductID": "P1", "CategoryID": "C1"}, {"ProductID": "P2", "CategoryID": "C1"},
        {"ProductID": "P3", "CategoryID": "C2"}, {"ProductID": "P4", "CategoryID": "C2"},
    ])
    thresholds, global_p75, audit = _inventory_category_thresholds(inventory, product)
    assert thresholds["C1"] == 17.5
    assert thresholds["C2"] == 115.0
    assert global_p75 == 105.0
    assert audit["method"].startswith("Inventory.ProductID")
