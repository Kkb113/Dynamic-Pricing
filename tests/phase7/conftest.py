from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture()
def rules():
    return pd.DataFrame([
        {
            "PricingRuleID": "R_GLOBAL", "RuleName": "global", "ProductID": None, "CategoryID": None, "StoreID": None, "Channel": None,
            "MinPrice": None, "MaxPrice": None, "MinMarginPct": None, "MaxDiscountPct": None, "MaxPriceChangePct": None, "Priority": 1,
            "EffectiveFrom": "2025-01-01", "EffectiveTo": None, "ActiveFlag": True,
        },
        {
            "PricingRuleID": "R_CATEGORY", "RuleName": "category", "ProductID": None, "CategoryID": "C1", "StoreID": None, "Channel": None,
            "MinPrice": 80.0, "MaxPrice": 120.0, "MinMarginPct": 30.0, "MaxDiscountPct": 20.0, "MaxPriceChangePct": 10.0, "Priority": 20,
            "EffectiveFrom": "2025-01-01", "EffectiveTo": "2026-01-01", "ActiveFlag": True,
        },
        {
            "PricingRuleID": "R_PRODUCT", "RuleName": "product", "ProductID": "P1", "CategoryID": "C1", "StoreID": None, "Channel": "Web",
            "MinPrice": 90.0, "MaxPrice": 110.0, "MinMarginPct": 30.0, "MaxDiscountPct": 10.0, "MaxPriceChangePct": 5.0, "Priority": 1,
            "EffectiveFrom": "2025-01-01", "EffectiveTo": None, "ActiveFlag": True,
        },
    ])
