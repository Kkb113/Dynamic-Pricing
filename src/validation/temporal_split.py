from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
import pandas as pd


class TemporalSplitError(ValueError):
    """Raised when a canonical temporal split cannot satisfy the contract."""


class InvalidTemporalFold(TemporalSplitError):
    """Raised when an expanding-window validation fold lacks target health."""


@dataclass(frozen=True)
class TemporalFold:
    fold_number: int
    train_indices: np.ndarray
    validation_indices: np.ndarray
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp


def _ordered(frame: pd.DataFrame, time_column: str, id_column: str) -> pd.DataFrame:
    if frame[time_column].isna().any():
        raise TemporalSplitError("DecisionTime contains null values")
    if frame[id_column].duplicated().any():
        raise TemporalSplitError("PricingDecisionID is not unique")
    ordered = frame.copy()
    ordered[time_column] = pd.to_datetime(ordered[time_column], errors="raise")
    return ordered.sort_values([time_column, id_column], kind="mergesort")


def _boundary_time(times: pd.Series, target_rows: int) -> pd.Timestamp:
    group_sizes = times.value_counts(sort=False).sort_index()
    cumulative = group_sizes.cumsum()
    eligible = cumulative[cumulative >= int(target_rows)]
    if eligible.empty:
        raise TemporalSplitError("TEMPORAL_SPLIT_OVERLAP: no valid boundary timestamp")
    return pd.Timestamp(eligible.index[0])


def build_temporal_split(
    frame: pd.DataFrame,
    *,
    time_column: str = "DecisionTime",
    id_column: str = "PricingDecisionID",
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> tuple[pd.DataFrame, dict[str, pd.Timestamp]]:
    """Assign all rows to strict train/validation/test time partitions.

    Boundaries are selected from unique timestamps.  Consequently, equal
    DecisionTime values can never be divided across partitions.
    """
    if train_fraction <= 0 or validation_fraction <= 0 or train_fraction + validation_fraction >= 1:
        raise TemporalSplitError("Temporal split fractions must leave a positive test partition")
    ordered = _ordered(frame, time_column, id_column)
    n_rows = len(ordered)
    train_target = max(1, int(round(n_rows * train_fraction)))
    validation_target = max(1, int(round(n_rows * (train_fraction + validation_fraction))))
    train_end = _boundary_time(ordered[time_column], train_target)
    validation_end = _boundary_time(ordered[time_column], validation_target)
    if validation_end <= train_end or validation_end >= ordered[time_column].max():
        raise TemporalSplitError("TEMPORAL_SPLIT_OVERLAP: chronological boundaries are not separable")
    assignment = pd.DataFrame({id_column: frame[id_column].to_numpy(), "split": "train"}, index=frame.index)
    timestamps = pd.to_datetime(frame[time_column], errors="raise")
    assignment.loc[timestamps > train_end, "split"] = "validation"
    assignment.loc[timestamps > validation_end, "split"] = "test"
    result = frame[[id_column, time_column]].copy()
    result[time_column] = pd.to_datetime(result[time_column], errors="raise")
    result["split"] = assignment["split"].to_numpy()
    result = result.sort_values([time_column, id_column], kind="mergesort").reset_index(drop=True)
    validate_temporal_split(result, id_column=id_column, time_column=time_column)
    boundaries = {
        "train_start": pd.Timestamp(result.loc[result["split"] == "train", time_column].min()),
        "train_end": pd.Timestamp(result.loc[result["split"] == "train", time_column].max()),
        "validation_start": pd.Timestamp(result.loc[result["split"] == "validation", time_column].min()),
        "validation_end": pd.Timestamp(result.loc[result["split"] == "validation", time_column].max()),
        "test_start": pd.Timestamp(result.loc[result["split"] == "test", time_column].min()),
        "test_end": pd.Timestamp(result.loc[result["split"] == "test", time_column].max()),
    }
    return result, boundaries


def validate_temporal_split(
    assignments: pd.DataFrame,
    *,
    id_column: str = "PricingDecisionID",
    time_column: str = "DecisionTime",
) -> None:
    required = {id_column, time_column, "split"}
    missing = required - set(assignments.columns)
    if missing:
        raise TemporalSplitError(f"Missing split columns: {sorted(missing)}")
    if assignments[id_column].duplicated().any():
        raise TemporalSplitError("A PricingDecisionID appears more than once in split assignments")
    if set(assignments["split"].dropna()) != {"train", "validation", "test"}:
        raise TemporalSplitError("All train, validation, and test partitions are required")
    timestamps = pd.to_datetime(assignments[time_column], errors="raise")
    maximums = assignments.assign(_time=timestamps).groupby("split")["_time"].max()
    minimums = assignments.assign(_time=timestamps).groupby("split")["_time"].min()
    if not maximums["train"] < minimums["validation"]:
        raise TemporalSplitError("TEMPORAL_SPLIT_OVERLAP: train and validation overlap")
    if not maximums["validation"] < minimums["test"]:
        raise TemporalSplitError("TEMPORAL_SPLIT_OVERLAP: validation and test overlap")


class ExpandingWindowSplitter:
    """Three chronological expanding-window folds within the development period."""

    def __init__(self, n_splits: int = 3, initial_fraction: float = 0.40):
        if n_splits != 3:
            raise ValueError("Phase 3 requires exactly three expanding-window folds")
        if not 0 < initial_fraction < 0.6:
            raise ValueError("initial_fraction must leave room for all folds")
        self.n_splits = n_splits
        self.initial_fraction = initial_fraction

    def split(self, frame: pd.DataFrame, *, time_column: str = "DecisionTime") -> Iterator[tuple[np.ndarray, np.ndarray]]:
        ordered = frame.copy()
        ordered[time_column] = pd.to_datetime(ordered[time_column], errors="raise")
        unique_times = pd.Series(ordered[time_column].drop_duplicates().sort_values().to_numpy())
        if len(unique_times) < self.n_splits + 2:
            raise InvalidTemporalFold("Not enough distinct timestamps for expanding folds")
        boundaries = [int(round(len(unique_times) * fraction)) for fraction in (0.40, 0.60, 0.80, 1.00)]
        boundaries = [max(1, min(len(unique_times), value)) for value in boundaries]
        for fold_number in range(self.n_splits):
            train_end = unique_times.iloc[boundaries[fold_number] - 1]
            validation_end = unique_times.iloc[boundaries[fold_number + 1] - 1]
            train_mask = ordered[time_column] <= train_end
            validation_mask = (ordered[time_column] > train_end) & (ordered[time_column] <= validation_end)
            train_indices = ordered.index[train_mask].to_numpy()
            validation_indices = ordered.index[validation_mask].to_numpy()
            if not len(train_indices) or not len(validation_indices):
                raise InvalidTemporalFold(f"Fold {fold_number + 1} has an empty partition")
            yield train_indices, validation_indices

    def manifest(self, frame: pd.DataFrame, *, target_column: str = "PurchasedFlag", time_column: str = "DecisionTime") -> list[dict]:
        rows: list[dict] = []
        for number, (train_indices, validation_indices) in enumerate(self.split(frame, time_column=time_column), start=1):
            train = frame.loc[train_indices]
            validation = frame.loc[validation_indices]
            if train[target_column].nunique() < 2 or validation[target_column].nunique() < 2:
                raise InvalidTemporalFold(f"INVALID_TEMPORAL_FOLD: fold {number} lacks both target classes")
            rows.append({
                "fold": number,
                "train_rows": int(len(train)),
                "validation_rows": int(len(validation)),
                "train_purchase_count": int(train[target_column].sum()),
                "train_non_purchase_count": int((train[target_column] == 0).sum()),
                "validation_purchase_count": int(validation[target_column].sum()),
                "validation_non_purchase_count": int((validation[target_column] == 0).sum()),
                "train_start": pd.Timestamp(train[time_column].min()).isoformat(),
                "train_end": pd.Timestamp(train[time_column].max()).isoformat(),
                "validation_start": pd.Timestamp(validation[time_column].min()).isoformat(),
                "validation_end": pd.Timestamp(validation[time_column].max()).isoformat(),
                "train_distinct_product": int(train["ProductID"].nunique(dropna=True)) if "ProductID" in train else None,
                "train_distinct_category": int(train["CategoryID"].nunique(dropna=True)) if "CategoryID" in train else None,
                "train_distinct_store": int(train["StoreID"].nunique(dropna=True)) if "StoreID" in train else None,
                "train_distinct_channel": int(train["Channel"].nunique(dropna=True)) if "Channel" in train else None,
                "validation_distinct_product": int(validation["ProductID"].nunique(dropna=True)) if "ProductID" in validation else None,
                "validation_distinct_category": int(validation["CategoryID"].nunique(dropna=True)) if "CategoryID" in validation else None,
                "validation_distinct_store": int(validation["StoreID"].nunique(dropna=True)) if "StoreID" in validation else None,
                "validation_distinct_channel": int(validation["Channel"].nunique(dropna=True)) if "Channel" in validation else None,
            })
        return rows
