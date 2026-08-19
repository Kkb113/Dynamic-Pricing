from app_services.model_performance_service import ModelPerformanceService
from phase9_10.validation import outcome_leakage_validation


def test_model_metrics_are_loaded_from_phase8_artifact(registry):
    result = ModelPerformanceService(registry).get_model_performance()
    source = registry.load_metrics()
    assert result["ROC-AUC"] == source["purchase"]["roc_auc"]
    assert result["Top-Decile Lift"] == source["purchase"]["top_decile_lift"]
    assert result["Demand aggregate error %"] == source["demand"]["aggregate_error_pct"]


def test_recommendation_context_never_loads_outcome_or_pii(registry):
    context = registry.load_feature_context("validation")
    forbidden = {"PurchasedFlag", "QuantityPurchased", "ActualRevenue", "OutcomeTime", "OrderLineID", "CustomerID", "SessionID"}
    assert forbidden.isdisjoint(context.columns)


def test_security_audit_has_no_exposed_fields(registry):
    result = outcome_leakage_validation(registry.root)
    assert result["status"] == "PASS", result
    assert result["outcome_fields_exposed"] == []
    assert result["PII_fields_exposed"] == []
