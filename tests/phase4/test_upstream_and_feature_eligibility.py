from __future__ import annotations

from pathlib import Path

import yaml

from features.feature_contract import FORBIDDEN_MODEL_COLUMNS, model_feature_columns
from models.catboost_data import build_feature_families, approved_conditional_groups


ROOT = Path(__file__).resolve().parents[2]


def _contract() -> dict:
    return yaml.safe_load((ROOT / "contracts/phase2_feature_contract_v1.yaml").read_text(encoding="utf-8"))


def test_phase2_fingerprint_and_reconciliation_are_frozen() -> None:
    fingerprint = __import__("json").loads((ROOT / "artifacts/phase2/dataset_fingerprint.json").read_text(encoding="utf-8"))
    assert fingerprint["canonical_feature_dataset_sha256"] == "7cc4e4fe97c1b36f1d5ba5df7ad911c09fd82efcda9a37d6305ef7aaafac93b2"
    assert fingerprint["row_count"] == 35000
    assert fingerprint["target_counts"] == {"non_purchases": 28508, "purchases": 6492, "quantity_population_rows": 6492}


def test_phase3_split_assignments_are_unchanged_and_chronological() -> None:
    summary = __import__("json").loads((ROOT / "artifacts/phase3/split_summary.json").read_text(encoding="utf-8"))
    assert summary["assignment_sha256"] == "9632ad58c980ee6d3c5f95a5bb78b03ea559c9198b004040a4a8d603e3528c1d"
    assert {item["split"]: item["row_count"] for item in summary["health"]} == {"train": 24500, "validation": 5250, "test": 5250}
    assert summary["boundaries"]["train_end"] < summary["boundaries"]["validation_start"] < summary["boundaries"]["test_start"]


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

