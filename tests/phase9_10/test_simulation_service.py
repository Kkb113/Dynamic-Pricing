import math

import pytest

from app_services.simulation_service import SimulationError, SimulationService


def test_known_candidate_matches_frozen_surface(registry):
    service = SimulationService(registry)
    row = registry.load_candidate_surface("validation").sort_values(["PricingDecisionID", "candidate_rank_by_price"]).iloc[0]
    result = service.simulate_price(str(row["PricingDecisionID"]), float(row["CandidatePrice"]))
    assert abs(result["purchase_probability"] - row["raw_purchase_probability"]) <= 1e-10
    assert abs(result["expected_units"] - row["safe_expected_units"]) <= 1e-10
    assert abs(result["expected_revenue"] - row["expected_revenue"]) <= 1e-10
    assert abs(result["expected_gross_profit"] - row["expected_gross_profit"]) <= 1e-10


def test_support_boundaries_and_outside_are_controlled(registry):
    service = SimulationService(registry)
    decision_id = str(registry.load_decisions("validation").sort_values("PricingDecisionID").iloc[0]["PricingDecisionID"])
    envelope = service.support_envelope(decision_id)
    for price in (envelope["support_low_price"], envelope["support_high_price"]):
        result = service.simulate_price(decision_id, price)
        assert result["within_model_support"] is True
    with pytest.raises(SimulationError, match="outside the range"):
        service.simulate_price(decision_id, envelope["support_high_price"] * 1.5)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_prices_are_rejected(registry, value):
    decision_id = str(registry.load_decisions("validation").sort_values("PricingDecisionID").iloc[0]["PricingDecisionID"])
    with pytest.raises(SimulationError) as exc:
        SimulationService(registry).simulate_price(decision_id, value)
    assert exc.value.code == "INVALID_CANDIDATE_PRICE"


def test_rule_compliance_is_returned(registry):
    service = SimulationService(registry)
    row = registry.load_candidate_surface("validation").sort_values(["PricingDecisionID", "candidate_rank_by_price"]).iloc[0]
    result = service.simulate_price(str(row["PricingDecisionID"]), float(row["CandidatePrice"]))
    assert "business_rule_compliance" in result
    assert "rule_violations" in result
