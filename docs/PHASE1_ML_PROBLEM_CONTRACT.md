# Phase 1 ML Problem Contract

The prediction grain is one `Pricing_Decision_Log` decision. The primary target is `PurchasedFlag`; the secondary target is `QuantityPurchased` among purchased observations. `AppliedPrice` is the observed historical treatment price and future `CandidatePrice` analogue. `RecommendedPrice` is never a target or feature.

The later optimizer—not the model—will maximize expected gross profit and report expected revenue. No model is trained in Phase 1. Every derived feature must satisfy `feature_timestamp <= DecisionTime`, and future validation must use chronological train/validation/holdout ranges without random row splitting.

The machine-readable source of truth is [`dynamic_pricing_ml_contract_v1.yaml`](../contracts/dynamic_pricing_ml_contract_v1.yaml).
