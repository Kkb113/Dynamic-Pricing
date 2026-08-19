"""Frozen-model scenario scoring and clearly labelled model-implied economics."""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
import pandas as pd


SCENARIOS = (
    "S0_HISTORICAL_APPLIED",
    "S1_CURRENT_PRICE",
    "S2_PHASE6_MODEL_OPTIMAL",
    "S3_PHASE7_FINAL_AUTOMATIC",
    "S4_PHASE7_WITH_HISTORICAL_FALLBACK",
)


def scenario_prices(
    outcomes: pd.DataFrame,
    recommendations: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    """Return one explicit evaluation-only price column per scenario."""

    base = outcomes[["PricingDecisionID", "AppliedPrice"]].copy()
    base = base.merge(recommendations[["PricingDecisionID", "ModelOptimalCandidatePrice"]], on="PricingDecisionID", how="left", validate="one_to_one")
    base = base.merge(decisions[["PricingDecisionID", "CurrentPrice", "FinalRecommendedPrice", "manual_review_flag"]], on="PricingDecisionID", how="left", validate="one_to_one")
    base = base.rename(columns={"AppliedPrice": "S0_HISTORICAL_APPLIED", "CurrentPrice": "S1_CURRENT_PRICE", "ModelOptimalCandidatePrice": "S2_PHASE6_MODEL_OPTIMAL", "FinalRecommendedPrice": "S3_PHASE7_FINAL_AUTOMATIC"})
    base["S4_PHASE7_WITH_HISTORICAL_FALLBACK"] = base["S3_PHASE7_FINAL_AUTOMATIC"].where(base["S3_PHASE7_FINAL_AUTOMATIC"].notna(), base["S0_HISTORICAL_APPLIED"])
    for column in SCENARIOS:
        base[column] = pd.to_numeric(base[column], errors="coerce")
    return base


def score_scenarios(
    context: pd.DataFrame,
    prices: pd.DataFrame,
    scorer: Any,
    timings: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Score every scenario through the frozen Phase 4/5 adapter."""

    output = prices.copy()
    source = context.set_index("PricingDecisionID", drop=False)
    for scenario in SCENARIOS:
        scenario_started = time.perf_counter()
        price_values = pd.to_numeric(output[scenario], errors="coerce")
        valid = price_values.notna() & np.isfinite(price_values)
        output[f"{scenario}_purchase_probability"] = np.nan
        output[f"{scenario}_expected_units"] = np.nan
        output[f"{scenario}_expected_revenue"] = np.nan
        output[f"{scenario}_expected_gross_profit"] = np.nan
        output[f"{scenario}_price"] = price_values
        if not valid.any():
            if timings is not None:
                timings[scenario] = timings.get(scenario, 0.0) + float(time.perf_counter() - scenario_started)
            continue
        rows = source.loc[output.loc[valid, "PricingDecisionID"].astype(str)].copy()
        rows = rows.reset_index(drop=True)
        scored = scorer.score_candidates(rows, price_values.loc[valid].to_numpy(float))
        indices = output.index[valid]
        output.loc[indices, f"{scenario}_purchase_probability"] = [item["raw_purchase_probability"] for item in scored]
        output.loc[indices, f"{scenario}_expected_units"] = [item["safe_expected_units"] for item in scored]
        output.loc[indices, f"{scenario}_expected_revenue"] = [item["expected_revenue"] for item in scored]
        output.loc[indices, f"{scenario}_expected_gross_profit"] = [item["expected_gross_profit"] for item in scored]
        if timings is not None:
            timings[scenario] = timings.get(scenario, 0.0) + float(time.perf_counter() - scenario_started)
    return output


def scenario_summary(frame: pd.DataFrame, scenario: str) -> dict[str, Any]:
    price = pd.to_numeric(frame[f"{scenario}_price"], errors="coerce")
    units = pd.to_numeric(frame[f"{scenario}_expected_units"], errors="coerce")
    revenue = pd.to_numeric(frame[f"{scenario}_expected_revenue"], errors="coerce")
    gross_profit = pd.to_numeric(frame[f"{scenario}_expected_gross_profit"], errors="coerce")
    historical = pd.to_numeric(frame["S0_HISTORICAL_APPLIED"], errors="coerce")
    valid = price.notna()
    change = price - historical
    increase = valid & (change > 0.005)
    decrease = valid & (change < -0.005)
    hold = valid & ~(increase | decrease)
    expected_gp = float(gross_profit[valid].sum()) if valid.any() else 0.0
    expected_revenue = float(revenue[valid].sum()) if valid.any() else 0.0
    return {
        "scenario": scenario,
        "label": "historical factual prediction at observed price" if scenario == "S0_HISTORICAL_APPLIED" else "model-implied scenario estimate",
        "rows": int(valid.sum()),
        "missing_price_rows": int((~valid).sum()),
        "aggregate_expected_units": float(units[valid].sum()) if valid.any() else 0.0,
        "aggregate_expected_revenue": expected_revenue,
        "aggregate_expected_gross_profit": expected_gp,
        "gross_margin_rate": float(expected_gp / expected_revenue) if expected_revenue else 0.0,
        "mean_price": float(price[valid].mean()) if valid.any() else None,
        "median_price": float(price[valid].median()) if valid.any() else None,
        "price_increase_rate": float(increase.sum() / valid.sum()) if valid.any() else 0.0,
        "price_decrease_rate": float(decrease.sum() / valid.sum()) if valid.any() else 0.0,
        "hold_rate": float(hold.sum() / valid.sum()) if valid.any() else 0.0,
        "mean_price_change_pct": float((change[valid] / historical[valid]).mean()) if valid.any() else None,
        "median_price_change_pct": float((change[valid] / historical[valid]).median()) if valid.any() else None,
        "factual_or_counterfactual": "factual_prediction" if scenario == "S0_HISTORICAL_APPLIED" else "counterfactual_model_implied",
    }


def all_scenario_summaries(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {scenario: scenario_summary(frame, scenario) for scenario in SCENARIOS}


def scenario_delta(summaries: dict[str, dict[str, Any]], scenario: str, baseline: str = "S0_HISTORICAL_APPLIED") -> dict[str, float]:
    current = summaries[scenario]
    base = summaries[baseline]
    return {
        "expected_units_delta": float(current["aggregate_expected_units"] - base["aggregate_expected_units"]),
        "expected_units_delta_pct": float((current["aggregate_expected_units"] - base["aggregate_expected_units"]) / base["aggregate_expected_units"]) if base["aggregate_expected_units"] else 0.0,
        "expected_revenue_delta": float(current["aggregate_expected_revenue"] - base["aggregate_expected_revenue"]),
        "expected_revenue_delta_pct": float((current["aggregate_expected_revenue"] - base["aggregate_expected_revenue"]) / base["aggregate_expected_revenue"]) if base["aggregate_expected_revenue"] else 0.0,
        "expected_gross_profit_delta": float(current["aggregate_expected_gross_profit"] - base["aggregate_expected_gross_profit"]),
        "expected_gross_profit_delta_pct": float((current["aggregate_expected_gross_profit"] - base["aggregate_expected_gross_profit"]) / base["aggregate_expected_gross_profit"]) if base["aggregate_expected_gross_profit"] else 0.0,
    }


def guard_counterfactual_language(text: str) -> None:
    forbidden = ("causal uplift", "causal elasticity", "guaranteed uplift", "will increase revenue", "realized uplift")
    lowered = text.lower()
    found = [term for term in forbidden if term in lowered]
    if found:
        raise ValueError(f"UNSUPPORTED_COUNTERFACTUAL_LANGUAGE: {found}")


__all__ = ["SCENARIOS", "all_scenario_summaries", "guard_counterfactual_language", "scenario_delta", "scenario_prices", "score_scenarios"]
