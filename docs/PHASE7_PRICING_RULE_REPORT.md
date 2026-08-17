# Phase 7 Pricing Rule Report

Pricing_Rules are loaded read-only. NULL scope values are wildcards, effective windows use `[EffectiveFrom, EffectiveTo)`, and priority/specificity semantics are selected from TRAIN reconciliation only.

Selected precedence: `None`. Percentage convention: `PERCENT_POINTS`.

Constraints use independent MinPrice, MaxPrice, minimum-margin, maximum-discount, and maximum-price-change bounds. Conflicting intervals never receive an automatic price.

Rule replay: {
  "validation": {
    "split": "validation",
    "status": "BLOCKED",
    "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
    "policy_used_for_diagnostic_replay": "P2_PRIORITY_ASC_SPECIFICITY_DESC",
    "semantics_status": "BLOCKED",
    "acceptance_threshold": 0.995,
    "metrics": {
      "rows": 5250,
      "exact_cent_match_rate": 0.9363809523809524,
      "absolute_delta_mean": 0.07673714285714288,
      "absolute_delta_median": 0.0,
      "absolute_delta_p95": 0.21550000000000477,
      "absolute_delta_max": 13.860000000000014,
      "constrained_decision_count": 896,
      "constrained_decision_rate": 0.17066666666666666,
      "rule_violation_count": 0
    },
    "reference_full_historical_constrained_rate": 0.173,
    "reference_historical_rule_violations": 0
  },
  "test": {
    "split": "test",
    "status": "BLOCKED",
    "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
    "policy_used_for_diagnostic_replay": "P2_PRIORITY_ASC_SPECIFICITY_DESC",
    "semantics_status": "BLOCKED",
    "acceptance_threshold": 0.995,
    "metrics": {
      "rows": 5250,
      "exact_cent_match_rate": 0.9335238095238095,
      "absolute_delta_mean": 0.09208380952380966,
      "absolute_delta_median": 0.0,
      "absolute_delta_p95": 0.2700000000000031,
      "absolute_delta_max": 13.360000000000014,
      "constrained_decision_count": 886,
      "constrained_decision_rate": 0.16876190476190475,
      "rule_violation_count": 0
    },
    "reference_full_historical_constrained_rate": 0.173,
    "reference_historical_rule_violations": 0
  },
  "train": {
    "split": "train",
    "status": "BLOCKED",
    "blocker": "PRICING_RULE_PRIORITY_SEMANTICS_UNRESOLVED",
    "policy_used_for_diagnostic_replay": "P2_PRIORITY_ASC_SPECIFICITY_DESC",
    "semantics_status": "BLOCKED",
    "acceptance_threshold": 0.995,
    "metrics": {
      "rows": 24500,
      "exact_cent_match_rate": 0.9343265306122449,
      "absolute_delta_mean": 0.07198326530612244,
      "absolute_delta_median": 0.0,
      "absolute_delta_p95": 0.2504999999999923,
      "absolute_delta_max": 13.389999999999986,
      "constrained_decision_count": 4373,
      "constrained_decision_rate": 0.17848979591836733,
      "rule_violation_count": 0
    },
    "reference_full_historical_constrained_rate": 0.173,
    "reference_historical_rule_violations": 0
  }
}

Constraint impact: {}
