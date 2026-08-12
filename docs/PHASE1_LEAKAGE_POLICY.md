# Phase 1 Leakage Policy

Synthetic policy outputs (`RecommendedPrice`, `ExpectedDemand`, `PurchaseProbability`, `PriceElasticity`, `ExpectedRevenue`, `ExpectedMarginPct`, `ModelVersion`, `ReasonCode`) and post-outcome fields (`ActualRevenue`, `OutcomeTime`, `OrderLineID`) are prohibited predictors. Purchase-model predictors also exclude `QuantityPurchased`; `PurchasedFlag` only filters the quantity-model population.

Direct PII is excluded. IDs are join-only unless ProductID/StoreID later pass coverage and sparsity review. Snapshot inventory is prohibited as historical ML context and allowed only as a current optimization constraint. The full policy is in [`leakage_policy_v1.yaml`](../contracts/leakage_policy_v1.yaml).
