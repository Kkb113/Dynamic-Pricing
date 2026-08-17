from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_phase6_contract_has_no_phase7_rules():
    path = Path(__file__).resolve().parents[2] / "contracts/phase6_price_optimization_contract_v1.yaml"
    text = path.read_text(encoding="utf-8")
    assert "NOT_APPLIED_PHASE6" in text
    assert "FinalRecommendedPrice" not in text
    assert "PROMOTE" not in text


def test_surface_schema_is_outcome_blind(candidate_surface):
    forbidden = {"PurchasedFlag", "QuantityPurchased", "ActualRevenue", "OutcomeTime", "OrderLineID"}
    assert not forbidden.intersection(candidate_surface.columns)
