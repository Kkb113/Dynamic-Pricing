"""Phase 8 evidence projections for the dashboard and agent."""

from __future__ import annotations

from typing import Any

from .artifact_registry import ArtifactRegistry


class ModelPerformanceService:
    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry

    def get_model_performance(self) -> dict[str, Any]:
        metrics = self.registry.load_metrics()
        purchase = metrics.get("purchase", {})
        demand = metrics.get("demand", {})
        revenue = metrics.get("revenue", {})
        gross_profit = metrics.get("gross_profit", {})
        result = {
            "ROC-AUC": purchase.get("roc_auc"),
            "Average Precision": purchase.get("average_precision"),
            "Log Loss": purchase.get("log_loss"),
            "Brier Score": purchase.get("brier_score"),
            "Top-Decile Lift": purchase.get("top_decile_lift"),
            "Actual aggregate units": demand.get("aggregate_observed"),
            "Predicted aggregate units": demand.get("aggregate_predicted"),
            "Demand aggregate error %": demand.get("aggregate_error_pct"),
            "Actual aggregate revenue": revenue.get("aggregate_observed"),
            "Predicted aggregate revenue": revenue.get("aggregate_predicted"),
            "Revenue aggregate error %": revenue.get("aggregate_error_pct"),
            "Actual aggregate gross profit": gross_profit.get("aggregate_observed"),
            "Predicted aggregate gross profit": gross_profit.get("aggregate_predicted"),
            "GP aggregate error %": gross_profit.get("aggregate_error_pct"),
            "Observed margin rate": metrics.get("observed_gross_margin_rate"),
            "Predicted margin rate": metrics.get("predicted_historical_gross_margin_rate"),
            "demand_mae": demand.get("mae"),
            "demand_rmse": demand.get("rmse"),
            "revenue_mae": revenue.get("mae"),
            "revenue_rmse": revenue.get("rmse"),
            "gp_mae": gross_profit.get("mae"),
            "gp_rmse": gross_profit.get("rmse"),
            "overall_purchase_rate": purchase.get("positive_rate"),
            "business_interpretation": [
                "The purchase model provides ranking signal: the highest-scored pricing situations contain more purchasers than the overall population.",
                "Historical-price demand, revenue, and gross-profit predictions are evaluated with aggregate backtest calibration.",
                "The business-rule layer converts model-optimal prices into governed final recommendations.",
            ],
            "caveat": "Aggregate calibration is considerably stronger than individual decision-level prediction accuracy. The pricing engine therefore uses expected probabilities and economics rather than treating each transaction outcome as deterministic.",
        }
        return result


__all__ = ["ModelPerformanceService"]
