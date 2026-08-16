from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import yaml

from features.feature_contract import FORBIDDEN_MODEL_COLUMNS, model_feature_columns
from models.catboost_data import build_feature_families, approved_conditional_groups


ROOT = Path(__file__).resolve().parents[2]


def _contract() -> dict:
    return yaml.safe_load((ROOT / "contracts/phase2_feature_contract_v1.yaml").read_text(encoding="utf-8"))


def test_phase2_fingerprint_and_reconciliation_are_frozen() -> None:
    frame = pd.read_parquet(ROOT / "artifacts/phase2/feature_dataset.parquet")
    assert len(frame) == 35000
    assert frame["PricingDecisionID"].nunique() == 35000
    assert int(frame["PurchasedFlag"].sum()) == 6492
    assert int((frame["PurchasedFlag"] == 0).sum()) == 28508
    contract = _contract()
    ordered = [feature["name"] for feature in contract["features"]]
    # The canonical Phase 2 hash is computed in the same order as Phase 2.
    import features.validation as validation
    assert validation.canonical_dataset_hash(frame, ordered) == "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2"


def test_phase3_split_assignments_are_unchanged_and_chronological() -> None:
    assignments = pd.read_parquet(ROOT / "artifacts/phase3/split_assignments.parquet")
    digest = hashlib.sha256((ROOT / "artifacts/phase3/split_assignments.parquet").read_bytes()).hexdigest()
    assert digest == "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d"
    assert assignments["PricingDecisionID"].is_unique
    assert set(assignments["split"]) == {"train", "validation", "test"}
    assignments["DecisionTime"] = pd.to_datetime(assignments["DecisionTime"])
    maximums = assignments.groupby("split")["DecisionTime"].max()
    minimums = assignments.groupby("split")["DecisionTime"].min()
    assert maximums["train"] < minimums["validation"] < minimums["test"]


def test_conditional_families_are_explicit_and_core_is_preserved() -> None:
    contract = _contract()
    groups = approved_conditional_groups(contract)
    families = build_feature_families(contract)
    core = model_feature_columns(contract, population="purchase")
    assert families["F0_CORE"].feature_names == tuple(core)
    assert set(groups) == {"HIGH_CARDINALITY_CONTEXT", "COMPETITOR_CONTEXT", "BEHAVIOR_CONTEXT", "CUSTOMER_CONTEXT"}
    assert "FavoriteCategoryID" not in set().union(*groups.values())
    assert "FavoriteBrandID" not in set().union(*groups.values())
    assert "CustomerID" not in set().union(*groups.values())
    for family in families.values():
        assert not (set(family.feature_names) & FORBIDDEN_MODEL_COLUMNS)


