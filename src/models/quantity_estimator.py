"""Unified Phase 5 conditional-quantity estimator abstraction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from models.quantity_catboost import predict_quantity_raw, project_quantity
from models.quantity_data import make_quantity_pool


class ConditionalQuantityEstimator:
    """Common inference surface for a CatBoost model and a mean fallback."""

    def __init__(
        self,
        estimator_type: str,
        *,
        mean_value: float | None = None,
        model: CatBoostRegressor | None = None,
        contract: dict[str, Any] | None = None,
        feature_names: Iterable[str] = (),
        minimum: float = 1.0,
    ) -> None:
        estimator_type = str(estimator_type).upper()
        if estimator_type not in {"CATBOOST", "CONSTANT_MEAN"}:
            raise ValueError(f"Unknown quantity estimator type: {estimator_type}")
        if estimator_type == "CONSTANT_MEAN" and mean_value is None:
            raise ValueError("CONSTANT_MEAN requires mean_value")
        if estimator_type == "CATBOOST" and (model is None or contract is None):
            raise ValueError("CATBOOST requires model and contract")
        self.estimator_type = estimator_type
        self.mean_value = None if mean_value is None else float(mean_value)
        self.model = model
        self.contract = contract
        self.feature_names = tuple(feature_names)
        self.minimum = float(minimum)

    def predict_raw(self, frame: pd.DataFrame) -> np.ndarray:
        if self.estimator_type == "CONSTANT_MEAN":
            return np.full(len(frame), float(self.mean_value), dtype=float)
        pool = make_quantity_pool(frame, self.contract, self.feature_names)
        return predict_quantity_raw(self.model, pool)

    def predict_conditional_quantity(self, frame: pd.DataFrame) -> np.ndarray:
        return project_quantity(self.predict_raw(frame), self.minimum)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.predict_conditional_quantity(frame)

    def metadata(self) -> dict[str, Any]:
        return {
            "estimator_type": self.estimator_type,
            "mean_value": self.mean_value,
            "ordered_feature_names": list(self.feature_names),
            "conditional_quantity_minimum": self.minimum,
            "prediction_method": "predict_conditional_quantity",
        }


def save_quantity_estimator_metadata(path: Path, estimator: ConditionalQuantityEstimator, **extra: Any) -> None:
    payload = {**estimator.metadata(), **extra}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_quantity_estimator(
    metadata_path: Path,
    *,
    contract: dict[str, Any] | None = None,
    model_path: Path | None = None,
    mean_path: Path | None = None,
) -> ConditionalQuantityEstimator:
    """Load either serialized official estimator through the common contract."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    estimator_type = str(metadata["estimator_type"]).upper()
    minimum = float(metadata.get("conditional_quantity_minimum", 1.0))
    features = tuple(metadata.get("ordered_feature_names", []))
    if estimator_type == "CONSTANT_MEAN":
        source = mean_path or metadata_path.parent / "conditional_quantity_mean.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        return ConditionalQuantityEstimator("CONSTANT_MEAN", mean_value=float(payload["mean_value"]), contract=contract, feature_names=features, minimum=minimum)
    source = model_path or metadata_path.parent / "conditional_quantity_catboost.cbm"
    model = CatBoostRegressor()
    model.load_model(str(source))
    return ConditionalQuantityEstimator("CATBOOST", model=model, contract=contract, feature_names=features, minimum=minimum)


__all__ = ["ConditionalQuantityEstimator", "save_quantity_estimator_metadata", "load_quantity_estimator"]
