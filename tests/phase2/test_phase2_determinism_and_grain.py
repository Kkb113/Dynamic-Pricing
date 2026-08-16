import pandas as pd

from features.validation import canonical_dataset_hash


def test_canonical_hash_is_stable_under_input_order():
    frame = pd.DataFrame({
        "PricingDecisionID": ["d2", "d1"],
        "DecisionTime": pd.to_datetime(["2025-01-02", "2025-01-01"]),
        "value": [2.0, 1.0],
    })
    shuffled = frame.iloc[[0, 1]].copy()
    assert canonical_dataset_hash(frame, list(frame.columns)) == canonical_dataset_hash(shuffled, list(frame.columns))


def test_canonical_hash_changes_when_feature_value_changes():
    frame = pd.DataFrame({
        "PricingDecisionID": ["d1"], "DecisionTime": pd.to_datetime(["2025-01-01"]), "value": [1.0],
    })
    changed = frame.copy(); changed.loc[0, "value"] = 2.0
    assert canonical_dataset_hash(frame, list(frame.columns)) != canonical_dataset_hash(changed, list(changed.columns))
