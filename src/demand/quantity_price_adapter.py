"""Candidate-price adapter shared by Phase 5 and downstream diagnostics."""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from models.quantity_data import build_quantity_model_features_for_candidate_price


def build_quantity_candidate_features(frame: pd.DataFrame, candidate_price: Any, contract: dict[str, Any], feature_names: Iterable[str]) -> pd.DataFrame:
    return build_quantity_model_features_for_candidate_price(frame, candidate_price, contract, feature_names)


__all__ = ["build_quantity_candidate_features", "build_quantity_model_features_for_candidate_price"]

