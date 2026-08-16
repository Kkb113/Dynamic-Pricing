from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

from .metrics import purchase_metrics


HEALTH_DIMENSIONS = ["ProductID", "CategoryID", "BrandID", "StoreID", "RegionID", "Channel"]
SEGMENT_COLUMNS = ["Channel", "Season", "RegionID", "CategoryID", "StoreType"]


def split_health(frame: pd.DataFrame, assignments: pd.DataFrame, *, target_column: str = "PurchasedFlag") -> pd.DataFrame:
    joined = frame.merge(assignments[["PricingDecisionID", "split"]], on="PricingDecisionID", how="inner", validate="one_to_one")
    rows = []
    for split, group in joined.groupby("split", sort=False):
        row: dict[str, Any] = {
            "split": split,
            "row_count": int(len(group)),
            "purchase_count": int(group[target_column].sum()),
            "non_purchase_count": int((group[target_column] == 0).sum()),
            "purchase_rate": float(group[target_column].mean()),
            "quantity_positive_rows": int((group[target_column] == 1).sum()),
            "decision_time_min": pd.Timestamp(group["DecisionTime"].min()).isoformat(),
            "decision_time_max": pd.Timestamp(group["DecisionTime"].max()).isoformat(),
        }
        for dimension in HEALTH_DIMENSIONS:
            row[f"distinct_{dimension}"] = int(group[dimension].nunique(dropna=True))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("split", key=lambda values: values.map({"train": 0, "validation": 1, "test": 2})).reset_index(drop=True)


def unseen_category_report(frame: pd.DataFrame, assignments: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    joined = frame.merge(assignments[["PricingDecisionID", "split"]], on="PricingDecisionID", how="inner", validate="one_to_one")
    train = joined[joined["split"] == "train"]
    rows = []
    for split in ["validation", "test"]:
        group = joined[joined["split"] == split]
        for column in columns:
            known = set(train[column].dropna().astype(str))
            values = group[column].dropna().astype(str)
            unseen = sorted(set(values) - known)
            rows.append({
                "split": split,
                "feature_name": column,
                "known_train_levels": len(known),
                "unseen_level_count": len(unseen),
                "unseen_row_count": int(values.isin(unseen).sum()),
                "unseen_levels": "|".join(unseen[:50]),
            })
    return pd.DataFrame(rows)


def feature_missingness_by_split(frame: pd.DataFrame, assignments: pd.DataFrame, feature_names: Iterable[str]) -> pd.DataFrame:
    joined = frame.merge(assignments[["PricingDecisionID", "split"]], on="PricingDecisionID", how="inner", validate="one_to_one")
    rows = []
    for feature in feature_names:
        rates = {}
        for split in ["train", "validation", "test"]:
            group = joined[joined["split"] == split]
            rates[split] = float(group[feature].isna().mean() * 100) if len(group) else None
        valid = [value for value in rates.values() if value is not None]
        shift = max(valid) - min(valid) if valid else None
        rows.append({
            "feature_name": feature,
            "train_null_pct": rates["train"],
            "validation_null_pct": rates["validation"],
            "test_null_pct": rates["test"],
            "max_absolute_split_shift_pp": shift,
            "warning_gt_10pp": bool(shift is not None and shift > 10.0),
        })
    return pd.DataFrame(rows)


def target_drift(frame: pd.DataFrame, assignments: pd.DataFrame) -> dict[str, Any]:
    joined = frame.merge(assignments[["PricingDecisionID", "split"]], on="PricingDecisionID", how="inner", validate="one_to_one")
    output: dict[str, Any] = {}
    for split, group in joined.groupby("split", sort=False):
        positive = group.loc[group["PurchasedFlag"] == 1, "QuantityPurchased"].astype(float)
        output[split] = {
            "purchase_rate": float(group["PurchasedFlag"].mean()),
            "purchase_count": int(group["PurchasedFlag"].sum()),
            "quantity_positive_count": int(len(positive)),
            "quantity_mean": float(positive.mean()) if len(positive) else None,
            "quantity_median": float(positive.median()) if len(positive) else None,
            "quantity_p95": float(positive.quantile(0.95)) if len(positive) else None,
            "quantity_min": float(positive.min()) if len(positive) else None,
            "quantity_max": float(positive.max()) if len(positive) else None,
        }
    return output


def segment_metrics(evaluation_frames: dict[str, pd.DataFrame], min_support: int = 100) -> pd.DataFrame:
    rows = []
    for split, frame in evaluation_frames.items():
        for dimension in SEGMENT_COLUMNS:
            for value, group in frame.groupby(dimension, dropna=False, sort=True):
                if len(group) < min_support:
                    continue
                metrics = purchase_metrics(group["PurchasedFlag"], group["predicted_probability"])
                rows.append({
                    "split": split,
                    "segment_dimension": dimension,
                    "segment_value": str(value),
                    "support": int(len(group)),
                    "purchase_rate": metrics["purchase_rate"],
                    "roc_auc": metrics["roc_auc"],
                    "average_precision": metrics["average_precision"],
                    "brier_score": metrics["brier_score"],
                    "mean_predicted_probability": float(group["predicted_probability"].mean()),
                    "minimum_support": min_support,
                })
    return pd.DataFrame(rows)


def price_bucket_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    values = pd.to_numeric(frame["price_change_pct"], errors="coerce") * 100.0
    rows = []
    for label, mask in [
        ("<= -20%", values <= -20),
        ("(-20%, -10%]", (values > -20) & (values <= -10)),
        ("(-10%, -5%]", (values > -10) & (values <= -5)),
        ("(-5%, 0%)", (values > -5) & (values < 0)),
        ("0%", values == 0),
        ("(0%, 5%]", (values > 0) & (values <= 5)),
        ("(5%, 10%]", (values > 5) & (values <= 10)),
        ("(10%, 20%]", (values > 10) & (values <= 20)),
        ("> 20%", values > 20),
    ]:
        group = frame.loc[mask].copy()
        if group.empty:
            rows.append({"price_change_bucket": label, "rows": 0, "observed_purchase_rate": None, "mean_predicted_probability": None, "brier_score": None, "interpretation": "observed predictive relationship"})
            continue
        metrics = purchase_metrics(group["PurchasedFlag"], group["predicted_probability"])
        rows.append({
            "price_change_bucket": label,
            "rows": int(len(group)),
            "observed_purchase_rate": metrics["purchase_rate"],
            "mean_predicted_probability": float(group["predicted_probability"].mean()),
            "brier_score": metrics["brier_score"],
            "interpretation": "observed predictive relationship",
        })
    return pd.DataFrame(rows)
