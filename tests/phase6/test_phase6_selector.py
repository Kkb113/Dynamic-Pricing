from __future__ import annotations

import pandas as pd

from optimization.price_selector import select_model_optimal_prices


def test_profit_optimizer_and_materiality_gate(candidate_surface):
    surface = candidate_surface.copy()
    surface["safe_expected_units"] = surface["raw_expected_units"]
    surface["expected_revenue"] = surface["CandidatePrice"] * surface["safe_expected_units"]
    surface["unit_gross_profit"] = surface["CandidatePrice"] - surface["CostPrice"]
    surface["candidate_margin_pct"] = surface["unit_gross_profit"] / surface["CandidatePrice"]
    surface["expected_gross_profit"] = surface["unit_gross_profit"] * surface["safe_expected_units"]
    surface["raw_expected_gross_profit"] = surface["unit_gross_profit"] * surface["raw_expected_units"]
    surface["negative_unit_margin_candidate"] = surface["unit_gross_profit"] < 0
    selected = select_model_optimal_prices(surface)
    assert set(selected["decision_status"]) == {"CHANGE_CANDIDATE"}
    assert (selected["ModelOptimalCandidatePrice"] == 120.0).all()
    # A 0.3% improvement is below the frozen 0.5% gate.
    small = surface.copy()
    current_gp = small.loc[small["CandidatePrice"] == 100.0, "expected_gross_profit"].iloc[0]
    small.loc[small["CandidatePrice"].isin([90.0, 110.0]), "expected_gross_profit"] = current_gp * 0.99
    small.loc[small["CandidatePrice"] == 120.0, "expected_gross_profit"] = small.loc[small["CandidatePrice"] == 100.0, "expected_gross_profit"].iloc[0] * 1.003
    small.loc[small["CandidatePrice"].isin([90.0, 110.0]), "raw_expected_gross_profit"] = current_gp * 0.99
    small.loc[small["CandidatePrice"] == 120.0, "raw_expected_gross_profit"] = small.loc[small["CandidatePrice"] == 100.0, "raw_expected_gross_profit"].iloc[0] * 1.003
    small_selected = select_model_optimal_prices(small)
    assert (small_selected["decision_status"] == "KEEP_CURRENT_NO_MATERIAL_UPLIFT").all()
    assert (small_selected["ModelOptimalCandidatePrice"] == 100.0).all()
