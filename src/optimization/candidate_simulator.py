from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from models.catboost_data import build_purchase_model_features_for_candidate_price, make_catboost_pool
from models.quantity_data import build_quantity_model_features_for_candidate_price
from models.quantity_estimator import ConditionalQuantityEstimator

from .candidate_grid import CandidateGrid, generate_candidate_rows, scenario_prices
from .economics import score_economics
from .response_safety import apply_response_safety


OUTCOME_COLUMNS = frozenset({"PurchasedFlag", "QuantityPurchased", "ActualRevenue", "OutcomeTime", "OrderLineID"})


def load_outcome_blind_context(frame: pd.DataFrame, *, allow_columns: list[str] | tuple[str, ...] | None = None) -> pd.DataFrame:
    """Select the optimizer allowlist and ensure outcome columns cannot flow downstream."""

    if allow_columns is None:
        allow_columns = list(frame.columns)
    selected = [column for column in allow_columns if column in frame.columns and column not in OUTCOME_COLUMNS]
    result = frame.loc[:, selected].copy()
    if OUTCOME_COLUMNS.intersection(result.columns):
        raise ValueError("OUTCOME_BLINDNESS_FAILURE")
    return result


def _prepare_candidate_features(
    context: pd.DataFrame,
    candidates: pd.DataFrame,
    *,
    purchase_contract: dict[str, Any],
    purchase_features: tuple[str, ...],
    quantity_contract: dict[str, Any],
    quantity_features: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Build model matrices by mutating only candidate-price-dependent fields."""

    purchase_parts: list[pd.DataFrame] = []
    quantity_parts: list[pd.DataFrame] = []
    orders: list[np.ndarray] = []
    for multiplier in candidates["candidate_multiplier"].drop_duplicates().tolist():
        ids = candidates.index[candidates["candidate_multiplier"].eq(multiplier)]
        source = context.loc[candidates.loc[ids, "_context_index"].to_numpy()].copy()
        prices = candidates.loc[ids, "CandidatePrice"].to_numpy(float)
        purchase_parts.append(build_purchase_model_features_for_candidate_price(source, prices, purchase_contract, purchase_features))
        quantity_parts.append(build_quantity_model_features_for_candidate_price(source, prices, quantity_contract, quantity_features))
        orders.append(ids.to_numpy(dtype=int))
    # Candidate rows are constructed in multiplier blocks, exactly matching the parts above.
    return pd.concat(purchase_parts, ignore_index=True), pd.concat(quantity_parts, ignore_index=True), np.concatenate(orders)


def simulate_candidate_prices(
    context_frame: pd.DataFrame,
    *,
    optimizer_spec: dict[str, Any],
    purchase_model: CatBoostClassifier,
    purchase_contract: dict[str, Any],
    quantity_estimator: ConditionalQuantityEstimator,
    quantity_contract: dict[str, Any],
    candidate_grid: CandidateGrid,
    batch_size: int = 250_000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Vectorized long-form candidate surface for one frozen context split."""

    context = load_outcome_blind_context(context_frame, allow_columns=list(context_frame.columns))
    context = context.reset_index(drop=True)
    candidate_started = time.perf_counter()
    candidates = generate_candidate_rows(context, candidate_grid)
    candidate_generation_seconds = time.perf_counter() - candidate_started
    # Preserve a stable source-row pointer without exposing it in the artifact.
    context_lookup = context.reset_index(drop=True)
    index_by_id = pd.Series(context_lookup.index, index=context_lookup["PricingDecisionID"].astype(str))
    candidates["_context_index"] = candidates["PricingDecisionID"].astype(str).map(index_by_id).to_numpy()
    if candidates["_context_index"].isna().any():
        raise ValueError("CANDIDATE_CONTEXT_INDEX_FAILURE")

    purchase_features = tuple(optimizer_spec["phase4_ordered_feature_names"])
    quantity_features = tuple(optimizer_spec["phase5_ordered_feature_names"])
    started = time.perf_counter()
    purchase_matrix, quantity_matrix, model_order = _prepare_candidate_features(
        context_lookup,
        candidates,
        purchase_contract=purchase_contract,
        purchase_features=purchase_features,
        quantity_contract=quantity_contract,
        quantity_features=quantity_features,
    )
    feature_seconds = time.perf_counter() - started

    started = time.perf_counter()
    probabilities: list[np.ndarray] = []
    for start in range(0, len(purchase_matrix), int(batch_size)):
        stop = min(len(purchase_matrix), start + int(batch_size))
        pool = make_catboost_pool(purchase_matrix.iloc[start:stop], purchase_contract, purchase_features)
        probabilities.append(np.asarray(purchase_model.predict_proba(pool)[:, 1], dtype=float))
    predicted_order = np.concatenate(probabilities) if probabilities else np.empty(0, dtype=float)
    raw_probability = np.empty(len(predicted_order), dtype=float)
    raw_probability[model_order] = predicted_order
    prediction_seconds = time.perf_counter() - started
    if not np.isfinite(raw_probability).all() or np.any(raw_probability < 0) or np.any(raw_probability > 1):
        raise ValueError("INVALID_PURCHASE_PROBABILITY")

    started = time.perf_counter()
    if quantity_estimator.estimator_type == "CONSTANT_MEAN":
        conditional_temp = quantity_estimator.predict_conditional_quantity(context_lookup.iloc[candidates.loc[model_order, "_context_index"].to_numpy()])
        conditional_quantity = np.empty(len(conditional_temp), dtype=float)
        conditional_quantity[model_order] = conditional_temp
    else:
        # The quantity adapter owns feature preparation and remains the sole official loader.
        conditional_temp = quantity_estimator.predict_conditional_quantity(quantity_matrix)
        conditional_quantity = np.empty(len(conditional_temp), dtype=float)
        conditional_quantity[model_order] = conditional_temp
    quantity_seconds = time.perf_counter() - started
    conditional_quantity = np.asarray(conditional_quantity, dtype=float)
    if not np.isfinite(conditional_quantity).all():
        raise ValueError("INVALID_CONDITIONAL_QUANTITY")
    if len(conditional_quantity) != len(candidates):
        raise ValueError("CONDITIONAL_QUANTITY_LENGTH_MISMATCH")

    surface = candidates.drop(columns=["_context_index"]).copy()
    surface["raw_purchase_probability"] = raw_probability
    surface["conditional_quantity"] = conditional_quantity
    surface["raw_expected_units"] = raw_probability * conditional_quantity
    if not np.isfinite(surface["raw_expected_units"]).all() or (surface["raw_expected_units"] < 0).any():
        raise ValueError("INVALID_RAW_EXPECTED_UNITS")
    surface, safety = apply_response_safety(surface)
    economics_started = time.perf_counter()
    surface = score_economics(surface)
    economics_seconds = time.perf_counter() - economics_started
    # Keep the surface outcome-blind and retain only scenario-engine fields.
    forbidden = OUTCOME_COLUMNS.intersection(surface.columns)
    if forbidden:
        raise ValueError(f"OUTCOME_COLUMNS_IN_SURFACE: {sorted(forbidden)}")
    surface["inventory_constraint_applied"] = False
    surface["available_inventory"] = np.nan
    surface = surface.sort_values(["PricingDecisionID", "CandidatePrice", "candidate_rank_by_price"], kind="mergesort").reset_index(drop=True)
    timings = {
        "decisions_scored": int(context["PricingDecisionID"].nunique()),
        "candidate_rows_scored": int(len(surface)),
        "candidate_generation_seconds": float(candidate_generation_seconds),
        "feature_generation_seconds": float(feature_seconds),
        "phase4_prediction_seconds": float(prediction_seconds),
        "phase5_quantity_seconds": float(quantity_seconds),
        "economic_scoring_seconds": float(economics_seconds),
        "safety_summary": safety["summary"],
    }
    return surface, timings


__all__ = ["OUTCOME_COLUMNS", "load_outcome_blind_context", "simulate_candidate_prices"]
