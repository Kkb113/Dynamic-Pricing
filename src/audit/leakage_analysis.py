from __future__ import annotations

MANDATORY_POLICY = {
    "PurchasedFlag": "TARGET", "QuantityPurchased": "TARGET", "AppliedPrice": "ALLOWED_PRE_DECISION",
    "CurrentPrice": "ALLOWED_PRE_DECISION", "RecommendedPrice": "PROHIBITED_SYNTHETIC_POLICY_OUTPUT",
    "ExpectedDemand": "PROHIBITED_SYNTHETIC_POLICY_OUTPUT", "PurchaseProbability": "PROHIBITED_SYNTHETIC_POLICY_OUTPUT",
    "PriceElasticity": "PROHIBITED_SYNTHETIC_POLICY_OUTPUT", "ExpectedRevenue": "PROHIBITED_SYNTHETIC_POLICY_OUTPUT",
    "ExpectedMarginPct": "PROHIBITED_SYNTHETIC_POLICY_OUTPUT", "ModelVersion": "PROHIBITED_SYNTHETIC_POLICY_OUTPUT",
    "ReasonCode": "PROHIBITED_SYNTHETIC_POLICY_OUTPUT", "ActualRevenue": "PROHIBITED_POST_OUTCOME",
    "OutcomeTime": "PROHIBITED_POST_OUTCOME", "OrderLineID": "PROHIBITED_POST_OUTCOME",
}
PII = {"FirstName", "LastName", "Email", "Gender", "BirthDate"}
JOIN_ONLY = {"PricingDecisionID", "SessionID", "CustomerID"}
CONDITIONAL = {"ProductID", "StoreID", "CustomerSegment", "LoyaltyTier", "PreferredChannel",
               "PriceSensitivity", "CategoryAffinityScore", "BrandAffinityScore", "Region"}


def classify(source_table: str, column: str) -> tuple[str, str]:
    if source_table == "Inventory":
        return "PROHIBITED_HISTORICAL_FEATURE", "Snapshot inventory is optimizer-only and cannot be back/forward-filled"
    if source_table == "Pricing_Decision_Log" and column in MANDATORY_POLICY:
        return MANDATORY_POLICY[column], "Locked target/leakage policy"
    if column in PII:
        return "PROHIBITED_PRIVACY_OR_IRRELEVANT", "Direct personal attribute is unnecessary for pricing"
    if column in JOIN_ONLY or column.endswith("ID"):
        if column in CONDITIONAL:
            return "CONDITIONAL_PRE_DECISION", "High-cardinality context requires coverage/sparsity validation"
        return "JOIN_ONLY_IDENTIFIER", "Use to join/derive context; do not feed blindly to ML"
    if column in CONDITIONAL:
        return "CONDITIONAL_PRE_DECISION", "Commercial/customer context requires fairness and proxy review"
    return "ALLOWED_PRE_DECISION", "Allowed only when a point-in-time join proves availability by DecisionTime"


def build_leakage_matrix(columns: list[dict]) -> list[dict]:
    result = []
    for item in columns:
        table, column = item["source_table"], item["column_name"]
        classification, reason = classify(table, column)
        prohibited = classification.startswith("PROHIBITED")
        target = classification == "TARGET"
        result.append({
            "source_table": table, "column": column, "classification": classification,
            "allowed_purchase_model": column == "PurchasedFlag" and "TARGET" or (not prohibited and not target),
            "allowed_quantity_model": column == "QuantityPurchased" and "TARGET" or (not prohibited and not target and column != "PurchasedFlag"),
            "allowed_optimizer": classification in {"OPTIMIZATION_ONLY", "PROHIBITED_HISTORICAL_FEATURE"} or not prohibited,
            "available_at_decision_time": classification not in {"PROHIBITED_POST_OUTCOME"},
            "leakage_risk": "HIGH" if prohibited or target else "MEDIUM" if classification.startswith("CONDITIONAL") else "LOW",
            "privacy_risk": "HIGH" if column in PII else "MEDIUM" if table.startswith("Customer") else "LOW",
            "reason": reason, "notes": "Inventory is allowed only as a current optimization constraint" if table == "Inventory" else "",
        })
    return result


def validate_candidate_features(fields: list[str]) -> None:
    forbidden = {k for k, v in MANDATORY_POLICY.items() if v.startswith("PROHIBITED")} | {"PurchasedFlag", "QuantityPurchased"}
    bad = forbidden.intersection(fields)
    if bad:
        raise ValueError(f"Prohibited leakage fields in candidate feature list: {sorted(bad)}")
