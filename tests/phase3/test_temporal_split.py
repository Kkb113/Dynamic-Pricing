from __future__ import annotations

import pandas as pd

from validation.temporal_split import ExpandingWindowSplitter, build_temporal_split, validate_temporal_split


def _fixture() -> pd.DataFrame:
    times = pd.to_datetime([
        "2025-01-01", "2025-01-01", "2025-01-01",
        "2025-01-02", "2025-01-02",
        "2025-01-03", "2025-01-03", "2025-01-03",
        "2025-01-04", "2025-01-04",
        "2025-01-05", "2025-01-05",
    ])
    return pd.DataFrame({
        "PricingDecisionID": [f"d{i:02d}" for i in range(len(times))],
        "DecisionTime": times,
        "PurchasedFlag": [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0],
        "ProductID": [f"p{i % 3}" for i in range(len(times))],
        "CategoryID": [f"c{i % 2}" for i in range(len(times))],
        "StoreID": [f"s{i % 2}" for i in range(len(times))],
        "Channel": ["Web" if i % 2 else "Store" for i in range(len(times))],
    })


def test_duplicate_timestamps_stay_in_one_partition_and_all_rows_are_assigned():
    frame = _fixture()
    assignments, boundaries = build_temporal_split(frame)
    validate_temporal_split(assignments)
    assert len(assignments) == len(frame)
    assert assignments["PricingDecisionID"].nunique() == len(frame)
    assert set(assignments["split"]) == {"train", "validation", "test"}
    assert assignments.groupby("DecisionTime")["split"].nunique().max() == 1
    maximums = assignments.groupby("split")["DecisionTime"].max()
    minimums = assignments.groupby("split")["DecisionTime"].min()
    assert maximums["train"] < minimums["validation"] < minimums["test"]
    assert boundaries["train_end"] < boundaries["validation_start"] < boundaries["test_start"]


def test_expanding_folds_are_ordered_non_overlapping_and_healthy():
    frame = _fixture()
    splitter = ExpandingWindowSplitter()
    folds = list(splitter.split(frame))
    assert len(folds) == 3
    previous_validation_end = None
    for train_indices, validation_indices in folds:
        train_times = frame.loc[train_indices, "DecisionTime"]
        validation_times = frame.loc[validation_indices, "DecisionTime"]
        assert train_times.max() < validation_times.min()
        assert set(train_indices).isdisjoint(validation_indices)
        assert frame.loc[train_indices, "PurchasedFlag"].nunique() == 2
        assert frame.loc[validation_indices, "PurchasedFlag"].nunique() == 2
        if previous_validation_end is not None:
            assert previous_validation_end < validation_times.min()
        previous_validation_end = validation_times.max()
    manifest = splitter.manifest(frame)
    assert all(row["train_purchase_count"] > 0 and row["validation_purchase_count"] > 0 for row in manifest)
