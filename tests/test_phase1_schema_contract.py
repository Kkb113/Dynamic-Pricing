import yaml
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_contract_locks_database_and_grain():
    contract = yaml.safe_load((ROOT / "contracts/dynamic_pricing_ml_contract_v1.yaml").read_text())
    assert contract["source_database"] == "Retail_Hyperpersonlaization"
    assert contract["primary_fact_table"] == "Pricing_Decision_Log"
    assert "One Pricing_Decision_Log record" in contract["prediction_grain"]


def test_contract_locks_targets_and_objective():
    contract = yaml.safe_load((ROOT / "contracts/dynamic_pricing_ml_contract_v1.yaml").read_text())
    assert contract["primary_target"]["field"].endswith("PurchasedFlag")
    assert contract["secondary_target"]["field"].endswith("QuantityPurchased")
    assert contract["optimization_objective"]["primary"] == "expected_gross_profit"


def test_no_production_training_declared():
    contract = yaml.safe_load((ROOT / "contracts/dynamic_pricing_ml_contract_v1.yaml").read_text())
    assert "primary_candidate" in contract["model_family_plan"]["purchase_model"]
    assert "trained_model" not in contract
